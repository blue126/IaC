#!/usr/bin/env python3
"""Check CT120 adoption and replacement protection using synthetic local state."""

import argparse
import http.server
import json
import os
from pathlib import Path
import platform
import shutil
import ssl
import subprocess
import tempfile
import threading

if not os.environ.get("SANDBOX_ID"):
    raise SystemExit("Run inside the task Docker Sandbox, not on production or the host")

parser = argparse.ArgumentParser()
parser.add_argument("--provider", type=Path, required=True, help="Existing bpg 0.70.0 binary for this Linux platform")
args = parser.parse_args()
if args.provider.name != "terraform-provider-proxmox_v0.70.0" or not args.provider.is_file():
    raise SystemExit("Provide the already installed bpg/proxmox 0.70.0 binary")

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(tempfile.mkdtemp(prefix="ct120-terraform-check-"))
MIRROR = WORK / "mirror"
architecture = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(platform.machine())
if platform.system() != "Linux" or architecture is None:
    raise SystemExit("The existing provider must run on a Linux amd64 or arm64 Sandbox")
provider_dir = MIRROR / f"registry.terraform.io/bpg/proxmox/0.70.0/linux_{architecture}"
provider_dir.mkdir(parents=True)
shutil.copy2(args.provider, provider_dir / args.provider.name)
MODULE = WORK / "module"
MODULE.mkdir()
shutil.copy2(ROOT / "terraform/proxmox/ct120.tf", MODULE / "ct120.tf")
(MODULE / "provider.tf").write_text('''terraform {
  required_providers {
    proxmox = { source = "bpg/proxmox", version = "0.70.0" }
  }
}
provider "proxmox" {
  alias = "pve2_root"
  endpoint = "https://127.0.0.1:1/"
  api_token = "root@pam!ct120=fixture-only"
  insecure = true
  ssh {
    agent = false
    username = "root"
    password = "fixture-only"
  }
}
''')
ENV = {key: value for key, value in os.environ.items()
       if not key.startswith(("TF_", "PROXMOX_"))}
ENV.update(TF_CLI_CONFIG_FILE=str(WORK / "terraform.rc"), CHECKPOINT_DISABLE="1", TF_IN_AUTOMATION="1")
(WORK / "terraform.rc").write_text("disable_checkpoint = true\n")


def terraform(*command):
    result = subprocess.run(["terraform", *command], cwd=MODULE, env=ENV,
                            capture_output=True, text=True, timeout=90)
    (WORK / (command[0] + ".log")).write_text(result.stdout + result.stderr)
    return result


for command in (("init", "-backend=false", "-input=false", f"-plugin-dir={MIRROR}"),
                ("validate", "-json"), ("fmt", "-check", "ct120.tf")):
    result = terraform(*command)
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)


def write_state(size):
    # These are synthetic values, not a production state export.
    attributes = {
        "id": "120", "node_name": "pve2", "vm_id": 120,
        "disk": [{"datastore_id": "mainpool", "size": size}],
        "cpu": [{"architecture": "amd64", "cores": 12, "units": 1024}],
        "memory": [{"dedicated": 16384, "swap": 0}],
        "mount_point": [{"volume": "/fixture/data", "path": "/data", "size": "",
                         "acl": False, "backup": False, "mount_options": [], "quota": False,
                         "read_only": False, "replicate": True, "shared": False}],
        "device_passthrough": [{"path": "/dev/nvidia0", "uid": 0, "gid": 0,
                                "mode": "0666", "deny_write": False}],
        "initialization": [{"hostname": "LLM", "dns": [], "ip_config": [], "user_account": []}],
        "network_interface": [{"name": "eth0", "bridge": "vmbr0", "enabled": True,
                               "firewall": False, "mac_address": "02:00:00:00:01:20",
                               "mtu": 0, "rate_limit": 0, "vlan_id": 0}],
        "started": False, "start_on_boot": True, "unprivileged": False,
        "timeout_clone": 1800, "timeout_create": 1800, "timeout_delete": 60,
        "timeout_start": 300, "timeout_update": 1800,
    }
    (MODULE / "terraform.tfstate").write_text(json.dumps({
        "version": 4, "terraform_version": "1.14.9", "serial": 0,
        "lineage": "b4336885-f3a8-4ae5-8342-07f1f641ed7a", "outputs": {},
        "resources": [{"mode": "managed", "type": "proxmox_virtual_environment_container",
                       "name": "ct120", "provider": 'provider["registry.terraform.io/bpg/proxmox"].pve2_root',
                       "instances": [{"schema_version": 0, "attributes": attributes}]}],
    }))


write_state(178)
matching = terraform("plan", "-refresh=false", "-input=false", "-lock=false", "-out=matching.tfplan")
if matching.returncode:
    raise SystemExit(matching.stdout + matching.stderr)
