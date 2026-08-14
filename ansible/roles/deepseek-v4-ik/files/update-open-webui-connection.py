#!/usr/bin/env python3
"""Replace only the legacy Open WebUI local OpenAI endpoint without printing secrets."""

import argparse
import datetime
import json
import shutil
import sqlite3
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--expected-url", required=True)
    parser.add_argument("--target-url", required=True)
    args = parser.parse_args()

    database = Path(args.database)
    if not database.is_file():
        raise SystemExit("Open WebUI database does not exist")
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    connection = sqlite3.connect(database)
    try:
        row = connection.execute("SELECT id, data, updated_at FROM config LIMIT 1").fetchone()
        if row is None:
            raise SystemExit("Open WebUI config row does not exist")
        data = json.loads(row[1])
        openai = data.get("openai")
        if not isinstance(openai, dict):
            raise SystemExit("Open WebUI OpenAI config is missing")
        urls = openai.get("api_base_urls")
        if not isinstance(urls, list) or not urls:
            raise SystemExit("Open WebUI OpenAI URL list is missing")

        if urls[0] == args.target_url:
            if isinstance(row[2], str):
                print(json.dumps({"changed": False, "connection_index": 0}))
                return
            connection.execute(
                "UPDATE config SET updated_at = ? WHERE id = ?",
                (datetime.datetime.now(datetime.timezone.utc).isoformat(), row[0]),
            )
            connection.commit()
            print(json.dumps({"changed": True, "connection_index": 0}))
            return
        if urls[0] != args.expected_url:
            raise SystemExit("Open WebUI local endpoint differs from the approved legacy target")

        backup = backup_dir / f"webui-before-deepseek-v4-ik-{int(time.time())}.db"
        shutil.copy2(database, backup)
        urls[0] = args.target_url
        connection.execute(
            "UPDATE config SET data = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(data, separators=(",", ":")),
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                row[0],
            ),
        )
        connection.commit()
        print(json.dumps({"changed": True, "connection_index": 0, "backup": str(backup)}))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
