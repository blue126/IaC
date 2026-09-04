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

Playwright 在宿主通过 `sbx mcp` 全局注册。每个 Sandbox 默认使用 dynamic MCP Gateway，Agent 在需要浏览器时从全局注册表附加 `playwright`，无需项目配置或创建参数。

将 `TASK` 替换为唯一的 kebab-case 任务名。Direct mode 必须从已分配的 host task worktree 启动；clone mode 必须从 verified main checkout 启动。开始任何 Ansible SSH 操作前，先运行 `ssh-add -L`，确认输出中包含用于 Ansible 认证的已加载 SSH 公钥身份（public identity）。

```bash
# Direct mode
sbx run --name iac-codex-TASK-direct-v130 codex . --kit ./.sandbox-kit
sbx run --name iac-claude-TASK-direct-v130 claude . --kit ./.sandbox-kit
sbx run --name iac-opencode-TASK-direct-v130 opencode . --kit ./.sandbox-kit

# Clone mode: --clone is fixed when the sandbox is first created
sbx run --clone --name iac-codex-TASK-clone-v130 codex . --kit ./.sandbox-kit
sbx run --clone --name iac-claude-TASK-clone-v130 claude . --kit ./.sandbox-kit
sbx run --clone --name iac-opencode-TASK-clone-v130 opencode . --kit ./.sandbox-kit

# OpenCode Desktop server
sbx run --name iac-opencode-desktop-TASK-v130 \
  --publish 127.0.0.1:4096:4096 \
  opencode . --kit ./.sandbox-kit \
  -- serve --hostname 0.0.0.0 --port 4096
```

Direct mode 直接挂载整个主机工作区，因此也会读取被 Git 忽略的 `ansible/.vault_pass` 和已生成的 Terraform tfvars。仓库工作区中严禁存放 `.ssh` 私钥：它们会随 direct mode 暴露给 sandbox。SSH 私钥只能由宿主 SSH agent 管理，并通过转发供 sandbox 使用。Clone mode 使用私有 clone；如需上述未追踪文件，必须从 `/run/sandbox/source` 手动复制所需文件，且不得输出其内容。

Playwright 不再由项目级 Agent 配置直接启动。先运行 `sbx mcp ls`，确认宿主全局注册的 `playwright` 为 `ready`。未传 `--static-mcp` 的 Sandbox 使用 dynamic mode，Agent 可通过 Gateway 的发现与附加工具按需启用；宿主也可运行 `sbx mcp load playwright --sandbox <name>`，绑定会跨重启保留。

### Git 与 host worktree 边界

- 从 **main checkout** 以 direct mode 启动时，sandbox 内可正常使用 Git。
- 从宿主 **linked worktree** 以 direct mode 启动时，agent 仍可编辑文件，但 Docker 只挂载该 worktree，无法解析指向外部 common Git directory 的 `.git` pointer，因此 sandbox 内 Git 不可用；Git 操作由宿主机管理，且不得自动挂载 common Git directory。
- `--clone` 必须从 main checkout 创建，不能从 linked worktree 创建；agent 在 private clone 中可使用 Git。

因此，当前 linked-worktree smoke 中的 `No Git` 是 Docker 的预期 host-worktree 限制，不是迁移缺陷；正式验收在 main checkout 中进行即可。参见 [Docker host worktree Git 边界](https://docs.docker.com/ai/sandboxes/workflows/git/) 与 [Docker Sandboxes clone mode 限制](https://docs.docker.com/ai/sandboxes/usage/)。

前端服务必须在 sandbox 内监听 `0.0.0.0`，并只将需要检查的端口发布到主机 loopback。宿主 Playwright 通过发布后的 `127.0.0.1:<host-port>` 访问服务，用户可以直接观察同一个浏览器窗口。OpenCode Desktop server 命令必须保持在长期 attached terminal/session 中运行；`--detached` 只会创建/启动 microVM，不会启动 agent server。

### Project-Specific Credential Handling

OCI 凭据注入是 IaC 项目要求，不是 Docker Sandbox 的 topology 或 Agent runtime。仅在 OCI 任务中执行以下宿主侧预检和只读挂载：

```bash
test -d "${HOME}/.oci" || { echo 'OCI credentials directory is missing; stop and ask the user to restore or provide approved OCI credentials.' >&2; exit 1; }
sbx run --name iac-codex-TASK-oci-v130 codex . "${HOME}/.oci:ro" --kit ./.sandbox-kit
```

目录不存在时必须停止或跳过 OCI Sandbox 创建，并请求用户恢复或提供已批准的 OCI credentials。不得创建空目录、搜索替代私钥位置或使用可写挂载。只读挂载允许 Sandbox 进程读取 OCI API 私钥，但禁止修改。修改 Kit 后需要重新创建 Sandbox；只有 `sbx kit add` 明确支持的变更例外。

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
