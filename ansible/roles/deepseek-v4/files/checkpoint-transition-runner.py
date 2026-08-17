#!/usr/bin/env python3
"""Measure 127K checkpoint handoff without retaining prompts or responses."""

import argparse
import json
import statistics
import threading
import time
import urllib.request
from pathlib import Path


FILLER = "The configuration record is intentionally repetitive and contains no marker."


def request_json(url, payload, timeout):
    """Issue one OpenAI-compatible JSON request and return payload plus elapsed."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode()), time.monotonic() - started


def token_count(base_url, prompt, timeout=120):
    """Count raw prompt tokens without creating a completion or warming KV state."""
    payload, _ = request_json(
        f"{base_url}/tokenize", {"content": prompt}, timeout
    )
    tokens = payload.get("tokens")
    if not isinstance(tokens, list) or any(
        isinstance(token, bool) or not isinstance(token, int) for token in tokens
    ):
        raise ValueError("tokenize response omitted the integer tokens array")
    return len(tokens)


class Heartbeat:
    """Touch the managed-host watchdog heartbeat while long prefills run."""

    def __init__(self, path):
        self.path = Path(path) if path else None
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        if not self.path:
            return
        self.path.touch()

        def keep_alive():
            while not self.stop.wait(30):
                self.path.touch()

        self.thread = threading.Thread(target=keep_alive, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.path:
            self.path.touch()


def completion_payload(model, prompt, max_tokens):
    """Build the deterministic zero-thinking request used by handoff checks."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "seed": 42,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "thinking_budget_tokens": 0,
    }


def complete(base_url, model, prompt, max_tokens, timeout):
    """Submit a deterministic completion and return only token metadata."""
    payload, elapsed = request_json(
        f"{base_url}/v1/chat/completions",
        completion_payload(model, prompt, max_tokens),
        timeout,
    )
    usage = payload.get("usage") or {}
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get(
        "content", ""
    )
    tokens = usage.get("prompt_tokens")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
        raise ValueError("API response omitted integer prompt token usage")
    reasoning = ((payload.get("choices") or [{}])[0].get("message") or {}).get(
        "reasoning_content", ""
    )
    return tokens, content, reasoning, elapsed


def long_prompt(marker, repeats):
    """Build one unique long request from a calibrated filler count."""
    return (
        f"Remember this exact marker: {marker}.\n"
        + " ".join([FILLER] * repeats)
        + "\nWhat is the exact marker from the start? Reply only with the marker."
    )


def calibrated_prompt(base_url, marker, target_tokens):
    """Approach the target via /tokenize without running or caching a completion."""
    repeats = max(1, target_tokens // 12)
    tolerance = max(256, round(target_tokens * 0.03))
    for _ in range(5):
        prompt = long_prompt(marker, repeats)
        observed = token_count(base_url, prompt)
        if abs(observed - target_tokens) <= tolerance:
            return prompt, observed, tolerance
        repeats = max(1, round(repeats * target_tokens / observed))
    raise ValueError(f"unable to calibrate to {target_tokens} +/- {tolerance} tokens")


def health_probe(base_url, stop, ready, samples):
    """Probe health independently while the short handoff request is in flight."""
    while not stop.is_set():
        started = time.monotonic()
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=10) as response:
                samples.append({"ok": response.status == 200, "elapsed": time.monotonic() - started})
        except Exception as error:  # Evidence must describe availability, never content.
            samples.append({"ok": False, "elapsed": time.monotonic() - started, "error": type(error).__name__})
        ready.set()
        stop.wait(5)


