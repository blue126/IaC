#!/usr/bin/env python3
"""Collect sanitized host, GPU, container, and service resource evidence."""

import argparse
import csv
import io
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


MIN_MEMAVAILABLE_BYTES = 32 * 1024 ** 3
MIN_GPU_FREE_MIB = 2048


def run_command(argv):
    """Run one fixed read-only command and return sanitized status/output."""
    if not shutil.which(argv[0]):
        return {"available": False, "returncode": None, "stdout": ""}
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return {"available": True, "returncode": None, "stdout": ""}
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
    }


def parse_meminfo(text):
    """Parse only memory capacity counters from procfs."""
    values = {}
    for line in text.splitlines():
        name, _, raw = line.partition(":")
        if name not in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            continue
        fields = raw.strip().split()
        if fields and fields[0].isdigit():
            values[f"{name.lower()}_bytes"] = int(fields[0]) * 1024
    if "swaptotal_bytes" in values and "swapfree_bytes" in values:
        values["swap_used_bytes"] = (
            values["swaptotal_bytes"] - values["swapfree_bytes"]
        )
    return values


def parse_vmstat(text):
    """Parse only the cumulative kernel OOM kill counter."""
    for line in text.splitlines():
        name, _, raw = line.partition(" ")
        if name == "oom_kill" and raw.strip().isdigit():
            return {"oom_kill_count": int(raw.strip())}
    return {}


def parse_size_bytes(value):
    """Parse a Docker human-readable binary or decimal size."""
    value = value.strip()
    units = {
        "B": 1,
        "kB": 1000,
        "MB": 1000 ** 2,
        "GB": 1000 ** 3,
        "KiB": 1024,
        "MiB": 1024 ** 2,
        "GiB": 1024 ** 3,
    }
    for unit in sorted(units, key=len, reverse=True):
        if value.endswith(unit):
            try:
                return int(float(value[:-len(unit)].strip()) * units[unit])
            except ValueError:
                return None
    return None


def parse_percent(value):
    """Parse a Docker percentage without retaining raw stats."""
    try:
        return float(value.strip().removesuffix("%"))
    except (AttributeError, ValueError):
        return None


