#!/usr/bin/env python3
"""Collect read-only vSphere host, VM, storage, PCI and perf evidence."""

import argparse
import json
import os
import ssl
import statistics
from datetime import datetime, timezone
from pathlib import Path

from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim


def one_named(content, object_type, name):
    """Return exactly one managed object with the requested name."""
    view = content.viewManager.CreateContainerView(
        content.rootFolder,
        [object_type],
        True,
    )
    matches = [item for item in view.view if item.name == name]
    view.Destroy()
    if len(matches) != 1:
        raise RuntimeError(f"expected one {name}, found {len(matches)}")
    return matches[0]


def gpu_evidence(host):
    """Return NVIDIA PCI functions and their passthrough state."""
    system = host.configManager.pciPassthruSystem
    system.Refresh()
    states = {item.id: item for item in system.pciPassthruInfo or []}
    results = []
    for device in host.hardware.pciDevice or []:
        if device.vendorId != 0x10DE:
            continue
        state = states.get(device.id)
        results.append({
            "id": device.id,
            "vendor_id": device.vendorId,
            "device_id": device.deviceId,
            "class_id": device.classId,
            "vendor_name": device.vendorName,
            "device_name": device.deviceName,
            "passthru_capable": getattr(state, "passthruCapable", None),
            "passthru_enabled": getattr(state, "passthruEnabled", None),
            "passthru_active": getattr(state, "passthruActive", None),
        })
    return sorted(results, key=lambda item: item["id"])


def perf_evidence(content, vm):
    """Collect recent realtime VM ready, consumed-memory and swap counters."""
    manager = content.perfManager
    names = {
        counter.key: (
            f"{counter.groupInfo.key}.{counter.nameInfo.key}."
            f"{counter.rollupType}"
        )
        for counter in manager.perfCounter
    }
    wanted = {
        "cpu.ready.summation",
        "cpu.costop.summation",
        "mem.consumed.average",
        "mem.swapinRate.average",
        "mem.swapoutRate.average",
    }
    metrics = [
        metric
        for metric in manager.QueryAvailablePerfMetric(entity=vm)
        if names.get(metric.counterId) in wanted
    ]
    if not metrics:
        return {"available": False, "metrics": {}}
    query = vim.PerformanceManager.QuerySpec(
        entity=vm,
        metricId=metrics,
        intervalId=20,
        maxSample=3,
    )
    series = manager.QueryPerf(querySpec=[query])
    results = {}
    if series:
        for item in series[0].value:
            name = names[item.id.counterId]
            values = [value for value in item.value if value >= 0]
            results[name] = {
                "instance": item.id.instance,
                "values": values,
                "mean": statistics.fmean(values) if values else None,
            }
    return {"available": True, "sample_interval_seconds": 20, "metrics": results}


def main():
    """Connect to vCenter and write a stable evidence document."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--vm", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    password = os.environ.get("DEEPSEEK_VSPHERE_PASSWORD")
    if not password:
        parser.error("DEEPSEEK_VSPHERE_PASSWORD is required")
    service = SmartConnect(
        host=args.server,
        user=args.user,
        pwd=password,
        sslContext=ssl._create_unverified_context(),
    )
    try:
        content = service.RetrieveContent()
        host = one_named(content, vim.HostSystem, args.host)
        vm = one_named(content, vim.VirtualMachine, args.vm)
        pci_backing = [
            device.backing.id
            for device in vm.config.hardware.device
            if isinstance(device, vim.vm.device.VirtualPCIPassthrough)
        ]
        disks = [
            {
                "label": device.deviceInfo.label,
                "capacity_bytes": device.capacityInBytes,
                "file": getattr(device.backing, "fileName", None),
            }
            for device in vm.config.hardware.device
            if isinstance(device, vim.vm.device.VirtualDisk)
        ]
        datastores = [
            {
                "name": datastore.summary.name,
                "capacity_bytes": datastore.summary.capacity,
                "free_bytes": datastore.summary.freeSpace,
                "uncommitted_bytes": datastore.summary.uncommitted,
                "accessible": datastore.summary.accessible,
            }
            for datastore in vm.datastore
        ]
        report = {
            "schema_version": 1,
            "status": "evidence-only",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "host": {
                "name": host.name,
                "connection_state": str(host.runtime.connectionState),
                "boot_time": host.runtime.bootTime.isoformat(),
                "vendor": host.hardware.systemInfo.vendor,
                "model": host.hardware.systemInfo.model,
                "cpu_threads": host.hardware.cpuInfo.numCpuThreads,
                "memory_bytes": host.hardware.memorySize,
                "nvidia_pci": gpu_evidence(host),
            },
            "vm": {
                "name": vm.name,
                "power_state": str(vm.runtime.powerState),
                "cpu_count": vm.config.hardware.numCPU,
                "memory_mb": vm.config.hardware.memoryMB,
                "memory_reservation_mb": vm.config.memoryAllocation.reservation,
                "memory_locked_to_max": (
                    vm.config.memoryReservationLockedToMax
                ),
                "pci_backing": sorted(pci_backing),
                "disks": disks,
            },
            "datastores": datastores,
            "performance": perf_evidence(content, vm),
        }
    finally:
        Disconnect(service)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
