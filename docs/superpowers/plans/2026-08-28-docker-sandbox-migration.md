# Docker Sandboxes Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository's local devcontainer workflow with one reusable Docker Sandboxes Kit that supports Codex, Claude Code, OpenCode, sandbox-local Playwright MCP, SSH agent forwarding, OCI opt-in key mounting, and OpenCode Desktop.

**Architecture:** A project-local `kind: mixin` Kit installs the shared IaC and browser toolchain into each agent-specific microVM. Claude Code and OpenCode use two tiny repository-scoped MCP adapters; Codex receives the same `iac-playwright-mcp` command through a per-launch CLI override. Migration is additive until Codex, Claude, OpenCode, Playwright, SSH forwarding, Terraform/Ansible, OCI mounting, and OpenCode Desktop pass smoke tests; only then is `.devcontainer/` retired.

**Tech Stack:** Docker Sandboxes `sbx` 0.39.0+, Kit schema v2, Terraform 1.14.9, Python venv, Ansible Core `>=2.16,<2.21`, Playwright MCP 0.0.78, Chromium, TOML, JSON, YAML, Bash.

**Spec:** `docs/designs/2026-08-28-docker-sandbox-migration.md`

## Global Constraints

- Never create a Git commit without explicit user authorization; use a `Ready to commit?` gate instead of automatic commit steps.
- Explain every CLI command briefly before running it.
- Execute no more than one or two tasks before stopping for user confirmation.
- Do not run Terraform `plan` or `apply`, and do not run any Ansible deployment during this migration.
- Do not deploy, modify, stop, or delete any homelab VM.
- Preserve historical wording under `docs/incidents/`, `docs/learningnotes/`, and `docs/archive/`.
- Use direct mode by default in smoke tests; users select `--clone` when they need private-clone isolation.
- Direct mode from the main checkout supports sandbox Git. From a host linked worktree, the agent can edit files but sandbox Git cannot resolve the external `.git` pointer; Git remains host-managed and the common Git directory must not be auto-mounted. Create `--clone` sandboxes only from the main checkout; the private clone has Git. Treat linked-worktree `No Git` smoke output as expected Docker behavior, not a migration failure.
- Keep agent model authentication in Docker's built-in agent Kits; never copy host agent credentials into the project Kit.
- Before an OCI command, run `test -d "${HOME}/.oci"`; if it fails, stop or skip OCI sandbox creation and ask the user to restore or provide approved OCI credentials. Never create an empty directory or search alternate private-key locations. Only then add the quoted `"${HOME}/.oci:ro"` extra workspace.
- Code and comments are English; project documentation and conversation are Chinese.
- Terraform/Ansible naming and validation rules in `AGENTS.md` remain authoritative.

---

## File Structure

**Create**

- `.sandbox-kit/spec.yaml` — shared system packages, Terraform, Python/Ansible, Playwright MCP, Chromium, and egress contract.
- `.sandbox-kit/files/home/.local/bin/iac-playwright-mcp` — one stable command used by both project adapters and the Codex CLI override.
- `opencode.json` — OpenCode project MCP adapter and server defaults.

**Replace or modify**

- `.mcp.json` — replace the old host HTTP Playwright endpoint with sandbox-local stdio.
- `.gitignore` — make `.mcp.json` trackable and later remove `.devcontainer/.generated/`.
- `.worktreeinclude` — remove `.mcp.json` once it becomes tracked.
- `ansible/ansible.cfg` — stop forcing a private-key file.
- `ansible/inventory/oci/hosts.yml` — stop forcing a private-key file.
- `terraform/esxi/llm-server.tf` — remove the inventory variable that forces a private-key file.
- `README.md` — replace devcontainer setup with Docker Sandboxes operations and credential boundaries.
- `AGENTS.md` — replace the OpenCode Dev Container section with Docker Sandbox instructions.
- `CLAUDE.md` — reduce to the authoritative `AGENTS.md` pointer.
- Current operational documents identified by the live-reference audit.

**Delete only after Phase 1 approval**

- `.devcontainer/ARCHITECTURE.md`
- `.devcontainer/Dockerfile`
- `.devcontainer/README.md`
- `.devcontainer/devcontainer-lock.json`
- `.devcontainer/devcontainer.json`
- `.devcontainer/host-setup.sh`
- `.devcontainer/setup-agents.sh`
- `.devcontainer/setup-project.sh`
- `ansible/playbooks/deploy-devcontainer.yml`
- The matching import block in `ansible/playbooks/site.yml`

---

### Task 1: Build the reusable IaC and Playwright Kit

