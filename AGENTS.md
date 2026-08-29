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

## Git and Pull Request Workflow

### Default Branch and Source of Truth

- During the default-branch migration, the authoritative baseline remains the GitHub remote's actual default branch, currently `origin/master`. After a human completes the GitHub default-branch rename, `origin/main` becomes the source of truth.
- Determine the remote default branch from the GitHub remote before starting work. Do not infer it from the current local branch name or assume that `origin/main` already exists.
- Local `main` and `master` branches are read-only mirrors of the remote default branch. Never develop, edit, commit, or push directly on either branch.

### Task Isolation

- Use one uniquely named branch and one independent worktree per task, created from the latest commit on the verified remote default branch. Do not switch or modify the user's existing checkout.
- Before editing, verify the current branch or detached HEAD, working-tree status, upstream, remotes, remote default branch, existing worktrees, and branch/worktree name conflicts.
- Never stash, reset, clean, overwrite, copy, commit, or otherwise absorb a user's existing uncommitted changes. A dirty checkout may only be bypassed by creating an independent worktree from a verified remote commit.

### Validation and Delivery

- Complete task work in this order: edit, run safe local validation, review the final diff, request any confirmation required by these project rules, commit on the task branch, push the current task branch normally, then create or update a Draft PR against the actual remote default branch.
- Run only repository-defined validation that does not deploy, publish, apply infrastructure, push images, release artifacts, use production secrets, or write to external systems. Report checks that were not run and why; never create an always-successful placeholder check.
- Use Conventional Commits and include the current state, changes, checks run, checks not run, manual migration steps, risks, and rollback method in the Draft PR description.

### Prohibited Git and GitHub Actions

- Agents must never merge or close a PR, force push (including `--force-with-lease`), rewrite history, or directly push `main` or `master`.
- Agents must never delete or rename branches, tags, remotes, or worktrees, and must never clean up user changes.
- Changing the GitHub default branch, Rulesets, branch protection, repository permissions, Actions secrets, Environments, or deploy/publish branch triggers requires separate explicit authorization. Such changes are not implied by ordinary code or documentation work.

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
10. **Subagents allowed**: Agents may delegate independent, clearly scoped tasks to subagents, including when an applicable skill workflow requires an independent review. The primary agent remains responsible for integrating findings and verifying the final result
11. **Minimize deployment scope**: For configuration-only changes, run local validation first, then deploy only the relevant tags (for example `--tags config`) and run the corresponding verification tags. Use a full deployment only when the requested change requires application, dependency, or infrastructure lifecycle tasks; inspect the playbook's task scope before doing so
12. **Package and system dependencies**: Never install packages or system dependencies without explicit user permission. This applies to Docker Sandboxes and the host system.
13. **Ansible inventory recovery**: If Ansible reports "no hosts matched" or a Terraform dynamic inventory parse failure, run `./scripts/refresh-terraform-state.sh` from the repository root. Inventory uses `cloud.terraform.terraform_provider`.

## Docker Sandboxes Environment

- Use `sbx run codex . --kit ./.sandbox-kit -- -c 'mcp_servers.playwright.command="iac-playwright-mcp"'`, `sbx run claude . --kit ./.sandbox-kit`, or `sbx run opencode . --kit ./.sandbox-kit`; do not recreate `.devcontainer/`.
- Claude Code and OpenCode use repository-scoped Playwright MCP adapters. Codex must receive the shown CLI override because an untrusted Codex 0.149.1 project skips `.codex/config.toml`. `iac-playwright-mcp` and Chromium run inside the sandbox microVM.
- Use unique sandbox names for parallel work. Select direct mode or `--clone` deliberately for each task.
- Direct mode from the main checkout supports Git inside the sandbox and mounts the whole workspace, including gitignored files. From a host linked worktree, the agent can edit files but sandbox Git is unavailable because Docker mounts only that worktree and cannot resolve its external `.git` pointer; manage Git on the host and do not mount the common Git directory automatically. Create `--clone` sandboxes only from the main checkout; Git is available in the private clone. The linked-worktree `No Git` smoke result is expected, not a migration defect. See https://docs.docker.com/ai/sandboxes/workflows/git/ and https://docs.docker.com/ai/sandboxes/usage/.
- Verify `ssh-add -L` before Ansible operations and confirm it shows loaded SSH public identities for Ansible authentication. Repository-local `.ssh` private keys are prohibited: SSH private keys stay in the host SSH agent and must not be copied into the repository or sandbox.
- In clone mode, gitignored Vault and Terraform secret files are absent from the private clone. Copy only the required files from `/run/sandbox/source` and never print their contents.
- Before an OCI command, run `test -d "${HOME}/.oci"`. If the directory is missing, stop or skip OCI sandbox creation and ask the user to restore or provide approved OCI credentials; never create an empty directory or search alternate private-key locations. Only when it exists, mount the quoted path `"${HOME}/.oci:ro"`; the read-only mount prevents writes but exposes the OCI API private key to processes in that sandbox.
- OpenCode Desktop connects to a dedicated server sandbox published only on `127.0.0.1:4096`.
- Keep `sbx run ... -- serve ...` for the OpenCode Desktop server in a long-lived attached terminal/session. Do not use `--detached`: it creates/starts only the microVM and does not start the agent server.
- Frontend services must listen on `0.0.0.0` inside the sandbox and publish only the required port to host loopback.
- Recreate a sandbox after Kit changes unless the change is explicitly supported by `sbx kit add`.
