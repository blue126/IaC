#!/usr/bin/env python3
"""Validate one exact v1 proposal without applying it."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

from contract import ContractError, atomic_write_json, canonical_json, payload_hash, read_json, sha256_bytes


TOOL_ROOT = Path(__file__).resolve().parent


def _load_validator() -> Any:
    path = TOOL_ROOT / "validate-contract.py"
    spec = importlib.util.spec_from_file_location("proposal_receipt_validator", path)
    if spec is None or spec.loader is None:
        raise ContractError("validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate(
    root: Path,
    manifest_data: Any,
    candidate_data: Any,
    proposal_data: Any,
    expected_base: str,
    expected_head: str,
) -> dict[str, Any]:
    validator = _load_validator()
    manifest = validator.validate_manifest_structure(manifest_data)
    if manifest["schema_version"] != 1:
        raise ContractError("proposal_manifest_version_invalid")
    validator.validate_manifest_repository(
        manifest,
        root,
        checkout_revision="base",
        expected_base=expected_base,
        expected_head=expected_head,
    )
    candidates = validator.validate_artifact(candidate_data, manifest)
    proposal = validator.validate_artifact(proposal_data, manifest)
    if candidates["kind"] != "claim_candidates" or proposal["kind"] != "edit_proposal":
        raise ContractError("proposal_artifact_kind_invalid")
    if len(candidates["candidates"]) != 1:
        raise ContractError("proposal_candidate_count_invalid")
    candidate = candidates["candidates"][0]
    if (
        proposal["candidate_id"] != candidate["id"]
        or proposal["hunk_id"] != candidate["hunk_id"]
        or proposal["source"] != candidate["source"]
        or proposal["evidence_refs"] != candidate["evidence_refs"]
    ):
        raise ContractError("proposal_candidate_binding_invalid")
    receipt = {
        "schema_version": 1,
        "kind": "proposal_receipt",
        "revision": manifest["revision"],
        "document_path": manifest["document"]["path"],
        "candidate_id": candidate["id"],
        "claim_id": candidate["evidence_refs"][0],
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_sha256": sha256_bytes(canonical_json(candidates)),
        "proposal_sha256": sha256_bytes(canonical_json(proposal)),
    }
    receipt["receipt_sha256"] = payload_hash(receipt, "receipt_sha256")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        receipt = validate(
            Path(arguments.root).resolve(),
            read_json(arguments.manifest),
            read_json(arguments.candidate),
            read_json(arguments.proposal),
            arguments.expected_base,
            arguments.expected_head,
        )
        atomic_write_json(arguments.output, receipt)
    except ContractError as error:
        print(f"validate-proposal: blocked: {error}", file=sys.stderr)
        return 2
    print("validate-proposal: validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
