#!/usr/bin/env python3
"""Validate that a PNetLab bundle exactly matches its SHA-256 manifest."""

from __future__ import annotations

import hashlib
import pathlib
import sys


def parse_manifest(path: pathlib.Path) -> dict[pathlib.PurePosixPath, str]:
    entries: dict[pathlib.PurePosixPath, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        try:
            digest, relative_path = line.split("  ", 1)
        except ValueError as error:
            raise ValueError(f"invalid manifest line {line_number}") from error
        path_key = pathlib.PurePosixPath(relative_path)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError(f"invalid SHA-256 on manifest line {line_number}")
        if path_key.is_absolute() or ".." in path_key.parts or path_key in entries:
            raise ValueError(f"unsafe or duplicate path on manifest line {line_number}")
        entries[path_key] = digest
    if not entries:
        raise ValueError("manifest has no entries")
    return entries


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {pathlib.Path(sys.argv[0]).name} MANIFEST BUNDLE", file=sys.stderr)
        return 2

    manifest = pathlib.Path(sys.argv[1]).resolve()
    bundle = pathlib.Path(sys.argv[2]).resolve()
    expected = parse_manifest(manifest)
    actual = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.resolve() != manifest
    }

    expected_paths = {path.as_posix() for path in expected}
    missing = sorted(expected_paths - actual)
    unexpected = sorted(actual - expected_paths)
    if missing or unexpected:
        if missing:
            print(f"missing bundle files: {', '.join(missing)}", file=sys.stderr)
        if unexpected:
            print(f"unexpected bundle files: {', '.join(unexpected)}", file=sys.stderr)
        return 1

    for relative_path, expected_digest in expected.items():
        actual_digest = sha256(bundle / relative_path)
        if actual_digest != expected_digest:
            print(f"checksum mismatch: {relative_path}", file=sys.stderr)
            return 1

    print(f"verified {len(expected)} PNetLab bundle files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
