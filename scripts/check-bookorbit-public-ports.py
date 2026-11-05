#!/usr/bin/env python3
"""Probe BookOrbit public ports from a direct host, outside the Sandbox proxy."""

import argparse
from datetime import datetime, timezone
import errno
import ipaddress
import json
import os
import socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, type=ipaddress.ip_address)
    args = parser.parse_args()
    if os.environ.get("SANDBOX_ID"):
        parser.error("Run on the direct host: Sandbox TCP proxies can accept a connection before reaching its destination")
    host = str(args.host)
    report = {"host": host, "probe_origin": "direct-host", "checked_at": datetime.now(timezone.utc).isoformat(),
              "control_port": 443, "control_reachable": False, "ports": []}
    try:
        with socket.create_connection((host, 443), timeout=5):
            report["control_reachable"] = True
    except OSError as error:
        report["error"] = "HTTPS control connection failed: " + type(error).__name__
        print(json.dumps(report, indent=2))
        return 2
    for port in (3000, 5432):
        try:
            with socket.create_connection((host, port), timeout=5):
                report["ports"].append({"port": port, "reachable": True})
        except OSError as error:
            if isinstance(error, (TimeoutError, socket.timeout)) or error.errno in (errno.ETIMEDOUT, errno.ECONNREFUSED):
                report["ports"].append({"port": port, "reachable": False, "reason": type(error).__name__})
            else:
                report["ports"].append({"port": port, "reachable": None, "status": "indeterminate",
                                        "reason": type(error).__name__, "errno": error.errno})
    report["success"] = all(item["reachable"] is False for item in report["ports"])
    print(json.dumps(report, indent=2))
    if any(item["reachable"] is None for item in report["ports"]):
        return 2
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