**Files:**

- Create: `.sandbox-kit/spec.yaml`
- Create: `.sandbox-kit/files/home/.local/bin/iac-playwright-mcp`

**Interfaces:**

- Consumes: Docker built-in Codex, Claude, and OpenCode images with Node.js, npm, UID 1000 user `agent`, passwordless sudo, and `/home/agent`.
- Produces: `terraform`, `python3`, `ansible`, `ansible-playbook`, `ansible-inventory`, `ansible-galaxy`, `ansible-lint`, `playwright-mcp`, and `iac-playwright-mcp` on the sandbox shell path; Chromium under `/opt/ms-playwright`.

- [ ] **Step 1: Record the expected pre-implementation failure**

Run:

```bash
sbx kit validate .sandbox-kit
```

Expected: FAIL because `.sandbox-kit/spec.yaml` does not exist.

- [ ] **Step 2: Create the common MCP wrapper**

Create `.sandbox-kit/files/home/.local/bin/iac-playwright-mcp` with executable mode:

```bash
#!/bin/sh
set -eu

exec playwright-mcp --headless --isolated "$@"
```

Then set the repository file mode explicitly:

```bash
chmod 0755 .sandbox-kit/files/home/.local/bin/iac-playwright-mcp
```

- [ ] **Step 3: Create the Kit v2 manifest**

Create `.sandbox-kit/spec.yaml` with this structure and values:

```yaml
schemaVersion: "2"
kind: mixin
name: iac-toolchain
version: "1.0.0"
displayName: IaC Toolchain
description: Terraform, Ansible, Python, and sandbox-local Playwright MCP for the IaC repository.

permissions:
  network:
    allow:
      - archive.ubuntu.com
      - security.ubuntu.com
      - ports.ubuntu.com
      - download.docker.com
      - releases.hashicorp.com
      - pypi.org
      - files.pythonhosted.org
      - galaxy.ansible.com
      - github.com
      - objects.githubusercontent.com
      - registry.npmjs.org
      - cdn.playwright.dev
      - playwright.download.prss.microsoft.com

environment:
  variables:
    PLAYWRIGHT_BROWSERS_PATH: /opt/ms-playwright

setup:
  install:
    - description: Install base operating system packages
      command: >-
        apt-get update &&
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends
        ca-certificates curl jq python3 python3-pip python3-venv unzip

    - description: Install Terraform 1.14.9 with checksum verification
      command: >-
        set -eu;
        terraform_version=1.14.9;
        architecture="$(dpkg --print-architecture)";
        case "$architecture" in amd64|arm64) ;; *) echo "unsupported architecture: $architecture" >&2; exit 1;; esac;
        archive="terraform_${terraform_version}_linux_${architecture}.zip";
        cd /tmp;
        curl -fsSLO "https://releases.hashicorp.com/terraform/${terraform_version}/${archive}";
        curl -fsSLO "https://releases.hashicorp.com/terraform/${terraform_version}/terraform_${terraform_version}_SHA256SUMS";
        grep " ${archive}$" "terraform_${terraform_version}_SHA256SUMS" | sha256sum -c -;
        unzip -o "$archive";
        install -m 0755 terraform /usr/local/bin/terraform;
        rm -f terraform "$archive" "terraform_${terraform_version}_SHA256SUMS"

    - description: Install Python and Ansible dependencies in an isolated virtual environment
      command: >-
        set -eu;
        python3 -m venv /opt/iac-venv;
        /opt/iac-venv/bin/pip install --upgrade pip;
        /opt/iac-venv/bin/pip install
        'ansible-core>=2.16,<2.21'
        ansible-lint ansible-dev-tools proxmoxer requests netaddr pyvmomi passlib
        'notion-client==2.2.1';
        for executable in ansible ansible-config ansible-galaxy ansible-inventory ansible-lint ansible-playbook ansible-vault; do
          ln -sfn "/opt/iac-venv/bin/${executable}" "/usr/local/bin/${executable}";
        done;
        grep -Fqx 'export VIRTUAL_ENV=/opt/iac-venv' /etc/sandbox-persistent.sh ||
          printf '%s\n' 'export VIRTUAL_ENV=/opt/iac-venv' 'export PATH=/opt/iac-venv/bin:$PATH' >> /etc/sandbox-persistent.sh

    - description: Install Ansible collections outside the workspace
      command: >-
        set -eu;
        install -d -o 1000 -g 1000 /home/agent/.ansible/collections;
        /opt/iac-venv/bin/ansible-galaxy collection install
        --collections-path /home/agent/.ansible/collections
        community.general community.vmware cloud.terraform community.docker
        ansible.posix netbox.netbox ansible.windows;
        chown -R 1000:1000 /home/agent/.ansible

    - description: Install Playwright MCP and Chromium inside the sandbox
      command: >-
        set -eu;
        npm install --global '@playwright/mcp@0.0.78';
        playwright_cli="$(npm root --global)/@playwright/mcp/node_modules/playwright/cli.js";
        test -f "$playwright_cli";
        install -d -m 0755 /opt/ms-playwright;
        PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright node "$playwright_cli" install --with-deps chromium;
        chmod -R a+rX /opt/ms-playwright;
        install -m 0755 /home/agent/.local/bin/iac-playwright-mcp /usr/local/bin/iac-playwright-mcp
```

