#!/usr/bin/env python3
"""Check a closed set of documentation claims against Ansible defaults."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = 1
UNKNOWN_REVISION = "UNKNOWN"


@dataclass(frozen=True)
class Claim:
    claim_id: str
    document_path: str
    locator: str
    oracle_path: str
    oracle_key: str
    registry_value: Any
    document_reader: Callable[[str, str], tuple[bool, Any, str | None]]


def _strip_yaml_comment(value: str) -> str:
    single_quoted = False
    double_quoted = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and double_quoted:
            escaped = True
            continue
        if character == "'" and not double_quoted:
            single_quoted = not single_quoted
            continue
        if character == '"' and not single_quoted:
            double_quoted = not double_quoted
            continue
        if character == "#" and not single_quoted and not double_quoted:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value.rstrip()


def _parse_scalar(raw_value: str) -> tuple[bool, Any]:
    value = _strip_yaml_comment(raw_value.strip())
    if not value or value[0] in "[{>|&*!":
        return False, None

    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False, None
        return (True, parsed) if isinstance(parsed, str) else (False, None)

    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            return False, None
        return True, value[1:-1].replace("''", "'")

    lowered = value.lower()
    if lowered in {"true", "false"}:
        return True, lowered == "true"
    if lowered in {"null", "~"}:
        return True, None
    if lowered in {"y", "yes", "n", "no", "on", "off", ".nan", ".inf", "+.inf", "-.inf"}:
        return False, None
    if re.fullmatch(r"[+-]?0(?:b[01_]+|o[0-7_]+|x[0-9a-f_]+)", lowered):
        return False, None
    if re.fullmatch(r"[+-]?0\d+", value):
        return False, None
    if re.fullmatch(r"[+-]?(?:\d[\d_]*)(?:\.\d[\d_]*)?[eE][+-]?\d[\d_]*", value):
        return False, None
    if re.fullmatch(r"[+-]?\d[\d_]*_\d[\d_]*", value):
        return False, None
    if re.fullmatch(r"[+-]?\d+", value):
        try:
            return True, int(value)
        except (ValueError, OverflowError):
            return False, None
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?", value):
        try:
            parsed_float = float(value)
        except (ValueError, OverflowError):
            return False, None
        return (True, parsed_float) if math.isfinite(parsed_float) else (False, None)
    if any(character in value for character in "{}[]") or re.search(r":\s", value):
        return False, None
    return True, value


def _yaml_key_values(text: str, key: str) -> list[tuple[bool, Any]]:
    values: list[tuple[bool, Any]] = []
    key_pattern = re.compile(rf"^{re.escape(key)}:(?:\s*(.*))?$")
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = key_pattern.match(line)
        if match:
            values.append(_parse_scalar(match.group(1) or ""))
    return values


def _fence_opener(line: str) -> tuple[str, int, str] | None:
    match = re.fullmatch(r" {0,3}(`{3,}|~{3,})([^\r\n]*)", line)
    if not match:
        return None
    marker = match.group(1)
    info = match.group(2).strip()
    if marker[0] == "`" and "`" in info:
        return None
    return marker[0], len(marker), info


def _is_fence_closer(line: str, marker: str, opener_length: int) -> bool:
    match = re.fullmatch(r" {0,3}(`{3,}|~{3,})[ \t]*", line)
    return bool(
        match
        and match.group(1)[0] == marker
        and len(match.group(1)) >= opener_length
    )


def _lines_outside_fences(text: str) -> list[str]:
    lines: list[str] = []
    active_fence: tuple[str, int] | None = None
    for line in text.splitlines():
        if active_fence is not None:
            if _is_fence_closer(line, *active_fence):
                active_fence = None
            continue
        opener = _fence_opener(line)
        if opener is not None:
            active_fence = opener[0], opener[1]
            continue
        lines.append(line)
    return lines


def _section_bodies(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    active_fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        if active_fence is not None:
            if _is_fence_closer(line, *active_fence):
                active_fence = None
            continue
        opener = _fence_opener(line)
        if opener is not None:
            active_fence = opener[0], opener[1]
            continue
        match = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2).replace("`", "")))

    bodies: list[str] = []
    for heading_index, (line_index, level, title) in enumerate(headings):
        if title != heading:
            continue
        end = len(lines)
        for next_line, next_level, _ in headings[heading_index + 1 :]:
            if next_level <= level:
                end = next_line
                break
        bodies.append("\n".join(lines[line_index + 1 : end]))
    return bodies


def _split_table_row(line: str) -> list[str] | None:
    if "|" not in line:
        return None
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line.strip():
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
            current.append(character)
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip())
    if cells and not cells[0]:
        cells.pop(0)
    if cells and not cells[-1]:
        cells.pop()
    return cells


def _table_value(text: str, locator: str) -> tuple[bool, Any, str | None]:
    heading, key = locator.split("::", 1)
    sections = _section_bodies(text, heading)
    if not sections:
        return False, None, "locator_missing"
    if len(sections) != 1:
        return False, None, "locator_multiple"

    raw_values: list[str] = []
    lines = _lines_outside_fences(sections[0])
    line_index = 0
    while line_index + 1 < len(lines):
        header = _split_table_row(lines[line_index])
        delimiter = _split_table_row(lines[line_index + 1])
        if not header or not delimiter or len(header) != len(delimiter):
            line_index += 1
            continue
        if not all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in delimiter):
            line_index += 1
            continue
        normalized_header = [cell.strip("`").strip().lower() for cell in header]
        if "variable" not in normalized_header or "default" not in normalized_header:
            line_index += 1
            continue
        variable_column = normalized_header.index("variable")
        default_column = normalized_header.index("default")
        line_index += 2
        while line_index < len(lines):
            cells = _split_table_row(lines[line_index])
            if not cells or len(cells) != len(header):
                break
            if cells[variable_column].strip("`").strip() == key:
                raw_values.append(cells[default_column].strip("`").strip())
            line_index += 1
    if not raw_values:
        return False, None, "locator_missing"
    if len(raw_values) != 1:
        return False, None, "locator_multiple"
    parsed, value = _parse_scalar(raw_values[0])
    return (True, value, None) if parsed else (False, None, "locator_non_scalar")


def _fenced_yaml_value(text: str, locator: str) -> tuple[bool, Any, str | None]:
    heading, key = locator.split("::", 1)
    sections = _section_bodies(text, heading)
    if not sections:
        return False, None, "locator_missing"
    if len(sections) != 1:
        return False, None, "locator_multiple"

    blocks: list[str] = []
    active_fence: tuple[str, int] | None = None
    current: list[str] | None = None
    for line in sections[0].splitlines():
        if active_fence is not None:
            if _is_fence_closer(line, *active_fence):
                if current is not None:
                    blocks.append("\n".join(current))
                active_fence = None
                current = None
            elif current is not None:
                current.append(line)
            continue
        opener = _fence_opener(line)
        if opener is not None:
            active_fence = opener[0], opener[1]
            current = [] if opener[2].lower() in {"yaml", "yml"} else None
    if active_fence is not None:
        return False, None, "locator_unparseable"

    values = [item for block in blocks for item in _yaml_key_values(block, key)]
    if not values:
        return False, None, "locator_missing"
    if len(values) != 1:
        return False, None, "locator_multiple"
    parsed, value = values[0]
    return (True, value, None) if parsed else (False, None, "locator_non_scalar")


CLAIMS = (
    Claim(
        "service.netbox.port",
        "docs/deployment/netbox-deployment.md",
        "Configuration Variables::netbox_port",
        "ansible/roles/netbox/defaults/main.yml",
        "netbox_port",
        8080,
        _table_value,
    ),
    Claim(
        "service.netbox.image",
        "docs/deployment/netbox-deployment.md",
        "Configuration Variables::netbox_image",
        "ansible/roles/netbox/defaults/main.yml",
        "netbox_image",
        "netboxcommunity/netbox:v4.1.11",
        _table_value,
    ),
)


def _read_source(root: Path, relative_path: str) -> tuple[str | None, str | None, str | None]:
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = (resolved_root / relative_path).resolve(strict=True)
    except FileNotFoundError:
        return None, None, "source_missing"
    except (OSError, RuntimeError):
        return None, None, "source_unreadable"
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return None, None, "source_outside_root"
    try:
        data = resolved_path.read_bytes()
    except OSError:
        return None, None, "source_unreadable"
    digest = hashlib.sha256(data).hexdigest()
    try:
        return data.decode("utf-8"), digest, None
    except UnicodeDecodeError:
        return None, digest, "source_unreadable"


def _revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_REVISION
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", revision) else UNKNOWN_REVISION


def _report_value(value: Any, registry_value: Any) -> Any:
    if isinstance(value, str) and value != registry_value:
        return {"type": "string", "redacted": True}
    return value


def _result_for_claim(root: Path, claim: Claim) -> dict[str, Any]:
    document_text, document_digest, document_error = _read_source(root, claim.document_path)
    oracle_text, oracle_digest, oracle_error = _read_source(root, claim.oracle_path)
    result: dict[str, Any] = {
        "id": claim.claim_id,
        "status": "indeterminate",
        "reason": None,
        "document": {
            "path": claim.document_path,
            "locator": claim.locator,
            "sha256": document_digest,
            "value": None,
        },
        "oracle": {
            "path": claim.oracle_path,
            "key": claim.oracle_key,
            "sha256": oracle_digest,
            "value": None,
        },
    }
    if document_error:
        result["reason"] = f"document_{document_error}"
        return result
    if oracle_error:
        result["reason"] = f"oracle_{oracle_error}"
        return result

    assert document_text is not None and oracle_text is not None
    document_ok, document_value, locator_error = claim.document_reader(
        document_text, claim.locator
    )
    if not document_ok:
        result["reason"] = locator_error
        return result

    oracle_values = _yaml_key_values(oracle_text, claim.oracle_key)
    if not oracle_values:
        result["reason"] = "oracle_key_missing"
        return result
    if len(oracle_values) != 1:
        result["reason"] = "oracle_key_duplicate"
        return result
    oracle_ok, oracle_value = oracle_values[0]
    if not oracle_ok:
        result["reason"] = "oracle_non_scalar"
        return result

    result["document"]["value"] = _report_value(document_value, claim.registry_value)
    result["oracle"]["value"] = _report_value(oracle_value, claim.registry_value)
    if type(document_value) is not type(oracle_value):
        result["status"] = "contradiction"
        result["reason"] = "type_mismatch"
    elif document_value != oracle_value:
        result["status"] = "contradiction"
        result["reason"] = "value_mismatch"
    else:
        result["status"] = "verified"
    return result


def build_report(root: Path) -> dict[str, Any]:
    claims = [_result_for_claim(root, claim) for claim in CLAIMS]
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": _revision(root),
        "claims": claims,
    }


def _write_report(output: Path, report: dict[str, Any]) -> bool:
    temporary_path: Path | None = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(report, temporary_file, ensure_ascii=False, indent=2, separators=(",", ": "))
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output)
    except (OSError, TypeError, ValueError):
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", help="JSON report path")
    arguments = parser.parse_args(argv)

    root = Path(arguments.root).resolve()
    output = Path(arguments.output) if arguments.output else root / "tmp/doc-accuracy/report.json"
    report = build_report(root)
    if not _write_report(output, report):
        print("doc-claims: report write failed", file=sys.stderr)
        return 2

    failed = sum(claim["status"] != "verified" for claim in report["claims"])
    print(f"doc-claims: checked={len(report['claims'])} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
