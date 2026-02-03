#!/bin/bash
# Script to fetch secrets from Ansible Vault and write them to Terraform secrets.auto.tfvars files
# Usage: ./get-secrets.sh

set -e

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Navigate to ansible directory to ensure ansible.cfg is picked up
cd "$PROJECT_ROOT/ansible"

echo "Fetching secrets from Ansible Vault..."

# 1. Generate Proxmox Secrets using a temporary playbook
echo "Writing terraform/proxmox/secrets.auto.tfvars..."

ansible-playbook /dev/stdin << PLAYBOOK
---
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Generate Proxmox secrets.auto.tfvars
      copy:
        dest: $PROJECT_ROOT/terraform/proxmox/secrets.auto.tfvars
        content: |
          pm_api_url          = "{{ vault_proxmox_api_url }}"
          pm_user             = "root@pam"
          pm_password         = "{{ vault_proxmox_password }}"
          pm_api_token_id     = "{{ vault_proxmox_api_token_id }}"
          pm_api_token_secret = "{{ vault_proxmox_api_token_secret }}"
          target_node         = "{{ vault_proxmox_target_node }}"
          storage_pool        = "{{ vault_proxmox_storage_pool }}"
          sshkeys             = <<EOF
          {{ vault_sshkeys }}
          EOF
PLAYBOOK

# 2. Generate OCI Secrets
echo "Writing terraform/oci/secrets.auto.tfvars..."

ansible-playbook /dev/stdin << PLAYBOOK
---
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Generate OCI secrets.auto.tfvars
      copy:
        dest: $PROJECT_ROOT/terraform/oci/secrets.auto.tfvars
        content: |
          tenancy_ocid     = "{{ vault_oci_tenancy_ocid }}"
          user_ocid        = "{{ vault_oci_user_ocid }}"
          fingerprint      = "{{ vault_oci_fingerprint }}"
          private_key_path = "{{ vault_oci_private_key_path }}"
PLAYBOOK

echo "Done! Secrets have been updated."