shown = terraform("show", "-json", "matching.tfplan")
if shown.returncode:
    raise SystemExit(shown.stdout + shown.stderr)
plan = json.loads(shown.stdout)
changes = plan.get("resource_changes", [])
assert len(changes) == 1 and changes[0]["change"]["actions"] == ["no-op"], changes
print("PASS existing 178G rootfs and non-disk settings remain unchanged", flush=True)

write_state(128)
replacement = terraform("plan", "-refresh=false", "-input=false", "-lock=false")
output = replacement.stdout + replacement.stderr
assert replacement.returncode == 1 and "prevent_destroy" in output, output
print("PASS bpg 0.70.0 capacity replacement is blocked by prevent_destroy", flush=True)

# Exercise declarative import from an empty local backend, with GET-only TLS API.
IMPORT_MODULE = WORK / "first-import"
IMPORT_MODULE.mkdir()
shutil.copy2(MODULE / "ct120.tf", IMPORT_MODULE / "ct120.tf")
shutil.copy2(MODULE / ".terraform.lock.hcl", IMPORT_MODULE / ".terraform.lock.hcl")
shutil.copytree(MODULE / ".terraform", IMPORT_MODULE / ".terraform", symlinks=True)
api_calls = []
fixture_config = {
    "arch": "amd64", "cores": 12, "cpuunits": 1024, "hostname": "LLM",
    "memory": 16384, "swap": 0, "mp0": "/fixture/data,mp=/data",
    "net0": "name=eth0,bridge=vmbr0,gw=192.0.2.1,hwaddr=02:00:00:00:01:20,ip=192.0.2.120/24,type=veth",
    "onboot": 1, "ostype": "ubuntu", "rootfs": "mainpool:subvol-120-disk-0,size=178G",
    "dev0": "deny-write=0,path=/dev/nvidia0,uid=0,gid=0,mode=0666",
}


class FixtureAPI(http.server.BaseHTTPRequestHandler):
    expected_token = "PVEAPIToken=root@pam!ct120=fixture-only"

    def log_message(self, *args):
        pass

    def do_GET(self):
        api_calls.append(("GET", self.path))
        if self.headers.get("Authorization") != self.expected_token:
            self.send_error(401)
            return
        data = {
            "/api2/json/nodes/pve2/lxc/120/config": fixture_config,
            "/api2/json/nodes/pve2/lxc/120/status/current": {"status": "running", "vmid": 120},
        }
        self.send_response(200 if self.path in data else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": data.get(self.path)}).encode())

    def do_POST(self):
        self.reject_write()

    def reject_write(self):
        api_calls.append((self.command, self.path))
        self.send_error(405)

    do_PUT = reject_write
    do_PATCH = reject_write
    do_DELETE = reject_write


certificate, key = WORK / "fixture.crt", WORK / "fixture.key"
subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(key), "-out", str(certificate), "-days", "1",
                "-subj", "/CN=localhost"], capture_output=True, check=True)
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureAPI)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certificate, key)
server.socket = context.wrap_socket(server.socket, server_side=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
fixture_provider = (MODULE / "provider.tf").read_text().replace(
    'endpoint = "https://127.0.0.1:1/"',
    f'endpoint = "https://127.0.0.1:{server.server_port}/"',
)
(IMPORT_MODULE / "provider.tf").write_text(fixture_provider)
try:
    imported = subprocess.run(["terraform", "plan", "-input=false", "-lock=false", "-out=import.tfplan"],
                              cwd=IMPORT_MODULE, env=ENV, capture_output=True, text=True, timeout=90)
    (WORK / "first-import.log").write_text(imported.stdout + imported.stderr)
    assert imported.returncode == 0, imported.stdout + imported.stderr
    shown = subprocess.run(["terraform", "show", "-json", "import.tfplan"], cwd=IMPORT_MODULE,
                           env=ENV, capture_output=True, text=True, timeout=90)
    assert shown.returncode == 0, shown.stderr
    changes = json.loads(shown.stdout).get("resource_changes", [])
    assert len(changes) == 1, changes
    change = changes[0]["change"]
    assert change["actions"] == ["no-op"] and change["importing"]["id"] == "pve2/120", change
    assert change["after"]["id"] == "120" and change["after"]["node_name"] == "pve2", change
    assert change["after"]["disk"] == [{"datastore_id": "mainpool", "size": 178}], change
    assert all(method == "GET" for method, _ in api_calls), api_calls
    print("PASS first declarative import only registers pve2/120 using the pve2 API token", flush=True)
finally:
    server.shutdown()
    server.server_close()
print(f"RESULT Terraform validation and 3 local plan checks passed; evidence={WORK}", flush=True)
