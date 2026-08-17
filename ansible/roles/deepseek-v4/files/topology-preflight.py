#!/usr/bin/env python3
"""Collect immutable dual-GPU topology and CUDA P2P evidence."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


P2P_CANDIDATES = (
    "/usr/local/cuda/extras/demo_suite/p2pBandwidthLatencyTest",
    "/usr/local/cuda/samples/bin/x86_64/linux/release/p2pBandwidthLatencyTest",
)
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def nvidia_p2p_enabled(output, gpu_count):
    """Require OK for every off-diagonal nvidia-smi P2P matrix cell."""
    rows = {}
    for raw_line in ANSI_ESCAPE.sub("", output).splitlines():
        fields = raw_line.split()
        if fields and re.fullmatch(r"GPU\d+", fields[0]):
            rows[fields[0]] = fields[1:1 + gpu_count]
    if len(rows) != gpu_count or any(
        len(rows.get(f"GPU{row}", [])) < gpu_count
        for row in range(gpu_count)
    ):
        return False
    return all(
        rows.get(f"GPU{row}", [])[column] == "OK"
        for row in range(gpu_count)
        for column in range(gpu_count)
        if row != column
    )


def cuda_p2p_enabled(output, gpu_count):
    """Require enabled peer access in the CUDA sample connectivity matrix."""
    lines = ANSI_ESCAPE.sub("", output).splitlines()
    try:
        marker_index = next(
            index
            for index, line in enumerate(lines)
            if "P2P Connectivity Matrix" in line
        )
    except StopIteration:
        return False
    rows = {}
    for raw_line in lines[marker_index + 1:]:
        fields = raw_line.split()
        if fields and fields[0].isdigit() and len(fields) >= gpu_count + 1:
            row = int(fields[0])
            if 0 <= row < gpu_count:
                rows[row] = fields[1:1 + gpu_count]
        if len(rows) == gpu_count:
            break
    if len(rows) != gpu_count or any(
        len(rows.get(row, [])) < gpu_count
        for row in range(gpu_count)
    ):
        return False
    return all(
        rows[row][column] == "1"
        for row in range(gpu_count)
        for column in range(gpu_count)
        if row != column
    )


def command(argv):
    """Run one fixed read-only command."""
    if not shutil.which(argv[0]):
        return {
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr": "command unavailable",
        }
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {
            "available": True,
            "returncode": None,
            "stdout": "",
            "stderr": "command timed out",
        }
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def find_p2p_binary(explicit=""):
    """Resolve only an explicit or known CUDA sample binary."""
    candidates = (explicit,) if explicit else P2P_CANDIDATES + (
        "p2pBandwidthLatencyTest",
    )
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    return None


def build_report(runner=command, p2p_binary=None):
    """Collect topology and require exactly two visible GPUs."""
    identity = runner([
        "nvidia-smi",
        "--query-gpu=index,name,pci.bus_id,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ])
    gpu_count = (
        len([line for line in identity["stdout"].splitlines() if line.strip()])
        if identity["returncode"] == 0
        else 0
    )
    bandwidth = (
        runner([p2p_binary])
        if p2p_binary
        else {
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr": "p2pBandwidthLatencyTest unavailable",
        }
    )
    gpu_topology = runner(["nvidia-smi", "topo", "-m"])
    gpu_p2p_read = runner(["nvidia-smi", "topo", "-p2p", "r"])
    gpu_p2p_write = runner(["nvidia-smi", "topo", "-p2p", "w"])
    report = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "p2p_binary": p2p_binary,
        "gpu_count": gpu_count,
        "gpu_identity": identity,
        "gpu_topology": gpu_topology,
        "gpu_p2p_read": gpu_p2p_read,
        "gpu_p2p_write": gpu_p2p_write,
        "gpu_pcie": runner([
            "nvidia-smi",
            "--query-gpu=index,pci.bus_id,pcie.link.gen.current,"
            "pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max",
            "--format=csv,noheader,nounits",
        ]),
        "p2p_bandwidth_latency": bandwidth,
        "nvidia_p2p_read_enabled": nvidia_p2p_enabled(
            gpu_p2p_read.get("stdout", ""),
            gpu_count,
        ),
        "nvidia_p2p_write_enabled": nvidia_p2p_enabled(
            gpu_p2p_write.get("stdout", ""),
            gpu_count,
        ),
        "p2p_enabled_matrix_reported": cuda_p2p_enabled(
            bandwidth.get("stdout", ""),
            gpu_count,
        ),
    }
    required = (
        report["gpu_count"] == 2,
        report["gpu_topology"]["returncode"] == 0,
        report["gpu_p2p_read"]["returncode"] == 0,
        report["gpu_p2p_write"]["returncode"] == 0,
        report["gpu_pcie"]["returncode"] == 0,
        report["p2p_bandwidth_latency"]["returncode"] == 0,
        report["nvidia_p2p_read_enabled"],
        report["nvidia_p2p_write_enabled"],
        report["p2p_enabled_matrix_reported"],
    )
    report["status"] = "pass" if all(required) else "incomplete"
    return report


def write_exclusive(path, report):
    """Write immutable JSON evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(report, indent=2, sort_keys=True) + "\n")


def self_test():
    """Verify the two-GPU and P2P gates without system commands."""
    def fake_runner(argv):
        if any(arg.startswith("--query-gpu=index,name") for arg in argv):
            stdout = "0, GPU A, 01:00.0, 1, 24576\n1, GPU B, 02:00.0, 1, 24576"
        elif argv == ["fake-p2p"]:
            stdout = (
                "P2P Connectivity Matrix\n"
                "     D\\D  0  1\n"
                "      0    1  1\n"
                "      1    1  1\n"
                "Unidirectional P2P=Enabled Bandwidth Matrix"
            )
        elif argv[-3:] in (["topo", "-p2p", "r"], ["topo", "-p2p", "w"]):
            stdout = "GPU0 GPU1\nGPU0 X OK\nGPU1 OK X"
        else:
            stdout = "OK"
        return {
            "available": True,
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
        }

    report = build_report(fake_runner, "fake-p2p")
    assert report["gpu_count"] == 2
    assert report["captured_at"].endswith("+00:00")
    assert len(report["runner_sha256"]) == 64
    assert report["p2p_binary"] == "fake-p2p"
    assert report["nvidia_p2p_read_enabled"] is True
    assert report["nvidia_p2p_write_enabled"] is True
    assert report["p2p_enabled_matrix_reported"] is True
    assert report["status"] == "pass"

    def disabled_p2p_runner(argv):
        result = fake_runner(argv)
        if argv == ["fake-p2p"]:
            result["stdout"] = (
                "P2P Connectivity Matrix\n"
                "     D\\D  0  1\n"
                "      0    1  0\n"
                "      1    0  1\n"
                "warning: P2P=Enabled check failed"
            )
        return result

    disabled_report = build_report(disabled_p2p_runner, "fake-p2p")
    assert disabled_report["p2p_enabled_matrix_reported"] is False
    assert disabled_report["status"] == "incomplete"
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--p2p-binary", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.output:
        parser.error("--output is required")
    report = build_report(command, find_p2p_binary(args.p2p_binary))
    write_exclusive(Path(args.output), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
