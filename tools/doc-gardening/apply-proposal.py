#!/usr/bin/env python3
"""Apply one revalidated proposal in a disposable detached worktree."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from contract import ContractError, atomic_write_json, canonical_json, payload_hash, read_json, sha256_bytes


TOOL_ROOT = Path(__file__).resolve().parent


def _load_validator() -> Any:
    path = TOOL_ROOT / "validate-contract.py"
    spec = importlib.util.spec_from_file_location("apply_proposal_validator", path)
    if spec is None or spec.loader is None:
        raise ContractError("validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_phase_one(root: Path) -> Any:
    path = root / "tools/check-doc-claims.py"
    spec = importlib.util.spec_from_file_location("apply_proposal_claims", path)
    if spec is None or spec.loader is None:
        raise ContractError("phase_one_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(root: Path, arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ContractError("git_execution_failed") from error
    if result.returncode:
        raise ContractError("git_command_failed")
    return result.stdout


def _proposal_binding(candidate_artifact: dict[str, Any], proposal: dict[str, Any]) -> None:
    candidates = candidate_artifact["candidates"]
    if len(candidates) != 1:
        raise ContractError("apply_candidate_count_invalid")
    candidate = candidates[0]
    if (
        proposal["candidate_id"] != candidate["id"]
        or proposal["hunk_id"] != candidate["hunk_id"]
        or proposal["source"] != candidate["source"]
        or proposal["evidence_refs"] != candidate["evidence_refs"]
    ):
        raise ContractError("apply_proposal_binding_invalid")


def _claim_statuses(root: Path) -> dict[str, str]:
    phase_one = _load_phase_one(root)
    report = phase_one.build_report(root)
    return {item["id"]: item["status"] for item in report["claims"]}


def _validate_claim_transition(root: Path, claim_id: str) -> None:
    statuses = _claim_statuses(root)
    if statuses.get(claim_id) != "verified":
        raise ContractError("apply_target_not_verified")
    if any(status != "verified" for status in statuses.values()):
        raise ContractError("apply_claim_regression")


def _run_validation(root: Path) -> None:
    try:
        result = subprocess.run(
            [str(root / "scripts/ci/validate-documentation.sh"), "true"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ContractError("apply_validation_unavailable") from error
    if result.returncode:
        raise ContractError("apply_validation_failed")


def apply(
    root: Path,
    manifest_data: Any,
    candidate_data: Any,
    proposal_data: Any,
    expected_base: str,
    expected_head: str,
    validation_runner: Callable[[Path], None] = _run_validation,
) -> dict[str, Any]:
    validator = _load_validator()
    manifest = validator.validate_manifest_structure(manifest_data)
    if manifest["schema_version"] != 1:
        raise ContractError("apply_manifest_version_invalid")
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
        raise ContractError("apply_artifact_kind_invalid")
    _proposal_binding(candidates, proposal)
    claim_id = proposal["evidence_refs"][0]

    temporary = Path(tempfile.mkdtemp(prefix="oink-apply-"))
    worktree = temporary / "checkout"
    created_worktree = False
    try:
        _run(root, ["worktree", "add", "--detach", str(worktree), expected_head])
        created_worktree = True
        validator.validate_manifest_repository(
            manifest,
            worktree,
            checkout_revision="head",
            expected_base=expected_base,
            expected_head=expected_head,
        )
        document_path = worktree / manifest["document"]["path"]
        original = document_path.read_text(encoding="utf-8")
        source_quote = proposal["source"]["quote"]
        find = proposal["edit"]["find"]
        replace = proposal["edit"]["replace"]
        if original.count(find) != 1 or source_quote.count(find) != 1:
            raise ContractError("apply_find_not_unique")
        updated = original.replace(find, replace, 1)
        document_path.write_text(updated, encoding="utf-8")
        changed = _run(worktree, ["diff", "--name-only"]).splitlines()
        if changed != [manifest["document"]["path"]]:
            raise ContractError("apply_scope_invalid")
        _run(worktree, ["diff", "--check"])
        _validate_claim_transition(worktree, claim_id)
        validation_runner(worktree)
        patch = _run(worktree, ["diff", "--no-ext-diff", "--", manifest["document"]["path"]])
        receipt = {
            "schema_version": 1,
            "kind": "apply_receipt",
            "revision": manifest["revision"],
            "document_path": manifest["document"]["path"],
            "claim_id": claim_id,
            "candidate_id": proposal["candidate_id"],
            "manifest_sha256": manifest["manifest_sha256"],
            "proposal_sha256": sha256_bytes(canonical_json(proposal)),
            "pre_sha256": sha256_bytes(original.encode("utf-8")),
            "post_sha256": sha256_bytes(updated.encode("utf-8")),
            "patch_sha256": sha256_bytes(patch.encode("utf-8")),
        }
        receipt["receipt_sha256"] = payload_hash(receipt, "receipt_sha256")
        return receipt
    finally:
        if created_worktree:
            try:
                _run(root, ["worktree", "remove", "--force", str(worktree)])
            except ContractError:
                pass
        shutil.rmtree(temporary, ignore_errors=True)


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
        receipt = apply(
            Path(arguments.root).resolve(),
            read_json(arguments.manifest),
            read_json(arguments.candidate),
            read_json(arguments.proposal),
            arguments.expected_base,
            arguments.expected_head,
        )
        atomic_write_json(arguments.output, receipt)
    except ContractError as error:
        print(f"apply-proposal: blocked: {error}", file=sys.stderr)
        return 2
    print("apply-proposal: validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
