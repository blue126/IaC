#!/usr/bin/env python3
"""Score a labelled Phase 2A Shadow quality corpus without calling a model."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from contract import ContractError, atomic_write_json, canonical_json, safe_document_path, sha256_bytes


TOOL_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOL_ROOT.parents[1]
CORPUS_SCHEMA_VERSION = 1


def _load_phase_one() -> Any:
    path = REPOSITORY_ROOT / "tools/check-doc-claims.py"
    spec = importlib.util.spec_from_file_location("phase_one_claims", path)
    if spec is None or spec.loader is None:
        raise ContractError("phase_one_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError("corpus_input_invalid") from error


def _exact(value: Any, keys: set[str], error: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ContractError(error)
    return value


def _string(value: Any, error: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(error)
    return value


def _revision(value: Any, error: str) -> dict[str, str]:
    revision = _exact(value, {"base", "head"}, error)
    for name in ("base", "head"):
        item = revision[name]
        if not isinstance(item, str) or len(item) != 40 or any(
            character not in "0123456789abcdef" for character in item
        ):
            raise ContractError(error)
    return revision


def _corpus(value: Any) -> dict[str, Any]:
    corpus = _exact(value, {"schema_version", "kind", "configuration", "cases"}, "corpus_invalid")
    if corpus["schema_version"] != CORPUS_SCHEMA_VERSION or corpus["kind"] != "shadow_quality_corpus":
        raise ContractError("corpus_version_invalid")
    configuration = _exact(
        corpus["configuration"], {"model", "runtime", "schema_sha256"}, "corpus_configuration_invalid"
    )
    for name in configuration:
        _string(configuration[name], "corpus_configuration_invalid")
    if not isinstance(corpus["cases"], list):
        raise ContractError("corpus_cases_invalid")
    return corpus


def _case(value: Any) -> dict[str, Any]:
    case = _exact(
        value,
        {"id", "kind", "document_path", "revision", "result_file", "claim_id"},
        "corpus_case_invalid",
    )
    _string(case["id"], "corpus_case_invalid")
    if case["kind"] not in {"positive", "negative"}:
        raise ContractError("corpus_case_invalid")
    try:
        safe_document_path(_string(case["document_path"], "corpus_case_invalid"))
    except ContractError as error:
        raise ContractError("corpus_case_invalid") from error
    _revision(case["revision"], "corpus_case_invalid")
    result_file = Path(_string(case["result_file"], "corpus_case_invalid"))
    if result_file.is_absolute() or result_file.as_posix() != case["result_file"] or ".." in result_file.parts:
        raise ContractError("corpus_case_invalid")
    if case["kind"] == "positive":
        _string(case["claim_id"], "corpus_case_invalid")
    elif case["claim_id"] is not None:
        raise ContractError("corpus_case_invalid")
    return case


def _result(value: Any) -> dict[str, Any]:
    result = _exact(
        value,
        {
            "schema_version",
            "kind",
            "revision",
            "document_path",
            "change_type",
            "previous_path",
            "status",
            "reason",
            "manifest_sha256",
            "run_record_sha256",
            "candidate_count",
            "candidates",
        },
        "result_invalid",
    )
    if result["schema_version"] != 2 or result["kind"] != "candidate_discovery_result":
        raise ContractError("result_invalid")
    _revision(result["revision"], "result_invalid")
    if not isinstance(result["candidates"], list) or result["candidate_count"] != len(result["candidates"]):
        raise ContractError("result_invalid")
    return result


def _run_record(value: Any) -> dict[str, Any]:
    record = _exact(
        value,
        {
            "schema_version",
            "kind",
            "status",
            "reason",
            "manifest_sha256",
            "prompt_sha256",
            "schema_sha256",
            "model",
            "runtime",
            "output_sha256",
            "artifact_kind",
            "live",
        },
        "run_record_invalid",
    )
    if record["schema_version"] != 2 or record["kind"] != "run_record" or record["artifact_kind"] != "claim_candidates":
        raise ContractError("run_record_invalid")
    if not isinstance(record["live"], bool):
        raise ContractError("run_record_invalid")
    return record


def _candidate_matches(candidate: Any, claim_id: str) -> bool:
    if not isinstance(candidate, dict):
        return False
    required = {"id", "classification", "reason", "hunk_id", "source", "evidence_refs", "edit"}
    if set(candidate) != required:
        return False
    source = candidate["source"]
    return (
        candidate["classification"] == "candidate_contradiction"
        and candidate["reason"] == "evidence_conflict"
        and candidate["evidence_refs"] == [claim_id]
        and candidate["edit"] is None
        and isinstance(candidate["hunk_id"], str)
        and isinstance(source, dict)
        and set(source) == {"span_id", "quote"}
        and isinstance(source["span_id"], str)
        and isinstance(source["quote"], str)
    )


def _safe_negative(candidate: Any) -> bool:
    return isinstance(candidate, dict) and candidate.get("classification") not in {
        "candidate_contradiction",
        "possibly_stale",
    }


def evaluate(corpus_data: Any, results_dir: Path) -> dict[str, Any]:
    corpus = _corpus(corpus_data)
    configuration = corpus["configuration"]
    phase_one = _load_phase_one()
    required_claims = {claim.claim_id: claim.document_path for claim in phase_one.CLAIMS}
    cases = [_case(item) for item in corpus["cases"]]
    case_ids = [item["id"] for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ContractError("corpus_case_duplicate")
    positives = [item for item in cases if item["kind"] == "positive"]
    negatives = [item for item in cases if item["kind"] == "negative"]
    if len(positives) != len(required_claims) or len(negatives) != 2:
        raise ContractError("corpus_shape_invalid")
    if {item["claim_id"] for item in positives} != set(required_claims):
        raise ContractError("corpus_claim_coverage_invalid")
    if any(item["document_path"] != required_claims[item["claim_id"]] for item in positives):
        raise ContractError("corpus_claim_document_invalid")

    counters = {
        "evaluable_positives": 0,
        "correct_positives": 0,
        "false_negatives": 0,
        "evaluable_negatives": 0,
        "false_positives": 0,
        "action_failures": 0,
        "output_failures": 0,
        "integrity_failures": 0,
    }
    outcomes: list[dict[str, str]] = []

    for case in cases:
        outcome = ""
        try:
            result_path = results_dir / case["result_file"]
            result = _result(_read_json(result_path))
            run_record_path = result_path.with_suffix(".run.json")
            record = _run_record(_read_json(run_record_path))
            if result["revision"] != case["revision"] or result["document_path"] != case["document_path"]:
                raise ContractError("result_case_mismatch")
            if result["run_record_sha256"] != sha256_bytes(canonical_json(record)):
                raise ContractError("run_record_hash_mismatch")
            if (
                not record["live"]
                or record["model"] != configuration["model"]
                or record["runtime"] != configuration["runtime"]
                or record["schema_sha256"] != configuration["schema_sha256"]
                or record["manifest_sha256"] != result["manifest_sha256"]
            ):
                raise ContractError("configuration_fingerprint_mismatch")
            if result["status"] == "blocked" and result["reason"] in {"action_failed", "execution_failed", "timeout", "refusal"}:
                counters["action_failures"] += 1
                outcome = "not_evaluable_action_failure"
            elif result["status"] != "completed":
                counters["output_failures"] += 1
                outcome = "not_evaluable_output_failure"
            elif case["kind"] == "positive":
                counters["evaluable_positives"] += 1
                candidates = result["candidates"]
                if len(candidates) == 1 and _candidate_matches(candidates[0], case["claim_id"]):
                    counters["correct_positives"] += 1
                    outcome = "true_positive"
                else:
                    counters["false_negatives"] += 1
                    if any(not _candidate_matches(candidate, case["claim_id"]) for candidate in candidates):
                        counters["false_positives"] += 1
                    outcome = "false_negative"
            else:
                counters["evaluable_negatives"] += 1
                if all(_safe_negative(candidate) for candidate in result["candidates"]):
                    outcome = "true_negative"
                else:
                    counters["false_positives"] += 1
                    outcome = "false_positive"
        except ContractError:
            counters["integrity_failures"] += 1
            outcome = "integrity_failure"
        outcomes.append({"id": case["id"], "outcome": outcome})

    promotion_eligible = counters == {
        "evaluable_positives": 6,
        "correct_positives": 6,
        "false_negatives": 0,
        "evaluable_negatives": 2,
        "false_positives": 0,
        "action_failures": 0,
        "output_failures": 0,
        "integrity_failures": 0,
    }
    return {
        "schema_version": CORPUS_SCHEMA_VERSION,
        "kind": "shadow_quality_report",
        "counters": counters,
        "promotion_eligible": promotion_eligible,
        "outcomes": outcomes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        report = evaluate(_read_json(arguments.corpus), arguments.results_dir)
        atomic_write_json(arguments.output, report)
    except ContractError as error:
        print(f"corpus-quality: blocked: {error}", file=sys.stderr)
        return 2
    print(f"corpus-quality: promotion_eligible={str(report['promotion_eligible']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
