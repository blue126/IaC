# Ansible Vault Secret Management

**Date:** 2025-12-02
**Topic:** Security, Ansible, IaC

## Context
As our Infrastructure as Code (IaC) repository grew, we faced the challenge of managing sensitive information (API keys, passwords, tokens) securely. Hardcoding these secrets in inventory files or Terraform variables is a security risk, especially when pushing to a remote repository (even a private one). We needed a centralized, encrypted solution that integrates seamlessly with our existing Ansible workflow.

## Solution: Ansible Vault
We chose **Ansible Vault** as our secret management solution. It allows us to encrypt sensitive data files (or individual variables) using a password, which can then be checked into version control.

### Key Concepts

1.  **Vault File**: A YAML file encrypted with AES256. We placed ours at `ansible/inventory/group_vars/all/vault.yml` so it's globally accessible to all hosts.
2.  **Vault Password**: The key to decrypt the vault. We store this in a local file `.vault_pass` which is **gitignored** to prevent accidental leaks.
3.  **Ansible Configuration**: We configured `ansible.cfg` to automatically use the password file, avoiding the need to type the password for every command.

### Implementation Details

#### 1. Configuration (`ansible.cfg`)
We added the `vault_password_file` setting to the `[defaults]` section:
```ini
[defaults]
vault_password_file = .vault_pass
```

#### 2. Directory Structure
```
ansible/
├── .vault_pass              # Contains the vault password (GITIGNORED)
├── ansible.cfg              # Points to .vault_pass
└── inventory/
    └── group_vars/
        └── all/
            └── vault.yml    # Encrypted variables
```

#### 3. Variable Naming Convention
We prefix all vault variables with `vault_` to clearly distinguish them from regular variables and avoid naming collisions.
Example: `vault_proxmox_api_password`

#### 4. Usage in Inventory
In our inventory files (e.g., `homepage.yml`), we reference the encrypted variables using Jinja2 syntax:
```yaml
proxmox_api_password: "{{ vault_proxmox_api_password }}"
```

## Workflow

### Creating/Editing Secrets
To edit the encrypted file, we use:
```bash
ansible-vault edit inventory/group_vars/all/vault.yml
```
This opens the file in the default editor (vim/nano), decrypts it temporarily, and re-encrypts it on save.

### Running Playbooks
Since `ansible.cfg` is configured, running playbooks is unchanged:
```bash
ansible-playbook playbooks/deploy-homepage.yml
```
Ansible automatically decrypts the variables in memory.

## Lessons Learned
- **Structure Matters**: Placing `vault.yml` in `group_vars/all/` ensures it's loaded for every host, which is convenient for a centralized secret store.
- **Gitignore is Critical**: Always double-check that `.vault_pass` is ignored before committing.
- **Terraform Integration**: While Ansible handles its own secrets, we also migrated Terraform secrets (like Proxmox tokens) to Vault for backup and centralization. We created a helper script `scripts/get-secrets.sh` to automatically generate `secrets.auto.tfvars` files from Vault, keeping our workflow secure and efficient.

## Future Learning: HashiCorp Vault
While Ansible Vault is perfect for our current needs (static, file-based encryption), **HashiCorp Vault** represents the enterprise standard for secret management and is a valuable technology to learn for advanced scenarios.

### Why consider HashiCorp Vault?
- **Dynamic Secrets**: Instead of static passwords, Vault can generate temporary credentials (e.g., a database user or AWS key) that expire automatically after 1 hour. This is "Identity-based Security".
- **Centralized Service**: Unlike Ansible Vault (which is just a file), HashiCorp Vault is a running server. This allows for fine-grained access control policies (ACLs) and audit logging of *who* accessed *what* secret and *when*.
- **Encryption as a Service**: It can handle encryption/decryption for applications without them needing to manage keys.

### Potential Workflow
If we were to adopt HashiCorp Vault in the future:
1.  **Deploy**: Run a Vault server (e.g., on a PVE VM or OCI).
2.  **Terraform**: Use the `vault` provider to read secrets dynamically during `terraform apply`. Secrets would never touch the disk.
3.  **Ansible**: Use the `community.hashi_vault` collection to lookup secrets at runtime.

For now, Ansible Vault provides the right balance of security and simplicity for our Homelab, but HashiCorp Vault is on the roadmap for advanced security engineering.

## Future Improvements
- **Terraform Wrapper**: Create a script to automatically inject Vault secrets into Terraform as environment variables (`TF_VAR_...`), enabling a fully automated pipeline.
- **Secret Rotation**: Establish a process for rotating keys and re-encrypting the vault.
