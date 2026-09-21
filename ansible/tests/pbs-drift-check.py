#!/usr/bin/env python3
"""Run PBS regression checks on Sandbox localhost with fake storage commands."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml
from jinja2 import Environment, StrictUndefined, meta

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get("SANDBOX_ID"):
    raise SystemExit("Run inside the task Docker Sandbox, not on production or the host")
WORK = Path(tempfile.mkdtemp(prefix="pbs-drift-check-", dir=os.environ["TMPDIR"]))
BIN = WORK / "bin"
BIN.mkdir()
CONFIG = WORK / "ansible.cfg"
CONFIG.write_text("[defaults]\ncollections_path=/home/agent/.ansible/collections\n")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("ANSIBLE_")}
ENV.update(ANSIBLE_CONFIG=str(CONFIG), PATH=str(BIN) + os.pathsep + os.environ["PATH"])


def load(path):
    return yaml.safe_load((ROOT / path).read_text())


# Unexpected storage operations fail and are logged; no real zfs/zpool is called.
STUB = '''#!/opt/iac-venv/bin/python
import json, os, sys
from pathlib import Path
with open(os.environ["PBS_TEST_LOG"], "a") as handle:
    handle.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + "\\n")
name = Path(sys.argv[0]).name
if name == "zpool" and sys.argv[1:] == ["list", "-H", "-o", "name", "tank"]:
    if os.environ.get("PBS_TEST_MISSING") == "1":
        sys.exit(1)
    print("tank")
elif name == "zfs" and sys.argv[1:3] == ["get", "-H"]:
    path = "/wrong" if os.environ.get("PBS_TEST_MISMATCH") == "1" else "/mnt/datastore/tank"
    print("mountpoint\\t" + path + "\\ncompression\\ton\\nrecordsize\\t128K\\natime\\ton")
else:
    sys.exit(99)
'''
for command in ("zpool", "zfs"):
    path = BIN / command
    path.write_text(STUB)
    path.chmod(0o700)

results = []


def run_case(name, tasks, variables, success=True, extra_env=None):
    playbook = WORK / (name + ".yml")
    log = WORK / (name + ".commands.jsonl")
    playbook.write_text(yaml.safe_dump([{
        "hosts": "localhost", "gather_facts": False,
        "vars": dict(variables, ansible_python_interpreter="/opt/iac-venv/bin/python"),
        "tasks": tasks,
    }], sort_keys=False))
    env = dict(ENV, PBS_TEST_LOG=str(log), **(extra_env or {}))
    proc = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
        cwd=WORK, env=env, capture_output=True, text=True, timeout=90,
    )
    output = proc.stdout + proc.stderr
    (WORK / (name + ".log")).write_text(output)
    ok = proc.returncode == 0 if success else (proc.returncode == 2 and "failed=1" in output)
    if success:
        ok = ok and "changed=0" in output
    commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    ok = ok and all(row[1] in ("list", "get") for row in commands)
    if name == "pool-missing":
        ok = ok and len(commands) == 1
    print(f'{"PASS" if ok else "FAIL"} {name} (exit={proc.returncode})')
    results.append(ok)


server = load("ansible/roles/pbs/defaults/main.yml")
# Select public scalar values only; never load a Vault or inventory file.
pool_vars = {key: server[key] for key in (
    "pbs_zfs_pool_name", "pbs_zfs_mount_point", "pbs_zfs_compression", "pbs_zfs_atime", "pbs_zfs_recordsize"
)}
expected = ("tank", "/mnt/datastore/tank", "on", "on", "128K")
assert tuple(pool_vars.values()) == expected
pool_tasks = load("ansible/roles/pbs/tasks/zfs-pool.yml")
run_case("pool-existing", pool_tasks, pool_vars)
run_case("pool-existing-repeat", pool_tasks, pool_vars)
run_case("pool-missing", pool_tasks, pool_vars, False, {"PBS_TEST_MISSING": "1"})
run_case("pool-path-mismatch", pool_tasks, pool_vars, False, {"PBS_TEST_MISMATCH": "1"})

verify = load("ansible/playbooks/deploy-pbs.yml")[1]["tasks"]
load_defaults = copy.deepcopy(verify[0])
load_defaults["ansible.builtin.include_vars"]["file"] = str(ROOT / "ansible/roles/pbs/defaults/main.yml")
assert "name" in load_defaults["ansible.builtin.include_vars"]
datastore_assert = next(t for t in verify if t["name"] == "Verify the configured datastore and path")
override_vars = {
    "pbs_datastore_name": "override-store", "pbs_zfs_mount_point": "/override-path",
    "ds_list": {"stdout": json.dumps([{"name": "override-store", "path": "/override-path"}])},
}
run_case("verify-inventory-override", [load_defaults, datastore_assert], override_vars)
wrong_path = copy.deepcopy(override_vars)
wrong_path["ds_list"]["stdout"] = json.dumps([{"name": "override-store", "path": "/wrong"}])
run_case("verify-wrong-datastore-path", [load_defaults, datastore_assert], wrong_path, False)

# Backup business policy belongs to the operator, not to an Ansible playbook.
assert not (ROOT / "ansible/playbooks/setup-pbs-backup.yml").exists()
assert not list((ROOT / "ansible/roles/pbs-client").rglob("*.yml"))
assert "pbs_gc_schedule" not in server
assert "--gc-schedule" not in (ROOT / "ansible/roles/pbs/tasks/zfs-datastore.yml").read_text()
print("PASS backup-policy-not-managed-by-ansible")
results.append(True)

# Render only public templates using fictional credentials, with and without pve2.
env = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
env.filters["to_json"] = json.dumps
sources = {name: (ROOT / "ansible/roles/homepage/templates" / name).read_text()
           for name in ("proxmox.yaml.j2", "services.yaml.j2")}
for configured in (False, True):
    variables = {key: "fixture" for source in sources.values()
                 for key in meta.find_undeclared_variables(env.parse(source))}
    variables.update(homepage_pve2_api_token_id="root@pam!fixture" if configured else "",
                     homepage_pve2_api_token_secret="fictional-secret" if configured else "")
    rendered = {name: yaml.safe_load(env.from_string(source).render(variables)) for name, source in sources.items()}
    tile = next(item["Proxmox Backup Server"] for group in rendered["services.yaml.j2"]
                for entries in group.values() for item in entries if "Proxmox Backup Server" in item)
    pdm = next(item["Proxmox Datacenter Manager"] for group in rendered["services.yaml.j2"]
               for entries in group.values() for item in entries if "Proxmox Datacenter Manager" in item)
    assert (pdm["proxmoxNode"], pdm["proxmoxVMID"], pdm["href"]) == (
        "pve1", 117, "https://192.168.1.117:8443"
    )
    if configured:
        assert rendered["proxmox.yaml.j2"]["pve2"]["token"] == "root@pam!fixture"
        assert (tile["proxmoxNode"], tile["proxmoxVMID"]) == ("pve2", 100)
    else:
        assert "pve2" not in rendered["proxmox.yaml.j2"]
        assert "proxmoxNode" not in tile and "monitoring unconfigured" in tile["description"]
    print(f"PASS homepage-pve2-configured={configured}")
    results.append(True)

print(f"RESULT {sum(results)}/{len(results)} passed; evidence={WORK}")
raise SystemExit(0 if all(results) else 1)