def sanitize_container_stats(text):
    """Retain only numeric container resource counters."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None
    memory_used = str(raw.get("MemUsage", "")).partition("/")[0]
    try:
        pids = int(str(raw.get("PIDs", "")).strip())
    except ValueError:
        pids = None
    return {
        "memory_used_bytes": parse_size_bytes(memory_used),
        "memory_percent": parse_percent(str(raw.get("MemPerc", ""))),
        "cpu_percent": parse_percent(str(raw.get("CPUPerc", ""))),
        "pids": pids,
    }


def parse_gpu_csv(text):
    """Parse numeric nvidia-smi CSV output by GPU index."""
    gpus = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) != 5:
            continue
        try:
            gpus.append({
                "index": int(row[0].strip()),
                "memory_used_mib": int(row[1].strip()),
                "memory_total_mib": int(row[2].strip()),
                "utilization_percent": int(row[3].strip()),
                "temperature_c": int(row[4].strip()),
            })
        except ValueError:
            continue
    return gpus


def parse_properties(text):
    """Parse systemctl show key/value output."""
    return {
        key: value
        for line in text.splitlines()
        for key, separator, value in [line.partition("=")]
        if separator and key in {"ActiveState", "NRestarts", "Result", "ExecMainStatus"}
    }


def collect_sample(compose_project, service_units, command_runner=run_command):
    """Collect one resource snapshot without request or environment content."""
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    vmstat = Path("/proc/vmstat").read_text(encoding="utf-8")
    gpu_result = command_runner([
        "nvidia-smi",
        "--query-gpu=index,memory.used,memory.total,utilization.gpu,temperature.gpu",
        "--format=csv,noheader,nounits",
    ])
    services = {}
    for unit in service_units:
        result = command_runner([
            "systemctl",
            "show",
            unit,
            "--property=ActiveState,NRestarts,Result,ExecMainStatus",
        ])
        services[unit] = {
            "available": result["available"],
            "returncode": result["returncode"],
            "properties": parse_properties(result["stdout"]),
        }
    container = {
        "available": False,
        "returncode": None,
        "stats": None,
        "state": None,
        "restart_count": None,
    }
    if compose_project:
        identity = command_runner([
            "docker", "ps", "--all", "--quiet",
            "--filter", f"label=com.docker.compose.project={compose_project}",
            "--filter", "label=com.docker.compose.service=candidate",
        ])
        container.update({
            "available": identity["available"],
            "returncode": identity["returncode"],
        })
        if identity["returncode"] == 0 and identity["stdout"]:
            stats = command_runner([
                "docker", "stats", "--no-stream", "--format", "{{json .}}",
                identity["stdout"].splitlines()[0],
            ])
            if stats["returncode"] == 0:
                container["stats"] = sanitize_container_stats(stats["stdout"])
            state = command_runner([
                "docker", "inspect", "--format", "{{json .State}}",
                identity["stdout"].splitlines()[0],
            ])
            if state["returncode"] == 0:
                try:
                    raw_state = json.loads(state["stdout"])
                    container["state"] = {
                        "status": raw_state.get("Status"),
                        "running": raw_state.get("Running"),
                        "oom_killed": raw_state.get("OOMKilled"),
                        "exit_code": raw_state.get("ExitCode"),
                    }
                except json.JSONDecodeError:
                    container["state"] = None
            restarts = command_runner([
                "docker", "inspect", "--format", "{{.RestartCount}}",
                identity["stdout"].splitlines()[0],
            ])
            if restarts["returncode"] == 0 and restarts["stdout"].isdigit():
                container["restart_count"] = int(restarts["stdout"])
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": {**parse_meminfo(meminfo), **parse_vmstat(vmstat)},
        "gpus": (
            parse_gpu_csv(gpu_result["stdout"])
            if gpu_result["returncode"] == 0
            else None
        ),
        "gpu_collection": {
            "available": gpu_result["available"],
            "returncode": gpu_result["returncode"],
        },
        "container": container,
        "services": services,
    }


def unsafe_reasons(sample, initial_oom_count):
    """Return immediate fail-closed pressure or restart reasons."""
    reasons = []
    host = sample.get("host") if isinstance(sample.get("host"), dict) else {}
    memavailable = host.get("memavailable_bytes")
    swap_used = host.get("swap_used_bytes")
    oom_count = host.get("oom_kill_count")
    if not isinstance(memavailable, int):
        reasons.append("memavailable-unavailable")
    elif memavailable < MIN_MEMAVAILABLE_BYTES:
        reasons.append("memavailable-below-32-gib")
    if not isinstance(swap_used, int):
        reasons.append("swap-unavailable")
    elif swap_used != 0:
        reasons.append("swap-in-use")
    if not isinstance(oom_count, int) or not isinstance(initial_oom_count, int):
        reasons.append("oom-counter-unavailable")
    elif oom_count > initial_oom_count:
        reasons.append("host-oom-kill-increased")

    gpu_collection = sample.get("gpu_collection", {})
    gpus = sample.get("gpus")
    if (
        gpu_collection.get("available") is not True
        or gpu_collection.get("returncode") != 0
        or not isinstance(gpus, list)
        or {gpu.get("index") for gpu in gpus if isinstance(gpu, dict)} != {0, 1}
    ):
        reasons.append("gpu-collection-incomplete")
    else:
        for gpu in gpus:
            free_mib = gpu.get("memory_total_mib", 0) - gpu.get("memory_used_mib", 0)
            if free_mib < MIN_GPU_FREE_MIB:
                reasons.append(f"gpu-{gpu['index']}-free-below-2-gib")

    for unit, service in sample.get("services", {}).items():
        properties = service.get("properties", {}) if isinstance(service, dict) else {}
        try:
            restarts = int(properties["NRestarts"])
        except (KeyError, TypeError, ValueError):
            reasons.append(f"service-{unit}-restart-counter-unavailable")
            continue
        if service.get("available") is not True or service.get("returncode") != 0:
            reasons.append(f"service-{unit}-collection-incomplete")
        elif restarts != 0:
            reasons.append(f"service-{unit}-restarted")

    container = sample.get("container", {})
    if isinstance(container.get("restart_count"), int) and container[
        "restart_count"
    ] != 0:
        reasons.append("candidate-container-restarted")
    state = container.get("state")
    if isinstance(state, dict) and state.get("oom_killed") is True:
        reasons.append("candidate-container-oom-killed")
    return sorted(set(reasons))


def summarize(samples):
    """Calculate peak pressure and minimum headroom from resource snapshots."""
    summary = {
        "schema_version": 1,
        "sample_count": len(samples),
        "first_timestamp": samples[0]["timestamp"] if samples else None,
        "last_timestamp": samples[-1]["timestamp"] if samples else None,
        "host": {},
        "gpus": {},
        "services": {},
        "container": {},
        "thresholds": {
            "minimum_memavailable_bytes": MIN_MEMAVAILABLE_BYTES,
            "minimum_gpu_free_mib": MIN_GPU_FREE_MIB,
        },
    }
    available = [
        sample["host"]["memavailable_bytes"]
        for sample in samples
        if "memavailable_bytes" in sample.get("host", {})
    ]
    swap_used = [
        sample["host"]["swap_used_bytes"]
        for sample in samples
        if "swap_used_bytes" in sample.get("host", {})
    ]
    summary["host"]["minimum_memavailable_bytes"] = min(available) if available else None
    summary["host"]["maximum_swap_used_bytes"] = max(swap_used) if swap_used else None
    oom_counts = [
        sample["host"]["oom_kill_count"]
        for sample in samples
        if "oom_kill_count" in sample.get("host", {})
    ]
    summary["host"]["oom_kill_count_start"] = oom_counts[0] if oom_counts else None
    summary["host"]["oom_kill_count_end"] = oom_counts[-1] if oom_counts else None
    summary["host"]["oom_kill_count_delta"] = (
        oom_counts[-1] - oom_counts[0] if oom_counts else None
    )
    gpu_indexes = sorted({
        gpu["index"]
        for sample in samples
        for gpu in (sample.get("gpus") or [])
    })
    for index in gpu_indexes:
        records = [
            gpu
            for sample in samples
            for gpu in (sample.get("gpus") or [])
            if gpu["index"] == index
        ]
        summary["gpus"][str(index)] = {
            "sample_count": len(records),
            "maximum_memory_used_mib": max(
                gpu["memory_used_mib"] for gpu in records
            ),
            "minimum_memory_free_mib": min(
                gpu["memory_total_mib"] - gpu["memory_used_mib"]
                for gpu in records
            ),
            "maximum_utilization_percent": max(
                gpu["utilization_percent"] for gpu in records
            ),
        }
    units = sorted({
        unit
        for sample in samples
        for unit in sample.get("services", {})
    })
    for unit in units:
        restarts = []
        active_states = []
        complete_samples = 0
        for sample in samples:
            service = sample.get("services", {}).get(unit, {})
            properties = service.get("properties", {})
            active_states.append(properties.get("ActiveState"))
            if (
                service.get("available") is True
                and service.get("returncode") == 0
                and properties.get("ActiveState")
                and properties.get("NRestarts") is not None
            ):
                complete_samples += 1
            try:
                restarts.append(int(properties["NRestarts"]))
            except (KeyError, TypeError, ValueError):
                pass
        summary["services"][unit] = {
            "sample_count": complete_samples,
            "collection_complete": complete_samples == len(samples),
            "maximum_restarts": max(restarts) if restarts else None,
            "active_states": sorted({state for state in active_states if state}),
        }
    containers = [sample.get("container", {}) for sample in samples]
    memory_used = [
        container["stats"]["memory_used_bytes"]
        for container in containers
        if isinstance(container.get("stats"), dict)
        and container["stats"].get("memory_used_bytes") is not None
    ]
    restart_counts = [
        container["restart_count"]
        for container in containers
        if isinstance(container.get("restart_count"), int)
    ]
    states = [
        container["state"]
        for container in containers
        if isinstance(container.get("state"), dict)
    ]
    summary["container"] = {
        "observed_sample_count": len(states),
        "stats_sample_count": len(memory_used),
        "restart_sample_count": len(restart_counts),
        "maximum_memory_used_bytes": max(memory_used) if memory_used else None,
        "maximum_restart_count": max(restart_counts) if restart_counts else None,
        "oom_killed_observed": any(state.get("oom_killed") is True for state in states),
        "statuses": sorted({state.get("status") for state in states if state.get("status")}),
        "exit_codes": sorted({state.get("exit_code") for state in states
                              if isinstance(state.get("exit_code"), int)}),
    }
    return summary


def parse_jsonl(raw):
    """Parse JSONL and tolerate only an unterminated final partial record."""
    lines = raw.splitlines()
    samples = []
    for index, line in enumerate(lines):
        try:
            samples.append(json.loads(line))
        except json.JSONDecodeError:
            is_trailing_partial = index == len(lines) - 1 and not raw.endswith("\n")
            if not is_trailing_partial:
                raise
    return samples


def read_jsonl(path):
    """Read completed JSONL records and ignore a trailing partial line."""
    return parse_jsonl(path.read_text(encoding="utf-8"))


def write_json_exclusive(path, document):
    """Write one immutable JSON document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output_file:
        output_file.write(json.dumps(document, indent=2, sort_keys=True) + "\n")