def one_repeat(base_url, model, target_tokens, repeat_number, deadline):
    """Run recall then a short handoff while recording fixed-cadence health."""
    marker = f"COBALT-731-{repeat_number}"
    prompt, calibrated_tokens, tolerance = calibrated_prompt(
        base_url, marker, target_tokens
    )
    observed, recall_answer, recall_reasoning, recall_elapsed = complete(
        base_url, model, prompt, 256,
        timeout=max(1, deadline - time.monotonic()),
    )
    normalized_recall = recall_answer.strip().upper().rstrip(".。")
    recall_answer_matches = normalized_recall == marker
    recall_marker_present = marker in recall_answer.upper()
    recall_token_count_matches = (
        abs(observed - target_tokens) <= tolerance
        and abs(observed - calibrated_tokens) <= tolerance
    )
    recall_ok = recall_answer_matches and recall_token_count_matches
    samples, stop, ready = [], threading.Event(), threading.Event()
    probe = threading.Thread(
        target=health_probe, args=(base_url, stop, ready, samples), daemon=True
    )
    probe.start()
    try:
        if not ready.wait(timeout=15):
            raise TimeoutError("initial health sample did not complete")
        _, handoff_answer, handoff_reasoning, handoff_elapsed = complete(
            base_url, model, "Reply only with OK.", 256,
            timeout=max(1, min(600, deadline - time.monotonic())),
        )
    finally:
        stop.set()
        probe.join(timeout=10)
    normalized_handoff = handoff_answer.strip().upper().rstrip(".。")
    handoff_ok = normalized_handoff == "OK"
    latencies = [sample["elapsed"] for sample in samples]
    health_ok = bool(samples) and all(sample["ok"] for sample in samples)
    return {
        "recall_ok": recall_ok,
        "recall_answer_matches": recall_answer_matches,
        "recall_marker_present": recall_marker_present,
        "recall_answer_character_count": len(recall_answer),
        "recall_reasoning_character_count": len(recall_reasoning),
        "calibrated_prompt_tokens": calibrated_tokens,
        "recall_token_count_matches": recall_token_count_matches,
        "observed_prompt_tokens": observed,
        "recall_elapsed_seconds": recall_elapsed,
        "handoff_ok": handoff_ok,
        "handoff_expected_present": "OK" in handoff_answer.upper(),
        "handoff_answer_character_count": len(handoff_answer),
        "handoff_reasoning_character_count": len(handoff_reasoning),
        "handoff_elapsed_seconds": handoff_elapsed,
        "health_sample_count": len(samples),
        "health_failures": sum(not sample["ok"] for sample in samples),
        "maximum_health_latency_seconds": max(latencies, default=None),
        "health_ok": health_ok,
        "pass": recall_ok and handoff_ok and health_ok,
    }


def evaluate(results, expected_repeats):
    """Return a compact pass/fail summary for the requested repeat count."""
    handoffs = [result["handoff_elapsed_seconds"] for result in results]
    return {
        "repeat_count": len(results),
        "expected_repeat_count": expected_repeats,
        "median_handoff_elapsed_seconds": statistics.median(handoffs) if handoffs else None,
        "status": (
            "pass"
            if len(results) == expected_repeats
            and all(result["pass"] for result in results)
            else "fail"
        ),
    }


def self_test():
    """Exercise summary semantics without network I/O."""
    payload = completion_payload("model", "prompt", 256)
    assert payload["thinking_budget_tokens"] == 0
    assert payload["max_tokens"] == 256
    row = {
        "pass": True,
        "handoff_elapsed_seconds": 2.0,
    }
    assert evaluate([row, row, row], 3)["status"] == "pass"
    assert evaluate([row], 1)["status"] == "pass"
    assert evaluate([row, row], 3)["status"] == "fail"
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--target-prompt-tokens", type=int)
    parser.add_argument("--output")
    parser.add_argument("--heartbeat-file")
    parser.add_argument("--deadline-seconds", type=int, default=10800)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.base_url, args.model, args.target_prompt_tokens, args.output)):
        parser.error("base URL, model, target tokens, and output are required")
    if args.target_prompt_tokens < 8192:
        parser.error("target prompt must be at least 8192 tokens")
    if args.deadline_seconds < 60:
        parser.error("deadline must be at least 60 seconds")
    if args.repeats not in (1, 3):
        parser.error("repeats must be 1 for diagnosis or 3 for qualification")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    heartbeat = Heartbeat(args.heartbeat_file)
    try:
        heartbeat.start()
        deadline = time.monotonic() + args.deadline_seconds
        results = [
            one_repeat(
                args.base_url.rstrip("/"), args.model,
                args.target_prompt_tokens, repeat_number, deadline,
            )
            for repeat_number in range(1, args.repeats + 1)
        ]
        evidence = {
            "schema_version": 1,
            "fixture_revision": "checkpoint-transition-v2",
            "target_prompt_tokens": args.target_prompt_tokens,
            "deadline_seconds": args.deadline_seconds,
            "results": results,
            **evaluate(results, args.repeats),
        }
    except Exception as error:
        evidence = {
            "schema_version": 1,
            "fixture_revision": "checkpoint-transition-v2",
            "target_prompt_tokens": args.target_prompt_tokens,
            "error_type": type(error).__name__,
            "status": "fail",
        }
    finally:
        heartbeat.close()
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    raise SystemExit(0 if evidence["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
