#!/bin/bash
set -e

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Define paths relative to project root
TERRAFORM_DIR="${PROJECT_ROOT}/terraform/proxmox"
STATE_FILE="terraform.tfstate"

echo "Refreshing Terraform state from Cloud..."
echo "Project root: $PROJECT_ROOT"
echo "Terraform dir: $TERRAFORM_DIR"

if [ ! -d "$TERRAFORM_DIR" ]; then
    echo "Error: Directory $TERRAFORM_DIR does not exist."
    exit 1
fi

cd "$TERRAFORM_DIR"

if command -v terraform &> /dev/null; then
    # Pull current state to local file for Ansible
    terraform state pull > "$STATE_FILE"
    echo "Successfully pulled state to $TERRAFORM_DIR/$STATE_FILE"
else
    echo "Error: terraform command not found."
    exit 1
fi
