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
- After reviewing the final diff, ask exactly `Ready to commit?` before committing. Commit authorization does not authorize push, Draft PR creation, local integration, merge, deployment, or any later external write; obtain separate authorization for each requested boundary.
- Changes to GitHub defaults, Rulesets, protection, permissions, Actions secrets, Environments, deploy/publish triggers, infrastructure, deployments, releases, or other external systems require separate explicit authorization.
- Repository validation must not deploy, publish, apply infrastructure, push images, release artifacts, use production secrets, or write to external systems.

## Reference Documents (load on demand)

When working on specific areas, read the relevant design doc for detailed patterns:

- **Ansible Vault details**: `docs/designs/ansible-vault-architecture.md`
- **Ansible Role patterns**: `docs/designs/ansible-role-architecture.md`
- **CI/CD pipeline design**: `docs/designs/cicd-architecture.md`
- **Docker Sandbox agent architecture**: `docs/designs/docker-sandbox-agent-architecture.md`

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

## Project-Specific Credential Handling

- OCI credential injection is an IaC project requirement, not a Docker Sandbox topology or Agent runtime.
- Only for tasks that require OCI, run `test -d "${HOME}/.oci"` on the host before launching the Sandbox. If it fails, stop and ask the user to restore or provide approved credentials.
- After the check succeeds, pass `"${HOME}/.oci:ro"` as an additional read-only workspace. Never create an empty replacement, search alternate private-key locations, or use a writable mount.

## Docker Sandbox Environment

- Use the repository `.sandbox-kit`; do not recreate `.devcontainer/`.
- Choose the topology before running an entry command. Treat the main checkout as coordination-only; direct-mode commands must run from an assigned host task worktree. Create clone-mode Sandboxes only from the verified main checkout when Git will be managed inside the Sandbox. Never create a clone-mode Sandbox from a host linked worktree.
- Replace `TASK` with a unique kebab-case task name. Use versioned, task-specific Sandbox names so parallel work and Kit-upgrade testing never reconnect to an unrelated or stale Sandbox.
- Direct mode from an assigned host task worktree:
  - Codex: `sbx run --name iac-codex-TASK-direct-v120 --no-share-skills codex . --kit ./.sandbox-kit`
  - Claude Code: `sbx run --name iac-claude-TASK-direct-v120 claude . --kit ./.sandbox-kit`
  - OpenCode: `sbx run --name iac-opencode-TASK-direct-v120 opencode . --kit ./.sandbox-kit`
- Clone mode from the verified main checkout:
  - Codex: `sbx run --clone --name iac-codex-TASK-clone-v120 --no-share-skills codex . --kit ./.sandbox-kit`
  - Claude Code: `sbx run --clone --name iac-claude-TASK-clone-v120 claude . --kit ./.sandbox-kit`
  - OpenCode: `sbx run --clone --name iac-opencode-TASK-clone-v120 opencode . --kit ./.sandbox-kit`
- OpenCode Desktop must run in a long-lived attached session: `sbx run --name iac-opencode-desktop-TASK-v120 --publish 127.0.0.1:4096:4096 opencode . --kit ./.sandbox-kit -- serve --hostname 0.0.0.0 --port 4096`. Do not use `--detached`; publish the server only through host loopback.
- Each task must use one independent worktree and one unique branch. When multiple tasks share one clone-mode Sandbox, each task also needs its own agent session and runtime namespace. Use separate, uniquely named Sandboxes when tasks require runtime isolation.
- Worktrees isolate files and Git state, not Docker, networking, ports, volumes, `/tmp`, or service state. Shared-Sandbox tasks must use distinct Compose project names, ports, volumes, and temporary paths.
- Worker agents must not modify another task's worktree or merge other task branches. Local integration is allowed only when explicitly assigned and must use a dedicated integration worktree. No agent may merge or close a pull request without explicit authorization.
- The Kit installs a managed Sandbox-only instruction block into the global instruction locations for Codex, Claude Code, and OpenCode while preserving existing non-managed content. Repository rules remain authoritative for project policy and external-write boundaries.
- Recreate a Sandbox after Kit changes unless the change is explicitly supported by `sbx kit add`.
