#!/bin/bash
set -e

# Refresh Terraform state from HCP Terraform for all workspaces.
# Pulls remote state to local terraform.tfstate so Ansible dynamic
# inventory plugins (cloud.terraform.terraform_provider) can read it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WORKSPACES=(esxi proxmox)
STATE_FILE="terraform.tfstate"

if ! command -v terraform &> /dev/null; then
    echo "Error: terraform command not found."
    exit 1
fi

echo "Project root: $PROJECT_ROOT"

for ws in "${WORKSPACES[@]}"; do
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