Do not add model-provider credentials or a blanket `**` network allow rule.

- [ ] **Step 4: Validate manifest syntax and wrapper mode**

Run:

```bash
sbx kit validate .sandbox-kit
test -x .sandbox-kit/files/home/.local/bin/iac-playwright-mcp
```

Expected: Kit validation succeeds and `test` exits 0.

- [ ] **Step 5: Review dependency duplication explicitly**

Compare the Python and collection lists in `.sandbox-kit/spec.yaml` with `requirements.txt` and `ansible/requirements.yml`:

```bash
sed -n '1,120p' requirements.txt
sed -n '1,120p' ansible/requirements.yml
rg -n 'ansible-core|ansible-lint|notion-client|community\.general|ansible\.windows' .sandbox-kit/spec.yaml
```

Expected: every current Python requirement and every Ansible collection appears in the Kit. Document in the Kit description or README that these lists must change together because Kit install hooks run before workspace files are available.

- [ ] **Step 6: Stop for review**

Show the new Kit diff and validation output. Do not commit. Ask whether to continue to Task 2.

---

### Task 2: Add Claude/OpenCode Playwright MCP adapters and Codex CLI override

**Files:**

- Delete: obsolete `.codex/config.toml`
- Modify: `.mcp.json`
- Create: `opencode.json`
- Modify: `.gitignore`
- Modify: `.worktreeinclude`

**Interfaces:**

- Consumes: `/usr/local/bin/iac-playwright-mcp` from Task 1.
- Produces: one MCP server named `playwright` for Codex, Claude Code, and OpenCode without touching Docker-managed user configuration; Codex receives it through its launch arguments.

- [ ] **Step 1: Capture the old Claude MCP state and historical Codex adapter state**

Run:

```bash
jq . .mcp.json
git check-ignore -v .mcp.json
test ! -f opencode.json
```

Expected: `.mcp.json` points to `host.docker.internal:8931`, is ignored, and the OpenCode adapter does not exist. Historical intent: this migration originally added a Codex project adapter, before runtime validation established that it is skipped for untrusted projects.

- [ ] **Step 2: Remove the ineffective Codex project configuration and use a CLI override**

Do not create a Codex project adapter. Remove any existing `.codex/config.toml` and start every Codex sandbox with:

```bash
sbx run --name iac-codex codex . --kit ./.sandbox-kit -- -c 'mcp_servers.playwright.command="iac-playwright-mcp"'
```

Codex 0.149.1 skips project configuration when the project lacks a persistent trust entry. The override is verified to list both the sandbox-local `playwright` server and Docker `mcp-gateway`:

```bash
codex -c 'mcp_servers.playwright.command="iac-playwright-mcp"' mcp list
```

- [ ] **Step 3: Replace the Claude adapter**

