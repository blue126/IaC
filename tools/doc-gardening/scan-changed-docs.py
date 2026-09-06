#!/usr/bin/env python3
"""Deterministic Phase 2A changed-document Shadow controller."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from contract import (
    MAX_SHADOW_CANDIDATES,
    MAX_SHADOW_DOCUMENTS,
    SHADOW_RESULT_REASONS,
    SHADOW_RESULT_STATUSES,
    SHADOW_RUN_REASONS,
    SHADOW_SCHEMA_VERSION,
    ContractError,
    atomic_write_json,
    build_run_record,
    canonical_json,
    contains_secret,
    exact_keys,
    git,
    read_json,
    require_enum,
    require_integer,
    require_revision,
    require_sha256,
    require_string,
    resolve_revision,
    safe_document_path,
    sha256_bytes,
)


TOOL_ROOT = Path(__file__).resolve().parent
REQUIRED_TRUSTED_RUNTIME = (
    "tools/check-doc-claims.py",
    "tools/doc-gardening/contract.py",
    "tools/doc-gardening/build-candidate.py",
    "tools/doc-gardening/validate-contract.py",
    "tools/doc-gardening/scan-changed-docs.py",
    "tools/doc-gardening/prompts/analyze-v2.md",
    "tools/doc-gardening/schemas/claim-candidates-v2.json",
)


def _load_script(filename: str, module_name: str) -> Any:
    path = TOOL_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ContractError("runtime_module_unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, RuntimeError) as error:
        raise ContractError("runtime_module_unavailable") from error
    return module


def _load_phase_one(root: Path) -> Any:
    path = root / "tools/check-doc-claims.py"
    spec = importlib.util.spec_from_file_location("candidate_discovery_claims", path)
    if spec is None or spec.loader is None:
        raise ContractError("evidence_validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except (OSError, RuntimeError) as error:
        raise ContractError("evidence_validator_unavailable") from error
    return module


def _git_object_exists(root: Path, revision: str, path: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{revision}:{path}"],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ContractError("git_execution_failed") from error
    return result.returncode == 0


def trusted_runtime_available(root: Path, base: str) -> bool:
    return all(_git_object_exists(root, base, path) for path in REQUIRED_TRUSTED_RUNTIME)


def _in_scope(path: str) -> bool:
    try:
        safe_document_path(path)
    except ContractError:
        return False
    return True


def _decode_path(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractError("changed_path_not_utf8") from error


def changed_documents(root: Path, base: str, head: str) -> list[dict[str, Any]]:
    raw = git(root, ["diff", "--name-status", "--find-renames", "-z", base, head])
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changes: list[dict[str, Any]] = []
    index = 0
    while index < len(fields):
        status_field = _decode_path(fields[index])
        index += 1
        status = status_field[:1]
        if status in {"R", "C"}:
            if index + 1 >= len(fields):
                raise ContractError("changed_paths_invalid")
            previous = _decode_path(fields[index])
            current = _decode_path(fields[index + 1])
            index += 2
            if status != "R" or (not _in_scope(previous) and not _in_scope(current)):
                continue
            if _in_scope(current):
                document_path = current
                previous_path = previous if _in_scope(previous) else None
            else:
                document_path = previous
                previous_path = None
            changes.append(
                {
                    "document_path": safe_document_path(document_path),
                    "change_type": "R",
                    "previous_path": previous_path,
                }
            )
            continue
        if index >= len(fields):
            raise ContractError("changed_paths_invalid")
        path = _decode_path(fields[index])
        index += 1
        if status not in {"A", "M", "D"} or not _in_scope(path):
            continue
        changes.append(
            {
                "document_path": safe_document_path(path),
                "change_type": status,
                "previous_path": None,
            }
        )
    return sorted(
        changes,
        key=lambda item: (
            item["document_path"].encode("utf-8"),
            item["change_type"],
            (item["previous_path"] or "").encode("utf-8"),
        ),
    )


def _evidence_report(root: Path, head: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    phase_one = _load_phase_one(root)
    report = phase_one.build_report(root)
    if report.get("revision") != head:
        raise ContractError("evidence_report_stale")
    by_document: dict[str, list[str]] = {}
    for claim in report.get("claims", []):
        if not isinstance(claim, dict):
            continue
        document = claim.get("document")
        oracle = claim.get("oracle")
        if not isinstance(document, dict) or not isinstance(oracle, dict):
            continue
        if not isinstance(document.get("sha256"), str) or not isinstance(
            oracle.get("sha256"), str
        ):
            continue
        path = document.get("path")
        claim_id = claim.get("id")
        if isinstance(path, str) and isinstance(claim_id, str):
            by_document.setdefault(path, []).append(claim_id)
    for identifiers in by_document.values():
        identifiers.sort()
    return report, by_document


def _manifest_id(path: str) -> str:
    return f"doc-{sha256_bytes(path.encode('utf-8'))[:20]}"


def _result(
    revision: dict[str, str],
    item: dict[str, Any],
    *,
    status: str,
    reason: str,
    manifest_sha256: str | None = None,
    candidates: list[dict[str, Any]] | None = None,
    run_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_items = candidates or []
    result = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "kind": "candidate_discovery_result",
        "revision": revision,
        "document_path": item["document_path"],
        "change_type": item["change_type"],
        "previous_path": item.get("previous_path"),
        "status": status,
        "reason": reason,
        "manifest_sha256": manifest_sha256,
        "run_record_sha256": (
            sha256_bytes(canonical_json(run_record)) if run_record is not None else None
        ),
        "candidate_count": len(candidate_items),
        "candidates": candidate_items,
    }
    validate_shadow_result(result)
    return result


def _blocked_reason(error: ContractError) -> str:
    code = str(error)
    if code in {"unsafe_input", "unsafe_output"}:
        return code
    if "stale" in code or code in {
        "head_revision_stale",
        "manifest_revision_stale",
        "manifest_diff_stale",
    }:
        return "stale_input"
    return "validation_failed"


def _report(revision: dict[str, str], results: list[dict[str, Any]], selected: int) -> dict[str, Any]:
    report = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "kind": "candidate_discovery_report",
        "revision": revision,
        "summary": {
            "documents": len(results),
            "selected": selected,
            "completed": sum(item["status"] == "completed" for item in results),
            "unknown": sum(item["status"] == "unknown" for item in results),
            "blocked": sum(item["status"] == "blocked" for item in results),
            "no_analysis": sum(item["status"] == "no_analysis" for item in results),
            "candidates": sum(item["candidate_count"] for item in results),
        },
        "results": results,
    }
    if contains_secret(report):
        raise ContractError("unsafe_output")
    return report


def prepare(
    root: Path,
    base_revision: str,
    head_revision: str,
    output_dir: Path,
    preparation_path: Path,
    matrix_path: Path,
    bootstrap_report_path: Path,
) -> dict[str, Any]:
    head = resolve_revision(root, head_revision)
    if resolve_revision(root, "HEAD") != head:
        raise ContractError("head_revision_stale")
    base_tip = resolve_revision(root, base_revision)
    merge_base_output = git(root, ["merge-base", base_tip, head])
    base = require_revision(
        merge_base_output.decode("ascii", errors="ignore").strip(), "merge_base"
    )
    revision = {"base": base, "head": head}
    changes = changed_documents(root, base, head)
    bootstrapped = trusted_runtime_available(root, base)
    evidence_report, evidence_by_document = _evidence_report(root, head)
    builder = _load_script("build-candidate.py", "candidate_discovery_builder")

    empty_added_paths = {
        item["document_path"]
        for item in changes
        if item["change_type"] == "A"
        and len(git(root, ["show", f"{head}:{item['document_path']}"])) == 0
    }
    eligible = [
        item
        for item in changes
        if item["change_type"] in {"A", "M"}
        and item["document_path"] not in empty_added_paths
    ]
    eligible_paths = {
        item["document_path"] for item in eligible[:MAX_SHADOW_DOCUMENTS]
    }
    manifests_dir = output_dir / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    bootstrap_results: list[dict[str, Any]] = []
    matrix: list[dict[str, str]] = []

    for change in changes:
        item = dict(change)
        item["id"] = _manifest_id(item["document_path"])
        item["manifest_file"] = None
        item["manifest_sha256"] = None
        change_type = item["change_type"]
        if change_type == "D":
            item.update(status="no_analysis", reason="deleted")
        elif change_type == "R":
            item.update(status="no_analysis", reason="renamed")
        elif item["document_path"] in empty_added_paths:
            item.update(status="no_analysis", reason="empty_added")
        elif not bootstrapped:
            item.update(status="no_analysis", reason="runtime_not_bootstrapped")
        elif item["document_path"] not in eligible_paths:
            item.update(status="no_analysis", reason="budget_exhausted")
        else:
            try:
                manifest = builder.build_manifest(
                    root,
                    item["document_path"],
                    base,
                    head,
                    evidence_report,
                    evidence_by_document.get(item["document_path"], []),
                    schema_version=SHADOW_SCHEMA_VERSION,
                    change_type=change_type,
                )
                manifest_file = Path("manifests") / f"{item['id']}.json"
                atomic_write_json(output_dir / manifest_file, manifest)
                item.update(
                    status="selected",
                    reason="selected",
                    manifest_file=manifest_file.as_posix(),
                    manifest_sha256=manifest["manifest_sha256"],
                )
                matrix.append({"id": item["id"]})
            except ContractError as error:
                item.update(status="blocked", reason=_blocked_reason(error))
        items.append(item)
        if item["status"] != "selected":
            bootstrap_results.append(
                _result(
                    revision,
                    item,
                    status=item["status"],
                    reason=item["reason"],
                )
            )

    preparation = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "kind": "candidate_discovery_preparation",
        "revision": revision,
        "runtime_bootstrapped": bootstrapped,
        "items": items,
    }
    if contains_secret(preparation):
        raise ContractError("unsafe_output")
    atomic_write_json(preparation_path, preparation)
    atomic_write_json(matrix_path, {"include": matrix})
    atomic_write_json(
        bootstrap_report_path,
        _report(revision, bootstrap_results, selected=len(matrix)),
    )
    return preparation


def verify_manifest(
    root: Path,
    manifest_path: Path,
    expected_base: str,
    expected_head: str,
    output: Path,
    prompt_output: Path | None = None,
    expected_id: str | None = None,
) -> dict[str, Any]:
    validator = _load_script("validate-contract.py", "candidate_discovery_validator")
    manifest = validator.validate_manifest_structure(read_json(manifest_path))
    if manifest["schema_version"] != SHADOW_SCHEMA_VERSION:
        raise ContractError("manifest_version_invalid")
    path = manifest["document"]["path"]
    if expected_id is not None and expected_id != _manifest_id(path):
        raise ContractError("manifest_id_unexpected")
    base = resolve_revision(root, expected_base)
    head = resolve_revision(root, expected_head)
    changes = changed_documents(root, base, head)
    eligible: list[dict[str, Any]] = []
    for change in changes:
        if change["change_type"] not in {"A", "M"}:
            continue
        if change["change_type"] == "A" and len(
            git(root, ["show", f"{head}:{change['document_path']}"])
        ) == 0:
            continue
        eligible.append(change)
    selected = {
        item["document_path"]: item["change_type"]
        for item in eligible[:MAX_SHADOW_DOCUMENTS]
    }
    if selected.get(path) != manifest["document"]["change_type"]:
        raise ContractError("manifest_not_selected")
    validator.validate_manifest_repository(
        manifest,
        root,
        checkout_revision="base",
        expected_base=expected_base,
        expected_head=expected_head,
    )
    validator.validate_manifest_evidence_repository(manifest, root)
    atomic_write_json(output, manifest)
    if prompt_output is not None:
        try:
            template = (TOOL_ROOT / "prompts/analyze-v2.md").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ContractError("prompt_unreadable") from error
        if template.count("{{MANIFEST_JSON}}") != 1:
            raise ContractError("prompt_template_invalid")
        prompt = template.replace(
            "{{MANIFEST_JSON}}", canonical_json(manifest).decode("utf-8")
        )
        if contains_secret(prompt):
            raise ContractError("unsafe_input")
        try:
            prompt_output.parent.mkdir(parents=True, exist_ok=True)
            prompt_output.write_text(prompt, encoding="utf-8")
        except OSError as error:
            raise ContractError("output_write_failed") from error
    return manifest


def finalize(
    root: Path,
    manifest_path: Path,
    structured_output: Path | None,
    action_outcome: str,
    expected_base: str,
    expected_head: str,
    prompt_path: Path,
    schema_path: Path,
    model: str,
    runtime: str,
    run_record_output: Path,
    output: Path,
) -> dict[str, Any]:
    manifest = verify_manifest(
        root, manifest_path, expected_base, expected_head, output.parent / ".validated.json"
    )
    try:
        (output.parent / ".validated.json").unlink(missing_ok=True)
    except OSError:
        pass
    try:
        prompt_data = prompt_path.read_bytes()
        schema_data = schema_path.read_bytes()
    except OSError as error:
        raise ContractError("provenance_input_unreadable") from error
    item = {
        "document_path": manifest["document"]["path"],
        "change_type": manifest["document"]["change_type"],
        "previous_path": None,
    }
    validator = _load_script("validate-contract.py", "candidate_discovery_output_validator")
    artifact: dict[str, Any] | None = None
    output_data: bytes | None = None
    candidates: list[dict[str, Any]] = []
    status = "blocked"
    reason = "action_failed"
    run_reason = "execution_failed"

    if action_outcome == "success" and structured_output is not None and structured_output.is_file():
        try:
            output_data = structured_output.read_bytes()
            if contains_secret(output_data.decode("utf-8", errors="replace")):
                raise ContractError("unsafe_output")
            artifact = validator.validate_artifact(json.loads(output_data), manifest)
            if artifact["kind"] != "claim_candidates":
                raise ContractError("artifact_kind_unexpected")
            candidates = artifact["candidates"]
            status = "completed"
            reason = "analysis_completed"
            run_reason = "shadow_completed"
            if candidates and all(
                candidate["classification"] == "unknown" for candidate in candidates
            ):
                status = "unknown"
                if not manifest["evidence"]:
                    reason = "missing_evidence"
        except (ContractError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            contract_error = (
                error if isinstance(error, ContractError) else ContractError("validation_failed")
            )
            reason = _blocked_reason(contract_error)
            run_reason = reason if reason in SHADOW_RUN_REASONS else "validation_failed"
            artifact = None
            candidates = []

    record = build_run_record(
        status=status,
        reason=run_reason,
        manifest=manifest,
        prompt_data=prompt_data,
        schema_data=schema_data,
        model=require_string(model, "shadow_model"),
        runtime=require_string(runtime, "shadow_runtime"),
        output_data=output_data,
        artifact_kind="claim_candidates",
        live=True,
    )
    validator.validate_run_record(record, manifest, artifact)
    atomic_write_json(run_record_output, record)
    result = _result(
        manifest["revision"],
        item,
        status=status,
        reason=reason,
        manifest_sha256=manifest["manifest_sha256"],
        candidates=candidates,
        run_record=record,
    )
    atomic_write_json(output, result)
    return result


def validate_shadow_result(value: Any) -> dict[str, Any]:
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
        "shadow_result",
    )
    if result["schema_version"] != SHADOW_SCHEMA_VERSION or result["kind"] != "candidate_discovery_result":
        raise ContractError("shadow_result_version_invalid")
    revision = exact_keys(result["revision"], {"base", "head"}, "shadow_result_revision")
    require_revision(revision["base"], "shadow_result_base")
    require_revision(revision["head"], "shadow_result_head")
    safe_document_path(result["document_path"])
    require_enum(result["change_type"], {"A", "M", "D", "R"}, "shadow_result_change_invalid")
    if result["previous_path"] is not None:
        safe_document_path(result["previous_path"])
    require_enum(result["status"], SHADOW_RESULT_STATUSES, "shadow_result_status_invalid")
    require_enum(result["reason"], SHADOW_RESULT_REASONS, "shadow_result_reason_invalid")
    if result["manifest_sha256"] is not None:
        require_sha256(result["manifest_sha256"], "shadow_result_manifest_sha256")
    if result["run_record_sha256"] is not None:
        require_sha256(result["run_record_sha256"], "shadow_result_run_record_sha256")
    count = require_integer(result["candidate_count"], "shadow_result_candidate_count")
    if not isinstance(result["candidates"], list) or len(result["candidates"]) != count:
        raise ContractError("shadow_result_candidates_invalid")
    if count > MAX_SHADOW_CANDIDATES:
        raise ContractError("shadow_result_candidates_invalid")
    if result["status"] in {"blocked", "no_analysis"} and count:
        raise ContractError("shadow_result_candidates_invalid")
    if result["status"] == "no_analysis" and (
        result["manifest_sha256"] is not None
        or result["run_record_sha256"] is not None
    ):
        raise ContractError("shadow_result_manifest_invalid")
    if result["status"] in {"completed", "unknown"} and result["run_record_sha256"] is None:
        raise ContractError("shadow_result_run_record_missing")
    if contains_secret(result):
        raise ContractError("unsafe_output")
    return result


def _validate_selected_result(
    result: dict[str, Any],
    item: dict[str, Any],
    preparation: dict[str, Any],
) -> None:
    if result["revision"] != preparation["revision"]:
        raise ContractError("shadow_result_revision_mismatch")
    if result["document_path"] != item["document_path"]:
        raise ContractError("shadow_result_document_mismatch")
    if result["change_type"] != item["change_type"] or result["previous_path"] is not None:
        raise ContractError("shadow_result_change_mismatch")
    if result["manifest_sha256"] != item["manifest_sha256"]:
        raise ContractError("shadow_result_manifest_mismatch")


def aggregate(
    root: Path,
    preparation_path: Path,
    results_dir: Path,
    output: Path,
    run_records_output_dir: Path | None = None,
) -> dict[str, Any]:
    preparation = exact_keys(
        read_json(preparation_path),
        {"schema_version", "kind", "revision", "runtime_bootstrapped", "items"},
        "preparation",
    )
    if preparation["schema_version"] != SHADOW_SCHEMA_VERSION or preparation["kind"] != "candidate_discovery_preparation":
        raise ContractError("preparation_version_invalid")
    revision = exact_keys(preparation["revision"], {"base", "head"}, "preparation_revision")
    require_revision(revision["base"], "preparation_base")
    require_revision(revision["head"], "preparation_head")
    if type(preparation["runtime_bootstrapped"]) is not bool or not isinstance(preparation["items"], list):
        raise ContractError("preparation_invalid")
    if sum(
        isinstance(item, dict) and item.get("status") == "selected"
        for item in preparation["items"]
    ) > MAX_SHADOW_DOCUMENTS:
        raise ContractError("preparation_budget_invalid")

    results: list[dict[str, Any]] = []
    selected = 0
    for item in preparation["items"]:
        item = exact_keys(
            item,
            {
                "document_path",
                "change_type",
                "previous_path",
                "id",
                "manifest_file",
                "manifest_sha256",
                "status",
                "reason",
            },
            "preparation_item",
        )
        safe_document_path(item["document_path"])
        require_string(item["id"], "preparation_item_id")
        if item["id"] != _manifest_id(item["document_path"]):
            raise ContractError("preparation_item_id_invalid")
        if item["status"] != "selected":
            result = _result(
                revision,
                item,
                status=item["status"],
                reason=item["reason"],
            )
            results.append(result)
            continue

        selected += 1
        failure_reason = "action_failed"
        try:
            manifest_file = require_string(item["manifest_file"], "preparation_manifest_file")
            if Path(manifest_file).is_absolute() or ".." in Path(manifest_file).parts:
                raise ContractError("preparation_manifest_file_invalid")
            manifest_path = preparation_path.parent / manifest_file
            try:
                manifest = verify_manifest(
                    root,
                    manifest_path,
                    revision["base"],
                    revision["head"],
                    output.parent / ".validated.json",
                )
            except ContractError as error:
                failure_reason = _blocked_reason(error)
                raise
            result_path = results_dir / f"{item['id']}.json"
            result = validate_shadow_result(read_json(result_path))
            _validate_selected_result(result, item, preparation)
            if result["status"] not in {"completed", "unknown", "blocked"}:
                raise ContractError("shadow_result_status_invalid")
            artifact: dict[str, Any] | None = None
            if result["status"] in {"completed", "unknown"}:
                artifact = {
                    "schema_version": SHADOW_SCHEMA_VERSION,
                    "kind": "claim_candidates",
                    "manifest_sha256": manifest["manifest_sha256"],
                    "document_path": manifest["document"]["path"],
                    "revision": manifest["revision"],
                    "candidates": result["candidates"],
                }
            run_record_path = results_dir / f"{item['id']}.run.json"
            run_record = read_json(run_record_path)
            if result["run_record_sha256"] != sha256_bytes(canonical_json(run_record)):
                raise ContractError("shadow_result_run_record_mismatch")
            validator = _load_script(
                "validate-contract.py", "candidate_discovery_aggregate_validator"
            )
            if artifact is not None:
                validator.validate_artifact(artifact, manifest)
            validator.validate_run_record(run_record, manifest, artifact)
            if run_records_output_dir is not None:
                atomic_write_json(
                    run_records_output_dir / f"{item['id']}.json", run_record
                )
        except (ContractError, OSError, TypeError, ValueError):
            result = _result(
                revision,
                item,
                status="blocked",
                reason=failure_reason,
                manifest_sha256=item["manifest_sha256"],
            )
        finally:
            try:
                (output.parent / ".validated.json").unlink(missing_ok=True)
            except OSError:
                pass
        results.append(result)

    report = _report(revision, results, selected)
    atomic_write_json(output, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--root", default=".")
    prepare_parser.add_argument("--base", required=True)
    prepare_parser.add_argument("--head", required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--preparation", type=Path, required=True)
    prepare_parser.add_argument("--matrix", type=Path, required=True)
    prepare_parser.add_argument("--bootstrap-report", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify-manifest")
    verify_parser.add_argument("--root", default=".")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--expected-base", required=True)
    verify_parser.add_argument("--expected-head", required=True)
    verify_parser.add_argument("--expected-id", required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--prompt-output", type=Path)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--root", default=".")
    finalize_parser.add_argument("--manifest", type=Path, required=True)
    finalize_parser.add_argument("--structured-output", type=Path)
    finalize_parser.add_argument("--action-outcome", required=True)
    finalize_parser.add_argument("--expected-base", required=True)
    finalize_parser.add_argument("--expected-head", required=True)
    finalize_parser.add_argument("--prompt", type=Path, required=True)
    finalize_parser.add_argument("--schema", type=Path, required=True)
    finalize_parser.add_argument("--model", required=True)
    finalize_parser.add_argument("--runtime", required=True)
    finalize_parser.add_argument("--run-record", type=Path, required=True)
    finalize_parser.add_argument("--output", type=Path, required=True)

    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--root", default=".")
    aggregate_parser.add_argument("--preparation", type=Path, required=True)
    aggregate_parser.add_argument("--results-dir", type=Path, required=True)
    aggregate_parser.add_argument("--run-records-output-dir", type=Path)
    aggregate_parser.add_argument("--output", type=Path, required=True)

    arguments = parser.parse_args(argv)
    try:
        root = Path(arguments.root).resolve()
        if arguments.command == "prepare":
            prepare(
                root,
                arguments.base,
                arguments.head,
                arguments.output_dir,
                arguments.preparation,
                arguments.matrix,
                arguments.bootstrap_report,
            )
        elif arguments.command == "verify-manifest":
            verify_manifest(
                root,
                arguments.manifest,
                arguments.expected_base,
                arguments.expected_head,
                arguments.output,
                arguments.prompt_output,
                arguments.expected_id,
            )
        elif arguments.command == "finalize":
            finalize(
                root,
                arguments.manifest,
                arguments.structured_output,
                arguments.action_outcome,
                arguments.expected_base,
                arguments.expected_head,
                arguments.prompt,
                arguments.schema,
                arguments.model,
                arguments.runtime,
                arguments.run_record,
                arguments.output,
            )
        elif arguments.command == "aggregate":
            aggregate(
                root,
                arguments.preparation,
                arguments.results_dir,
                arguments.output,
                arguments.run_records_output_dir,
            )
    except ContractError as error:
        print(f"candidate-discovery: blocked: {error}", file=sys.stderr)
        return 2
    print("candidate-discovery: complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
