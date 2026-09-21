#!/bin/bash
set -e

# Refresh Terraform state from HCP Terraform for all workspaces.
# Pulls remote state to local terraform.tfstate so Ansible dynamic
# inventory plugins (cloud.terraform.terraform_provider) can read it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ALL_WORKSPACES=(proxmox oci)
STATE_FILE="terraform.tfstate"

if ! command -v terraform &> /dev/null; then
    echo "Error: terraform command not found."
    exit 1
fi

# Use specified workspaces or default to all
if [ $# -gt 0 ]; then
    WORKSPACES=("$@")
else
    WORKSPACES=("${ALL_WORKSPACES[@]}")
fi

echo "Project root: $PROJECT_ROOT"
echo "Workspaces to refresh: ${WORKSPACES[*]}"

for ws in "${WORKSPACES[@]}"; do
    if [[ "$ws" == "esxi" ]]; then
        printf 'Error: ESXi is retired; its archived state must not feed active inventory.\n' >&2
        exit 1
    fi
    dir="${PROJECT_ROOT}/terraform/${ws}"
    if [ ! -d "$dir" ]; then
        echo "⚠ Skipping ${ws}: directory not found"
        continue
    fi
    echo "→ Pulling state for ${ws}..."
    (cd "$dir" && terraform state pull > "$STATE_FILE")
    echo "  ✓ ${dir}/${STATE_FILE}"
done

echo "Done."
