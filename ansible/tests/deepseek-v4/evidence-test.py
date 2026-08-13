#!/usr/bin/env python3
"""Exercise evidence validation with passing and failing documents."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = (
    ROOT / "ansible/roles/deepseek-v4/files/evidence-validator.py"
)
SPEC = importlib.util.spec_from_file_location("evidence_validator", VALIDATOR_PATH)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def accepted(document):
    """Apply the same type dispatch as the validator CLI."""
    if not VALIDATOR.validate_common(document):
        return False
    return (
        VALIDATOR.validate_benchmark(document)
        if "model" in document
        else VALIDATOR.validate_contract(document)
    )


contract = {
    "schema_version": 1,
    "fixture_revision": "v1",
    "status": "pass",
    "results": [{"id": "sync", "pass": True}],
}
benchmark = {
    "schema_version": 1,
    "fixture_revision": "v1",
    "model": "fixture",
    "status": "pass",
    "results": [{
        "id": "1k",
        "target_prompt_tokens": 1024,
        "prompt_token_tolerance": 154,
        "samples": [{
            "prompt_tokens": 1020,
            "decode_tokens_per_second": 9.0,
            "e2e_seconds": 30.0,
            "ttft_seconds": 2.0,
            "seconds_per_output_token": 0.11,
        }],
        "median_decode_tokens_per_second": 9.0,
        "threshold_tokens_per_second": 8,
        "verdict": "pass",
    }],
}
invalid_benchmark = json.loads(json.dumps(benchmark))
invalid_benchmark["results"][0]["samples"][0]["prompt_tokens"] = 500

checks = {
    "contract_pass": accepted(contract),
    "benchmark_pass": accepted(benchmark),
    "benchmark_token_mismatch_rejected": not accepted(invalid_benchmark),
}
report = {
    "schema_version": 1,
    "status": "pass" if all(checks.values()) else "fail",
    "checks": checks,
}
print(json.dumps(report, indent=2, sort_keys=True))
sys.exit(0 if report["status"] == "pass" else 1)
