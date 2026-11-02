# Homelab Infrastructure as Code

本仓库使用 Terraform 与 Ansible 管理 **Proxmox VE（pve0/pve1 集群及独立 pve2）** 和 **Oracle Cloud（OCI）**。原 T7910 ESXi 宿主已退役并改为 pve2；保留的 ESXi 代码仅供历史与 state 对账，不代表仍有运行中的 ESXi 主机。备份作业及保留策略由 PVE/PBS 管理，不由 Ansible 下发。

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
     |   Proxmox VE   |  | Proxmox pve2    |  |   Oracle Cloud  |
     |  (pve0/pve1)   |  | (standalone)    |  |   (Free Tier)   |
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

2026-10-02 集群仲裁已调整为 pve0/pve1 各 1 票，加 N100 上独立 qnetd `192.168.1.53` 的 1 票，总票数 3、quorum 2。见证只参与仲裁，不等于 VM HA 或共享存储；其网络限制、启动门控与回滚见 [QDevice 架构](docs/architecture/proxmox-qdevice-architecture.md)。该现场配置当前由操作者维护，未纳入 Terraform/Ansible ownership。

### Design Principles

- **Separation of Concerns** — Terraform provisions infrastructure; Ansible configures services
- **Single Source of Truth** — HCP Terraform for state, Ansible Vault for secrets, Netbox for IPAM
- **Two-Stage Deployments** — Every playbook includes automated verification (port checks, HTTP tests, DB connectivity)
- **Dynamic Inventory** — Ansible discovers hosts from Terraform state via `cloud.terraform.terraform_provider`

## Tech Stack

| Layer | Tools |
|-------|-------|
| **Provisioning** | Terraform (bpg/proxmox, oracle/oci；vSphere 配置已退役) |
| **Configuration** | Ansible 2.16+ with custom service roles |
| **CI/CD** | Jenkins pipelines with change-based routing |
| **Networking** | Tailscale mesh VPN, Caddy reverse proxy, Cloudflare Tunnel |
| **Secret Management** | Ansible Vault + Terraform secrets bridge |
| **State Backend** | HCP Terraform (local execution mode) |
| **Dev Environment** | macOS host + per-checkout uv toolchain (`.venv`) |

## Repository Structure

```
.
├── terraform/
│   ├── proxmox/              # Proxmox VE VMs and LXCs
│   ├── esxi/                 # Retired ESXi configuration (history/state reference)
│   ├── oci/                  # Oracle Cloud instances
│   ├── netbox-integration/   # IPAM/DCIM data push
│   └── modules/              # Reusable modules (proxmox-vm, proxmox-lxc, esxi-vm)
├── ansible/
│   ├── inventory/            # Split inventory (groups, host_vars, group_vars)
│   ├── roles/                # Service roles (see below)
│   ├── playbooks/            # Deploy/utility playbooks
│   └── files/                # Cloud-init templates, config files
├── scripts/
│   ├── get-secrets.sh        # Vault → Terraform secrets bridge
│   ├── refresh-terraform-state.sh  # Sync remote state for dynamic inventory
│   └── jenkins/              # CI/CD helper scripts
├── docs/                     # 100+ pages of designs, guides, and learning notes
├── Jenkinsfile               # Main CI/CD pipeline
└── Jenkinsfile-webhook-router # Webhook event routing
```

## Services

