#!/bin/bash
set -euo pipefail

if [[ -z "${SANDBOX_ID:-}" ]]; then
  printf 'ERROR: Run this smoke check inside a Docker Sandbox.\n' >&2
  exit 1
fi

export TMPDIR="${TMPDIR:-$(python3 -c 'import tempfile; print(tempfile.gettempdir())')}"
work_dir=$(mktemp -d "${TMPDIR%/}/iac-smoke.XXXXXX")
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
project_root=$(cd -- "$script_dir/../../.." && pwd -P)
printf 'Smoke workspace: %s\n' "$work_dir"

terraform_credentials_dir="${IAC_TERRAFORM_CREDENTIALS_DIR:-}"
terraform_credentials_file="${terraform_credentials_dir}/credentials.tfrc.json"
if [[ -z "$terraform_credentials_dir" || ! -r "$terraform_credentials_file" ]]; then
  printf 'ERROR: Readable HCP Terraform credentials are required inside the Sandbox.\n' >&2
  exit 1
fi
install -d -m 0700 /home/agent/.terraform.d
if [[ -e /home/agent/.terraform.d/credentials.tfrc.json ]]; then
  printf 'ERROR: Refusing to replace existing Sandbox Terraform credentials.\n' >&2
  exit 1
fi
ln -s "$terraform_credentials_file" /home/agent/.terraform.d/credentials.tfrc.json

export CHECKPOINT_DISABLE=1
export ANSIBLE_CONFIG="$work_dir/ansible.cfg"
printf '[defaults]\ncollections_path = /home/agent/.ansible/collections\n' > "$ANSIBLE_CONFIG"
terraform version
ansible --version
/opt/iac-venv/bin/python -m pip --version
/opt/iac-venv/bin/python -c 'import proxmoxer, requests, netaddr, pyVmomi, passlib, notion_client'
ansible-galaxy collection list --format json > "$work_dir/collections.json"
/opt/iac-venv/bin/python - "$work_dir/collections.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as handle:
    installed = {name for group in json.load(handle).values() for name in group}
required = {
    'community.general', 'community.vmware', 'cloud.terraform', 'community.docker',
    'ansible.posix', 'netbox.netbox', 'ansible.windows',
}
missing = required - installed
if missing:
    raise SystemExit(f'Missing Ansible collections: {sorted(missing)}')
print('PASS: IaC Python imports and all seven required Ansible collections.')
PY

result=$(printf 'upper("iac-sandbox-ready")\n' | terraform -chdir="$work_dir" console -no-color)
if [[ "$result" != '"IAC-SANDBOX-READY"' ]]; then
  printf 'ERROR: Unexpected Terraform console result: %s\n' "$result" >&2
  exit 1
fi
printf 'PASS: Terraform evaluated a local expression without a backend.\n'

TF_DATA_DIR="$work_dir/terraform-data" terraform -chdir="$project_root/terraform/proxmox" \
  init -input=false -no-color -lockfile=readonly
printf 'HCP_TERRAFORM_AUTH_OK\n'

(
  cd "$work_dir"
  ansible localhost --inventory localhost, --connection local \
    --module-name ansible.builtin.ping \
    --extra-vars '{"ansible_python_interpreter":"/opt/iac-venv/bin/python"}'
)
printf 'PASS: Ansible executed against Sandbox localhost only.\n'
printf 'IAC_SANDBOX_SMOKE_OK\n'
