#!/usr/bin/env python3
"""Run repeatable 1K/8K OpenAI-compatible latency samples."""

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path


def request(base_url, model, prompt, seed, max_tokens, stream=True):
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
    with urllib.request.urlopen(req, timeout=1800) as response:
        if stream:
            for encoded_line in response:
                line = encoded_line.decode().strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[6:])
                usage = chunk.get("usage") or usage
                choices = chunk.get("choices") or []
                if choices and ttft is None:
                    delta = choices[0].get("delta") or {}
                    if delta.get("content") or delta.get("reasoning_content"):
                        ttft = time.monotonic() - started
        else:
            chunk = json.loads(response.read().decode())
            usage = chunk.get("usage") or {}
            ttft = time.monotonic() - started
    elapsed = time.monotonic() - started
    prompt_tokens = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if not isinstance(prompt_tokens, int) or not isinstance(completion, int):
        raise ValueError("API response omitted integer token usage")
    if ttft is None:
        raise ValueError("stream produced no content or reasoning delta")
    decode_seconds = max(elapsed - ttft, 0.000001)
    decode = completion / decode_seconds
    return {"e2e_seconds": elapsed, "ttft_seconds": ttft,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion,
            "decode_tokens_per_second": decode,
            "seconds_per_output_token": decode_seconds / max(completion, 1)}


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--case", choices=("1k", "8k"))
    parser.add_argument("--repeat-samples", type=int)
    args = parser.parse_args()
    corpus = json.loads(Path(__file__).with_name("benchmark-corpus-v1.json").read_text(encoding="utf-8"))
    repeat_samples = corpus.get("repeat_samples")
    if args.repeat_samples is not None:
        repeat_samples = args.repeat_samples
    if not isinstance(repeat_samples, int) or repeat_samples <= 0:
        parser.error("repeat_samples must be a positive integer")
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
        samples = [request(args.base_url.rstrip("/"), args.model, prompt, corpus["seed"], corpus["max_output_tokens"])
                   for _ in range(repeat_samples)]
        decode = [item["decode_tokens_per_second"] for item in samples]
        results.append({"id": case["id"], "target_prompt_tokens": case["target_prompt_tokens"],
                        "prompt_token_tolerance": tolerance, "samples": samples,
                        "median_decode_tokens_per_second": statistics.median(decode),
                        "threshold_tokens_per_second": 8, "verdict": "pass" if statistics.median(decode) >= 8 else "fail"})
    evidence = {"schema_version": 1, "fixture_revision": corpus["fixture_revision"],
                "model": args.model, "seed": corpus["seed"], "results": results,
                "status": "pass" if all(item["verdict"] == "pass" for item in results) else "fail"}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    raise SystemExit(0 if evidence["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
