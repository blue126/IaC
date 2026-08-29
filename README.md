# Homelab Infrastructure as Code

Production-grade IaC managing a hybrid homelab across **Proxmox VE**, **VMware ESXi**, and **Oracle Cloud (OCI)** — using Terraform for provisioning and Ansible for configuration management.

## Architecture

```
                        +-----------------------+
                        |    HCP Terraform      |
                        |   (Remote State)      |
                        +----------+------------+
                                   |
              +--------------------+--------------------+
              |                    |                     |
     +--------v-------+  +--------v--------+  +--------v--------+
     |   Proxmox VE   |  |   VMware ESXi   |  |   Oracle Cloud  |
     |   (3-node HA)  |  |   (standalone)  |  |   (Free Tier)   |
     +--------+-------+  +--------+--------+  +--------+--------+
              |                    |                     |
              +--------------------+--------------------+
                                   |
                        +----------v-----------+
                        |       Ansible        |
                        |  (Config Management) |
                        +----------+-----------+
                                   |
         +------------+------------+------------+------------+
         |            |            |            |            |
     +---v---+   +----v---+  +----v---+   +----v---+  +----v----+
     |Netbox |   |Immich  |  |Jenkins |   | Caddy  |  | 15 more |
     |IPAM   |   |Photos  |  | CI/CD  |   |  TLS   |  |services |
     +-------+   +--------+  +--------+   +--------+  +---------+
```

### Design Principles

- **Separation of Concerns** — Terraform provisions infrastructure; Ansible configures services
- **Single Source of Truth** — HCP Terraform for state, Ansible Vault for secrets, Netbox for IPAM
- **Two-Stage Deployments** — Every playbook includes automated verification (port checks, HTTP tests, DB connectivity)
- **Dynamic Inventory** — Ansible discovers hosts from Terraform state via `cloud.terraform.terraform_provider`

## Tech Stack

| Layer | Tools |
|-------|-------|
| **Provisioning** | Terraform (bpg/proxmox, vmware/vsphere, oracle/oci) |
| **Configuration** | Ansible 2.16+ with 22 custom roles |
| **CI/CD** | Jenkins pipelines with change-based routing |
| **Networking** | Tailscale mesh VPN, Caddy reverse proxy, Cloudflare Tunnel |
| **Secret Management** | Ansible Vault + Terraform secrets bridge |
| **State Backend** | HCP Terraform (local execution mode) |
| **Dev Environment** | Docker Sandboxes (isolated microVMs) |

## Repository Structure

```
.
├── terraform/
│   ├── proxmox/              # Proxmox VE VMs and LXCs
│   ├── esxi/                 # ESXi virtual machines
│   ├── oci/                  # Oracle Cloud instances
│   ├── netbox-integration/   # IPAM/DCIM data push
│   └── modules/              # Reusable modules (proxmox-vm, proxmox-lxc, esxi-vm)
├── ansible/
│   ├── inventory/            # Split inventory (groups, host_vars, group_vars)
│   ├── roles/                # 22 service roles (see below)
│   ├── playbooks/            # 25 deploy/utility playbooks
│   └── files/                # Cloud-init templates, config files
├── scripts/
│   ├── get-secrets.sh        # Vault → Terraform secrets bridge
│   ├── refresh-terraform-state.sh  # Sync remote state for dynamic inventory
│   └── jenkins/              # CI/CD helper scripts
├── docs/                     # 100+ pages of designs, guides, and learning notes
├── Jenkinsfile               # Main CI/CD pipeline
└── Jenkinsfile-webhook-router # Webhook event routing
```

## Services (22 Ansible Roles)

| Service | Platform | Deployment | Description |
|---------|----------|------------|-------------|
| **Netbox** | Proxmox VM | Docker Compose | IPAM/DCIM network management |
| **Immich** | Proxmox VM | Docker Compose | Photo management with ML |
| **Jenkins** | Proxmox VM | Docker Compose | CI/CD orchestration |
| **n8n** | Proxmox VM | Docker Compose | Workflow automation |
| **Gitea** | Proxmox VM | Docker Compose | Self-hosted Git |
| **RustDesk** | Proxmox VM | Docker Compose | Remote desktop |
| **Homepage** | Proxmox LXC | Docker Compose | Service dashboard |
| **Caddy** | Proxmox LXC | Native binary | Reverse proxy + auto TLS |
| **Anki Sync** | Proxmox LXC | Systemd | Flashcard synchronization |
| **PBS** | ESXi VM | Native | Proxmox Backup Server |
| **LLM Server** | ESXi VM | Systemd | GPU inference (llama.cpp + Open WebUI) |
| **Unified Proxy** | OCI | Docker Compose | Public-facing Caddy relay |
| **Tailscale** | All nodes | Native | Mesh VPN connectivity |
| **Cloudflared** | Proxmox VM | Service | Cloudflare tunnel |
| **Docker** | Multi | Foundation | Container runtime (role dependency) |
| **Common** | Multi | Foundation | Base OS config (timezone, SSH, packages) |

## CI/CD Pipeline

The Jenkins pipeline provides **change-based routing** — only affected infrastructure gets planned/deployed:

```
Git Push → Jenkins → Detect Changes → Route to Workspace
                                        ├── terraform/proxmox/* → Proxmox Plan
                                        ├── terraform/esxi/*    → ESXi Plan
                                        ├── ansible/roles/*     → Lint + Syntax Check
                                        └── ansible/playbooks/* → Service Deploy
```

