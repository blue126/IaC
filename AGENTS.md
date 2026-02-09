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
scripts/            # Helper scripts (secrets bridge, Netbox fetch, Jenkins tests)
docs/               # Deployment guides, technical guides, learning notes
```

## Key Commands

```bash
# Terraform
terraform init && terraform validate && terraform plan    # in terraform/<env>/
terraform fmt -check -recursive

# Ansible
ansible-playbook playbooks/<service>.yml --syntax-check   # in ansible/
ansible-playbook playbooks/<service>.yml --check --diff    # dry run
ansible-playbook playbooks/<service>.yml                   # deploy
ansible-playbook playbooks/<service>.yml --tags verify     # health check

# Secrets: Ansible Vault → Terraform *.auto.tfvars
./scripts/get-secrets.sh
```

There are **no CI pipelines, Makefiles, or automated test frameworks**. Validation is manual.

## Code Style Guidelines

### Terraform

- **Naming**: `snake_case` for all HCL identifiers (resources, variables, modules, outputs)
- **File organization**: `versions.tf`, `provider.tf`, `variables.tf`, then **one `.tf` file per service** (module call + outputs + `ansible_host` resource)
- **Module structure**: `main.tf`, `variables.tf`, `outputs.tf` (3-file standard)
- **Sensitive variables**: Always mark `sensitive = true`
- **Backend**: HCP Terraform Cloud (`cloud { organization = "homelab-roseville" }`)
- **Lifecycle blocks**: Use `ignore_changes` for clone, full_clone, efidisk, ostemplate, description

### Ansible

- **Role structure**: `tasks/main.yml`, `defaults/main.yml`, `templates/`, `handlers/main.yml`. Omit empty directories
- **Task names**: English, start with a verb — "Install required packages", "Deploy systemd service file"
- **Variable naming**: `snake_case`, service-prefixed — `netbox_port`, `pbs_zfs_pool_name`
- **Playbook pattern**: Every playbook has a **Deploy** play (`roles:`) + a **Verify** play (`tags: [verify]`) with health checks
- **Idempotency**: All tasks must be safely re-runnable. Use `creates:`, `when:`, `failed_when:` guards
- **What to parameterize**: Only values that **realistically vary** (domains, IPs, credentials, paths). Do NOT variablize standard port numbers, protocol-fixed identifiers, or tightly-coupled version numbers
- **Fix playbooks first**: If a playbook fails, fix the playbook — do not bypass with CLI workarounds

### Ansible Vault

- **Single vault file**: `ansible/inventory/group_vars/all/vault.yml`, auto-decrypted via `ansible/.vault_pass`
- **Naming**: All vault variables use `vault_` prefix. Consumer variables drop the prefix
- **Indirection**: Host-specific → `host_vars/`, group-shared → `group_vars/`, role config → `roles/<role>/defaults/main.yml`
- **Terraform bridge**: `scripts/get-secrets.sh` extracts vault secrets into `*.auto.tfvars` (gitignored). Ansible Vault is the single source of truth
- Never store plaintext credentials in inventory or defaults — always use vault indirection

### Naming Conventions

**Principle**: Code identifiers use `snake_case`; filenames and infrastructure names use `kebab-case`.

- `snake_case`: Terraform HCL identifiers, Ansible variables, Ansible group names, Python identifiers
- `kebab-case`: `.tf` filenames, module/role directories, playbook filenames, script filenames, hostnames, systemd units, Docker Compose services, documentation filenames (`YYYY-MM-DD-topic.md`)

### General

- **Comments/code**: English. **Documentation/conversation**: Chinese
- **Commit messages**: Conventional Commits — `feat(scope):`, `fix:`, `chore:`, `docs:` in English
- **Line endings**: LF enforced via `.gitattributes`
- **Shell scripts**: `#!/bin/bash`, quote variables, use `[[ ]]`

### Reference Documents (load on demand)

When working on specific areas, read the relevant design doc for detailed patterns:

- **Ansible Vault details**: `docs/designs/ansible-vault-architecture.md`
- **Ansible Role patterns**: `docs/designs/ansible-role-architecture.md`
- **CI/CD pipeline design**: `docs/designs/cicd-architecture.md`

## AI Agent Rules

0. **CRITICAL: NO AUTOMATIC COMMITS** — Never commit without explicit user authorization. Always ask: "Ready to commit?"
1. **Explain CLI commands** briefly before executing
2. **Incremental changes**: Split large modifications into logical units, one at a time
3. **Multi-step operations**: Present 1–2 steps, then **stop and wait for user confirmation**
4. **Verify after every step**: Use `--syntax-check`, `terraform validate`, etc. Never assume — prove it
5. **Reply in Chinese**, code comments in English
6. **State reasoning and sources** when making judgments
7. **Admit uncertainty** rather than fabricate — investigate first
8. **Ask for info incrementally** — don't request everything at once
9. **Learning notes**: Place in `docs/learningnotes/`, follow `YYYY-MM-DD-topic.md` naming, Chinese markdown, define key concepts, include Q&A summaries
