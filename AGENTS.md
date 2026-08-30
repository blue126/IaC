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
                    # Exception: OCI hosts use a static inventory, not the plugin
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

The repository has Jenkins deployment pipelines and a GitHub Pages documentation workflow, but no general-purpose PR validation workflow, Makefile, or automated test framework. Validation is primarily manual. Never treat a deploy, publish, apply, release, image-push, or other external-write pipeline as PR validation.

## Code Style Guidelines

### Terraform

- **Naming**: `snake_case` for all HCL identifiers (resources, variables, modules, outputs)
- **File organization**: `versions.tf`, `provider.tf`, `variables.tf`, then **one `.tf` file per service** (module call + outputs + `ansible_host` resource)
- **Module structure**: `main.tf`, `variables.tf`, `outputs.tf` (3-file standard)
- **Sensitive variables**: Always mark `sensitive = true`
- **Backend**: HCP Terraform Cloud (`cloud { organization = "homelab-roseville" }`), **Local execution mode** — plan/apply run on this machine, HCP only stores state
- **Workspaces**: `iac-proxmox` → `terraform/proxmox/`, `iac-esxi` → `terraform/esxi/`, `iac-oci` → `terraform/oci/`
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

## Version Control and External-Write Boundaries

- `origin/main` is authoritative; local `main` and `master` are read-only mirrors.
- Never absorb, overwrite, clean, stash, reset, or otherwise modify unrelated user changes.
- Commit, push, merge, PR close, history rewrite, force-push, and branch/tag/remote/worktree deletion or rename require explicit user authorization.
- Changes to GitHub defaults, Rulesets, protection, permissions, Actions secrets, Environments, deploy/publish triggers, infrastructure, deployments, releases, or other external systems require separate explicit authorization.
- Repository validation must not deploy, publish, apply infrastructure, push images, release artifacts, use production secrets, or write to external systems.

## Reference Documents (load on demand)

When working on specific areas, read the relevant design doc for detailed patterns:

- **Ansible Vault details**: `docs/designs/ansible-vault-architecture.md`
- **Ansible Role patterns**: `docs/designs/ansible-role-architecture.md`
- **CI/CD pipeline design**: `docs/designs/cicd-architecture.md`

## Workflow Ownership

- BMad skills own planning, task decomposition, checkpoints, implementation sequencing, validation strategy, Git/PR lifecycle, and completion criteria.
- `AGENTS.md` provides repository facts, technical conventions, environment capabilities, and non-negotiable safety boundaries only.
- Workflow ownership does not grant authorization: BMad must stop at any commit, push, merge, deployment, or other external-write boundary that has not been explicitly approved.
- Do not layer an additional generic agent workflow on top of an active BMad workflow.

## Repository Interaction Constraints

- Reply in Chinese; write code comments in English.
- State reasoning and sources when making judgments, and investigate uncertainty instead of fabricating.
- Place learning notes in `docs/learningnotes/` using `YYYY-MM-DD-topic.md`; write Chinese Markdown, define key concepts, and include Q&A summaries.
- Never install packages or system dependencies without explicit user permission. This applies to Docker Sandboxes and the host system.
- If Ansible reports "no hosts matched" or a Terraform dynamic inventory parse failure, run `./scripts/refresh-terraform-state.sh` from the repository root. Inventory uses `cloud.terraform.terraform_provider`.

## Docker Sandbox Environment

- Use the repository `.sandbox-kit`; do not recreate `.devcontainer/`.
- The standard Codex entry is `sbx run --name iac-codex --no-share-skills codex . --kit ./.sandbox-kit`. `--no-share-skills` is fixed at sandbox creation, keeps Codex system skills and project BMad skills, and excludes Docker's host-shared skills store.
- Codex reads the sandbox-local Playwright adapter from `.codex/config.toml`. Project configuration loads only after the IaC project is trusted; verify trust and `codex mcp list` in each new sandbox.
- Claude Code and OpenCode use repository-scoped Playwright MCP adapters. `iac-playwright-mcp` and Chromium run inside the sandbox microVM.
- Direct mode from the main checkout has Git and mounts the full workspace, including gitignored files. Direct mode from a host linked worktree can edit and validate files but may lack Git because Docker cannot resolve the external common Git directory. Clone mode has private Git state but excludes gitignored files. See https://docs.docker.com/ai/sandboxes/workflows/git/ and https://docs.docker.com/ai/sandboxes/usage/.
- Verify `ssh-add -L` before Ansible operations and confirm it shows loaded SSH public identities for Ansible authentication. Repository-local `.ssh` private keys are prohibited: SSH private keys stay in the host SSH agent and must not be copied into the repository or sandbox.
- In clone mode, gitignored Vault and Terraform secret files are absent from the private clone. Copy only the required files from `/run/sandbox/source` and never print their contents.
- Before an OCI command, run `test -d "${HOME}/.oci"`. If the directory is missing, stop or skip OCI sandbox creation and ask the user to restore or provide approved OCI credentials; never create an empty directory or search alternate private-key locations. Only when it exists, mount the quoted path `"${HOME}/.oci:ro"`; the read-only mount prevents writes but exposes the OCI API private key to processes in that sandbox.
- OpenCode Desktop connects to a dedicated server sandbox published only on `127.0.0.1:4096`.
- Keep `sbx run ... -- serve ...` for the OpenCode Desktop server in a long-lived attached terminal/session. Do not use `--detached`: it creates/starts only the microVM and does not start the agent server.
- Frontend services must listen on `0.0.0.0` inside the sandbox and publish only the required port to host loopback.
- Recreate a sandbox after Kit changes unless the change is explicitly supported by `sbx kit add`.