Pipeline stages: **Change Detection → Terraform Lint → Terraform Plan → Ansible Lint → Syntax Check → Auto-Deploy** (conditional)

## Quick Start

### Prerequisites

- Proxmox VE 8.x / ESXi / OCI account
- Terraform 1.14+
- Ansible 2.16+
- Python 3.8+

### 1. Docker Sandboxes 环境

在仓库根目录使用 Docker Sandboxes 启动对应的 agent。开始任何 Ansible SSH 操作前，先运行 `ssh-add -L`，确认输出中包含用于 Ansible 认证的已加载 SSH 公钥身份（public identity）。

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

Direct mode 直接挂载整个主机工作区，因此也会读取被 Git 忽略的 `ansible/.vault_pass` 和已生成的 Terraform tfvars。仓库工作区中严禁存放 `.ssh` 私钥：它们会随 direct mode 暴露给 sandbox。SSH 私钥只能由宿主 SSH agent 管理，并通过转发供 sandbox 使用。Clone mode 使用私有 clone；如需上述未追踪文件，必须从 `/run/sandbox/source` 手动复制所需文件，且不得输出其内容。

### Git 与 host worktree 边界

- 从 **main checkout** 以 direct mode 启动时，sandbox 内可正常使用 Git。
- 从宿主 **linked worktree** 以 direct mode 启动时，agent 仍可编辑文件，但 Docker 只挂载该 worktree，无法解析指向外部 common Git directory 的 `.git` pointer，因此 sandbox 内 Git 不可用；Git 操作由宿主机管理，且不得自动挂载 common Git directory。
- `--clone` 必须从 main checkout 创建，不能从 linked worktree 创建；agent 在 private clone 中可使用 Git。

因此，当前 linked-worktree smoke 中的 `No Git` 是 Docker 的预期 host-worktree 限制，不是迁移缺陷；正式验收在 main checkout 中进行即可。参见 [Docker host worktree Git 边界](https://docs.docker.com/ai/sandboxes/workflows/git/) 与 [Docker Sandboxes clone mode 限制](https://docs.docker.com/ai/sandboxes/usage/)。

仅在 OCI 工作中挂载 `"${HOME}/.oci:ro"`，且运行命令前必须先执行 `test -d "${HOME}/.oci"`。目录不存在时必须停止或跳过 OCI sandbox 创建，并请求用户恢复或提供已批准的 OCI credentials；不得自动创建空目录，也不得搜索替代私钥位置。目录存在后只使用带引号的挂载路径。只读挂载禁止修改，但允许 sandbox 内的进程读取 OCI API 私钥。修改 Kit 后需要重新创建 sandbox；只有 `sbx kit add` 明确支持的变更例外。

前端服务必须在 sandbox 内监听 `0.0.0.0`，并只将需要检查的端口发布到主机 loopback。OpenCode Desktop server 命令必须保持在长期 attached terminal/session 中运行；`--detached` 只会创建/启动 microVM，不会启动 agent server。Playwright MCP 与 headless Chromium 均在 microVM 内运行。Codex 0.149.1 在项目未持久受信任时会跳过项目 `.codex/config.toml`，因此 Codex 命令必须保留上述 `-- -c 'mcp_servers.playwright.command="iac-playwright-mcp"'` 覆盖；Claude Code 和 OpenCode 继续使用各自的项目配置。

### 2. Provision Infrastructure

```bash
# Generate secrets.auto.tfvars from Ansible Vault
./scripts/get-secrets.sh

cd terraform/proxmox   # or esxi / oci
terraform init && terraform plan
terraform apply
```

### 3. Deploy Services

```bash
# Sync Terraform state for dynamic inventory
./scripts/refresh-terraform-state.sh

cd ansible/
ansible-playbook playbooks/deploy-<service>.yml

# Run verification only
ansible-playbook playbooks/deploy-<service>.yml --tags verify
```

### Deployment Verification

All playbooks include automated health checks:

```
TASK [Display deployment summary] ************************************
ok: [netbox] => {
    "msg": [
        "Deployment Successful",
        "Web Interface: http://<host>:8080",
        "Healthy Containers: 6/6"
    ]
}
```

## Secret Management

```
Ansible Vault (vault.yml)
    │
    ├──→ Ansible playbooks     (direct {{ vault_* }} references)
    │
    └──→ scripts/get-secrets.sh
              │
              └──→ secrets.auto.tfvars  (gitignored, consumed by Terraform)
```

All secrets flow from a single encrypted Ansible Vault file. Terraform consumes secrets via a bridge script that renders Vault variables into `.tfvars` format.

## Documentation

The [`docs/`](docs/) directory contains 100+ pages of technical documentation. Browse the [published site](https://blue126.github.io/IaC/) or preview it locally with `hugo server --baseURL http://localhost:1313/IaC/ --appendPort=false` (see [`docs-site/README.md`](docs-site/README.md) for pinned prerequisites):

- **[Architecture Design](docs/designs/homelab-iac-architecture.md)** — Comprehensive system design
- **[Deployment Guides](docs/deployment/)** — Step-by-step service deployment
- **[Troubleshooting](docs/troubleshooting/)** — Common issues and solutions
- **[Learning Notes](docs/learningnotes/INDEX.md)** — Technical deep-dives and lessons learned

## License

This project is for personal homelab use. Feel free to reference the patterns and configurations for your own infrastructure.
