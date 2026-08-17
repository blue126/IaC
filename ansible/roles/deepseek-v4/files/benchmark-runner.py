#!/usr/bin/env python3
"""Run repeatable 1K/8K OpenAI-compatible latency samples."""

import argparse
import hashlib
import json
import statistics
import time
import urllib.request
from pathlib import Path


TIMING_FIELDS = (
    "prompt_n",
    "prompt_ms",
    "prompt_per_token_ms",
    "prompt_per_second",
    "predicted_n",
    "predicted_ms",
    "predicted_per_token_ms",
    "predicted_per_second",
)
CACHE_FIELDS = ("cache_n", "cached_tokens", "cache_tokens", "prompt_cache_hit_tokens")
HEARTBEAT_PATH = None


def touch_heartbeat():
    """Refresh the managed-host watchdog heartbeat when configured."""
    if HEARTBEAT_PATH is not None:
        HEARTBEAT_PATH.touch(exist_ok=True)


def is_number(value):
    """Return true for JSON numbers but not booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def merge_optional_metrics(metrics, payload):
    """Feature-detect only known numeric timing and cache counters."""
    timings = payload.get("timings")
    if isinstance(timings, dict):
        for field in TIMING_FIELDS:
            if is_number(timings.get(field)):
                metrics["server_timings"][field] = timings[field]
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    for field in CACHE_FIELDS:
        for source_name, source in (("response", payload), ("usage", usage)):
            if is_number(source.get(field)):
                metrics["cache_fields"][f"{source_name}.{field}"] = source[field]
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and is_number(details.get("cached_tokens")):
        metrics["cache_fields"]["usage.prompt_tokens_details.cached_tokens"] = details[
            "cached_tokens"
        ]


def request(base_url, model, prompt, seed, max_tokens, stream=True):
    """Make one request and retain only timing, token, and cache evidence."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "seed": seed,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream:
        body["stream_options"] = {"include_usage": True}
    body = json.dumps(body).encode()
    started = time.monotonic()
    req = urllib.request.Request(f"{base_url}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    usage = {}
    ttft = None
    done_count = 0
    saw_finish_reason = not stream
    optional = {"server_timings": {}, "cache_fields": {}}
    touch_heartbeat()
    with urllib.request.urlopen(req, timeout=1800) as response:
        if stream:
            for encoded_line in response:
                line = encoded_line.decode().strip()
                if line == "data: [DONE]":
                    done_count += 1
                    continue
                if not line.startswith("data: "):
                    continue
                if done_count:
                    raise ValueError("stream emitted data after [DONE]")
                chunk = json.loads(line[6:])
                usage = chunk.get("usage") or usage
                merge_optional_metrics(optional, chunk)
                choices = chunk.get("choices") or []
                saw_finish_reason = saw_finish_reason or any(
                    choice.get("finish_reason") is not None
                    for choice in choices
                    if isinstance(choice, dict)
                )
                if choices and ttft is None:
                    delta = choices[0].get("delta") or {}
                    if delta.get("content") or delta.get("reasoning_content"):
                        ttft = time.monotonic() - started
        else:
            chunk = json.loads(response.read().decode())
            usage = chunk.get("usage") or {}
            merge_optional_metrics(optional, chunk)
            ttft = time.monotonic() - started
    touch_heartbeat()
    elapsed = time.monotonic() - started
    prompt_tokens = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if stream and done_count != 1:
        raise ValueError("stream requires exactly one terminal [DONE] event")
    if not saw_finish_reason:
        raise ValueError("stream ended without a finish reason")
    if (
        not isinstance(prompt_tokens, int)
        or isinstance(prompt_tokens, bool)
        or prompt_tokens <= 0
        or not isinstance(completion, int)
        or isinstance(completion, bool)
        or completion <= 0
    ):
        raise ValueError("API response omitted integer token usage")
    if ttft is None:
        raise ValueError("stream produced no content or reasoning delta")
    decode_seconds = max(elapsed - ttft, 0.000001)
    decode = completion / decode_seconds
    server_pp = optional["server_timings"].get("prompt_per_second")
    return {"e2e_seconds": elapsed, "ttft_seconds": ttft,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion,
            "prompt_tokens_per_ttft_second": (
                prompt_tokens / max(ttft, 0.000001)
            ),
            "server_pp_tokens_per_second": server_pp,
            "tg_tokens_per_second": decode,
            "decode_tokens_per_second": decode,
            "seconds_per_output_token": decode_seconds / max(completion, 1),
            "server_timings": optional["server_timings"] or None,
            "cache_fields": optional["cache_fields"] or None}


def calibrated_prompt(case, base_url, model, seed, max_tokens):
    """Use reported tokenizer usage to approach the fixed token target."""
    words = case["repeat_text"].split()
    if not words:
        raise ValueError(f"empty repeat_text for {case['id']}")
    target = int(case["target_prompt_tokens"])
    tolerance = max(32, round(target * 0.15))
    repeats = max(1, target // len(words))
    for _ in range(4):
        prompt = " ".join(words * repeats)
        observed = request(base_url, model, prompt, seed, 1, stream=False)["prompt_tokens"]
        if abs(observed - target) <= tolerance:
            return prompt, tolerance
        repeats = max(1, round(repeats * target / observed))
    raise ValueError(
        f"unable to calibrate {case['id']} to {target} +/- {tolerance} tokens"
    )


def optional_medians(samples, field):
    """Return per-field medians and presence counts for optional metrics."""
    keys = sorted({
        key
        for sample in samples
        for key in (sample.get(field) or {}).keys()
    })
    if not keys:
        return None, {}
    medians = {}
    availability = {}
    for key in keys:
        values = [
            sample[field][key]
            for sample in samples
            if isinstance(sample.get(field), dict)
            and is_number(sample[field].get(key))
        ]
        if values:
            medians[key] = statistics.median(values)
            availability[key] = len(values)
    return medians or None, availability


def summarize_case(case, tolerance, samples, threshold_tokens_per_second=8):
    """Build stable protocol-level and optional server metric medians."""
    median_tg = statistics.median(item["tg_tokens_per_second"] for item in samples)
    server_pp = [
        item["server_pp_tokens_per_second"]
        for item in samples
        if is_number(item.get("server_pp_tokens_per_second"))
    ]
    timing_medians, timing_counts = optional_medians(samples, "server_timings")
    cache_medians, cache_counts = optional_medians(samples, "cache_fields")
    return {
        "id": case["id"],
        "target_prompt_tokens": case["target_prompt_tokens"],
        "prompt_token_tolerance": tolerance,
        "samples": samples,
        "median_pp_tokens_per_second": (
            statistics.median(server_pp) if server_pp else None
        ),
        "pp_metric_source": (
            "server.timings.prompt_per_second" if server_pp else "unavailable"
        ),
        "pp_metric_sample_count": len(server_pp),
        "median_prompt_tokens_per_ttft_second": statistics.median(
            item["prompt_tokens_per_ttft_second"] for item in samples
        ),
        "median_ttft_seconds": statistics.median(
            item["ttft_seconds"] for item in samples
        ),
        "median_e2e_seconds": statistics.median(
            item["e2e_seconds"] for item in samples
        ),
        "median_tg_tokens_per_second": median_tg,
        "median_decode_tokens_per_second": median_tg,
        "median_optional_server_timings": timing_medians,
        "median_optional_cache_fields": cache_medians,
        "optional_field_sample_counts": {
            "server_timings": timing_counts,
            "cache_fields": cache_counts,
        },
        "threshold_tokens_per_second": threshold_tokens_per_second,
        "verdict": (
            "pass" if median_tg >= threshold_tokens_per_second else "fail"
        ),
    }


def self_test():
    """Exercise optional-field detection and median calculation without network I/O."""
    optional = {"server_timings": {}, "cache_fields": {}}
    merge_optional_metrics(
        optional,
        {
            "timings": {"prompt_per_second": 100.0, "ignored": "unsafe"},
            "usage": {
                "cache_n": 64,
                "prompt_tokens_details": {"cached_tokens": 32},
            },
        },
    )
    assert optional["server_timings"] == {"prompt_per_second": 100.0}
    assert optional["cache_fields"]["usage.cache_n"] == 64
    samples = [
        {
            "prompt_tokens_per_ttft_second": 80.0,
            "server_pp_tokens_per_second": 90.0,
            "ttft_seconds": 10.0,
            "e2e_seconds": 14.0,
            "tg_tokens_per_second": 8.0,
            "server_timings": {"prompt_per_second": 90.0},
            "cache_fields": None,
        },
        {
            "prompt_tokens_per_ttft_second": 100.0,
            "server_pp_tokens_per_second": 110.0,
            "ttft_seconds": 8.0,
            "e2e_seconds": 12.0,
            "tg_tokens_per_second": 10.0,
            "server_timings": {"prompt_per_second": 110.0},
            "cache_fields": {"usage.cache_n": 64},
        },
        {
            "prompt_tokens_per_ttft_second": 90.0,
            "server_pp_tokens_per_second": None,
            "ttft_seconds": 9.0,
            "e2e_seconds": 13.0,
            "tg_tokens_per_second": 9.0,
            "server_timings": None,
            "cache_fields": {"usage.cache_n": 96},
        },
    ]
    summary = summarize_case(
        {"id": "self-test", "target_prompt_tokens": 1024},
        128,
        samples,
        8,
    )
    assert summary["median_pp_tokens_per_second"] == 100.0
    assert summary["median_prompt_tokens_per_ttft_second"] == 90.0
    assert summary["median_ttft_seconds"] == 9.0
    assert summary["median_e2e_seconds"] == 13.0
    assert summary["median_tg_tokens_per_second"] == 9.0
    assert summary["median_optional_server_timings"]["prompt_per_second"] == 100.0
    assert summary["median_optional_cache_fields"]["usage.cache_n"] == 80.0
    evidence_only = summarize_case(
        {"id": "self-test", "target_prompt_tokens": 1024},
        128,
        samples,
        0,
    )
    assert evidence_only["threshold_tokens_per_second"] == 0
    assert evidence_only["verdict"] == "pass"
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--output")
    parser.add_argument("--case", choices=("1k", "8k"))
    parser.add_argument("--repeat-samples", type=int)
    parser.add_argument("--threshold-tokens-per-second", type=float, default=8.0)
    parser.add_argument(
        "--cold-prefill",
        action="store_true",
        help="Prefix every measured sample with a unique nonce to avoid prompt-cache reuse.",
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--heartbeat-file")
    args = parser.parse_args()
    global HEARTBEAT_PATH
    HEARTBEAT_PATH = Path(args.heartbeat_file) if args.heartbeat_file else None
    if args.self_test:
        self_test()
        return
    for required in ("base_url", "model", "output"):
        if not getattr(args, required):
            parser.error(f"--{required.replace('_', '-')} is required")
    corpus = json.loads(
        Path(__file__).with_name("benchmark-corpus-v1.json").read_text(
            encoding="utf-8"
        )
    )
    repeat_samples = corpus.get("repeat_samples")
    if args.repeat_samples is not None:
        repeat_samples = args.repeat_samples
    if not isinstance(repeat_samples, int) or repeat_samples <= 0:
        parser.error("repeat_samples must be a positive integer")
    if args.threshold_tokens_per_second < 0:
        parser.error("--threshold-tokens-per-second must be non-negative")
    cases = corpus.get("cases")
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
    if not cases:
        parser.error("benchmark corpus must contain at least one case")
    results = []
    for case in cases:
        prompt, tolerance = calibrated_prompt(
            case,
            args.base_url.rstrip("/"),
            args.model,
            corpus["seed"],
            corpus["max_output_tokens"],
        )
        samples = []
        for sample_index in range(repeat_samples):
            measured_prompt = prompt
            if args.cold_prefill:
                nonce = hashlib.sha256(
                    f"{case['id']}:{sample_index}:{corpus['seed']}".encode()
                ).hexdigest()[:16]
                measured_prompt = f"{nonce}\n{prompt}"
            samples.append(request(
                args.base_url.rstrip("/"), args.model, measured_prompt,
                corpus["seed"], corpus["max_output_tokens"]
            ))
        results.append(summarize_case(
            case,
            tolerance,
            samples,
            args.threshold_tokens_per_second,
        ))
    evidence = {"schema_version": 2, "fixture_revision": corpus["fixture_revision"],
                "model": args.model, "seed": corpus["seed"], "results": results,
                "cold_prefill": args.cold_prefill,
                "status": "pass" if all(item["verdict"] == "pass" for item in results) else "fail"}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    raise SystemExit(0 if evidence["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
