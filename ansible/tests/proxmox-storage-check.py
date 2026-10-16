#!/usr/bin/env python3
"""Exercise ZFS reservation policy on Sandbox localhost with fake commands."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

if not os.environ.get("SANDBOX_ID"):
    raise SystemExit("Run inside the task Docker Sandbox, not on production or the host")

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(tempfile.mkdtemp(prefix="proxmox-storage-check-"))
BIN = WORK / "bin"
BIN.mkdir()
CONFIG = WORK / "ansible.cfg"
CONFIG.write_text(f"[defaults]\nroles_path={ROOT}/ansible/roles\n")
ENV = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_")}
ENV.update(ANSIBLE_CONFIG=str(CONFIG), PATH=str(BIN) + os.pathsep + os.environ["PATH"])

# Only public storage policy is loaded; the fixture never loads a Vault or tfstate.
host_vars = yaml.safe_load((ROOT / "ansible/inventory/host_vars/pve2.yml").read_text())
policy = {key: value for key, value in host_vars.items() if key.startswith("proxmox_storage_")}
assert "proxmox_storage_container" not in policy
assert policy["proxmox_storage_vm_disk"]["dataset"] == "mainpool/vm-250-disk-0"
INVENTORY = WORK / "inventory.yml"
INVENTORY.write_text(yaml.safe_dump({"all": {"hosts": {"pve2": dict(
    policy, ansible_connection="local", ansible_become=False,
    ansible_python_interpreter="/opt/iac-venv/bin/python",
)}}}, sort_keys=False))

STUB = r'''#!/opt/iac-venv/bin/python
import json, os, sys
from pathlib import Path
name, args = Path(sys.argv[0]).name, sys.argv[1:]
state_path = Path(os.environ["PROXMOX_STORAGE_TEST_STATE"])
state = json.loads(state_path.read_text())
with open(os.environ["PROXMOX_STORAGE_TEST_LOG"], "a") as handle:
    handle.write(json.dumps([name, *args]) + chr(10))
if name == "hostname" and not args:
    print(state.get("node", "pve2"))
elif name == "pvesh" and args == ["get", "/nodes/pve2/qemu/250/config", "--output-format", "json"]:
    config = {"name": state.get("vm_name", "pnetlab"),
              "scsi0": state.get("vm_volume", "mainpool:vm-250-disk-0") + ",size=400G",
              "cipassword": "fictional-password-sentinel"}
    if state.get("locked"):
        config["lock"] = "backup"
    print(json.dumps(config))
elif name == "pvesm" and args == ["path", "mainpool:vm-250-disk-0"]:
    print(state.get("vm_path", "/dev/zvol/mainpool/vm-250-disk-0"))
elif name == "zfs" and args == ["get", "-H", "-p", "-o", "property,value",
                              "type,volsize,refreservation", "mainpool/vm-250-disk-0"]:
    if state.get("missing"):
        sys.exit(1)
    for prop, value in {"type": state.get("zvol_type", "volume"), "volsize": state["volsize"],
                        "refreservation": state["reservation"]}.items():
        print(prop + chr(9) + str(value))
elif name == "zfs" and args == ["set", "refreservation=none", "mainpool/vm-250-disk-0"]:
    state["reservation"] = 0
    state_path.write_text(json.dumps(state))
else:
    sys.exit(99)
'''
for command in ("hostname", "pvesh", "pvesm", "pct", "zfs"):
    path = BIN / command
    path.write_text(STUB)
    path.chmod(0o700)

results = []


def run_case(name, initial, success=True, check=False, writes=None, changed=0, tags=None):
    state_path, log = WORK / f"{name}.state.json", WORK / f"{name}.commands.jsonl"
    state_path.write_text(json.dumps(initial))
    command = ["ansible-playbook", "-i", str(INVENTORY),
               str(ROOT / "ansible/playbooks/configure-pve2-storage.yml"), "-vv"]
    if check:
        command.append("--check")
    if tags:
        command.extend(["--tags", tags])
    proc = subprocess.run(command, cwd=WORK, env=dict(
        ENV, PROXMOX_STORAGE_TEST_STATE=str(state_path), PROXMOX_STORAGE_TEST_LOG=str(log),
    ), capture_output=True, text=True, timeout=90)
    output = proc.stdout + proc.stderr
    (WORK / f"{name}.log").write_text(output)
    rows = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    mutations = [row for row in rows if row[0] == "pct" or row[:2] == ["zfs", "set"]]
    after = json.loads(state_path.read_text())
    ok = proc.returncode == (0 if success else 2)
    ok = ok and "fictional-password-sentinel" not in output
    ok = ok and mutations == (writes or []) and after["volsize"] == initial["volsize"]
    ok = ok and after["ct120_quota"] == initial["ct120_quota"]
    if success:
        ok = ok and f"changed={changed}" in output
        ok = ok and any(row[:2] == ["zfs", "get"] for row in rows)
    else:
        ok = ok and "failed=1" in output
    if check or not success:
        ok = ok and after == initial
    print(f'{"PASS" if ok else "FAIL"} {name} (exit={proc.returncode})', flush=True)
    if not ok:
        print(output, flush=True)
    results.append(ok)
    return after


configured = {"reservation": 0, "volsize": 400 * 1024**3, "ct120_quota": 178 * 1024**3}
run_case("configured", configured)
reserved = dict(configured, reservation=436216266752)
released = run_case("release-reservation", reserved, writes=[
    ["zfs", "set", "refreservation=none", "mainpool/vm-250-disk-0"],
], changed=1)
assert released["reservation"] == 0
run_case("released-repeat", released)
run_case("check-reserved", reserved, check=True, changed=1)
run_case("check-configured", configured, check=True)
run_case("verify-only", configured, tags="verify")
run_case("verify-reject-reservation", reserved, success=False, tags="verify")
run_case("verify-check-configured", configured, check=True, tags="verify")
run_case("verify-check-reject-reservation", reserved, success=False, check=True, tags="verify")
for name, overrides in (
    ("wrong-node", {"node": "pve1"}),
    ("wrong-vm", {"vm_name": "unrelated"}),
    ("wrong-vm-volume", {"vm_volume": "mainpool:vm-250-disk-01"}),
    ("wrong-vm-path", {"vm_path": "/dev/zvol/mainpool/vm-251-disk-0"}),
    ("wrong-zvol-type", {"zvol_type": "filesystem"}),
    ("missing-dataset", {"missing": True}),
    ("locked-vm", {"locked": True}),
):
    run_case(name, dict(reserved, **overrides), success=False)
print(f"RESULT {sum(results)}/{len(results)} passed; evidence={WORK}", flush=True)
raise SystemExit(0 if all(results) else 1)
