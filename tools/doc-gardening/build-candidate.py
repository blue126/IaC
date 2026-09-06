#!/usr/bin/env python3
"""Build a closed, redacted Phase 2 analysis manifest from one document."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from contract import (
    SCHEMA_VERSION,
    SHADOW_SCHEMA_VERSION,
    ContractError,
    atomic_write_json,
    contains_secret,
    git,
    git_file,
    parse_unified_hunks,
    payload_hash,
    read_json,
    require_identifier,
    require_revision,
    require_sha256,
    require_string,
    resolve_revision,
    safe_document_path,
    sha256_bytes,
)


_parse_hunks = parse_unified_hunks


def _redacted_evidence(
    report: Any,
    document_path: str,
    head: str,
    head_sha256: str,
    selected_ids: list[str],
    *,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    if not selected_ids:
        if allow_empty:
            return []
        raise ContractError("evidence_ids_invalid")
    if not isinstance(report, dict) or set(report) != {"schema_version", "revision", "claims"}:
        raise ContractError("evidence_report_invalid")
    if report["schema_version"] != 1 or report["revision"] != head or not isinstance(report["claims"], list):
        raise ContractError("evidence_report_stale")
    if len(selected_ids) != len(set(selected_ids)):
        raise ContractError("evidence_ids_invalid")
    claims_by_id = {
        claim.get("id"): claim
        for claim in report["claims"]
        if isinstance(claim, dict) and isinstance(claim.get("id"), str)
    }
    evidence: list[dict[str, Any]] = []
    for evidence_id in selected_ids:
        require_identifier(evidence_id, "evidence_id")
        claim = claims_by_id.get(evidence_id)
        if claim is None:
            raise ContractError("evidence_ref_unknown")
        document = claim.get("document")
        oracle = claim.get("oracle")
        if not isinstance(document, dict) or not isinstance(oracle, dict):
            raise ContractError("evidence_claim_invalid")
        if document.get("path") != document_path or document.get("sha256") != head_sha256:
            raise ContractError("evidence_claim_out_of_scope")
        if claim.get("status") not in {"verified", "contradiction", "indeterminate"}:
            raise ContractError("evidence_claim_invalid")
        locator = require_string(document.get("locator"), "evidence_locator")
        oracle_path = require_string(oracle.get("path"), "evidence_oracle_path")
        oracle_key = require_string(oracle.get("key"), "evidence_oracle_key")
        oracle_sha256 = require_sha256(oracle.get("sha256"), "evidence_oracle_sha256")
        reason = claim.get("reason")
        if reason is not None:
            require_string(reason, "evidence_reason")
        evidence.append(
            {
                "id": evidence_id,
                "status": claim["status"],
                "reason": reason,
                "document": {
                    "path": document_path,
                    "locator": locator,
                    "sha256": head_sha256,
                },
                "oracle": {
                    "path": oracle_path,
                    "key": oracle_key,
                    "sha256": oracle_sha256,
                },
            }
        )
    return evidence


def build_manifest(
    root: Path,
    document: str,
    base_revision: str,
    head_revision: str,
    evidence_report: Path | dict[str, Any] | None,
    evidence_ids: list[str],
    *,
    schema_version: int = SCHEMA_VERSION,
    change_type: str | None = None,
    require_head_checkout: bool = True,
) -> dict[str, Any]:
    document_path = safe_document_path(document)
    base = resolve_revision(root, base_revision)
    head = resolve_revision(root, head_revision)
    if require_head_checkout and resolve_revision(root, "HEAD") != head:
        raise ContractError("head_revision_stale")
    require_revision(base, "base_revision")
    if schema_version not in {SCHEMA_VERSION, SHADOW_SCHEMA_VERSION}:
        raise ContractError("manifest_version_invalid")
    if schema_version == SHADOW_SCHEMA_VERSION:
        if change_type not in {"A", "M"}:
            raise ContractError("document_change_type_invalid")
    elif change_type is not None:
        raise ContractError("document_change_type_invalid")

    head_data = git_file(root, head, document_path)
    base_data: bytes | None
    if change_type == "A":
        try:
            git_file(root, base, document_path)
        except ContractError:
            base_data = None
        else:
            raise ContractError("added_document_base_present")
    else:
        base_data = git_file(root, base, document_path)
    try:
        head_text = head_data.decode("utf-8")
        if base_data is not None:
            base_data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("document_not_utf8") from error
    if contains_secret(head_text):
        raise ContractError("unsafe_input")
    if require_head_checkout:
        working_path = root / document_path
        try:
            resolved_root = root.resolve(strict=True)
            resolved_working_path = working_path.resolve(strict=True)
            resolved_working_path.relative_to(resolved_root)
            working_data = resolved_working_path.read_bytes()
        except (OSError, RuntimeError, ValueError) as error:
            raise ContractError("working_document_unreadable") from error
        if working_data != head_data:
            raise ContractError("working_document_stale")
    diff_bytes = git(
        root,
        ["diff", "--no-ext-diff", "--unified=3", base, head, "--", document_path],
    )
    try:
        diff = diff_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("document_diff_not_utf8") from error
    hunks, spans = _parse_hunks(
        diff,
        head_text.splitlines(),
        require_spans=schema_version == SCHEMA_VERSION,
    )
    head_sha256 = sha256_bytes(head_data)
    report = (
        read_json(evidence_report)
        if isinstance(evidence_report, Path)
        else evidence_report
    )
    evidence = _redacted_evidence(
        report,
        document_path,
        head,
        head_sha256,
        evidence_ids,
        allow_empty=schema_version == SHADOW_SCHEMA_VERSION,
    )
    document_record: dict[str, Any] = {
        "path": document_path,
        "base_sha256": sha256_bytes(base_data) if base_data is not None else None,
        "head_sha256": head_sha256,
    }
    if schema_version == SHADOW_SCHEMA_VERSION:
        document_record["change_type"] = change_type
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "kind": "analysis_input",
        "revision": {"base": base, "head": head},
        "document": document_record,
        "hunks": hunks,
        "spans": spans,
        "evidence": evidence,
        "manifest_sha256": "",
    }
    if contains_secret(manifest):
        raise ContractError("unsafe_input")
    manifest["manifest_sha256"] = payload_hash(manifest, "manifest_sha256")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--document", action="append", default=[], required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument(
        "--schema-version",
        type=int,
        choices=(SCHEMA_VERSION, SHADOW_SCHEMA_VERSION),
        default=SCHEMA_VERSION,
    )
    parser.add_argument("--change-type", choices=("A", "M"))
    parser.add_argument("--evidence-report", type=Path)
    parser.add_argument("--evidence-id", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        # One manifest carries exactly one document. argparse keeps every
        # --document, so more than one is a rejection rather than a silent
        # last-wins overwrite.
        if len(arguments.document) != 1:
            raise ContractError("document_multiple")
        manifest = build_manifest(
            Path(arguments.root).resolve(),
            arguments.document[0],
            arguments.base,
            arguments.head,
            arguments.evidence_report,
            arguments.evidence_id,
            schema_version=arguments.schema_version,
            change_type=arguments.change_type,
        )
        atomic_write_json(arguments.output, manifest)
    except ContractError as error:
        print(f"doc-gardening: blocked: {error}", file=sys.stderr)
        return 2
    print("doc-gardening: manifest built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
