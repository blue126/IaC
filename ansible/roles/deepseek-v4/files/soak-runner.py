#!/usr/bin/env python3
"""Exercise a stable OpenAI-compatible endpoint without storing content."""

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


CHECK_MESSAGE = "Reply with exactly OK."


def utc_now():
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def is_ok_reply(content):
    """Accept OK with only surrounding whitespace or terminal punctuation."""
    if not isinstance(content, str):
        return False
    return content.strip().upper().rstrip(".!。！") == "OK"


def health_probe(base_url):
    """Probe health and retain only status and latency."""
    started = time.monotonic()
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=30) as response:
            response.read()
            status_code = response.status
        return {
            "ok": status_code == 200,
            "status_code": status_code,
            "elapsed_seconds": time.monotonic() - started,
        }
    except (OSError, urllib.error.URLError) as error:
        return {
            "ok": False,
            "status_code": getattr(error, "code", None),
            "elapsed_seconds": time.monotonic() - started,
            "error_type": type(error).__name__,
        }


def completion_probe(base_url, model):
    """Run a tiny deterministic completion and retain no prompt or response."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": CHECK_MESSAGE}],
        "seed": 42,
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.loads(response.read().decode())
            status_code = response.status
        usage = payload.get("usage") or {}
        message = ((payload.get("choices") or [{}])[0].get("message") or {})
        content = message.get("content")
        answer_matches = is_ok_reply(content)
        return {
            "ok": status_code == 200 and answer_matches,
            "status_code": status_code,
            "elapsed_seconds": time.monotonic() - started,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "content_nonempty": isinstance(content, str) and bool(content.strip()),
            "answer_matches": answer_matches,
        }
    except (OSError, ValueError, urllib.error.URLError) as error:
        return {
            "ok": False,
            "status_code": getattr(error, "code", None),
            "elapsed_seconds": time.monotonic() - started,
            "error_type": type(error).__name__,
        }


def summarize(
    samples,
    duration_seconds,
    interval_seconds,
    completion_interval_seconds,
    observed_duration_seconds,
    started_at,
    ended_at,
    completion_samples=None,
):
    """Build a content-free soak verdict."""
    health = [sample["health"] for sample in samples]
    if completion_samples is None:
        completion_samples = [
            {
                "timestamp": sample["timestamp"],
                "offset_seconds": sample.get("offset_seconds"),
                "completion": sample["completion"],
            }
            for sample in samples
            if sample.get("completion")
        ]
    completions = [sample["completion"] for sample in completion_samples]
    health_failures = sum(not sample.get("ok", False) for sample in health)
    completion_failures = sum(not sample.get("ok", False) for sample in completions)
    minimum_health_count = max(
        1,
        int((duration_seconds / interval_seconds) * 0.9),
    )
    minimum_completion_count = max(
        1,
        duration_seconds // completion_interval_seconds,
    )
    offsets = [sample.get("offset_seconds") for sample in samples]
    offsets_valid = all(
        isinstance(offset, (int, float)) and not isinstance(offset, bool)
        for offset in offsets
    )
    health_gaps = []
    if offsets_valid and offsets:
        health_gaps = [offsets[0]]
        health_gaps.extend(
            current - previous for previous, current in zip(offsets, offsets[1:])
        )
        health_gaps.append(max(0, observed_duration_seconds - offsets[-1]))
    maximum_health_gap_seconds = max(health_gaps) if health_gaps else None
    maximum_allowed_health_gap_seconds = max(
        interval_seconds * 2,
        interval_seconds + 5,
    )
    maximum_completion_seconds = max(
        (sample.get("elapsed_seconds", 0) for sample in completions),
        default=None,
    )
    maximum_allowed_completion_seconds = completion_interval_seconds
    coverage_complete = (
        observed_duration_seconds >= duration_seconds
        and len(samples) >= minimum_health_count
        and len(completions) >= minimum_completion_count
        and maximum_health_gap_seconds is not None
        and maximum_health_gap_seconds <= maximum_allowed_health_gap_seconds
        and maximum_completion_seconds is not None
        and maximum_completion_seconds <= maximum_allowed_completion_seconds
    )
    return {
        "schema_version": 3,
        "fixture_revision": "production-soak-v4",
        "completion_max_tokens": 64,
        "duration_target_seconds": duration_seconds,
        "duration_observed_seconds": observed_duration_seconds,
        "minimum_health_count": minimum_health_count,
        "minimum_completion_count": minimum_completion_count,
        "coverage_complete": coverage_complete,
        "maximum_health_gap_seconds": maximum_health_gap_seconds,
        "maximum_allowed_health_gap_seconds": maximum_allowed_health_gap_seconds,
        "maximum_allowed_completion_seconds": maximum_allowed_completion_seconds,
        "started_at": started_at,
        "ended_at": ended_at,
        "sample_count": len(samples),
        "health_failures": health_failures,
        "completion_count": len(completions),
        "completion_failures": completion_failures,
        "maximum_health_seconds": max(
            (sample.get("elapsed_seconds", 0) for sample in health),
            default=None,
        ),
        "maximum_completion_seconds": maximum_completion_seconds,
        "samples": samples,
        "completion_samples": completion_samples,
        "status": (
            "pass"
            if samples and coverage_complete and health_failures == 0 and completions
            and completion_failures == 0
            else "fail"
        ),
    }


def self_test():
    """Verify verdict aggregation without network or waiting."""
    samples = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "offset_seconds": 0.0,
            "health": {"ok": True, "status_code": 200, "elapsed_seconds": 0.1},
            "completion": {
                "ok": True,
                "status_code": 200,
                "elapsed_seconds": 1.0,
                "content_nonempty": True,
            },
        },
        {
            "timestamp": "2026-01-01T00:00:30+00:00",
            "offset_seconds": 30.0,
            "health": {"ok": True, "status_code": 200, "elapsed_seconds": 0.1},
            "completion": None,
        },
    ]
    report = summarize(
        samples,
        60,
        30,
        60,
        60.0,
        samples[0]["timestamp"],
        samples[-1]["timestamp"],
    )
    assert report["status"] == "pass"
    assert report["sample_count"] == 2
    assert report["completion_count"] == 1
    assert report["coverage_complete"] is True
    assert report["maximum_health_gap_seconds"] == 30.0
    assert is_ok_reply(" OK。 ") is True
    assert is_ok_reply("WRONG") is False
    samples[1]["health"]["ok"] = False
    assert summarize(samples, 60, 30, 60, 60.0, "start", "end")["status"] == "fail"
    samples[1]["health"]["ok"] = True
    samples[0]["completion"]["ok"] = False
    assert summarize(samples, 60, 30, 60, 60.0, "start", "end")["status"] == "fail"
    assert summarize(samples, 60, 30, 60, 59.0, "start", "end")["status"] == "fail"
    samples[1]["offset_seconds"] = 70.0
    assert summarize(samples, 60, 30, 60, 70.0, "start", "end")["status"] == "fail"
    independent_health = [
        {
            "timestamp": f"t{offset}",
            "offset_seconds": float(offset),
            "health": {"ok": True, "status_code": 200, "elapsed_seconds": 0.1},
            "completion": None,
        }
        for offset in (0, 30, 60, 90, 120)
    ]
    slow_completion = [{
        "timestamp": "t0",
        "offset_seconds": 0.0,
        "completion": {
            "ok": True,
            "status_code": 200,
            "elapsed_seconds": 87.4,
            "answer_matches": True,
        },
    }]
    independent_report = summarize(
        independent_health,
        120,
        30,
        120,
        120.0,
        "start",
        "end",
        slow_completion,
    )
    assert independent_report["status"] == "pass"
    assert independent_report["maximum_health_gap_seconds"] == 30.0
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--output")
    parser.add_argument("--duration-seconds", type=int, default=3600)
    parser.add_argument("--interval-seconds", type=int, default=30)
    parser.add_argument("--completion-interval-seconds", type=int, default=300)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.base_url or not args.model or not args.output:
        parser.error("--base-url, --model, and --output are required")
    if min(
        args.duration_seconds,
        args.interval_seconds,
        args.completion_interval_seconds,
    ) <= 0:
        parser.error("soak durations must be positive")

    base_url = args.base_url.rstrip("/")
    started_at = utc_now()
    started = time.monotonic()
    deadline = started + args.duration_seconds
    samples = []
    completion_samples = []
    sample_lock = threading.Lock()
    stop_health = threading.Event()

    def collect_health():
        """Probe health on a fixed cadence independent of model completions."""
        next_health = started
        while not stop_health.is_set():
            remaining = next_health - time.monotonic()
            if remaining > 0 and stop_health.wait(remaining):
                break
            now = time.monotonic()
            if now >= deadline:
                break
            sample = {
                "timestamp": utc_now(),
                "offset_seconds": now - started,
                "health": health_probe(base_url),
                "completion": None,
            }
            with sample_lock:
                samples.append(sample)
            next_health += args.interval_seconds
            while next_health <= time.monotonic():
                next_health += args.interval_seconds

    health_thread = threading.Thread(target=collect_health, daemon=True)
    health_thread.start()
    next_completion = started
    try:
        while next_completion < deadline:
            remaining = next_completion - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            now = time.monotonic()
            if now >= deadline:
                break
            completion_samples.append({
                "timestamp": utc_now(),
                "offset_seconds": now - started,
                "completion": completion_probe(base_url, args.model),
            })
            next_completion += args.completion_interval_seconds
            while next_completion <= now:
                next_completion += args.completion_interval_seconds
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
    finally:
        stop_health.set()
        health_thread.join(timeout=35)

    observed_duration_seconds = time.monotonic() - started
    with sample_lock:
        samples = sorted(samples, key=lambda sample: sample["offset_seconds"])
    report = summarize(
        samples,
        args.duration_seconds,
        args.interval_seconds,
        args.completion_interval_seconds,
        observed_duration_seconds,
        started_at,
        utc_now(),
        completion_samples,
    )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
