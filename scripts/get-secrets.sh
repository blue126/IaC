#!/bin/bash
# Script to fetch secrets from Ansible Vault and write them to Terraform secrets.auto.tfvars files
# Usage: ./get-secrets.sh

# Navigate to ansible directory to ensure ansible.cfg is picked up
cd "$(dirname "$0")/../ansible"

echo "Fetching secrets from Ansible Vault..."

# 1. Generate Proxmox Secrets
echo "Writing terraform/proxmox/secrets.auto.tfvars..."
ansible localhost -m debug -a "msg='
pm_password         = \"{{ vault_proxmox_password }}\"
pm_api_token_id     = \"{{ vault_proxmox_api_token_id }}\"
pm_api_token_secret = \"{{ vault_proxmox_api_token_secret }}\"
'" --raw | sed 's/localhost | SUCCESS => //' | sed "s/^'//" | sed "s/'$//" > ../terraform/proxmox/secrets.auto.tfvars

# 2. Generate OCI Secrets
echo "Writing terraform/oci/secrets.auto.tfvars..."
ansible localhost -m debug -a "msg='
tenancy_ocid     = \"{{ vault_oci_tenancy_ocid }}\"
user_ocid        = \"{{ vault_oci_user_ocid }}\"
fingerprint      = \"{{ vault_oci_fingerprint }}\"
private_key_path = \"{{ vault_oci_private_key_path }}\"
'" --raw | sed 's/localhost | SUCCESS => //' | sed "s/^'//" | sed "s/'$//" > ../terraform/oci/secrets.auto.tfvars

echo "Done! Secrets have been updated."
