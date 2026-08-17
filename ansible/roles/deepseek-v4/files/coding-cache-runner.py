#!/usr/bin/env python3
"""Measure deterministic A/continuation/B/return-A prompt-cache behavior."""

import argparse
import hashlib
import json
import statistics
import time
import urllib.request
from pathlib import Path


FIXTURE_REVISION = "coding-cache-v1"
CACHE_FIELDS = ("cache_n", "cached_tokens", "cache_tokens", "prompt_cache_hit_tokens")
HEARTBEAT_PATH = None


def touch_heartbeat():
    """Refresh the managed-host watchdog heartbeat when configured."""
    if HEARTBEAT_PATH is not None:
        HEARTBEAT_PATH.touch(exist_ok=True)


def is_number(value):
    """Return true for JSON numbers but not booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def extract_cache_fields(payload):
    """Feature-detect known cache counters without retaining response content."""
    found = {}
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    for field in CACHE_FIELDS:
        for source_name, source in (("response", payload), ("usage", usage)):
            if is_number(source.get(field)):
                found[f"{source_name}.{field}"] = source[field]
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and is_number(details.get("cached_tokens")):
        found["usage.prompt_tokens_details.cached_tokens"] = details["cached_tokens"]
    return found


def request_chat(base_url, model, messages, seed, max_tokens):
    """Run one streaming request and return private continuation text separately."""
    body = {
        "model": model,
        "messages": messages,
        "seed": seed,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    request_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    started = time.monotonic()
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    usage = {}
    cache_fields = {}
    content_parts = []
    reasoning_parts = []
    ttft = None
    done_count = 0
    saw_finish_reason = False
    touch_heartbeat()
    with urllib.request.urlopen(req, timeout=1800) as response:
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
            cache_fields.update(extract_cache_fields(chunk))
            choices = chunk.get("choices") or []
            saw_finish_reason = saw_finish_reason or any(
                choice.get("finish_reason") is not None
                for choice in choices
                if isinstance(choice, dict)
            )
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or ""
            if (content or reasoning) and ttft is None:
                ttft = time.monotonic() - started
            if content:
                content_parts.append(content)
            if reasoning:
                reasoning_parts.append(reasoning)
    touch_heartbeat()
    elapsed = time.monotonic() - started
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if done_count != 1:
        raise ValueError("stream requires exactly one terminal [DONE] event")
    if not saw_finish_reason:
        raise ValueError("stream ended without a finish reason")
    if (
        not isinstance(prompt_tokens, int)
        or isinstance(prompt_tokens, bool)
        or prompt_tokens <= 0
        or not isinstance(completion_tokens, int)
        or isinstance(completion_tokens, bool)
        or completion_tokens <= 0
    ):
        raise ValueError("API response omitted integer token usage")
    if ttft is None:
        raise ValueError("stream produced no visible delta")
    return {
        "assistant_text": "".join(content_parts) or "".join(reasoning_parts),
        "request_hash": request_hash,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "ttft_seconds": ttft,
        "e2e_seconds": elapsed,
        "cache_fields": cache_fields or None,
    }


def project_prompt(project, sample_index, prompt_repeats):
    """Build public synthetic source-like text with a unique deterministic prefix."""
    nonce = hashlib.sha256(
        f"{FIXTURE_REVISION}:{project}:{sample_index}".encode()
    ).hexdigest()[:16]
    vocabulary = (
        "module dependency interface invariant validation rollback evidence "
        "function variable caller boundary deterministic repository"
    )
    return (
        f"Synthetic project {project} identifier {nonce}. "
        "Review this architecture without quoting it. "
        + (f"{vocabulary} " * prompt_repeats)
    )


def public_sample(result):
    """Drop generated text before evidence serialization."""
    return {key: value for key, value in result.items() if key != "assistant_text"}


def summarize_stage(identifier, samples):
    """Summarize one phase across comparable A/B/A sequences."""
    cache_keys = sorted({
        key
        for sample in samples
        for key in (sample.get("cache_fields") or {}).keys()
    })
    cache_medians = {}
    cache_counts = {}
    for key in cache_keys:
        values = [
            sample["cache_fields"][key]
            for sample in samples
            if isinstance(sample.get("cache_fields"), dict)
            and is_number(sample["cache_fields"].get(key))
        ]
        if values:
            cache_medians[key] = statistics.median(values)
            cache_counts[key] = len(values)
    return {
        "id": identifier,
        "samples": samples,
        "median_ttft_seconds": statistics.median(
            sample["ttft_seconds"] for sample in samples
        ),
        "median_e2e_seconds": statistics.median(
            sample["e2e_seconds"] for sample in samples
        ),
        "median_prompt_tokens": statistics.median(
            sample["prompt_tokens"] for sample in samples
        ),
        "median_optional_cache_fields": cache_medians or None,
        "optional_cache_field_sample_counts": cache_counts,
    }


def run_sequences(
    repeat_samples,
    requester,
    seed=4242,
    max_tokens=32,
    prompt_repeats=1024,
):
    """Run isolated, deterministic A/continuation/B/return-A sequences."""
    stages = {
        "a_cold": [],
        "a_continuation": [],
        "b_cold": [],
        "a_return": [],
    }
    for sample_index in range(repeat_samples):
        a_messages = [{
            "role": "user",
            "content": project_prompt("A", sample_index, prompt_repeats),
        }]
        a_cold = requester(a_messages, seed, max_tokens)
        stages["a_cold"].append(public_sample(a_cold))

        a_messages.extend([
            {"role": "assistant", "content": a_cold["assistant_text"]},
            {"role": "user", "content": "Continue with one concise invariant."},
        ])
        a_continuation = requester(a_messages, seed, max_tokens)
        stages["a_continuation"].append(public_sample(a_continuation))

        b_messages = [{
            "role": "user",
            "content": project_prompt("B", sample_index, prompt_repeats),
        }]
        b_cold = requester(b_messages, seed, max_tokens)
        stages["b_cold"].append(public_sample(b_cold))

        a_messages.extend([
            {"role": "assistant", "content": a_continuation["assistant_text"]},
            {"role": "user", "content": "Return to this project and state the boundary."},
        ])
        a_return = requester(a_messages, seed, max_tokens)
        stages["a_return"].append(public_sample(a_return))

    results = [
        summarize_stage(identifier, stages[identifier])
        for identifier in ("a_cold", "a_continuation", "b_cold", "a_return")
    ]
    return {
        "schema_version": 1,
        "fixture_revision": FIXTURE_REVISION,
        "seed": seed,
        "repeat_samples": repeat_samples,
        "prompt_repeats": prompt_repeats,
        "sequence": ["a_cold", "a_continuation", "b_cold", "a_return"],
        "results": results,
        "qualification_status": "evidence-only",
        "status": "pass",
    }


def self_test():
    """Verify ordering, medians, and prompt/response redaction without I/O."""
    calls = []

    def fake_requester(messages, seed, max_tokens):
        calls.append((messages, seed, max_tokens))
        index = len(calls)
        return {
            "assistant_text": f"private-output-{index}",
            "request_hash": hashlib.sha256(str(index).encode()).hexdigest(),
            "prompt_tokens": 100 + index,
            "completion_tokens": 8,
            "ttft_seconds": float(index),
            "e2e_seconds": float(index + 1),
            "cache_fields": {"usage.cache_n": index},
        }

    evidence = run_sequences(3, fake_requester, prompt_repeats=2)
    assert len(calls) == 12
    assert [item["id"] for item in evidence["results"]] == evidence["sequence"]
    assert all(len(item["samples"]) == 3 for item in evidence["results"])
    rendered = json.dumps(evidence, sort_keys=True)
    assert "private-output" not in rendered
    assert "Synthetic project" not in rendered
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--output")
    parser.add_argument("--repeat-samples", type=int, default=3)
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--prompt-repeats", type=int, default=1024)
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
    if args.repeat_samples < 3:
        parser.error("--repeat-samples must be at least 3")
    if args.prompt_repeats <= 0:
        parser.error("--prompt-repeats must be positive")

    def requester(messages, seed, max_tokens):
        return request_chat(
            args.base_url.rstrip("/"),
            args.model,
            messages,
            seed,
            max_tokens,
        )

    evidence = run_sequences(
        args.repeat_samples,
        requester,
        seed=args.seed,
        max_tokens=args.max_tokens,
        prompt_repeats=args.prompt_repeats,
    )
    evidence["model"] = args.model
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
