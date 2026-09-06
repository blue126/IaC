#!/usr/bin/env python3
"""Exercise the Kit's actual apt hook without installing host packages."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MOCK_APT = r'''
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["MOCK_APT_ROOT"])
action = "update" if "update" in sys.argv else "install"
assert "Acquire::Retries=3" in sys.argv
if action == "update":
    assert "APT::Update::Error-Mode=any" in sys.argv
else:
    assert "DPkg::Lock::Timeout=60" in sys.argv
    assert os.environ["DEBIAN_FRONTEND"] == "noninteractive"
    assert "python3-venv" in sys.argv
counter = root / action
count = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(count))
mode = os.environ["MOCK_APT_MODE"]
if mode == "transient" and count == 1 or mode == action:
    print("Simulated apt failure", file=sys.stderr)
    sys.exit(100)
'''


def main():
    kit = json.loads(subprocess.check_output(
        ["sbx", "kit", "inspect", str(ROOT / ".sandbox-kit"), "--json"], text=True
    ))
    hook = kit["setup"]["install"][0]["command"]
    assert "retry_apt" in hook
    temp_root = Path(tempfile.mkdtemp(prefix="iac-apt-retry-", dir=os.environ["TMPDIR"]))
    print(f"Test artifacts retained: {temp_root}")
    for mode, expected_rc, update_count, install_count in [
        ("success", 0, 1, 1),
        ("transient", 0, 2, 2),
        ("update", 1, 6, 0),
        ("install", 1, 1, 6),
    ]:
        case_dir = temp_root / mode
        case_dir.mkdir()
        apt = case_dir / "apt-get"
        apt.write_text(f"#!{sys.executable}\n" + MOCK_APT)
        apt.chmod(0o700)
        sleep = case_dir / "sleep"
        sleep.write_text('#!/bin/sh\n[ "$1" = 5 ]\n')
        sleep.chmod(0o700)
        env = dict(os.environ, MOCK_APT_ROOT=str(case_dir), MOCK_APT_MODE=mode)
        env["PATH"] = f"{case_dir}:{env['PATH']}"
        result = subprocess.run(["/bin/sh", "-c", hook], env=env, text=True, capture_output=True, timeout=20)
        assert result.returncode == expected_rc, (mode, result.stdout, result.stderr)
        for action, expected in [("update", update_count), ("install", install_count)]:
            counter = case_dir / action
            actual = int(counter.read_text()) if counter.exists() else 0
            assert actual == expected, (mode, action, actual, expected)
        if expected_rc:
            assert "APT failed after 6 attempts" in result.stderr, result.stderr
        print(f"PASS: {mode}")
    print("PASS: apt retries recover from transient errors and fail after six attempts")


if __name__ == "__main__":
    main()
