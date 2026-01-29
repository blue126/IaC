#!/bin/bash
set -e

# Define paths
TERRAFORM_DIR="/workspaces/IaC/terraform/proxmox"
STATE_FILE="terraform.tfstate"

echo "Refreshing Terraform state from Cloud..."

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
