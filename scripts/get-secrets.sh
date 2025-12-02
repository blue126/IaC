#!/bin/bash
# Script to fetch secrets from Ansible Vault and output in Terraform tfvars format
# Usage: ./get-secrets.sh > ../terraform/proxmox/secrets.auto.tfvars

# Navigate to ansible directory to ensure ansible.cfg is picked up
cd "$(dirname "$0")/../ansible"

# Fetch secrets using ansible ad-hoc command
# We use a single debug message to format the output
ansible localhost -m debug -a "msg='
# Proxmox Secrets
pm_password         = \"{{ vault_proxmox_password }}\"
pm_api_token_id     = \"{{ vault_proxmox_api_token_id }}\"
pm_api_token_secret = \"{{ vault_proxmox_api_token_secret }}\"

# OCI Secrets
tenancy_ocid     = \"{{ vault_oci_tenancy_ocid }}\"
user_ocid        = \"{{ vault_oci_user_ocid }}\"
fingerprint      = \"{{ vault_oci_fingerprint }}\"
private_key_path = \"{{ vault_oci_private_key_path }}\"
'" --raw | sed 's/localhost | SUCCESS => //' | sed "s/^'//" | sed "s/'$//"