Replace `.mcp.json` with:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "iac-playwright-mcp"
    }
  }
}
```

- [ ] **Step 4: Create the OpenCode adapter**

Create `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "playwright": {
      "type": "local",
      "command": ["iac-playwright-mcp"],
      "enabled": true
    }
  }
}
```

- [ ] **Step 5: Make project adapters trackable**

Remove `.mcp.json` from `.gitignore`. Remove the `.mcp.json` entry and its now-obsolete comment from `.worktreeinclude`, because tracked files already appear in Git worktrees and Docker clone mode.

- [ ] **Step 6: Parse the two project adapters and verify the Codex override**

Run:

```bash
test ! -e .codex/config.toml
jq -e '.mcpServers.playwright.command == "iac-playwright-mcp"' .mcp.json
jq -e '.mcp.playwright.command == ["iac-playwright-mcp"] and (.server == null)' opencode.json
codex -c 'mcp_servers.playwright.command="iac-playwright-mcp"' mcp list
git check-ignore .mcp.json && exit 1 || true
git diff --check
```

Expected: the ineffective Codex project configuration is absent, both project adapter assertions succeed, the Codex override lists local `playwright` and Docker `mcp-gateway`, and `.mcp.json` is no longer ignored.

- [ ] **Step 7: Stop for review**

Show the adapter diff and parsing evidence. Do not commit. Ask whether to continue to Tasks 3–4.

---

### Task 3: Normalize SSH authentication for agent forwarding

**Files:**

- Modify: `ansible/ansible.cfg`
- Modify: `ansible/inventory/oci/hosts.yml`
- Modify: `terraform/esxi/llm-server.tf`

**Interfaces:**

- Consumes: Docker Sandboxes automatic forwarding of host `SSH_AUTH_SOCK`.
- Produces: SSH connections that use standard OpenSSH identity discovery and the forwarded agent instead of a sandbox-local private-key path.

- [ ] **Step 1: Prove the hard-coded paths currently exist**

Run:

```bash
rg -n 'private_key_file|ansible_ssh_private_key_file' \
  ansible/ansible.cfg ansible/inventory/oci/hosts.yml terraform/esxi/llm-server.tf
```

Expected: three hard-coded key-path references are reported.

- [ ] **Step 2: Remove only the forced key-path settings**

Apply these minimal changes:

- Delete `private_key_file = ~/.ssh/id_ed25519` from `ansible/ansible.cfg`.
- Delete `ansible_ssh_private_key_file: ~/.ssh/id_ed25519` from `ansible/inventory/oci/hosts.yml`.
- Delete `ansible_ssh_private_key_file = "~/.ssh/id_ed25519"` from the `ansible_host.llm_server.variables` map in `terraform/esxi/llm-server.tf`.

Do not change usernames, hostnames, connection timeouts, or host-key policy in this task.

- [ ] **Step 3: Validate local syntax**

Run:

```bash
terraform fmt -check terraform/esxi/llm-server.tf
cd ansible
ansible-inventory --inventory inventory/oci/hosts.yml --list >/dev/null
ansible-config dump --only-changed | rg 'DEFAULT_PRIVATE_KEY_FILE' && exit 1 || true
```

Expected: Terraform formatting passes, OCI YAML inventory parses, and Ansible no longer reports an explicit private-key file.

- [ ] **Step 4: Confirm no active forced SSH key remains**

From the repository root, run:

```bash
rg -n 'ansible_ssh_private_key_file|private_key_file\s*=' \
  ansible terraform \
  --glob '!ansible/collections/**'
```

Expected: no active configuration matches; documentation matches are handled later.

---

### Task 4: Update primary user and agent documentation

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Replace: `CLAUDE.md`

**Interfaces:**

- Consumes: Task 1 commands, Task 2 MCP adapters, and Task 3 SSH behavior.
- Produces: authoritative, current setup instructions for humans and all three agents.

- [ ] **Step 1: Replace the README development-environment identity**

Change the Tech Stack row from `VS Code devcontainer (Ubuntu 24.04)` to `Docker Sandboxes (isolated microVMs)`.

Replace the old Environment Setup block with a Chinese Docker Sandboxes section containing these exact operational examples:

```bash
# Direct mode
sbx run --name iac-codex codex . --kit ./.sandbox-kit -- -c 'mcp_servers.playwright.command="iac-playwright-mcp"'
sbx run --name iac-claude claude . --kit ./.sandbox-kit
sbx run --name iac-opencode opencode . --kit ./.sandbox-kit

# Clone mode: add --clone when the sandbox is first created
sbx run --clone --name iac-codex-clone codex . --kit ./.sandbox-kit -- -c 'mcp_servers.playwright.command="iac-playwright-mcp"'

# OCI: expose the API signing-key directory only for OCI work
test -d "${HOME}/.oci" || { echo 'OCI credentials directory is missing; stop and ask the user to restore or provide approved OCI credentials.' >&2; exit 1; }
sbx run --name iac-oci codex . "${HOME}/.oci:ro" --kit ./.sandbox-kit -- -c 'mcp_servers.playwright.command="iac-playwright-mcp"'

# OpenCode Desktop server
sbx run --name iac-opencode-desktop \
  --publish 127.0.0.1:4096:4096 \
  opencode . --kit ./.sandbox-kit \
  -- serve --hostname 0.0.0.0 --port 4096
