#!/usr/bin/env python3
"""Collect read-only host facts for a gated DeepSeek preflight."""

import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path


def command(argv):
    if not shutil.which(argv[0]):
        return {"available": False, "returncode": None, "stdout": "", "stderr": "command unavailable"}
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "available": True,
            "returncode": None,
            "stdout": error.stdout or "",
            "stderr": "command timed out after 30 seconds",
        }
    return {"available": True, "returncode": result.returncode, "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    report = {
        "schema_version": 1,
        "status": "evidence-only",
        "platform": platform.platform(),
        "cpu": command(["lscpu", "--json"]),
        "memory": command(["free", "--bytes"]),
        "storage": command(["df", "--block-size=1", "--output=source,fstype,size,avail,target"]),
        "gpu_identity": command(["nvidia-smi", "--query-gpu=name,uuid,pci.bus_id,driver_version,memory.total", "--format=csv,noheader"]),
        "gpu_topology": command(["nvidia-smi", "topo", "-m"]),
        "gpu_p2p_read": command(["nvidia-smi", "topo", "-p2p", "r"]),
        "gpu_pcie": command([
            "nvidia-smi",
            "--query-gpu=index,pci.bus_id,pci.link.gen.current,"
            "pci.link.gen.max,pci.link.width.current,pci.link.width.max",
            "--format=csv,noheader",
        ]),
        "docker": command(["docker", "version", "--format", "{{json .}}"]),
        "docker_images": command([
            "docker", "image", "ls", "--digests", "--format", "{{json .}}",
        ]),
        "nvidia_container_toolkit": command(["nvidia-container-cli", "info"]),
        "nvidia_packages": command([
            "dpkg-query", "-W", "-f=${Package}\t${Version}\n",
            "nvidia-container-toolkit", "libnvidia-container1",
        ]),
        "numa": command(["numactl", "--hardware"]),
        "block_devices": command([
            "lsblk", "--bytes", "--json", "-o",
            "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS",
        ]),
        "model_storage_usage": command(["du", "-sb", "/data/models"]),
        "model_artifacts": command([
            "find", "/data/models", "-mindepth", "1", "-maxdepth", "2",
            "-printf", "%y\t%p\t%s\n",
        ]),
        "boot_warnings": command([
            "journalctl", "-b", "-p", "warning", "--no-pager", "-n", "200",
        ]),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
