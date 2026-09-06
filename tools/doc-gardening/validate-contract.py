#!/usr/bin/env python3
"""Fail-closed validator for Phase 2 manifests, artifacts, and run records."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

from contract import (
    CANDIDATE_REASONS,
    CLASSIFICATIONS,
    MAX_SHADOW_CANDIDATES,
    RUN_REASONS,
    RUN_STATUSES,
    SCHEMA_VERSION,
    SHADOW_RUN_REASONS,
    SHADOW_SCHEMA_VERSION,
    ContractError,
    contains_secret,
    exact_keys,
    git,
    git_file,
    parse_unified_hunks,
    payload_hash,
    read_json,
    require_enum,
    require_identifier,
    require_integer,
    require_revision,
    require_sha256,
    require_string,
    resolve_revision,
    safe_document_path,
    sha256_bytes,
)


def _revision(value: Any, location: str) -> dict[str, str]:
    revision = exact_keys(value, {"base", "head"}, location)
    return {
        "base": require_revision(revision["base"], f"{location}_base"),
        "head": require_revision(revision["head"], f"{location}_head"),
    }


def validate_manifest_structure(manifest: Any) -> dict[str, Any]:
    manifest = exact_keys(
        manifest,
        {
            "schema_version",
            "kind",
            "revision",
            "document",
            "hunks",
            "spans",
            "evidence",
            "manifest_sha256",
        },
        "manifest",
    )
    version = manifest["schema_version"]
    if version not in {SCHEMA_VERSION, SHADOW_SCHEMA_VERSION} or manifest["kind"] != "analysis_input":
        raise ContractError("manifest_version_invalid")
    revision = _revision(manifest["revision"], "manifest_revision")
    document_keys = {"path", "base_sha256", "head_sha256"}
    if version == SHADOW_SCHEMA_VERSION:
        document_keys.add("change_type")
    document = exact_keys(manifest["document"], document_keys, "manifest_document")
    path = safe_document_path(document["path"])
    if version == SHADOW_SCHEMA_VERSION:
        change_type = require_enum(
            document["change_type"], {"A", "M"}, "manifest_change_type_invalid"
        )
        if change_type == "A":
            if document["base_sha256"] is not None:
                raise ContractError("manifest_added_base_sha_invalid")
        else:
            require_sha256(document["base_sha256"], "manifest_base_sha256")
    else:
        require_sha256(document["base_sha256"], "manifest_base_sha256")
    require_sha256(document["head_sha256"], "manifest_head_sha256")
    require_sha256(manifest["manifest_sha256"], "manifest_sha256")
    if payload_hash(manifest, "manifest_sha256") != manifest["manifest_sha256"]:
        raise ContractError("manifest_hash_mismatch")
    if not isinstance(manifest["hunks"], list) or not manifest["hunks"]:
        raise ContractError("manifest_hunks_invalid")
    hunk_ids: set[str] = set()
    for item in manifest["hunks"]:
        hunk = exact_keys(
            item,
            {"id", "sha256", "old_start", "old_count", "new_start", "new_count", "text"},
            "manifest_hunk",
        )
        hunk_id = require_identifier(hunk["id"], "manifest_hunk_id")
        if hunk_id in hunk_ids:
            raise ContractError("manifest_hunk_duplicate")
        hunk_ids.add(hunk_id)
        require_sha256(hunk["sha256"], "manifest_hunk_sha256")
        for key in ("old_start", "old_count", "new_start", "new_count"):
            require_integer(hunk[key], f"manifest_hunk_{key}")
        text = require_string(hunk["text"], "manifest_hunk_text")
        if sha256_bytes(text.encode("utf-8")) != hunk["sha256"]:
            raise ContractError("manifest_hunk_hash_mismatch")
    if not isinstance(manifest["spans"], list) or (
        version == SCHEMA_VERSION and not manifest["spans"]
    ):
        raise ContractError("manifest_spans_invalid")
    span_ids: set[str] = set()
    for item in manifest["spans"]:
        span = exact_keys(
            item,
            {"id", "hunk_id", "start_line", "end_line", "quote", "sha256"},
            "manifest_span",
        )
        span_id = require_identifier(span["id"], "manifest_span_id")
        if span_id in span_ids:
            raise ContractError("manifest_span_duplicate")
        span_ids.add(span_id)
        if span["hunk_id"] not in hunk_ids:
            raise ContractError("manifest_span_hunk_unknown")
        start = require_integer(span["start_line"], "manifest_span_start", minimum=1)
        end = require_integer(span["end_line"], "manifest_span_end", minimum=1)
        if end < start:
            raise ContractError("manifest_span_range_invalid")
        quote = require_string(span["quote"], "manifest_span_quote", allow_empty=True)
        require_sha256(span["sha256"], "manifest_span_sha256")
        if sha256_bytes(quote.encode("utf-8")) != span["sha256"]:
            raise ContractError("manifest_span_hash_mismatch")
    if not isinstance(manifest["evidence"], list) or (
        version == SCHEMA_VERSION and not manifest["evidence"]
    ):
        raise ContractError("manifest_evidence_invalid")
    evidence_ids: set[str] = set()
    for item in manifest["evidence"]:
        evidence = exact_keys(
            item, {"id", "status", "reason", "document", "oracle"}, "manifest_evidence"
        )
        evidence_id = require_identifier(evidence["id"], "manifest_evidence_id")
        if evidence_id in evidence_ids:
            raise ContractError("manifest_evidence_duplicate")
        evidence_ids.add(evidence_id)
        require_enum(
            evidence["status"],
            {"verified", "contradiction", "indeterminate"},
            "manifest_evidence_status_invalid",
        )
        if evidence["reason"] is not None:
            require_string(evidence["reason"], "manifest_evidence_reason")
        evidence_document = exact_keys(
            evidence["document"], {"path", "locator", "sha256"}, "manifest_evidence_document"
        )
        if evidence_document["path"] != path:
            raise ContractError("manifest_multiple_documents")
        require_string(evidence_document["locator"], "manifest_evidence_locator")
        if evidence_document["sha256"] != document["head_sha256"]:
            raise ContractError("manifest_evidence_sha_mismatch")
        oracle = exact_keys(
            evidence["oracle"], {"path", "key", "sha256"}, "manifest_evidence_oracle"
        )
        safe_document_or_oracle_path = require_string(oracle["path"], "manifest_oracle_path")
        if Path(safe_document_or_oracle_path).is_absolute() or ".." in Path(safe_document_or_oracle_path).parts:
            raise ContractError("manifest_oracle_path_invalid")
        require_string(oracle["key"], "manifest_oracle_key")
        require_sha256(oracle["sha256"], "manifest_oracle_sha256")
    if contains_secret(manifest):
        raise ContractError("unsafe_input")
    manifest["revision"] = revision
    return manifest


def validate_manifest_repository(
    manifest: dict[str, Any],
    root: Path,
    *,
    checkout_revision: str = "head",
    expected_base: str | None = None,
    expected_head: str | None = None,
) -> None:
    revision = manifest["revision"]
    base = resolve_revision(root, revision["base"])
    head = resolve_revision(root, revision["head"])
    if expected_base is not None and resolve_revision(root, expected_base) != base:
        raise ContractError("manifest_base_unexpected")
    if expected_head is not None and resolve_revision(root, expected_head) != head:
        raise ContractError("manifest_head_unexpected")
    if checkout_revision not in {"base", "head"}:
        raise ContractError("checkout_revision_invalid")
    expected_checkout = base if checkout_revision == "base" else head
    if resolve_revision(root, "HEAD") != expected_checkout:
        raise ContractError("manifest_revision_stale")

    path = manifest["document"]["path"]
    version = manifest["schema_version"]
    change_type = manifest["document"].get("change_type")
    head_data = git_file(root, head, path)
    base_data: bytes | None
    if version == SHADOW_SCHEMA_VERSION and change_type == "A":
        try:
            git_file(root, base, path)
        except ContractError:
            base_data = None
        else:
            raise ContractError("manifest_added_base_present")
    else:
        base_data = git_file(root, base, path)
    if base_data is not None and sha256_bytes(base_data) != manifest["document"]["base_sha256"]:
        raise ContractError("manifest_base_stale")
    if sha256_bytes(head_data) != manifest["document"]["head_sha256"]:
        raise ContractError("manifest_head_stale")

    try:
        head_text = head_data.decode("utf-8")
        if base_data is not None:
            base_data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("manifest_document_not_utf8") from error
    diff_data = git(
        root,
        ["diff", "--no-ext-diff", "--unified=3", base, head, "--", path],
    )
    try:
        diff = diff_data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("manifest_diff_not_utf8") from error
    if version == SHADOW_SCHEMA_VERSION:
        expected_hunks, expected_spans = parse_unified_hunks(
            diff,
            head_text.splitlines(),
            require_spans=False,
        )
        if manifest["hunks"] != expected_hunks or manifest["spans"] != expected_spans:
            raise ContractError("manifest_diff_stale")
    else:
        lines = head_text.splitlines()
        for span in manifest["spans"]:
            quote = "\n".join(lines[span["start_line"] - 1 : span["end_line"]])
            if quote != span["quote"]:
                raise ContractError("manifest_span_quote_stale")

    if version == SHADOW_SCHEMA_VERSION:
        status_data = git(
            root,
            ["diff", "--name-status", "--no-renames", "-z", base, head, "--", path],
        )
        fields = status_data.split(b"\0")
        if fields and fields[-1] == b"":
            fields.pop()
        try:
            status = fields[0].decode("ascii")
            changed_path = fields[1].decode("utf-8")
        except (IndexError, UnicodeDecodeError) as error:
            raise ContractError("manifest_change_status_invalid") from error
        if len(fields) != 2 or status != change_type or changed_path != path:
            raise ContractError("manifest_change_status_invalid")

    if checkout_revision == "head":
        try:
            resolved_root = root.resolve(strict=True)
            working_path = (resolved_root / path).resolve(strict=True)
            working_path.relative_to(resolved_root)
            working_data = working_path.read_bytes()
        except (OSError, RuntimeError, ValueError) as error:
            raise ContractError("manifest_working_file_missing") from error
        if sha256_bytes(working_data) != manifest["document"]["head_sha256"]:
            raise ContractError("manifest_working_file_stale")


def _load_phase_one(root: Path) -> Any:
    path = root / "tools/check-doc-claims.py"
    spec = importlib.util.spec_from_file_location("trusted_doc_claims", path)
    if spec is None or spec.loader is None:
        raise ContractError("evidence_validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except (OSError, RuntimeError) as error:
        raise ContractError("evidence_validator_unavailable") from error
    return module


def validate_manifest_evidence_repository(manifest: dict[str, Any], root: Path) -> None:
    """Rebuild v2 evidence from trusted base code and head Git objects."""
    if manifest["schema_version"] != SHADOW_SCHEMA_VERSION:
        return
    phase_one = _load_phase_one(root)
    claims = {claim.claim_id: claim for claim in phase_one.CLAIMS}
    head = manifest["revision"]["head"]
    document_path = manifest["document"]["path"]
    for evidence in manifest["evidence"]:
        claim = claims.get(evidence["id"])
        if claim is None or claim.document_path != document_path:
            raise ContractError("manifest_evidence_untrusted")
        if evidence["document"]["locator"] != claim.locator:
            raise ContractError("manifest_evidence_untrusted")
        if evidence["oracle"]["path"] != claim.oracle_path or evidence["oracle"]["key"] != claim.oracle_key:
            raise ContractError("manifest_evidence_untrusted")
        try:
            document_data = git_file(root, head, claim.document_path)
            oracle_data = git_file(root, head, claim.oracle_path)
            document_text = document_data.decode("utf-8")
            oracle_text = oracle_data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ContractError("manifest_evidence_untrusted") from error
        if evidence["document"]["sha256"] != sha256_bytes(document_data):
            raise ContractError("manifest_evidence_untrusted")
        if evidence["oracle"]["sha256"] != sha256_bytes(oracle_data):
            raise ContractError("manifest_evidence_untrusted")

        status = "indeterminate"
        reason: str | None = None
        document_ok, document_value, locator_error = claim.document_reader(
            document_text, claim.locator
        )
        if not document_ok:
            reason = locator_error
        else:
            oracle_values = phase_one._yaml_key_values(oracle_text, claim.oracle_key)
            if not oracle_values:
                reason = "oracle_key_missing"
            elif len(oracle_values) != 1:
                reason = "oracle_key_duplicate"
            else:
                oracle_ok, oracle_value = oracle_values[0]
                if not oracle_ok:
                    reason = "oracle_non_scalar"
                elif type(document_value) is not type(oracle_value):
                    status = "contradiction"
                    reason = "type_mismatch"
                elif document_value != oracle_value:
                    status = "contradiction"
                    reason = "value_mismatch"
                else:
                    status = "verified"
        if evidence["status"] != status or evidence["reason"] != reason:
            raise ContractError("manifest_evidence_untrusted")


def _validate_source(
    source: Any,
    hunk_id: Any,
    manifest: dict[str, Any],
    location: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    hunk_ids = {item["id"] for item in manifest["hunks"]}
    require_enum(hunk_id, hunk_ids, f"{location}_hunk_unknown")
    source = exact_keys(source, {"span_id", "quote"}, f"{location}_source")
    span = next((item for item in manifest["spans"] if item["id"] == source["span_id"]), None)
    if span is None or span["hunk_id"] != hunk_id:
        raise ContractError(f"{location}_span_unknown")
    if source["quote"] != span["quote"]:
        raise ContractError(f"{location}_quote_mismatch")
    return source, span


def _validate_refs(refs: Any, manifest: dict[str, Any], location: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
        raise ContractError(f"{location}_refs_invalid")
    if len(refs) != len(set(refs)) or (not refs and not allow_empty):
        raise ContractError(f"{location}_refs_invalid")
    known = {item["id"] for item in manifest["evidence"]}
    if any(item not in known for item in refs):
        raise ContractError(f"{location}_ref_unknown")
    return refs


def _validate_edit(edit: Any, span: dict[str, Any], location: str) -> None:
    edit = exact_keys(edit, {"find", "replace"}, f"{location}_edit")
    find = require_string(edit["find"], f"{location}_find")
    require_string(edit["replace"], f"{location}_replace", allow_empty=True)
    if span["quote"].count(find) != 1:
        raise ContractError(f"{location}_find_not_exact")
    if contains_secret(edit):
        raise ContractError("unsafe_output")


def validate_artifact(artifact: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ContractError("artifact_type_invalid")
    common = {"schema_version", "kind", "manifest_sha256", "document_path", "revision"}
    if artifact.get("kind") == "claim_candidates":
        artifact = exact_keys(artifact, common | {"candidates"}, "artifact")
    elif artifact.get("kind") == "edit_proposal":
        artifact = exact_keys(
            artifact,
            common | {"candidate_id", "hunk_id", "source", "evidence_refs", "edit"},
            "artifact",
        )
    else:
        raise ContractError("artifact_kind_invalid")
    if artifact["schema_version"] != manifest["schema_version"]:
        raise ContractError("artifact_version_invalid")
    if (
        manifest["schema_version"] == SHADOW_SCHEMA_VERSION
        and artifact["kind"] != "claim_candidates"
    ):
        raise ContractError("artifact_kind_invalid")
    if artifact["manifest_sha256"] != manifest["manifest_sha256"]:
        raise ContractError("artifact_manifest_mismatch")
    if artifact["document_path"] != manifest["document"]["path"]:
        raise ContractError("artifact_document_mismatch")
    if _revision(artifact["revision"], "artifact_revision") != manifest["revision"]:
        raise ContractError("artifact_revision_mismatch")
    if artifact["kind"] == "claim_candidates":
        candidates = artifact["candidates"]
        if not isinstance(candidates, list) or (
            manifest["schema_version"] == SHADOW_SCHEMA_VERSION
            and len(candidates) > MAX_SHADOW_CANDIDATES
        ):
            raise ContractError("artifact_candidates_invalid")
        ids: set[str] = set()
        for item in candidates:
            candidate = exact_keys(
                item,
                {"id", "classification", "reason", "hunk_id", "source", "evidence_refs", "edit"},
                "candidate",
            )
            candidate_id = require_identifier(candidate["id"], "candidate_id")
            if candidate_id in ids:
                raise ContractError("candidate_id_duplicate")
            ids.add(candidate_id)
            require_enum(
                candidate["classification"], CLASSIFICATIONS, "candidate_classification_invalid"
            )
            require_enum(candidate["reason"], CANDIDATE_REASONS, "candidate_reason_invalid")
            _, span = _validate_source(candidate["source"], candidate["hunk_id"], manifest, "candidate")
            refs = _validate_refs(
                candidate["evidence_refs"],
                manifest,
                "candidate",
                allow_empty=candidate["classification"] == "unknown",
            )
            if manifest["schema_version"] == SHADOW_SCHEMA_VERSION:
                if candidate["edit"] is not None:
                    raise ContractError("candidate_shadow_has_edit")
                if not manifest["evidence"] and (
                    candidate["classification"] != "unknown"
                    or candidate["reason"] != "missing_evidence"
                    or refs
                ):
                    raise ContractError("candidate_missing_evidence_contract")
                if candidate["reason"] == "missing_evidence" and (
                    candidate["classification"] != "unknown" or refs
                ):
                    raise ContractError("candidate_missing_evidence_contract")
                if candidate["classification"] != "unknown" and not refs:
                    raise ContractError("candidate_missing_evidence")
            elif candidate["classification"] == "unknown":
                if candidate["edit"] is not None:
                    raise ContractError("candidate_unknown_has_edit")
            elif candidate["edit"] is not None:
                _validate_edit(candidate["edit"], span, "candidate")
            if candidate["classification"] == "candidate_contradiction" and not refs:
                raise ContractError("candidate_missing_evidence")
    else:
        if manifest["schema_version"] == SHADOW_SCHEMA_VERSION:
            raise ContractError("shadow_edit_proposal_forbidden")
        require_identifier(artifact["candidate_id"], "proposal_candidate_id")
        _, span = _validate_source(artifact["source"], artifact["hunk_id"], manifest, "proposal")
        _validate_refs(artifact["evidence_refs"], manifest, "proposal", allow_empty=False)
        _validate_edit(artifact["edit"], span, "proposal")
    if contains_secret(artifact):
        raise ContractError("unsafe_output")
    return artifact


def validate_run_record(record: Any, manifest: dict[str, Any], artifact: dict[str, Any] | None) -> dict[str, Any]:
    record = exact_keys(
        record,
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
        "run_record",
    )
    if record["schema_version"] != manifest["schema_version"] or record["kind"] != "run_record":
        raise ContractError("run_record_version_invalid")
    require_enum(record["status"], RUN_STATUSES, "run_record_outcome_invalid")
    reasons = (
        SHADOW_RUN_REASONS
        if manifest["schema_version"] == SHADOW_SCHEMA_VERSION
        else RUN_REASONS
    )
    require_enum(record["reason"], reasons, "run_record_outcome_invalid")
    if record["manifest_sha256"] != manifest["manifest_sha256"]:
        raise ContractError("run_record_manifest_mismatch")
    require_sha256(record["prompt_sha256"], "run_record_prompt_sha256")
    require_sha256(record["schema_sha256"], "run_record_schema_sha256")
    require_string(record["model"], "run_record_model")
    require_string(record["runtime"], "run_record_runtime")
    require_sha256(record["output_sha256"], "run_record_output_sha256")
    artifact_kinds = (
        {"claim_candidates"}
        if manifest["schema_version"] == SHADOW_SCHEMA_VERSION
        else {"claim_candidates", "edit_proposal"}
    )
    require_enum(
        record["artifact_kind"],
        artifact_kinds,
        "run_record_artifact_kind_invalid",
    )
    if type(record["live"]) is not bool:
        raise ContractError("run_record_live_invalid")
    if record["status"] == "completed" and artifact is None:
        raise ContractError("run_record_completed_without_artifact")
    if artifact is not None and record["artifact_kind"] != artifact["kind"]:
        raise ContractError("run_record_artifact_mismatch")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--run-record", type=Path)
    parser.add_argument("--trusted-base-checkout", action="store_true")
    parser.add_argument("--expected-base")
    parser.add_argument("--expected-head")
    parser.add_argument("--no-repository-check", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    try:
        manifest = validate_manifest_structure(read_json(arguments.manifest))
        if not arguments.no_repository_check:
            validate_manifest_repository(
                manifest,
                Path(arguments.root).resolve(),
                checkout_revision="base" if arguments.trusted_base_checkout else "head",
                expected_base=arguments.expected_base,
                expected_head=arguments.expected_head,
            )
            if arguments.trusted_base_checkout:
                validate_manifest_evidence_repository(
                    manifest, Path(arguments.root).resolve()
                )
        artifact = validate_artifact(read_json(arguments.artifact), manifest) if arguments.artifact else None
        if arguments.run_record:
            validate_run_record(read_json(arguments.run_record), manifest, artifact)
    except ContractError as error:
        print(f"doc-gardening: blocked: {error}", file=sys.stderr)
        return 2
    print("doc-gardening: contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
