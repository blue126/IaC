#!/usr/bin/env python3
"""Restore the stable DeepSeek owner if an experiment controller disappears."""

import argparse
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


SAFE_PROJECT = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")
SAFE_UNIT = re.compile(r"^[a-zA-Z0-9_.@-]+\.service$")


def command(argv, runner=subprocess.run):
    """Run one fixed recovery command without a shell."""
    try:
        result = runner(argv, capture_output=True, check=False, timeout=420)
        return {"program": argv[0], "returncode": result.returncode}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "program": argv[0],
            "returncode": None,
            "error_type": type(error).__name__,
        }


def write_exclusive(path, document):
    """Create content-free immutable watchdog evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def recover(compose_file, project_name, service_unit, proxy_unit, runner=subprocess.run):
    """Tear down only the named candidate project and start stable owners."""
    commands = [
        command([
            "docker", "compose", "--project-name", project_name,
            "--file", str(compose_file), "down", "--remove-orphans",
            "--timeout", "300",
        ], runner),
        command(["systemctl", "start", service_unit], runner),
        command(["systemctl", "start", proxy_unit], runner),
    ]
    return commands


def recovery_health(service_unit, proxy_unit, health_url, runner=subprocess.run):
    """Check both stable units and the public API without retaining content."""
    units = []
    for unit in (service_unit, proxy_unit):
        try:
            result = runner(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            units.append(result.returncode == 0 and result.stdout.strip() == "active")
        except (OSError, subprocess.TimeoutExpired):
            units.append(False)
    try:
        with urllib.request.urlopen(health_url, timeout=10) as response:
            api_ok = response.status == 200
    except (OSError, urllib.error.URLError):
        api_ok = False
    return all(units) and api_ok, {"units_active": units, "api_healthy": api_ok}


def verify_recovery(
    service_unit,
    proxy_unit,
    health_url,
    timeout_seconds=1200,
    runner=subprocess.run,
):
    """Retry stable starts until both owners and the public API are healthy."""
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    last_checks = {"units_active": [False, False], "api_healthy": False}
    while time.monotonic() < deadline:
        attempts += 1
        command(["systemctl", "start", service_unit], runner)
        command(["systemctl", "start", proxy_unit], runner)
        healthy, last_checks = recovery_health(
            service_unit, proxy_unit, health_url, runner
        )
        if healthy:
            return True, attempts, last_checks
        time.sleep(10)
    return False, attempts, last_checks


def self_test():
    """Prove recovery targets only the fixed project and stable units."""
    observed = []

    class Result:
        returncode = 0
        stdout = "active\n"

    def fake_runner(argv, **kwargs):
        observed.append((argv, kwargs))
        return Result()

    commands = recover(
        Path("/evidence/docker-compose.yml"),
        "deepseek-v4-ik-exp-safe-id",
        "deepseek-v4-ik.service",
        "deepseek-v4-ik-compat.service",
        fake_runner,
    )
    assert [item["returncode"] for item in commands] == [0, 0, 0]
    assert observed[0][0][-4:] == ["down", "--remove-orphans", "--timeout", "300"]
    assert observed[1][0] == ["systemctl", "start", "deepseek-v4-ik.service"]
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file")
    parser.add_argument("--project-name")
    parser.add_argument("--service-unit")
    parser.add_argument("--proxy-unit")
    parser.add_argument("--disarm-file")
    parser.add_argument("--status-output")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--heartbeat-file")
    parser.add_argument("--heartbeat-stale-seconds", type=int)
    parser.add_argument("--abort-file")
    parser.add_argument("--health-url")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    required = (
        "compose_file", "project_name", "service_unit", "proxy_unit",
        "disarm_file", "status_output", "timeout_seconds",
        "heartbeat_file", "heartbeat_stale_seconds", "abort_file", "health_url",
    )
    if any(getattr(args, field) in (None, "") for field in required):
        parser.error("all watchdog arguments are required")
    compose_file = Path(args.compose_file)
    if not compose_file.is_absolute() or not compose_file.is_file():
        parser.error("--compose-file must be an existing absolute path")
    if not SAFE_PROJECT.fullmatch(args.project_name):
        parser.error("unsafe Compose project name")
    if not SAFE_UNIT.fullmatch(args.service_unit) or not SAFE_UNIT.fullmatch(
        args.proxy_unit
    ):
        parser.error("unsafe systemd unit name")
    if args.timeout_seconds < 300 or args.timeout_seconds > 28800:
        parser.error("watchdog timeout must be between 300 and 28800 seconds")
    if args.heartbeat_stale_seconds < 60 or args.heartbeat_stale_seconds > 3600:
        parser.error("heartbeat staleness must be between 60 and 3600 seconds")
    if args.health_url != "http://127.0.0.1:8081/health":
        parser.error("watchdog health URL must be the fixed local stable endpoint")

    disarm_file = Path(args.disarm_file)
    heartbeat_file = Path(args.heartbeat_file)
    abort_file = Path(args.abort_file)
    deadline = time.monotonic() + args.timeout_seconds
    trigger = None
    while time.monotonic() < deadline:
        if disarm_file.exists():
            report = {"schema_version": 1, "status": "disarmed", "commands": []}
            write_exclusive(Path(args.status_output), report)
            print(json.dumps(report, sort_keys=True))
            return
        if abort_file.exists():
            trigger = "resource-abort"
            break
        try:
            heartbeat_age = time.time() - heartbeat_file.stat().st_mtime
        except OSError:
            heartbeat_age = args.heartbeat_stale_seconds + 1
        if heartbeat_age > args.heartbeat_stale_seconds:
            trigger = "heartbeat-expired"
            break
        time.sleep(min(5, max(0, deadline - time.monotonic())))

    if trigger is None:
        trigger = "absolute-timeout"

    commands = recover(
        compose_file,
        args.project_name,
        args.service_unit,
        args.proxy_unit,
    )
    healthy, attempts, checks = verify_recovery(
        args.service_unit,
        args.proxy_unit,
        args.health_url,
    )
    status = "recovered" if healthy else "failed"
    report = {
        "schema_version": 1,
        "status": status,
        "trigger": trigger,
        "commands": commands,
        "verification_attempts": attempts,
        "final_checks": checks,
    }
    write_exclusive(Path(args.status_output), report)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if status == "recovered" else 1)


if __name__ == "__main__":
    main()
