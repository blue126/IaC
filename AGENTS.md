# AGENTS.md

> Instructions for AI coding agents operating in this repository.

## Project Overview

This is a **homelab Infrastructure as Code** repository managing VM/LXC provisioning with **Terraform** and application configuration with **Ansible**. Infrastructure spans Proxmox VE, VMware ESXi, Oracle Cloud, and Netbox IPAM/DCIM.

## Repository Structure

```
terraform/
  proxmox/          # Primary - internal homelab Proxmox VMs/LXCs (bpg/proxmox provider)
  remotecc/         # Outward-facing RemoteCC VMs: employee workspaces, VM500, template, ws-executor
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

**Where these run:** by default on the macOS host, from the checkout or task worktree being worked on, using that checkout's own uv toolchain. Run `./scripts/setup-dev-env.sh` once per checkout (and again after `requirements.txt` or `ansible/requirements.yml` changes); it creates `.venv` from `requirements.txt` and installs the pinned collections into `ansible/collections`. Then `source .venv/bin/activate`. The host's `~/.local/bin/ansible` belongs to another project: it is ansible-core 2.21, outside this repository's `<2.21` pin, and cannot load the `cloud.terraform` dynamic inventory. Never use or change it for this repository. Git-ignored per-checkout state is not shared between worktrees: a new worktree needs `terraform init` in each Terraform root it uses, and `ansible/.vault_pass` comes from the main checkout (pass `--vault-password-file` with that path rather than copying it). Employee lifecycle writes (including onboarding) run only on the `ws-executor` VM, as stated under Ansible Vault.

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

PR validation is `.github/workflows/repo-validation.yml`: it classifies the changed files, then runs `scripts/ci/validate-repository.sh`, which applies only the relevant checks (`terraform fmt -check` / `validate` with `init -backend=false`, `ansible-lint` and `--syntax-check`, documentation and Hugo builds) plus the contract tests under `tests/ci/`. There is no Makefile or general-purpose test framework; deployment behavior is still validated manually. Jenkins pipelines and the GitHub Pages workflow deploy or publish. Never treat a deploy, publish, apply, release, image-push, or other external-write pipeline as PR validation.

## Code Style Guidelines

### Terraform

- **Naming**: `snake_case` for all HCL identifiers (resources, variables, modules, outputs)
- **File organization**: `versions.tf`, `provider.tf`, `variables.tf`, then **one `.tf` file per service** (module call + outputs + `ansible_host` resource)
- **Module structure**: `main.tf`, `variables.tf`, `outputs.tf` (3-file standard)
- **Sensitive variables**: Always mark `sensitive = true`
- **Backend**: HCP Terraform Cloud (`cloud { organization = "homelab-roseville" }`), **Local execution mode** — plan/apply run on this machine, HCP only stores state
- **Workspaces**: `iac-proxmox-lab` → `terraform/proxmox/` (internal homelab), `iac-remotecc` → `terraform/remotecc/` (employee workspaces, VM500, employee template, ws-executor; driven by `wsctl`, not Jenkins), `iac-oci` → `terraform/oci/`. The retired `iac-esxi-lab` workspace was backed up and deleted with user approval on 2026-09-21; `terraform/esxi/` is historical and has no cloud binding. Do not recreate it during init. `terraform/netbox-integration/` intentionally has no `cloud` block and keeps local state; do not add a backend. Read active `cloud` blocks rather than assuming workspace names.
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

- **IaC vault file**: `ansible/inventory/group_vars/all/vault.yml`, auto-decrypted via `ansible/.vault_pass`
- **Naming**: All vault variables use `vault_` prefix. Consumer variables drop the prefix
- **Indirection**: Host-specific → `host_vars/`, group-shared → `group_vars/`, role config → `roles/<role>/defaults/main.yml`
- **Terraform bridge**: `scripts/get-secrets.sh` extracts IaC vault secrets into `*.auto.tfvars` (gitignored). Ansible Vault is the source of truth for IaC credentials.
- **Employee credential exception**: RemoteCC secrets live in one Bitwarden Secrets Manager project, `remotecc` (formerly `EmployeeWorkspace-OCIHub`; the older `EmployeeWorkspace` and `HapiWorkspace` projects are retired): employee workspace SSH and WireGuard private keys, per-workspace HAPI tokens, executor credentials and the Cloudflare token, managed only by the private `remotecc/employee-admin/wsctl` workflow (the old `onboard.sh` alias and the retired `existing` workflow were removed on 2026-11-04). Employee lifecycle writes run only on the `ws-executor` VM (192.168.1.116, pve0) through Semaphore or `sudo /srv/remotecc/employee-admin/wsctl`; the administrator Mac is read-only and refuses writes with `WSCTL_WRITES_ON_EXECUTOR`. Executor credentials (runtime and IaC vault passwords, admin SSH key, HCP Terraform CLI config, Proxmox Terraform variables, site admin token) are the `executor/*` secrets of the `remotecc` project and are materialized under `/run` for one run only; the BWS access token stays on the executor disk. Mail goes out through the site's `/admin/mail` (Resend); the former Microsoft Mail.Send authorization and its OAuth cache are no longer used. Private code and runtime data live under the main checkout's Git-ignored `remotecc/`; see `docs/architecture/remotecc-layout.md`. Do not add these keys to the global Vault or run employee Ansible plays with that Vault alone; the private workflow composes a temporary encrypted runtime Vault from BWS and the IaC Vault.
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
- Commit, push, merge, PR close, history rewrite, and force-push require explicit user authorization.
- Agents may remove or rename an agent-created task worktree, its local task branch, and its matching remote task branch when the user explicitly authorizes that cleanup or the associated PR has merged. Before removal, verify the exact targets, associated PR state, branch/worktree ownership, and that no other worktree uses the branch. Never remove or rename `main`, `master`, tags, remotes, user-owned branches/worktrees, or unrelated task resources.
- Agents may remove task-local generated or untracked files only with explicit user authorization for the resolved targets. Never clean up user changes, unreviewed artifacts, credentials, or files outside the task worktree without target-specific authorization.
- Commit authorization does not authorize push, Draft PR creation, local integration, merge, deployment, or any later external write; obtain separate authorization for each requested boundary.
- Changes to GitHub defaults, Rulesets, protection, permissions, Actions secrets, Environments, deploy/publish triggers, infrastructure, deployments, releases, or other external systems require separate explicit authorization.
- Repository validation must not deploy, publish, apply infrastructure, push images, release artifacts, use production secrets, or write to external systems.

## Reference Documents (load on demand)

When working on specific areas, read the relevant design doc for detailed patterns:

- **Ansible Vault details**: `docs/architecture/ansible-vault-architecture.md`
- **Ansible Role patterns**: `docs/architecture/ansible-role-architecture.md`
- **CI/CD pipeline design**: `docs/architecture/cicd-architecture.md`
- **Deferred-work ↔ GitHub issue 同步**: `docs/architecture/deferred-work-sync.md`

## Project-local Employee Provisioning

- Automatically load this repository's `.agents/skills/employee-provision/SKILL.md` for employee workspace onboarding/provisioning (active `oci-hub`; `existing` is retired), device bundles and delivery, recovery, or changes/reviews of that workflow. This is a project-scoped exception to the default explicit-only skill preference.
- HAPI and WireGuard are access methods for the same employee workspace VM. HAPI is on by default: `wsctl provision` installs the `hapi` role with the desktop, and `wsctl hapi-sync` keeps VM500, the PVE 9443 grants and Cloudflare Access in step with the D1 employee table (no separate onboarding flow). Do not create a second VM or manage one VM from two Terraform states.
- Preserve existing HAPI services, infrastructure prototypes, credentials and runtime evidence. The historical standalone HAPI onboarding executor remains withdrawn; do not invoke it or integrate it into `wsctl` without the new design. See `docs/planning/2026-10-31-hapi-onboarding-withdrawal.md`.
- Reuse the existing administrator `wsctl` entry and read its README before changing the workflow. Extend the existing workflow instead of creating another provisioning engine.
- Do not match generic infrastructure VM work or employee-side bootstrap. For discussion and review, use the skill as read-only operational context; preserve the explicitly selected BMad workflow.
- Skill activation does not authorize apply, credential changes, uploads, email, commits, pushes, or other external writes.

## Workflow Ownership

- BMad skills own planning, task decomposition, checkpoints, implementation sequencing, validation strategy, Git/PR lifecycle, and completion criteria.
- `AGENTS.md` provides repository facts, technical conventions, environment capabilities, and non-negotiable safety boundaries only.
- Workflow ownership does not grant authorization: BMad must stop at any commit, push, merge, deployment, or other external-write boundary that has not been explicitly approved.
- Do not layer an additional generic agent workflow on top of an active BMad workflow.

## Repository Interaction Constraints

- Reply in Chinese; write code comments in English.
- State reasoning and sources when making judgments, and investigate uncertainty instead of fabricating.
- Place learning notes in `docs/learningnotes/` using `YYYY-MM-DD-topic.md`; write Chinese Markdown, define key concepts, and include Q&A summaries.
- Never install packages or system dependencies without explicit user permission.
- If Ansible reports "no hosts matched" or a Terraform dynamic inventory parse failure, run `./scripts/refresh-terraform-state.sh` from the repository root. Inventory uses `cloud.terraform.terraform_provider`.

## Project-Specific Credential Handling

- Only for tasks that require OCI, run `test -d "${HOME}/.oci"` on the host first. If it fails, stop and ask the user to restore or provide approved credentials.
- Never create an empty replacement, search alternate private-key locations, or modify the contents of `~/.oci`.

## Worktrees

- Treat the main checkout as coordination-only; agents work in an assigned task worktree.
- Each task must use one independent worktree and one unique branch.
- Worktrees isolate files and Git state, not Docker, networking, ports, volumes, `/tmp`, or service state. Parallel tasks must use distinct Compose project names, ports, volumes, and temporary paths.
- Worker agents must not modify another task's worktree or merge other task branches. Local integration is allowed only when explicitly assigned and must use a dedicated integration worktree. No agent may merge or close a pull request without explicit authorization.

<!-- bmad:context -->
<!-- Verified 2026-09-05 against e5dd546e965e6878b5edffe093699c81ff1e0dce. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## Minimal-Scope Implementation

- Implement the smallest correct change that satisfies the explicit request and acceptance criteria.
- Preserve the existing architecture and conventions. Do not refactor adjacent code or add abstractions, dependencies, configuration, extension points, or speculative edge-case handling unless they are required for correctness.
- Do not fix unrelated issues. Mention them briefly in the final response instead.
- Run required repository checks and tests directly relevant to the changed behavior. Do not invent new gates or repeat passing checks without a concrete reason.
- Once the acceptance criteria pass, stop immediately. Ask before materially expanding the scope.

<!-- /bmad:context -->

## BMAD / Multica Integration

参与 BMAD/Multica 工作时，先读取 docs/agent/bmad-multica-contract.md。
执行 BMAD Team 协调任务时，再读取 docs/agent/multica-team.md；不另写 BMAD 流程顺序。
执行任何 BMAD 评审前，读取 docs/agent/bmad-review-routing.md 确认该 reviewer 是否走 Claude。

`_bmad-output/` 是本地工作输出，整体不进入版本控制。取消 Git 跟踪必须保留已有本地文件字节；新检出需要历史输出时，从固定历史快照恢复，不覆盖已有本地工作。延期清单的“只增不改/不删除”约束适用于清单内容和同步行为，不要求将本地输出纳入 Git；历史记录的恢复入口见 `docs/architecture/deferred-work-sync.md`。

BMAD 会把"本次不做但该做"的工作追加到 `_bmad-output/implementation-artifacts/deferred-work.md`。该文件只增不改、没有退役机制，也不在日常视野里。**BMAD 工作产生新的延期条目后，把它同步成 GitHub issue：**

```bash
python3 scripts/sync-deferred-work.py --dry-run   # 先看它打算做什么（只读）
python3 scripts/sync-deferred-work.py             # 开 issue / 关闭已退役的 issue
```

脚本永不改写该清单（只读）；退役靠**追加** `retired:` 记录，脚本会把该追加的文本打出来。
设计见 docs/architecture/deferred-work-sync.md。
