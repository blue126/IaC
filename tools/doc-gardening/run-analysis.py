#!/usr/bin/env python3
"""Replay or explicitly run schema-constrained document gardening analysis."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from contract import (
    ContractError,
    atomic_write_json,
    build_run_record,
    canonical_json,
    contains_secret,
    read_json,
)


TOOL_ROOT = Path(__file__).resolve().parent


def _load_validator() -> Any:
    path = TOOL_ROOT / "validate-contract.py"
    spec = importlib.util.spec_from_file_location("doc_gardening_validator", path)
    if spec is None or spec.loader is None:
        raise ContractError("validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prompt(
    mode: str,
    candidate_path: Path | None,
    validator: Any,
    manifest: dict[str, Any],
) -> tuple[bytes, dict[str, Any] | None]:
    version = manifest["schema_version"]
    if version == 2 and mode != "analyze":
        raise ContractError("shadow_proposal_forbidden")
    prompt_path = TOOL_ROOT / "prompts" / f"{mode}-v{version}.md"
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ContractError("prompt_unreadable") from error
    selected: dict[str, Any] | None = None
    if mode == "propose":
        if candidate_path is None:
            raise ContractError("candidate_required")
        candidate = validator.validate_artifact(read_json(candidate_path), manifest)
        if candidate["kind"] != "claim_candidates" or len(candidate["candidates"]) != 1:
            raise ContractError("candidate_selection_ambiguous")
        selected = candidate["candidates"][0]
        if selected["classification"] == "unknown":
            raise ContractError("unknown_candidate_not_editable")
        prompt = prompt.replace(
            "{{CANDIDATE_JSON}}", canonical_json(selected).decode("utf-8")
        )
    elif candidate_path is not None:
        raise ContractError("candidate_not_allowed")
    if version == 2:
        prompt = prompt.replace(
            "{{MANIFEST_JSON}}", canonical_json(manifest).decode("utf-8")
        )
    return prompt.encode("utf-8"), selected


def _validate_proposal_binding(
    artifact: dict[str, Any], selected: dict[str, Any] | None
) -> None:
    if artifact["kind"] != "edit_proposal":
        return
    if selected is None:
        raise ContractError("proposal_candidate_missing")
    expected = {
        "candidate_id": selected["id"],
        "hunk_id": selected["hunk_id"],
        "source": selected["source"],
        "evidence_refs": selected["evidence_refs"],
    }
    if any(artifact[key] != value for key, value in expected.items()):
        raise ContractError("proposal_candidate_binding_mismatch")


def _record(
    *,
    status: str,
    reason: str,
    manifest: dict[str, Any],
    prompt_data: bytes,
    schema_data: bytes,
    model: str,
    runtime: str,
    output_data: bytes | None,
    artifact_kind: str,
    live: bool,
) -> dict[str, Any]:
    return build_run_record(
        status=status,
        reason=reason,
        manifest=manifest,
        prompt_data=prompt_data,
        schema_data=schema_data,
        model=model,
        runtime=runtime,
        output_data=output_data,
        artifact_kind=(
            "claim_candidates" if manifest["schema_version"] == 2 else artifact_kind
        ),
        live=live,
    )


def _codex_version() -> str:
    try:
        result = subprocess.run(
            ["codex", "--version"], check=False, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ContractError("codex_unavailable") from error
    version = result.stdout.strip()
    if result.returncode != 0 or not version:
        raise ContractError("codex_unavailable")
    return version


def _live_output(
    manifest: dict[str, Any],
    prompt_data: bytes,
    schema_path: Path,
    model: str,
    timeout: int,
) -> tuple[bytes, str]:
    version = _codex_version()
    with tempfile.TemporaryDirectory(prefix="doc-gardening-") as temporary_directory:
        root = Path(temporary_directory)
        manifest_path = root / "manifest.json"
        prompt_path = root / "prompt.md"
        copied_schema = root / "schema.json"
        output_path = root / "output.json"
        atomic_write_json(manifest_path, manifest)
        prompt_path.write_bytes(prompt_data)
        shutil.copyfile(schema_path, copied_schema)
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--cd",
            str(root),
            "--output-schema",
            str(copied_schema),
            "--output-last-message",
            str(output_path),
            "--model",
            model,
            "-",
        ]
        try:
            result = subprocess.run(
                command,
                input=prompt_data,
                check=False,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise ContractError("live_timeout") from error
        except OSError as error:
            raise ContractError("codex_unavailable") from error
        if result.returncode != 0 or not output_path.is_file():
            raise ContractError("live_execution_failed")
        try:
            output_data = output_path.read_bytes()
        except OSError as error:
            raise ContractError("live_output_unreadable") from error
        if set(path.name for path in root.iterdir()) != {
            "manifest.json",
            "prompt.md",
            "schema.json",
            "output.json",
        }:
            raise ContractError("live_workspace_boundary_failed")
        return output_data, version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mode", choices=("analyze", "propose"), default="analyze")
    parser.add_argument("--candidate-artifact", type=Path)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--recorded-output", type=Path)
    source.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output-artifact", type=Path, required=True)
    parser.add_argument("--run-record", type=Path, required=True)
    arguments = parser.parse_args(argv)
    artifact_kind = "claim_candidates" if arguments.mode == "analyze" else "edit_proposal"
    schema_path: Path | None = None
    prompt_data = b""
    schema_data = b""
    manifest: dict[str, Any] | None = None
    output_data: bytes | None = None
    selected_candidate: dict[str, Any] | None = None
    model = "recorded"
    runtime = "offline"
    reason = "validation_failed"
    try:
        validator = _load_validator()
        manifest = validator.validate_manifest_structure(read_json(arguments.manifest))
        if manifest["schema_version"] == 2 and arguments.live:
            raise ContractError("shadow_live_runner_forbidden")
        schema_path = (
            TOOL_ROOT
            / "schemas"
            / f"{artifact_kind.replace('_', '-')}-v{manifest['schema_version']}.json"
        )
        prompt_data, selected_candidate = _prompt(
            arguments.mode, arguments.candidate_artifact, validator, manifest
        )
        schema_data = schema_path.read_bytes()
        validator.validate_manifest_repository(manifest, Path(arguments.root).resolve())
        if arguments.live:
            if not arguments.confirm_live:
                raise ContractError("live_confirmation_required")
            # Claim the live provenance before the call so a failure inside it
            # is not recorded as a recorded/offline replay.
            model = arguments.model
            runtime = "live"
            output_data, runtime = _live_output(
                manifest, prompt_data, schema_path, arguments.model, arguments.timeout
            )
            reason = "live_completed"
        else:
            output_data = arguments.recorded_output.read_bytes()
            reason = "recorded_replay"
        if contains_secret(output_data.decode("utf-8", errors="replace")):
            raise ContractError("unsafe_output")
        artifact = validator.validate_artifact(json.loads(output_data), manifest)
        # The generic validator accepts either kind; the mode does not. Without
        # this, propose mode writes a claim_candidates artifact and records it
        # as an edit_proposal.
        if artifact["kind"] != artifact_kind:
            raise ContractError("artifact_kind_unexpected")
        _validate_proposal_binding(artifact, selected_candidate)
        atomic_write_json(arguments.output_artifact, artifact)
        status = "completed"
        # An empty candidate list is a clean "nothing found"; only candidates
        # the model could not resolve make the run undetermined.
        if artifact["kind"] == "claim_candidates" and artifact["candidates"] and all(
            candidate["classification"] == "unknown"
            for candidate in artifact["candidates"]
        ):
            status = "unknown"
        record = _record(
            status=status,
            reason=reason,
            manifest=manifest,
            prompt_data=prompt_data,
            schema_data=schema_data,
            model=model,
            runtime=runtime,
            output_data=output_data,
            artifact_kind=artifact_kind,
            live=arguments.live,
        )
        atomic_write_json(arguments.run_record, record)
    except (ContractError, OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        if manifest is not None:
            error_code = str(error)
            reason = "validation_failed"
            if error_code == "live_timeout":
                reason = "timeout"
            elif error_code in {"unsafe_input", "unsafe_output"}:
                reason = error_code
            elif error_code in {
                "manifest_revision_stale",
                "manifest_base_stale",
                "manifest_head_stale",
                "manifest_working_file_stale",
                "manifest_working_file_missing",
                "manifest_span_quote_stale",
            }:
                reason = "stale_input"
            elif error_code == "live_execution_failed":
                reason = "execution_failed"
            record = _record(
                status="blocked",
                reason=reason,
                manifest=manifest,
                prompt_data=prompt_data,
                schema_data=schema_data,
                model=model,
                runtime=runtime,
                output_data=output_data,
                artifact_kind=artifact_kind,
                live=arguments.live,
            )
            try:
                atomic_write_json(arguments.run_record, record)
            except ContractError:
                pass
        print(f"doc-gardening: blocked: {error}", file=sys.stderr)
        return 2
    print("doc-gardening: artifact validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
