#!/usr/bin/env python3
"""Shared deterministic contract helpers for Phase 2 document gardening."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ALLOWED_DOCUMENT_PREFIXES = ("docs/deployment/", "docs/designs/")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
CLASSIFICATIONS = {"candidate_contradiction", "possibly_stale", "unknown"}
CANDIDATE_REASONS = {
    "evidence_conflict",
    "possibly_outdated",
    "ambiguous_source",
    "missing_evidence",
    "hostile_input",
    "model_refusal",
}
RUN_STATUSES = {"completed", "unknown", "blocked"}
RUN_REASONS = {
    "recorded_replay",
    "live_completed",
    "validation_failed",
    "timeout",
    "refusal",
    "stale_input",
    "unsafe_input",
    "execution_failed",
}
SECRET_PATTERNS = (
    re.compile(r"SECRET_SENTINEL", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
)


class ContractError(ValueError):
    """A safe, non-payload-bearing contract failure."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def payload_hash(value: dict[str, Any], hash_key: str) -> str:
    payload = dict(value)
    payload.pop(hash_key, None)
    return sha256_bytes(canonical_json(payload))


def contains_secret(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in SECRET_PATTERNS)
    if isinstance(value, list):
        return any(contains_secret(item) for item in value)
    if isinstance(value, dict):
        return any(contains_secret(key) or contains_secret(item) for key, item in value.items())
    return False


def safe_document_path(raw_path: str) -> str:
    if not isinstance(raw_path, str) or not raw_path:
        raise ContractError("document_path_invalid")
    path = Path(raw_path)
    normalized = path.as_posix()
    if path.is_absolute() or normalized != raw_path or ".." in path.parts:
        raise ContractError("document_path_invalid")
    if not any(normalized.startswith(prefix) for prefix in ALLOWED_DOCUMENT_PREFIXES):
        raise ContractError("document_path_out_of_scope")
    if path.suffix.lower() != ".md":
        raise ContractError("document_path_out_of_scope")
    return normalized


def exact_keys(value: Any, expected: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError(f"{location}_keys_invalid")
    return value


def require_string(value: Any, location: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ContractError(f"{location}_type_invalid")
    return value


def require_integer(value: Any, location: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ContractError(f"{location}_type_invalid")
    return value


def require_sha256(value: Any, location: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ContractError(f"{location}_invalid")
    return value


def require_revision(value: Any, location: str) -> str:
    if not isinstance(value, str) or REVISION_PATTERN.fullmatch(value) is None:
        raise ContractError(f"{location}_invalid")
    return value


def require_identifier(value: Any, location: str) -> str:
    if not isinstance(value, str) or IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ContractError(f"{location}_invalid")
    return value


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError("json_unreadable") from error


def atomic_write_json(path: Path, value: Any) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(value, temporary_file, ensure_ascii=False, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except (OSError, TypeError, ValueError) as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ContractError("output_write_failed") from error


def git(root: Path, arguments: list[str], *, timeout: int = 10) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ContractError("git_execution_failed") from error
    if result.returncode != 0:
        raise ContractError("git_command_failed")
    return result.stdout


def resolve_revision(root: Path, revision: str) -> str:
    output = git(root, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
    resolved = output.decode("ascii", errors="ignore").strip()
    return require_revision(resolved, "revision")


def git_file(root: Path, revision: str, document_path: str) -> bytes:
    return git(root, ["show", f"{revision}:{document_path}"])