| Service | Platform | Deployment | Description |
|---------|----------|------------|-------------|
| **Netbox** | Proxmox VM | Docker Compose | IPAM/DCIM network management |
| **Immich** | Proxmox VM | Docker Compose | Photo management with ML |
| **Jenkins** | Proxmox VM | Docker Compose | CI/CD orchestration |
| **n8n** | Proxmox LXC | Docker Compose | Workflow automation |
| **Gitea** | Proxmox VM | Docker Compose | Self-hosted Git |
| **RustDesk** | Proxmox VM | Docker Compose | Remote desktop |
| **Homepage** | Proxmox LXC | Docker Compose | Service dashboard |
| **Caddy** | Proxmox LXC | Native binary | Reverse proxy + auto TLS |
| **Anki Sync** | Proxmox LXC | Systemd | Flashcard synchronization |
| **PBS** | Proxmox VM (pve2) | Native | Proxmox Backup Server |
| **Proxmox Datacenter Manager** | Proxmox VM (pve1 / 117) | Native | 多节点管理，192.168.1.117:8443 |
| **Home Assistant OS** | pve1 VM114 | HAOS appliance，操作者维护 | `192.168.1.114`，onboarding 已完成，Core 端口 80（2026-10-02 观测，后续可变）；已复用归档退役的 PaddleSpeech CT114 ID |
| **Corosync qnetd** | N100 独立容器 | Docker Compose，操作者维护 | `.53:5403`，TLS 外部见证，仅允许 pve0/pve1 `.50/.51` |
| **Hindsight** | pve1 LXC 118 | Docker Compose（LXC 内，host 网络），操作者维护 | `192.168.1.118:9077`，AI Agent 共用长期记忆（需 Bearer key）；另开放无登录的网页控制台 `:19077`；Claude Code/Codex/CodeBuddy 已切换，Hermes（Mac 与网关）已接入，网关上的旧部署已删除，备份由运维方另行规划，见 [Hindsight 架构](docs/architecture/hindsight-memory-architecture.md) |
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
                                        ├── ansible/roles/*     → Lint + Syntax Check
                                        └── ansible/playbooks/* → Service Deploy
```

Pipeline stages: **Change Detection → Terraform Lint → Terraform Plan → Ansible Lint → Syntax Check → Auto-Deploy** (conditional)

## Quick Start

### Prerequisites

- Proxmox VE / OCI account（ESXi 已退役）
- Terraform 1.14+
- Ansible 2.16+
- Python 3.8+

### 1. 宿主开发环境

所有命令默认在 macOS 宿主上、从当前 checkout 或任务 worktree 执行，使用该 checkout 自己的 uv 工具链：

```bash
./scripts/setup-dev-env.sh      # 每个 checkout 一次；requirements 变更后重跑
source .venv/bin/activate
```

脚本按 `requirements.txt` 创建 `.venv`，并把固定版本的 collections 装入 `ansible/collections`。宿主 `~/.local/bin/ansible` 属于其他项目（ansible-core 2.21，超出本仓库 `<2.21` 约束），不得用于本仓库。

每个任务使用独立 worktree 和唯一分支；main checkout 只做协调。Git 忽略的状态不在 worktree 间共享：新 worktree 需在所用 Terraform 根目录重新 `terraform init`，`ansible/.vault_pass` 来自 main checkout（用 `--vault-password-file` 指向该路径，不要复制）。开始任何 Ansible SSH 操作前，先运行 `ssh-add -L`，确认已加载用于 Ansible 认证的 SSH 公钥身份；仓库工作区中严禁存放 `.ssh` 私钥。

### Project-Specific Credential Handling

仅在需要 OCI 的任务中先做宿主侧预检：

```bash
test -d "${HOME}/.oci" || { echo 'OCI credentials directory is missing; stop and ask the user to restore or provide approved OCI credentials.' >&2; exit 1; }
```

目录不存在时必须停止，并请求用户恢复或提供已批准的 OCI credentials。不得创建空目录、搜索替代私钥位置或修改 `~/.oci` 内容。

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

- **[Architecture Design](docs/architecture/homelab-iac-architecture.md)** — Comprehensive system design
- **[Guides](docs/guides/)** — Deployment guides and practical how-to references
- **[Troubleshooting](docs/troubleshooting/)** — Common issues, solutions, and incident retrospectives
- **[Learning Notes](docs/learningnotes/INDEX.md)** — Technical deep-dives and lessons learned

## License

This project is for personal homelab use. Feel free to reference the patterns and configurations for your own infrastructure.
