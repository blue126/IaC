# Secret Management Deployment Guide

This guide outlines how to manage secrets in our IaC repository using Ansible Vault.

## Prerequisites
- Ansible installed on your control node (WSL/Linux).
- Access to the `ansible/` directory in this repository.

## 1. Initial Setup (First Time Only)

If you are cloning this repository for the first time, you need to set up the Vault password.

1.  **Obtain the Vault Password**: Ask the repository administrator (Will) for the current Vault password.
2.  **Create Password File**:
    In the `ansible/` directory, create a file named `.vault_pass` and paste the password into it.
    ```bash
    echo "YOUR_SECRET_PASSWORD" > ansible/.vault_pass
    ```
3.  **Verify Permissions**:
    Ensure the file is readable only by you.
    ```bash
    chmod 600 ansible/.vault_pass
    ```
4.  **Verify Git Ignore**:
    Ensure `.vault_pass` is ignored by git to prevent accidental commits.
    ```bash
    git check-ignore ansible/.vault_pass
    ```

## 2. Managing Secrets

All secrets are stored in `ansible/inventory/group_vars/all/vault.yml`.

### Viewing Secrets
To view the decrypted contents without editing:
```bash
ansible-vault view ansible/inventory/group_vars/all/vault.yml
```

### Editing/Adding Secrets
To modify existing secrets or add new ones:
```bash
ansible-vault edit ansible/inventory/group_vars/all/vault.yml
```
This will open your default editor. Add secrets using the `vault_` prefix convention:
```yaml
vault_my_new_secret: "super_secret_value"
```

### Encrypting a Plaintext File
If you accidentally decrypted the file or created a new one:
```bash
ansible-vault encrypt ansible/inventory/group_vars/all/vault.yml
```

## 3. Using Secrets in Inventory

Reference the Vault variables in your inventory files (`host_vars` or `group_vars`) using Jinja2 templates.

**Example (`inventory/pve_lxc/homepage.yml`):**
```yaml
homepage:
  hosts:
    homepage-node:
      # ...
      immich_api_key: "{{ vault_immich_api_key_homepage }}"
```

## 4. Terraform Secrets

We also store Terraform secrets (like Proxmox API tokens and OCI keys) in Vault for centralized management and backup.

**Automated Generation (Recommended):**
We have provided a helper script to generate the `secrets.auto.tfvars` file for Terraform.

```bash
# Generate secrets for Proxmox
./scripts/get-secrets.sh > terraform/proxmox/secrets.auto.tfvars

# Generate secrets for OCI
./scripts/get-secrets.sh > terraform/oci/secrets.auto.tfvars
```

**Manual Method:**
1.  View secrets: `ansible-vault view ansible/inventory/group_vars/all/vault.yml`
2.  Copy relevant values.
3.  Paste into `terraform/proxmox/terraform.tfvars`.

## Troubleshooting

**Error: "Attempting to decrypt but no vault secrets found"**
- Check that `ansible/.vault_pass` exists and contains the correct password.
- Ensure `ansible.cfg` has `vault_password_file = .vault_pass` under `[defaults]`.
- Try running with explicit password file: `ansible-playbook ... --vault-password-file .vault_pass`

**Error: "input is not vault encrypted data"**
- The file `vault.yml` is currently in plaintext. Run `ansible-vault encrypt ...` to fix it.
