#!/usr/bin/env python3
"""Verify a configured context window with a deterministic long-context recall."""

import argparse
import json
import time
import urllib.request
from pathlib import Path


MARKER = "COBALT-731"
FILLER = "The configuration record is intentionally repetitive and contains no marker."


def request_json(url, payload, timeout):
    """Issue one JSON request and return the decoded response."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def token_count(base_url, prompt):
    """Count raw prompt tokens without creating a completion or warming KV state."""
    payload = request_json(
        f"{base_url}/tokenize", {"content": prompt}, timeout=120
    )
    tokens = payload.get("tokens")
    if not isinstance(tokens, list) or any(
        isinstance(token, bool) or not isinstance(token, int) for token in tokens
    ):
        raise ValueError("tokenize response omitted the integer tokens array")
    return len(tokens)


def completion(base_url, model, prompt, max_tokens):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "seed": 42,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    started = time.monotonic()
    payload = request_json(
        f"{base_url}/v1/chat/completions", body, timeout=7200
    )
    elapsed = time.monotonic() - started
    usage = payload.get("usage") or {}
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    if (
        not isinstance(usage.get("prompt_tokens"), int)
        or isinstance(usage.get("prompt_tokens"), bool)
        or usage["prompt_tokens"] <= 0
    ):
        raise ValueError("API response omitted integer prompt token usage")
    return usage["prompt_tokens"], content, elapsed


def calibrated_prompt(base_url, model, target_tokens):
    repeats = max(1, target_tokens // 12)
    tolerance = max(256, round(target_tokens * 0.03))
    for _ in range(5):
        prompt = (
            f"Remember this exact marker: {MARKER}.\n"
            + " ".join([FILLER] * repeats)
            + "\nWhat is the exact marker from the start? Reply only with the marker."
        )
        observed = token_count(base_url, prompt)
        if abs(observed - target_tokens) <= tolerance:
            return prompt, observed, tolerance
        repeats = max(1, round(repeats * target_tokens / observed))
    raise ValueError(f"unable to calibrate to {target_tokens} +/- {tolerance} tokens")


def evaluate(target_tokens, tolerance, calibrated_tokens, observed_tokens, answer):
    """Evaluate recall and prove the final request stayed near the target size."""
    normalized_answer = answer.strip().upper().rstrip(".。")
    token_count_matches = (
        abs(observed_tokens - target_tokens) <= tolerance
        and abs(observed_tokens - calibrated_tokens) <= tolerance
    )
    answer_matches = normalized_answer == MARKER
    return answer_matches, token_count_matches, answer_matches and token_count_matches


def self_test():
    """Reject marker-only responses whose measured prompt is not near 127K."""
    assert evaluate(127000, 3810, 126992, 126992, MARKER) == (
        True,
        True,
        True,
    )
    assert evaluate(127000, 3810, 126992, 1, MARKER) == (
        True,
        False,
        False,
    )
    assert evaluate(127000, 3810, 126992, 126992, "WRONG") == (
        False,
        True,
        False,
    )
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--target-prompt-tokens", type=int)
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.base_url, args.model, args.target_prompt_tokens, args.output)):
        parser.error(
            "--base-url, --model, --target-prompt-tokens, and --output are required"
        )
    if args.target_prompt_tokens < 8192:
        parser.error("target prompt must be at least 8192 tokens")
    base_url = args.base_url.rstrip("/")
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        prompt, calibrated_tokens, tolerance = calibrated_prompt(
            base_url, args.model, args.target_prompt_tokens
        )
        # Keep headroom for chat-template framing and the completion inside the
        # configured context window. The evidence never stores prompt/response.
        observed_tokens, answer, elapsed = completion(
            base_url,
            args.model,
            prompt,
            64,
        )
        answer_matches, token_count_matches, passed = evaluate(
            args.target_prompt_tokens,
            tolerance,
            calibrated_tokens,
            observed_tokens,
            answer,
        )
        evidence = {
            "schema_version": 2,
            "fixture_revision": "context-window-v2",
            "model": args.model,
            "seed": 42,
            "target_prompt_tokens": args.target_prompt_tokens,
            "prompt_token_tolerance": tolerance,
            "calibrated_prompt_tokens": calibrated_tokens,
            "observed_prompt_tokens": observed_tokens,
            "elapsed_seconds": elapsed,
            "answer_matches": answer_matches,
            "token_count_matches": token_count_matches,
            "status": "pass" if passed else "fail",
        }
    except Exception as error:  # Keep failure evidence without response content.
        evidence = {
            "schema_version": 2,
            "fixture_revision": "context-window-v2",
            "model": args.model,
            "seed": 42,
            "target_prompt_tokens": args.target_prompt_tokens,
            "error_type": type(error).__name__,
            "http_status": getattr(error, "code", None),
            "status": "fail",
        }
    with target.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    raise SystemExit(0 if evidence["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
