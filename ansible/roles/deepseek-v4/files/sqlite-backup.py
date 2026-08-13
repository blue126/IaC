#!/usr/bin/env python3
"""Create and verify an idempotent SQLite backup from a stopped writer."""

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path


def integrity(path):
    """Require SQLite to report an internally consistent database."""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        return connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def logical_digest(path):
    """Hash a stable logical dump instead of SQLite file-layout bytes."""
    hasher = hashlib.sha256()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        for statement in connection.iterdump():
            hasher.update(statement.encode("utf-8"))
            hasher.update(b"\n")
    return hasher.hexdigest()


def main():
    """Create a verified logical snapshot, replacing only stale backups."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    source = Path(args.source)
    target = Path(args.target)
    if not source.is_file() or source.stat().st_size <= 0:
        parser.error("source database is absent or empty")
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
        with sqlite3.connect(temporary) as target_db:
            source_db.backup(target_db)
    os.chmod(temporary, 0o600)
    if not integrity(temporary) or logical_digest(source) != logical_digest(temporary):
        temporary.unlink(missing_ok=True)
        return 1
    if (
        target.exists()
        and integrity(target)
        and logical_digest(target) == logical_digest(source)
    ):
        temporary.unlink()
        print("existing backup matches")
        return 0
    os.replace(temporary, target)
    print(f"backup created: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