def self_test():
    """Test parsers and peak aggregation without running system commands."""
    memory = parse_meminfo(
        "MemTotal: 1000 kB\nMemAvailable: 700 kB\n"
        "SwapTotal: 100 kB\nSwapFree: 80 kB\n"
    )
    assert memory["memavailable_bytes"] == 700 * 1024
    assert memory["swap_used_bytes"] == 20 * 1024
    assert parse_vmstat("pgfault 1\noom_kill 3\n") == {"oom_kill_count": 3}
    assert parse_size_bytes("1.5GiB") == int(1.5 * 1024 ** 3)
    assert sanitize_container_stats(
        '{"MemUsage":"1.5GiB / 8GiB","MemPerc":"18.75%",'
        '"CPUPerc":"50.0%","PIDs":"12"}'
    )["pids"] == 12
    observed_commands = []

    def fake_command(argv):
        observed_commands.append(argv)
        if argv[:3] == ["docker", "ps", "--all"]:
            return {"available": True, "returncode": 0, "stdout": ""}
        if argv[0] == "nvidia-smi":
            return {"available": True, "returncode": 0, "stdout": ""}
        return {"available": True, "returncode": 0, "stdout": ""}

    collect_sample("safe-project", [], fake_command)
    assert any(
        "label=com.docker.compose.project=safe-project" in command
        for command in observed_commands
    )
    gpus = parse_gpu_csv("0, 100, 1000, 25, 40\n1, 200, 1000, 50, 45\n")
    assert len(gpus) == 2 and gpus[1]["memory_used_mib"] == 200
    samples = [
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "host": {"memavailable_bytes": 700, "swap_used_bytes": 0,
                     "oom_kill_count": 2},
            "gpus": gpus,
            "services": {
                "owner.service": {
                    "available": True,
                    "returncode": 0,
                    "properties": {"NRestarts": "0", "ActiveState": "active"},
                }
            },
            "container": {"stats": {"memory_used_bytes": 100},
                          "restart_count": 0,
                          "state": {"status": "running", "oom_killed": False,
                                    "exit_code": 0}},
        },
        {
            "timestamp": "2026-01-01T00:00:01+00:00",
            "host": {"memavailable_bytes": 600, "swap_used_bytes": 10,
                     "oom_kill_count": 3},
            "gpus": [
                {"index": 0, "memory_used_mib": 300, "memory_total_mib": 1000,
                 "utilization_percent": 75, "temperature_c": 50},
                gpus[1],
            ],
            "services": {
                "owner.service": {
                    "available": True,
                    "returncode": 0,
                    "properties": {"NRestarts": "1", "ActiveState": "active"},
                }
            },
            "container": {"stats": {"memory_used_bytes": 200},
                          "restart_count": 0,
                          "state": {"status": "exited", "oom_killed": True,
                                    "exit_code": 137}},
        },
    ]
    summary = summarize(samples)
    assert summary["host"]["minimum_memavailable_bytes"] == 600
    assert summary["gpus"]["0"]["minimum_memory_free_mib"] == 700
    assert summary["services"]["owner.service"]["maximum_restarts"] == 1
    assert summary["services"]["owner.service"]["collection_complete"] is True
    assert summary["container"]["observed_sample_count"] == 2
    assert summary["host"]["oom_kill_count_delta"] == 1
    assert summary["container"]["maximum_memory_used_bytes"] == 200
    assert summary["container"]["oom_killed_observed"] is True
    safe_sample = json.loads(json.dumps(samples[0]))
    safe_sample["host"]["memavailable_bytes"] = MIN_MEMAVAILABLE_BYTES + 1
    safe_sample["gpu_collection"] = {"available": True, "returncode": 0}
    safe_sample["gpus"] = [
        {"index": 0, "memory_used_mib": 100, "memory_total_mib": 4096},
        {"index": 1, "memory_used_mib": 100, "memory_total_mib": 4096},
    ]
    assert unsafe_reasons(safe_sample, 2) == []
    safe_sample["host"]["swap_used_bytes"] = 1
    assert "swap-in-use" in unsafe_reasons(safe_sample, 2)
    assert parse_jsonl('{"sample": 1}\n{"partial":') == [{"sample": 1}]
    try:
        parse_jsonl('{"sample": 1}\nnot-json\n{"sample": 2}\n')
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("internal malformed JSONL must fail closed")
    print(json.dumps({"self_test": "pass"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--summary-output")
    parser.add_argument("--summarize")
    parser.add_argument("--compose-project", default="")
    parser.add_argument("--service-unit", action="append", default=[])
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--sample-limit", type=int, default=1)
    parser.add_argument("--stop-file")
    parser.add_argument("--abort-output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.summarize:
        if not args.summary_output:
            parser.error("--summary-output is required with --summarize")
        write_json_exclusive(
            Path(args.summary_output),
            summarize(read_jsonl(Path(args.summarize))),
        )
        return
    if not args.output:
        parser.error("--output is required")
    if args.interval <= 0 or args.sample_limit <= 0:
        parser.error("--interval and --sample-limit must be positive")

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    stop_file = Path(args.stop_file) if args.stop_file else None
    abort_output = Path(args.abort_output) if args.abort_output else None
    initial_oom_count = None
    with target.open("x", encoding="utf-8") as output_file:
        for sample_index in range(args.sample_limit):
            sample_started = time.monotonic()
            sample = collect_sample(args.compose_project, args.service_unit)
            output_file.write(json.dumps(sample, sort_keys=True) + "\n")
            output_file.flush()
            if initial_oom_count is None:
                initial_oom_count = sample.get("host", {}).get("oom_kill_count")
            reasons = unsafe_reasons(sample, initial_oom_count)
            if reasons and abort_output:
                write_json_exclusive(
                    abort_output,
                    {
                        "schema_version": 1,
                        "status": "abort",
                        "timestamp": sample["timestamp"],
                        "reasons": reasons,
                    },
                )
                break
            if stop_file and stop_file.exists():
                break
            if sample_index + 1 < args.sample_limit:
                sample_elapsed = time.monotonic() - sample_started
                time.sleep(max(0, args.interval - sample_elapsed))
    if args.summary_output:
        write_json_exclusive(
            Path(args.summary_output),
            summarize(read_jsonl(target)),
        )


if __name__ == "__main__":
    main()
