#!/usr/bin/env python3
"""Bridge one trusted Shadow contradiction into the v1 proposal contract."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from contract import (
    SHADOW_SCHEMA_VERSION,
    ContractError,
    atomic_write_json,
    canonical_json,
    exact_keys,
    payload_hash,
    read_json,
    sha256_bytes,
)


TOOL_ROOT = Path(__file__).resolve().parent


def _load_validator() -> Any:
    path = TOOL_ROOT / "validate-contract.py"
    spec = importlib.util.spec_from_file_location("phase_two_bridge_validator", path)
    if spec is None or spec.loader is None:
        raise ContractError("validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _result(value: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    result = exact_keys(
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
        "bridge_result",
    )
    if (
        result["schema_version"] != SHADOW_SCHEMA_VERSION
        or result["kind"] != "candidate_discovery_result"
        or result["revision"] != manifest["revision"]
        or result["document_path"] != manifest["document"]["path"]
        or result["manifest_sha256"] != manifest["manifest_sha256"]
        or result["status"] != "completed"
        or result["reason"] != "analysis_completed"
        or not isinstance(result["candidates"], list)
        or result["candidate_count"] != len(result["candidates"])
    ):
        raise ContractError("bridge_result_invalid")
    return result


def _v1_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    document = dict(manifest["document"])
    document.pop("change_type", None)
    bridged = {
        "schema_version": 1,
        "kind": "analysis_input",
        "revision": manifest["revision"],
        "document": document,
        "hunks": manifest["hunks"],
        "spans": manifest["spans"],
        "evidence": manifest["evidence"],
    }
    bridged["manifest_sha256"] = payload_hash(bridged, "manifest_sha256")
    return bridged


def bridge(
    root: Path,
    manifest_data: Any,
    result_data: Any,
    run_record_data: Any,
    candidate_id: str,
    expected_base: str,
    expected_head: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validator = _load_validator()
    manifest = validator.validate_manifest_structure(manifest_data)
    if manifest["schema_version"] != SHADOW_SCHEMA_VERSION:
        raise ContractError("bridge_manifest_version_invalid")
    validator.validate_manifest_repository(
        manifest,
        root,
        checkout_revision="base",
        expected_base=expected_base,
        expected_head=expected_head,
    )
    validator.validate_manifest_evidence_repository(manifest, root)
    result = _result(result_data, manifest)

    artifact = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "kind": "claim_candidates",
        "manifest_sha256": manifest["manifest_sha256"],
        "document_path": manifest["document"]["path"],
        "revision": manifest["revision"],
        "candidates": result["candidates"],
    }
    artifact = validator.validate_artifact(artifact, manifest)
    record = validator.validate_run_record(run_record_data, manifest, artifact)
    if result["run_record_sha256"] != sha256_bytes(canonical_json(record)):
        raise ContractError("bridge_run_record_mismatch")
    if not record["live"] or record["status"] != "completed":
        raise ContractError("bridge_run_record_ineligible")
    if len(artifact["candidates"]) != 1:
        raise ContractError("bridge_candidate_count_invalid")

    candidate = artifact["candidates"][0]
    if candidate["id"] != candidate_id or candidate["classification"] != "candidate_contradiction":
        raise ContractError("bridge_candidate_ineligible")
    if len(candidate["evidence_refs"]) != 1:
        raise ContractError("bridge_candidate_evidence_invalid")
    claim_id = candidate["evidence_refs"][0]
    evidence = next((item for item in manifest["evidence"] if item["id"] == claim_id), None)
    if evidence is None or evidence["status"] != "contradiction":
        raise ContractError("bridge_claim_not_provable")

    phase_one = validator._load_phase_one(root)
    claims = {claim.claim_id: claim for claim in phase_one.CLAIMS}
    claim = claims.get(claim_id)
    if claim is None or claim.document_path != manifest["document"]["path"]:
        raise ContractError("bridge_claim_not_approved")

    v1_manifest = _v1_manifest(manifest)
    validator.validate_manifest_structure(v1_manifest)
    v1_artifact = {
        "schema_version": 1,
        "kind": "claim_candidates",
        "manifest_sha256": v1_manifest["manifest_sha256"],
        "document_path": v1_manifest["document"]["path"],
        "revision": v1_manifest["revision"],
        "candidates": [candidate],
    }
    validator.validate_artifact(v1_artifact, v1_manifest)
    return v1_manifest, v1_artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--run-record", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-candidate", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        manifest, candidate = bridge(
            Path(arguments.root).resolve(),
            read_json(arguments.manifest),
            read_json(arguments.result),
            read_json(arguments.run_record),
            arguments.candidate_id,
            arguments.expected_base,
            arguments.expected_head,
        )
        atomic_write_json(arguments.output_manifest, manifest)
        atomic_write_json(arguments.output_candidate, candidate)
    except ContractError as error:
        print(f"phase2-bridge: blocked: {error}", file=sys.stderr)
        return 2
    print("phase2-bridge: eligible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
