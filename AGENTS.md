# AGENTS.md

> Instructions for AI coding agents operating in this repository.

## Project Overview

This is a **homelab Infrastructure as Code** repository managing VM/LXC provisioning with **Terraform** and application configuration with **Ansible**. Infrastructure spans Proxmox VE, VMware ESXi, Oracle Cloud, and Netbox IPAM/DCIM.

## Repository Structure

```
terraform/
  proxmox/          # Primary - Proxmox VMs/LXCs (telmate/proxmox provider)
  esxi/             # ESXi host management (vmware/vsphere provider)
  oci/              # Oracle Cloud Infrastructure
  netbox-integration/ # Netbox resource management
  modules/          # Reusable modules: proxmox-vm/, proxmox-lxc/, esxi-vm/
ansible/
  playbooks/        # Deployment playbooks (one per service)
  roles/            # Modular roles (common, docker, tailscale, netbox, pbs, etc.)
  inventory/        # Dynamic inventory from Terraform state + group/host vars
scripts/            # Helper scripts (setup, secrets bridge, Netbox fetch)
docs/               # Deployment guides, technical guides, learning notes, troubleshooting
```

## Environment Setup

The project uses a **devcontainer** (Ubuntu 24.04) with Terraform, Python 3.12, and Ansible pre-installed.

```bash
# Initial setup (runs automatically in devcontainer post-create)
./scripts/setup_env.sh           # Creates venv, installs pip deps + Ansible Galaxy collections

# Ansible Galaxy collections (if needed manually)
ansible-galaxy install -r ansible/requirements.yml
```

## Build / Validate / Deploy Commands

### Terraform

```bash
cd terraform/proxmox              # or terraform/esxi, terraform/netbox-integration

terraform init                    # Initialize providers and backend
terraform validate                # Syntax and config validation
terraform fmt -check -recursive   # Check formatting (no config enforced, but use this)
terraform plan                    # Preview changes
terraform apply                   # Apply changes

# Pull remote state for Ansible dynamic inventory
./scripts/refresh_terraform_state.sh
```

### Ansible

```bash
cd ansible

# Syntax check
ansible-playbook playbooks/deploy-netbox.yml --syntax-check

# Dry run (check mode)
ansible-playbook playbooks/deploy-netbox.yml --check --diff

# Deploy a service
ansible-playbook playbooks/deploy-netbox.yml

# Run only verification tasks
ansible-playbook playbooks/deploy-netbox.yml --tags verify

# Run a specific role tag
ansible-playbook playbooks/deploy-netbox.yml --tags pbs_storage

# Test host connectivity
ansible pbs -m ping
ansible-inventory --list          # View resolved inventory
```

### Linting

```bash
# Ansible lint (note: many checks disabled in .ansible-lint)
ansible-lint ansible/

# Terraform format
terraform fmt -recursive terraform/

# YAML syntax validation (quick check)
python3 -c "import yaml; yaml.safe_load(open('path/to/file.yml'))"
```

There are **no CI pipelines, Makefiles, or automated test frameworks**. Validation is manual. Ansible playbooks include built-in `[verify]` tagged plays for deployment health checks.

### Secrets

```bash
# Extract Ansible Vault secrets into Terraform *.auto.tfvars files
./scripts/get-secrets.sh

# Vault is auto-decrypted via ansible/.vault_pass (gitignored)
# Vault-managed secrets are prefixed: vault_proxmox_password, vault_tailscale_auth_key, etc.
```

## Code Style Guidelines

### Terraform

- **Naming**: `snake_case` for all resources, variables, modules, outputs
- **File organization** per environment directory:
  - `versions.tf` — terraform block, cloud backend, required_providers
  - `provider.tf` — provider configuration
  - `variables.tf` — all input variables (with `description` and `type`)
  - **One `.tf` file per service** (e.g., `netbox.tf`, `homepage.tf`) containing: module call + outputs + `ansible_host` resource
- **Module structure**: `main.tf`, `variables.tf`, `outputs.tf` (3-file standard)
- **Sensitive variables**: Always mark `sensitive = true`
- **Backend**: HCP Terraform Cloud (`cloud { organization = "homelab-roseville" }`)
- **Lifecycle blocks**: Use `ignore_changes` for clone, full_clone, efidisk, ostemplate, description
- **Comments**: English, `#` style. Explain non-obvious choices inline

### Ansible

- **Role structure**: Standard layout — `tasks/main.yml`, `defaults/main.yml`, `templates/`, `handlers/main.yml`. Keep minimal; omit empty directories
- **Task names**: Descriptive English, start with a verb — "Install required packages", "Deploy systemd service file", "Enable and start service"
- **Variable naming**: `snake_case`, service-prefixed — `netbox_port`, `pbs_zfs_pool_name`, `immich_upload_dir`
- **Playbook pattern**: Every playbook has two plays:
  1. **Deploy** play with `roles:`
  2. **Verify** play with `tags: [verify]` containing health checks (`wait_for`, `uri`, `assert`)
