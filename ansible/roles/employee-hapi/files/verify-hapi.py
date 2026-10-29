#!/usr/bin/python3
"""Verify the pinned HAPI protocol without printing credentials or session data."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def request(origin, path, expected, *, payload=None, jwt=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; EmployeeHapiVerifier/1.0)",
    }
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(origin + path, data=data, headers=headers)
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    if response.status not in expected:
        actual_status = response.status
        response.close()
        raise RuntimeError(
            f"Unexpected HTTP status for {req.get_method()} {path}: "
            f"got {actual_status}, expected {expected}"
        )
    return response


def read_json(origin, path, **kwargs):
    with request(origin, path, [200], **kwargs) as response:
        return json.load(response)


def verify(origin):
    env = dict(
        line.split("=", 1)
        for line in Path("/etc/employee-hapi/hapi.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    access_token = env["CLI_API_TOKEN"]
    for path in ("/api/sessions", "/api/machines", "/api/events"):
        with request(origin, path, [401, 403]):
            pass
        with request(origin, path, [401, 403], jwt="invalid-pilot-jwt"):
            pass
    with request(
        origin, "/api/auth", [401, 403], payload={"accessToken": "invalid-pilot-token"}
    ):
        pass
    jwt = read_json(origin, "/api/auth", payload={"accessToken": access_token})["token"]
    if origin == "https://hapi-test.willfan.me":
        with request(origin, "/api/push/vapid-public-key", [403], jwt=jwt):
            pass
    sessions = read_json(origin, "/api/sessions", jwt=jwt)
    if not isinstance(sessions.get("sessions"), list):
        raise RuntimeError("Missing session list")
    machines = read_json(origin, "/api/machines", jwt=jwt)
    if not machines.get("machines"):
        raise RuntimeError("Runner has not registered with the Hub")
    with request(origin, "/api/events?all=true", [200], jwt=jwt) as response:
        if "text/event-stream" not in response.headers.get("Content-Type", ""):
            raise RuntimeError("Missing SSE content type")
        for _ in range(20):
            line = response.readline(16384)
            if line.startswith(b"data:"):
                event = json.loads(line[5:])
                if event.get("type") != "connection-changed":
                    raise RuntimeError("Missing SSE connection event")
                if event.get("data", {}).get("status") != "connected":
                    raise RuntimeError("SSE is disconnected")
                break
        else:
            raise RuntimeError("Missing SSE event")
    # A fresh JWT exercises the session-list reload used when opening a new tab.
    jwt = read_json(origin, "/api/auth", payload={"accessToken": access_token})["token"]
    if not isinstance(read_json(origin, "/api/sessions", jwt=jwt).get("sessions"), list):
        raise RuntimeError("Session list could not be reloaded")
    print("PASS: invalid/missing tokens denied; valid API, Runner, SSE and session-list reload")


if __name__ == "__main__":
    origin = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3006"
    if origin not in ("http://127.0.0.1:3006", "https://hapi-test.willfan.me"):
        sys.exit("Unsupported pilot origin")
    try:
        verify(origin)
    except RuntimeError as error:
        sys.exit(f"FAIL: {error}")
    except Exception:
        # HTTP exceptions may carry response details; deliberately report no body/token.
        sys.exit("FAIL: HAPI protocol check failed; inspect the service privately")
