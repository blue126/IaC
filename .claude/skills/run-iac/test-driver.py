#!/usr/bin/env python3
"""Test driver boundaries with a fake sbx; never create a real Sandbox."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


DRIVER = Path(__file__).with_name("driver.sh").resolve()
MOCK_SBX = r'''
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with Path(os.environ["MOCK_SBX_LOG"]).open("a") as handle:
    handle.write(json.dumps(args) + "\n")
command = args[0]
if command not in {"version", "kit", "ls", "create", "exec", "stop"}:
    raise SystemExit(99)
if command == "version":
    print("sbx version: v0.39.0 mock")
mode = os.environ["MOCK_SBX_MODE"]
if command == "create" and mode == "create-failure":
    raise SystemExit(7)
if command == "exec" and mode == "exec-failure":
    raise SystemExit(9)
if command == "stop" and mode == "stop-failure":
    raise SystemExit(8)
'''


def main():
    temp_root = Path(tempfile.mkdtemp(prefix="iac-driver-test-", dir=os.environ["TMPDIR"]))
    print(f"Test artifacts retained: {temp_root}")
    sbx = temp_root / "sbx"
    sbx.write_text(f"#!{sys.executable}\n" + MOCK_SBX)
    sbx.chmod(0o700)
    cases = [
        ("approval-required", 2, False),
        ("nested-sandbox", 1, False),
        ("create-failure", 7, False),
        ("exec-failure", 9, True),
        ("stop-failure", 1, True),
        ("success", 0, True),
    ]
    for mode, expected_rc, should_stop in cases:
        log = temp_root / f"{mode}.jsonl"
        env = dict(os.environ, MOCK_SBX_LOG=str(log), MOCK_SBX_MODE=mode)
        env.pop("SANDBOX_ID", None)
        env["PATH"] = f"{temp_root}:{env['PATH']}"
        if mode == "nested-sandbox":
            env["SANDBOX_ID"] = "test-sandbox"
        args = ["bash", str(DRIVER)]
        if mode != "approval-required":
            args.append("--allow-sandbox-install")
        result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=15)
        assert result.returncode == expected_rc, (mode, result.stdout, result.stderr)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        stops = [call for call in calls if call[0] == "stop"]
        assert bool(stops) == should_stop, (mode, calls)
        if should_stop:
            create = next(call for call in calls if call[0] == "create")
            name = create[create.index("--name") + 1]
            assert stops == [["stop", name]], (mode, calls)
        if mode in {"approval-required", "nested-sandbox"}:
            assert not calls, calls
        assert all(call[0] != "rm" for call in calls)
        print(f"PASS: {mode}")
    print("PASS: driver requires approval, preserves failures, and only stops its own Sandbox")


if __name__ == "__main__":
    main()