```

The surrounding Chinese text must state:

- `ssh-add -L` must show a loaded SSH public identity used for Ansible authentication before Ansible SSH work.
- Direct mode sees gitignored `ansible/.vault_pass` and generated tfvars in the host workspace.
- Clone mode must copy required untracked files from `/run/sandbox/source` into the private clone manually.
- Direct mode from the main checkout supports sandbox Git. A host linked worktree permits file editing but not sandbox Git because its external `.git` pointer cannot be resolved; manage Git on the host and do not mount the common Git directory. Create clone mode only from the main checkout; Git is available in the private clone. Link to the Docker host-worktree Git and clone-mode documentation.
- After `test -d "${HOME}/.oci"` succeeds, `"${HOME}/.oci:ro"` prevents modification but permits sandbox processes to read the OCI API key; a missing directory stops or skips OCI creation and requires the user to restore or provide approved OCI credentials. Do not create an empty directory or search alternate private-key locations.
- Kit changes require sandbox recreation.
- Frontend services must bind `0.0.0.0`; publish their ports to host loopback for human inspection.
- Playwright MCP and headless Chromium run inside the microVM.

- [ ] **Step 2: Replace the obsolete AGENTS OpenCode section**

Replace `## OpenCode Container Environment` with `## Docker Sandboxes Environment` and include these rules:

```markdown
## Docker Sandboxes Environment

- Use `sbx run codex . --kit ./.sandbox-kit -- -c 'mcp_servers.playwright.command="iac-playwright-mcp"'`, `sbx run claude . --kit ./.sandbox-kit`, or `sbx run opencode . --kit ./.sandbox-kit`; do not recreate `.devcontainer/`.
- Claude Code and OpenCode use repository-scoped Playwright MCP adapters. Codex uses the CLI override because untrusted Codex 0.149.1 projects skip their project configuration. `iac-playwright-mcp` and Chromium run inside the sandbox microVM.
- Use unique sandbox names for parallel work. Select direct mode or `--clone` deliberately for each task.
- Verify `ssh-add -L` before Ansible operations. SSH private keys stay in the host SSH agent and must not be copied into the repository or sandbox.
- In clone mode, gitignored Vault and Terraform secret files are absent from the private clone. Copy only the required files from `/run/sandbox/source` and never print their contents.
- Mount `"${HOME}/.oci:ro"` only for OCI Terraform work. The read-only mount prevents writes but exposes the OCI API private key to processes in that sandbox.
- OpenCode Desktop connects to a dedicated server sandbox published only on `127.0.0.1:4096`.
- Frontend services must listen on `0.0.0.0` inside the sandbox and publish only the required port to host loopback.
- Recreate a sandbox after Kit changes unless the change is explicitly supported by `sbx kit add`.
```

- [ ] **Step 3: Replace CLAUDE.md with the authoritative pointer**

Use exactly:

```markdown
# Claude Code Instructions

Read and follow [AGENTS.md](./AGENTS.md) as the authoritative project instructions.
```

- [ ] **Step 4: Audit the primary docs**

Run:

```bash
rg -n -i 'devcontainer|/workspaces/IaC' README.md AGENTS.md CLAUDE.md
rg -n 'Docker Sandboxes|\$\{HOME\}/\.oci:ro|ssh-add -L|iac-playwright-mcp' README.md AGENTS.md
git diff --check
```

Expected: no obsolete devcontainer or `/workspaces/IaC` guidance remains in the three primary files; all four new operational concepts are documented.

- [ ] **Step 5: Checkpoint before external sandbox creation**

Show Tasks 3–4 diffs and local validation. Stop and request explicit approval to let `sbx` download packages, create smoke-test microVMs, and write sandbox state outside the repository. Do not commit.

---

### Task 5: Execute Phase 1 smoke tests without retiring devcontainer

**Files:** None expected.

**Interfaces:**

- Consumes: Tasks 1–4 and host `sbx` login, network policy, SSH agent, model authentication.
- Produces: evidence that the new environment works while `.devcontainer/` remains available as rollback.

- [ ] **Step 1: Run host preflight**

Explain that these commands verify host readiness without changing infrastructure, then run:

```bash
sbx version
sbx diagnose
ssh-add -L >/dev/null
sbx kit validate .sandbox-kit
```

Expected: `sbx` is 0.39.0 or newer, diagnose reports no blocking error, an SSH public key is loaded, and Kit validation succeeds.

- [ ] **Step 2: Create three uniquely named smoke sandboxes**

Explain that each command downloads/installs the Kit into a new local microVM and does not deploy homelab resources, then run sequentially so failures are attributable:

