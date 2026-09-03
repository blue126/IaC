#!/usr/bin/env python3
"""Evaluate recorded Phase 2 artifacts against deterministic golden fixtures."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from contract import ContractError, read_json


TOOL_ROOT = Path(__file__).resolve().parent


def _load_validator() -> Any:
    path = TOOL_ROOT / "validate-contract.py"
    spec = importlib.util.spec_from_file_location("doc_gardening_eval_validator", path)
    if spec is None or spec.loader is None:
        raise ContractError("validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(fixtures: Path) -> dict[str, Any]:
    validator = _load_validator()
    manifest = validator.validate_manifest_structure(read_json(fixtures / "manifest.json"))
    expectations = read_json(fixtures / "expectations.json")
    if not isinstance(expectations, list) or not expectations:
        raise ContractError("fixture_expectations_invalid")
    results: list[dict[str, Any]] = []
    false_proposals = 0
    security_leakage = 0
    for expectation in expectations:
        if not isinstance(expectation, dict) or set(expectation) != {
            "name",
            "file",
            "valid",
            "security",
        }:
            raise ContractError("fixture_expectation_invalid")
        # Without this a mistyped filename reads as a correct rejection and
        # the gate passes with no coverage at all.
        if not (fixtures / expectation["file"]).is_file():
            raise ContractError("fixture_missing")
        accepted = False
        artifact: dict[str, Any] | None = None
        try:
            artifact = validator.validate_artifact(read_json(fixtures / expectation["file"]), manifest)
            accepted = True
        except ContractError:
            accepted = False
        matched = accepted is expectation["valid"]
        if accepted and not expectation["valid"]:
            false_proposals += 1
        if expectation["security"] and not matched:
            security_leakage += 1
        if accepted and artifact is not None and artifact["kind"] == "claim_candidates":
            if any(
                candidate["classification"] == "unknown" and candidate["edit"] is not None
                for candidate in artifact["candidates"]
            ):
                false_proposals += 1
        results.append(
            {
                "name": expectation["name"],
                "expected_valid": expectation["valid"],
                "accepted": accepted,
                "matched": matched,
            }
        )
    return {
        "schema_version": 1,
        "cases": len(results),
        "matched": sum(item["matched"] for item in results),
        "false_proposals": false_proposals,
        "security_leakage": security_leakage,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        report = evaluate(arguments.fixtures)
    except ContractError as error:
        print(f"doc-gardening eval: blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    passed = (
        report["matched"] == report["cases"]
        and report["false_proposals"] == 0
        and report["security_leakage"] == 0
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
