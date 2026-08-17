#!/usr/bin/env python3
"""Write a prompt-free allowlist of Docker Compose runtime log lines."""

import argparse
import json
import re
import subprocess
from pathlib import Path


SAFE_PROJECT = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")
SAFE_LINE_MARKERS = (
    "llama_model_loader",
    "llama_context",
    "ggml_cuda",
    "load_tensors",
    "server is listening",
    "prompt cache save took",
    "prompt cache load took",
)
SENSITIVE_MARKERS = (
    "<think>",
    "</think>",
    "<｜User｜>",
    "<｜Assistant｜>",
    "prompt:",
    "cache :",
)


def sanitize(raw):
    """Count known events without retaining any raw log text."""
    counts = {marker: 0 for marker in SAFE_LINE_MARKERS}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        lowered = line.casefold()
        if any(marker.casefold() in lowered for marker in SENSITIVE_MARKERS):
            continue
        for marker in SAFE_LINE_MARKERS:
            if marker.casefold() in lowered:
                counts[marker] += 1
                break
    return [
        f"event={marker} count={count}"
        for marker, count in counts.items()
        if count > 0
    ]


def collect(compose_file, project_name, service, runner=subprocess.run):
    """Collect bytes locally on the managed host without controller transport."""
    if not SAFE_PROJECT.fullmatch(project_name):
        raise ValueError("unsafe Compose project name")
    if service != "candidate":
        raise ValueError("only the fixed candidate service is allowed")
    result = runner(
        [
            "docker",
            "compose",
            "--project-name",
            project_name,
            "--file",
            str(compose_file),
            "logs",
            "--no-color",
            "--timestamps",
            service,
        ],
        capture_output=True,
        check=False,
        timeout=60,
    )
    return result.returncode, sanitize(result.stdout + b"\n" + result.stderr)


def write_exclusive(path, lines):
    """Create one immutable sanitized log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output_file:
        output_file.write("\n".join(lines))
        if lines:
            output_file.write("\n")


def write_status(path, document):
    """Write a content-free collection status document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def self_test():
    """Prove invalid UTF-8 and prompt-bearing cache lines are discarded."""
    raw = (
        b"candidate | llama_model_loader: loaded metadata\n"
        b"candidate | cache : private prompt <think>secret</think>\n"
        b"candidate | prompt cache save took 10.50 ms\n"
        b"candidate | ggml_cuda: device ready\xff\n"
        b"candidate | user text ggml_cuda token=secret-value\n"
    )
    lines = sanitize(raw)
    rendered = "\n".join(lines)
    assert "private prompt" not in rendered
    assert "<think>" not in rendered
    assert "secret-value" not in rendered
    assert "llama_model_loader" in rendered
    assert "prompt cache save took" in rendered
    assert "ggml_cuda" in rendered
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file")
    parser.add_argument("--project-name")
    parser.add_argument("--service", default="candidate")
    parser.add_argument("--output")
    parser.add_argument("--status-output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    for required in ("compose_file", "project_name", "output", "status_output"):
        if not getattr(args, required):
            parser.error(f"--{required.replace('_', '-')} is required")
    compose_file = Path(args.compose_file)
    if not compose_file.is_file():
        parser.error("--compose-file must be a regular file")
    returncode, lines = collect(compose_file, args.project_name, args.service)
    write_exclusive(Path(args.output), lines)
    status = {
        "schema_version": 1,
        "docker_logs_returncode": returncode,
        "line_count": len(lines),
        "status": "pass" if returncode == 0 else "unavailable",
    }
    write_status(Path(args.status_output), status)
    print(json.dumps(status, sort_keys=True))
    raise SystemExit(0 if returncode == 0 else 1)


if __name__ == "__main__":
    main()