```bash
sbx create --name iac-smoke-codex --kit ./.sandbox-kit codex .
sbx create --name iac-smoke-claude --kit ./.sandbox-kit claude .
sbx create --name iac-smoke-opencode --kit ./.sandbox-kit opencode .
```

Expected: all three sandboxes are created. If a request is blocked, inspect the matching exact command (`sbx policy log iac-smoke-codex`, `sbx policy log iac-smoke-claude`, or `sbx policy log iac-smoke-opencode`), add only the required host to `permissions.network.allow`, recreate that sandbox, and repeat.

- [ ] **Step 3: Verify the common toolchain in each sandbox**

Run the same checks in all three sandboxes:

```bash
for sandbox_name in iac-smoke-codex iac-smoke-claude iac-smoke-opencode; do
  sbx exec "$sandbox_name" -- sh -lc '
    terraform version | head -1
    python3 --version
    ansible --version | head -1
    ansible-galaxy collection list
    command -v iac-playwright-mcp
    command -v playwright-mcp
    ssh-add -L >/dev/null
  '
done
```

Expected:

- Terraform reports `v1.14.9`.
- `python3` resolves through `/opt/iac-venv/bin` in login shells.
- Ansible Core is at least 2.16 and lower than 2.21.
- All seven required collections are listed.
- Both Playwright commands exist.
- SSH agent forwarding exposes at least one public key.

- [ ] **Step 4: Launch Chromium entirely inside each microVM**

Run this in all three sandboxes:

```bash
for sandbox_name in iac-smoke-codex iac-smoke-claude iac-smoke-opencode; do
  sbx exec "$sandbox_name" -- sh -lc '
    playwright_root="$(npm root --global)/@playwright/mcp/node_modules/playwright"
    NODE_PATH="$(dirname "$playwright_root")" node - <<"NODE"
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto("data:text/html,<title>sbx-browser-ok</title>");
  console.log(await page.title());
  await browser.close();
})();
NODE
  '
done
```

Expected: `sbx-browser-ok` is printed and no host browser process is required.

- [ ] **Step 5: Verify agent-specific MCP discovery**

Run from the project workspace inside each matching sandbox. The Codex command must include the same per-launch override used by every `sbx run` invocation:

```bash
sbx exec iac-smoke-codex -- sh -lc 'codex -c '\''mcp_servers.playwright.command="iac-playwright-mcp"'\'' mcp list'
sbx exec iac-smoke-claude -- sh -lc 'claude mcp list'
sbx exec iac-smoke-opencode -- sh -lc 'opencode mcp list'
```

Expected: each client lists `playwright` and its local command. The Codex check uses the required CLI override; Claude may require one-time approval of the project `.mcp.json`; approve only the checked-in `iac-playwright-mcp` entry.

- [ ] **Step 6: Validate Ansible and Terraform without plans or deployments**

Run in one smoke sandbox:

```bash
sbx exec iac-smoke-codex -- sh -lc '
  cd ansible
  ansible-playbook playbooks/site.yml --syntax-check
'
```

Run validation for all four Terraform roots:

```bash
for terraform_directory in \
  terraform/proxmox \
  terraform/esxi \
  terraform/oci \
  terraform/netbox-integration; do
  sbx exec iac-smoke-codex -- sh -lc "
    cd '$terraform_directory'
    terraform init -backend=false
    terraform validate
  "
done
```

Expected: syntax and validation pass. Do not run `plan` or `apply`.

- [ ] **Step 7: Verify OCI opt-in mount without exposing key contents**

Create a separate OCI smoke sandbox because workspaces are fixed at creation:

```bash
test -d "${HOME}/.oci" || { echo 'OCI credentials directory is missing; stop and ask the user to restore or provide approved OCI credentials.' >&2; exit 1; }
sbx create --name iac-smoke-oci --kit ./.sandbox-kit codex . "${HOME}/.oci:ro"
```

If the guard fails, stop or skip OCI sandbox creation and ask the user to restore or provide approved OCI credentials; do not create an empty directory or search alternate private-key locations. Only when it succeeds, use the quoted `"${HOME}/.oci:ro"` workspace. Inside it, resolve only the `private_key_path` value without printing the tfvars file, verify readability, and validate Terraform:

```bash
sbx exec iac-smoke-oci -- sh -lc '
  key_path="$(sed -n '\''s/^[[:space:]]*private_key_path[[:space:]]*=[[:space:]]*"\([^" ]*\)".*/\1/p'\'' terraform/oci/secrets.auto.tfvars | head -1)"
  test -n "$key_path"
  if ! test -r "$key_path"; then
    printf "OCI key path is not readable: %s\n" "$key_path" >&2
    exit 1
  fi
  cd terraform/oci
  terraform init -backend=false
  terraform validate
'
```

