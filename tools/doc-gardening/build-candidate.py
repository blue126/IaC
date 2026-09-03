#!/usr/bin/env python3
"""Build a closed, redacted Phase 2 analysis manifest from one document."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from contract import (
    ContractError,
    atomic_write_json,
    contains_secret,
    git,
    git_file,
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


HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)


def _parse_hunks(diff: str, head_lines: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hunks: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    current_header: re.Match[str] | None = None
    current_lines: list[str] = []

    def finish() -> None:
        nonlocal current_header, current_lines
        if current_header is None:
            return
        old_start = int(current_header.group(1))
        old_count = int(current_header.group(2) or "1")
        new_start = int(current_header.group(3))
        new_count = int(current_header.group(4) or "1")
        text = current_header.group(0) + "\n" + "\n".join(current_lines) + "\n"
        digest = sha256_bytes(text.encode("utf-8"))
        hunk_id = f"hunk-{len(hunks) + 1}-{digest[:12]}"
        hunks.append(
            {
                "id": hunk_id,
                "sha256": digest,
                "old_start": old_start,
                "old_count": old_count,
                "new_start": new_start,
                "new_count": new_count,
                "text": text,
            }
        )
        if new_count:
            # new_start is 1-based whenever the hunk adds lines; 0 would slice
            # from the end of the document and quote unrelated content.
            if new_start < 1:
                raise ContractError("document_diff_invalid")
            quote = "\n".join(head_lines[new_start - 1 : new_start - 1 + new_count])
            span_digest = sha256_bytes(quote.encode("utf-8"))
            spans.append(
                {
                    "id": f"span-{len(spans) + 1}-{span_digest[:12]}",
                    "hunk_id": hunk_id,
                    "start_line": new_start,
                    "end_line": new_start + new_count - 1,
                    "quote": quote,
                    "sha256": span_digest,
                }
            )
        current_header = None
        current_lines = []

    for line in diff.splitlines():
        match = HUNK_HEADER.match(line)
        if match:
            finish()
            current_header = match
        elif current_header is not None:
            current_lines.append(line)
    finish()
    if not hunks or not spans:
        raise ContractError("document_diff_missing")
    return hunks, spans


def _redacted_evidence(
    report: Any,
    document_path: str,
    head: str,
    head_sha256: str,
    selected_ids: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(report, dict) or set(report) != {"schema_version", "revision", "claims"}:
        raise ContractError("evidence_report_invalid")
    if report["schema_version"] != 1 or report["revision"] != head or not isinstance(report["claims"], list):
        raise ContractError("evidence_report_stale")
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
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
    evidence_report: Path,
    evidence_ids: list[str],
) -> dict[str, Any]:
    document_path = safe_document_path(document)
    base = resolve_revision(root, base_revision)
    head = resolve_revision(root, head_revision)
    if resolve_revision(root, "HEAD") != head:
        raise ContractError("head_revision_stale")
    require_revision(base, "base_revision")
    base_data = git_file(root, base, document_path)
    head_data = git_file(root, head, document_path)
    try:
        head_text = head_data.decode("utf-8")
        base_data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("document_not_utf8") from error
    if contains_secret(head_text):
        raise ContractError("unsafe_input")
    working_path = root / document_path
    try:
        working_data = working_path.read_bytes()
        resolved_root = root.resolve(strict=True)
        working_path.resolve(strict=True).relative_to(resolved_root)
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
    hunks, spans = _parse_hunks(diff, head_text.splitlines())
    head_sha256 = sha256_bytes(head_data)
    evidence = _redacted_evidence(
        read_json(evidence_report), document_path, head, head_sha256, evidence_ids
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "analysis_input",
        "revision": {"base": base, "head": head},
        "document": {
            "path": document_path,
            "base_sha256": sha256_bytes(base_data),
            "head_sha256": head_sha256,
        },
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
    parser.add_argument("--evidence-report", type=Path, required=True)
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
        )
        atomic_write_json(arguments.output, manifest)
    except ContractError as error:
        print(f"doc-gardening: blocked: {error}", file=sys.stderr)
        return 2
    print("doc-gardening: manifest built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