- **Conditionals**: Use boolean flags for optional features (e.g., `pbs_zfs_use_special_vdev: false`)
- **Idempotency**: All tasks must be safely re-runnable. Use `creates:`, `when:`, `failed_when:` guards
- **What to parameterize**: Only extract values into variables when they **realistically vary** across environments (domains, IPs, credentials, file paths). Do NOT variablize standard port numbers (e.g., 8007 for PBS, 5678 for n8n, 21116 for RustDesk), protocol-fixed identifiers (e.g., `root@pam`, `backup@pbs`), or software version numbers that are tightly coupled to the role logic
- **Fix playbooks first**: If an Ansible playbook fails, fix the playbook — do not bypass with CLI workarounds

### Ansible Vault Architecture

**Single vault file**: `ansible/inventory/group_vars/all/vault.yml` — all secrets in one encrypted file, auto-decrypted via `ansible/.vault_pass` (gitignored).

**Naming convention**: All vault variables use `vault_` prefix (e.g., `vault_pbs_root_password`). Consumer variables drop the prefix (e.g., `pbs_root_password`).

**Indirection pattern — choose by variable scope**:

| Scope | Pattern | Alias location | Example |
|-------|---------|----------------|---------|
| Host-specific secrets | Pattern A | `inventory/host_vars/<host>.yml` | `homepage.yml`: `proxmox_api_password: "{{ vault_proxmox_api_password_homepage }}"` |
| Group-shared secrets | Pattern A | `inventory/group_vars/<group>.yml` | `tailscale.yml`: `tailscale_auth_key: "{{ vault_tailscale_auth_key }}"` |
| Role config secrets (no host/group distinction) | Pattern B | `roles/<role>/defaults/main.yml` | `caddy/defaults`: `cloudflare_api_token: "{{ vault_cloudflare_api_token }}"` |
| Terraform-only secrets | No alias | Only in vault, consumed by `scripts/get-secrets.sh` | `vault_proxmox_password` |

**Terraform secrets bridge**: Ansible Vault is the **single source of truth** for all secrets. Terraform does not have its own secrets store — instead, `scripts/get-secrets.sh` extracts `vault_` variables from the encrypted vault and writes them into `*.auto.tfvars` files (gitignored) that Terraform reads at plan/apply time. This means: add secrets to the Ansible vault first, then run `get-secrets.sh` to sync them to Terraform.

**Rules**:
- Never store plaintext credentials in inventory files or role defaults — always use vault indirection
- When adding a new secret: add `vault_` variable to vault.yml, then create the alias in the appropriate location per the scope table above
- Role defaults with vault references must include a comment: `# ... (vault indirect reference)`
- Playbook `vars:` should NOT be used for vault indirection — use role defaults or inventory instead

### Python

- **Version**: 3.12 (devcontainer default)
- **No linter configured**: Follow PEP 8 conventions, use `snake_case`
- **Scripts live in** `scripts/` with clear docstring/header comments

### Shell Scripts

- **Use** `#!/bin/bash` and `set -e`
- **Use** `"$(dirname "${BASH_SOURCE[0]}")"` for relative paths
- **No shellcheck configured**: Follow best practices (quote variables, use `[[ ]]`)

### General

- **Line endings**: LF enforced via `.gitattributes` for all IaC file types
- **Comments/code**: Always in **English**
- **Documentation/conversation**: Always in **Chinese** (unless explicitly asked for English)
- **Commit messages**: Conventional Commits — `feat(scope):`, `fix:`, `chore:`, `docs:` in English

## AI Agent Rules

From `.github/copilot-instructions.md` and `.agent/`:

0. **🔴 CRITICAL: NO AUTOMATIC COMMITS** — You must **NEVER** commit code without explicit, specific authorization from the user for that specific commit. Even if a workflow implies a commit at the end, you must STOP and ask: "Ready to commit?"
1. **Explain CLI commands** briefly before executing them
2. **Incremental changes**: Large modifications must be split into logical units, one at a time
3. **Multi-step operations**: Present 1–2 steps at a time. **Stop and wait for user confirmation** before proceeding to the next step. Do NOT execute multiple logical steps in a row without pausing for approval — even if the steps seem straightforward
4. **Verify after every step**: Each step must be validated before proceeding to the next. Use syntax checks (`--syntax-check`), variable resolution (`ansible ... -m debug`), `terraform validate`, or other appropriate verification. Never assume a change is correct — prove it
5. **Reply in Chinese**, code comments in English
6. **State reasoning and sources** when making judgments
7. **Admit uncertainty** rather than fabricate answers — investigate first
8. **Ask for info incrementally** — don't request everything at once
9. **Learning notes**: Created from work since last commit; placed in `docs/learningnotes/` following `YYYY-MM-DD-topic-description.md` naming; written in Chinese markdown; define key concepts; include Q&A summaries

## Common Patterns

### Per-Service Terraform File

Each service gets its own `.tf` file with this structure:

```hcl
module "service_name" {
  source = "../modules/proxmox-vm"
  # ... config ...
}

resource "ansible_host" "service_name" {
  name   = "service_name"
  groups = ["group_name"]
  variables = { ansible_host = "..." }
  depends_on = [module.service_name]
}

output "service_name_ip" { value = module.service_name.ip }
```

### Ansible Verification Play

Every deployment playbook ends with a verification play:

```yaml
- name: Verify Service Deployment
  hosts: service_name
  become: yes
  tags: [verify]
  tasks:
    - name: Wait for service port
      wait_for:
        port: "{{ service_port }}"
        timeout: 60
    - name: Check HTTP endpoint
      uri:
        url: "http://localhost:{{ service_port }}"
        status_code: [200, 301, 302]
```