Expected: the directory guard succeeds before creation, the quoted key path is readable inside the OCI sandbox, Terraform initializes and validates, and no secret contents are printed. If the guard fails, OCI creation is skipped/stopped and the user is asked for approved credentials. If the stored path is stale, stop and report that exact path mismatch; do not search the host for alternate private keys.

- [ ] **Step 8: Verify OpenCode Desktop server mode**

Start the server in a long-lived attached terminal/session:

```bash
sbx run --name iac-smoke-opencode-desktop \
  --publish 127.0.0.1:4096:4096 \
  opencode . --kit ./.sandbox-kit \
  -- serve --hostname 0.0.0.0 --port 4096
```

Do not use `--detached`: it creates/starts only the microVM and does not start the agent
server. While that attached session remains running, use a second host terminal for the
health check:

Check from the host:

```bash
curl -fsS http://127.0.0.1:4096/global/health | jq -e '.healthy == true'
```

Then ask the user to connect OpenCode Desktop to `http://127.0.0.1:4096` and confirm the project path and one response. Do not treat the HTTP health check alone as Desktop acceptance.

- [ ] **Step 9: Phase 1 approval gate**

Report every command result, blocked domain added, sandbox name, and unresolved issue. Leave `.devcontainer/` intact. Ask the user whether to proceed with final cutover and deletion.

---

### Task 6: Retire devcontainer and the obsolete VM playbook

**Files:**

- Delete: all eight tracked files under `.devcontainer/`
- Delete: `ansible/playbooks/deploy-devcontainer.yml`
- Modify: `ansible/playbooks/site.yml`
- Modify: `.gitignore`

**Interfaces:**

- Consumes: explicit Phase 1 approval from Task 5.
- Produces: no remaining runnable devcontainer entrypoint and no site playbook import for the retired VM configuration playbook.

- [ ] **Step 1: Reconfirm exact deletion targets**

Run:

```bash
git ls-files .devcontainer
sed -n '1,20p' ansible/playbooks/deploy-devcontainer.yml
sed -n '1,20p' ansible/playbooks/site.yml
```

Expected: only the eight listed `.devcontainer` files, the obsolete playbook, and the matching import block are in scope.

- [ ] **Step 2: Delete tracked devcontainer files with an explicit patch**

Use `apply_patch` to delete each tracked `.devcontainer` file. Do not use recursive `rm`.

- [ ] **Step 3: Retire the Ansible playbook safely**

Use `apply_patch` to delete `ansible/playbooks/deploy-devcontainer.yml` and remove only this block from `ansible/playbooks/site.yml`:

```yaml
- name: Deploy DevContainer
  import_playbook: deploy-devcontainer.yml
  when: "'devcontainer' in groups['pve_vms']"
```

Keep the common baseline play unchanged.

- [ ] **Step 4: Remove the obsolete generated-config ignore**

Delete `.devcontainer/.generated/` from `.gitignore`. Preserve all unrelated ignore rules.

- [ ] **Step 5: Validate the retirement unit**

Run:

```bash
test ! -e .devcontainer
test ! -e ansible/playbooks/deploy-devcontainer.yml
! rg -n 'deploy-devcontainer' ansible/playbooks/site.yml
cd ansible
ansible-playbook playbooks/site.yml --syntax-check
```

Expected: retired files are absent and site syntax passes.

- [ ] **Step 6: Stop for review**

Show the deletion diff and syntax evidence. Do not commit. Ask whether to continue with documentation cleanup and final validation.

---

### Task 7: Update current operational documentation and preserve history

**Files:**

- Modify as indicated by audit: current files under `docs/designs/`, `docs/deployment/`, `docs/guides/`, `docs/troubleshooting/`, and `docs/agent-setup/`
- Do not rewrite: `docs/incidents/`, `docs/learningnotes/`, `docs/archive/`

**Interfaces:**

- Consumes: final Docker Sandbox commands and retired-file list.
- Produces: no current operational page that directs users to devcontainer or `/workspaces/IaC`.

- [ ] **Step 1: Generate the live-reference inventory**

Run:

```bash
rg -n -i 'devcontainer|\.devcontainer|/workspaces/IaC' \
  README.md AGENTS.md CLAUDE.md docs \
  --glob '!docs/incidents/**' \
  --glob '!docs/learningnotes/**' \
  --glob '!docs/archive/**'
```

Classify each hit as current instruction, architecture history embedded in a live document, or unrelated use of the word `sandbox`.

