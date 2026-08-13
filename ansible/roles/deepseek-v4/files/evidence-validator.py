#!/usr/bin/env python3
"""Validate stable DeepSeek contract and benchmark evidence."""

import argparse
import json
import sys
from pathlib import Path


def validate_common(document):
    """Validate fields shared by every evidence document."""
    results = document.get("results")
    if document.get("schema_version") != 1 or not document.get("fixture_revision"):
        return False
    if document.get("status") not in {"pass", "fail"}:
        return False
    if not isinstance(results, list) or not results:
        return False
    identifiers = [item.get("id") for item in results]
    return all(identifiers) and len(identifiers) == len(set(identifiers))


def validate_contract(document):
    """Require a boolean verdict for every contract result."""
    results = document["results"]
    valid = all(isinstance(item.get("pass"), bool) for item in results)
    expected = "pass" if valid and all(item["pass"] for item in results) else "fail"
    return valid and document["status"] == expected


def validate_benchmark(document):
    """Require samples, token calibration, finite timing, and threshold verdicts."""
    valid = True
    for item in document["results"]:
        samples = item.get("samples")
        if not isinstance(samples, list) or not samples:
            valid = False
            continue
        target = item.get("target_prompt_tokens")
        tolerance = item.get("prompt_token_tolerance")
        if not all(isinstance(value, int) for value in (target, tolerance)):
            valid = False
            continue
        rates = []
        for sample in samples:
            prompt_tokens = sample.get("prompt_tokens")
            rate = sample.get("decode_tokens_per_second")
            elapsed = sample.get("e2e_seconds")
            ttft = sample.get("ttft_seconds")
            seconds_per_token = sample.get("seconds_per_output_token")
            if not all(
                isinstance(value, (int, float))
                for value in (
                    prompt_tokens,
                    rate,
                    elapsed,
                    ttft,
                    seconds_per_token,
                )
            ):
                valid = False
                continue
            rates.append(rate)
            valid = valid and 0 <= ttft <= elapsed
            valid = valid and rate >= 0 and seconds_per_token >= 0
            valid = valid and abs(prompt_tokens - target) <= tolerance
        threshold = item.get("threshold_tokens_per_second")
        median = item.get("median_decode_tokens_per_second")
        verdict = item.get("verdict")
        valid = valid and bool(rates) and isinstance(median, (int, float))
        valid = valid and isinstance(threshold, (int, float))
        valid = valid and verdict == ("pass" if median >= threshold else "fail")
    expected = "pass" if valid and all(
        item.get("verdict") == "pass" for item in document["results"]
    ) else "fail"
    return valid and document["status"] == expected


def main():
    """Validate one JSON evidence file and fail closed."""
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence")
    args = parser.parse_args()
    document = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    valid = validate_common(document)
    if valid:
        valid = (
            validate_benchmark(document)
            if "model" in document
            else validate_contract(document)
        )
    print(json.dumps({"schema_version": 1, "valid": valid}, sort_keys=True))
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