- [ ] **Step 2: Rewrite current instructions with exact portable commands**

For every current operational hit:

- Replace absolute `/workspaces/IaC/...` commands with repository-relative commands.
- Replace devcontainer startup/rebuild guidance with the appropriate `sbx run ... --kit ./.sandbox-kit` command or a link to the README Docker Sandboxes section.
- Replace host Playwright and generated-config troubleshooting with sandbox-local MCP checks:

```bash
command -v iac-playwright-mcp
codex -c 'mcp_servers.playwright.command="iac-playwright-mcp"' mcp list  # Codex sandbox
claude mcp list       # Claude sandbox
opencode mcp list     # OpenCode sandbox
```

- Keep historical statements when they explain a past incident, but label them as historical if they appear in an otherwise current guide.

- [ ] **Step 3: Verify the history boundary**

Run:

```bash
git diff --name-only -- docs/incidents docs/learningnotes docs/archive
```

Expected: no files are listed unless the user explicitly approved a small historical-status annotation.

- [ ] **Step 4: Re-run the live-reference audit**

Use the Step 1 command again. Expected: remaining hits are deliberate historical descriptions or the migration design/plan themselves; no current command instructs users to run devcontainer or `cd /workspaces/IaC`.

---

### Task 8: Final verification and handoff

**Files:** All migration files.

**Interfaces:**

- Consumes: Tasks 1–7.
- Produces: evidence-backed completion report and a commit approval prompt.

- [ ] **Step 1: Run repository-wide static validation**

Run:

```bash
sbx kit validate .sandbox-kit
terraform fmt -check -recursive
git diff --check
test ! -e .codex/config.toml
jq -e . .mcp.json >/dev/null
jq -e . opencode.json >/dev/null
codex -c 'mcp_servers.playwright.command="iac-playwright-mcp"' mcp list
```

Expected: every command exits 0. For Git acceptance, a direct sandbox created from the main
checkout must support Git. A direct sandbox created from a host linked worktree may report
`No Git` because Docker cannot resolve the external `.git` pointer; it is expected and Git
must remain host-managed without mounting the common Git directory. Clone mode must be
created from the main checkout and provides Git in the private clone. Do not report the
linked-worktree result as unexplained migration noise.

- [ ] **Step 2: Run final Ansible validation**

From `ansible/`:

```bash
ansible-playbook playbooks/site.yml --syntax-check
ansible-inventory --graph >/dev/null
```

Expected: syntax passes. Record any pre-existing inventory warning separately; do not hide new warnings.

- [ ] **Step 3: Recheck security boundaries**

Run searches that print paths and configuration, never secret contents:

```bash
rg -n 'private_key_file|ansible_ssh_private_key_file' ansible terraform --glob '!ansible/collections/**'
rg -n 'host\.docker\.internal:8931|\.devcontainer|devcontainer up|/workspaces/IaC' \
  README.md AGENTS.md CLAUDE.md docs \
  --glob '!docs/incidents/**' \
  --glob '!docs/learningnotes/**' \
  --glob '!docs/archive/**'
git status --short
```

Expected: no active private-key path, host Playwright endpoint, devcontainer startup command, or `/workspaces/IaC` operational instruction remains.

- [ ] **Step 4: Review the complete diff by logical unit**

Run:

```bash
git diff --stat
git diff -- .sandbox-kit .mcp.json opencode.json
git diff -- ansible/ansible.cfg ansible/inventory/oci/hosts.yml terraform/esxi/llm-server.tf
git diff -- README.md AGENTS.md CLAUDE.md docs
git diff -- .devcontainer ansible/playbooks/site.yml ansible/playbooks/deploy-devcontainer.yml .gitignore .worktreeinclude
```

Check for unrelated user changes before proposing any staging set.

- [ ] **Step 5: Report completion without committing**

The final report must include:

- Files added, modified, and deleted.
- Versions installed by the Kit.
- Direct, clone, OCI, frontend-port, OpenCode TUI, and OpenCode Desktop command examples.
- Static validation and smoke-test evidence.
- Any remaining experimental Docker Sandboxes limitations.
- Whether temporary smoke sandboxes still exist and the exact names.
- A reminder that removing a sandbox deletes its microVM state but not direct-mounted workspace files.

End with: `Ready to commit?`

- [ ] **Step 6: Commit only after explicit approval**

If and only if the user explicitly approves a commit, stage only the reviewed migration files and use a Conventional Commit message such as:

```text
feat(dev-env): migrate to Docker Sandboxes
```

If approval is not given, leave all changes uncommitted.
