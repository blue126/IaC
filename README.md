# Infrastructure as Code (IaC)

This repository manages a homelab infrastructure spanning Proxmox VE, ESXi, and Oracle Cloud (OCI), using Terraform for provisioning and Ansible for configuration management.

## Project Overview
- **Terraform**: Infrastructure provisioning (Proxmox VMs/LXCs, ESXi VMs, OCI instances, networking). State stored in HCP Terraform (org: `homelab-roseville`)
- **Ansible**: Application configuration management via roles, secrets managed with Ansible Vault
- **Platforms**: Proxmox VE (on-prem), ESXi (on-prem), OCI (Oracle Cloud Free Tier, ap-sydney-1)

### Architecture
```
Terraform (Provision) → Ansible (Configure) → Verify (Health Check)
```

**Separation of Concerns**:
- **Provisioning (Terraform)**: Creates VMs/LXCs/cloud instances, networking, security groups
- **Configuration (Ansible)**: Installs and configures services using roles
- **Verification (Ansible)**: Automated health checks and deployment validation

## Repository Structure
```
├── ansible/
│   ├── inventory/
│   │   ├── pve_vms/         # VM inventory (Netbox, Samba, Immich)
│   │   └── pve_lxc/         # LXC inventory (Anki Sync Server)
│   ├── playbooks/           # Deployment playbooks with verification
│   └── roles/               # Modular service roles
│       ├── docker/          # Docker engine installation
│       ├── samba/           # Samba file server
│       ├── immich/          # Immich photo management
│       ├── netbox/          # Netbox IPAM/DCIM
│       └── anki-sync-server/  # Anki synchronization
├── terraform/
│   ├── proxmox/
│   │   └── modules/         # Reusable modules (proxmox-vm, proxmox-lxc)
│   └── netbox-integration/  # Netbox resource management
├── docs/
│   ├── learningnotes/       # Technical learning documentation
│   └── *.md                 # Deployment guides
└── scripts/                 # Environment setup
```

## Ansible Configuration

The project uses a customized `ansible.cfg` to streamline operations and improve output readability.

### Key Settings (`ansible.cfg`)
*   **Inventory**: Defaults to `inventory/`, so you don't need to specify `-i` for every command.
*   **Roles Path**: Defaults to `roles/`.
*   **Vault Password**: Automatically reads the password from `.vault_pass` (gitignored) for transparent decryption.
*   **Output Format**: Uses `stdout_callback = debug` to provide clean, human-readable output without JSON clutter or escape characters (like `\n`).

### Inventory Structure
We use a **split inventory** approach for better organization and scalability:
*   **`groups.yml`**: Defines the hierarchy of groups (e.g., `pve_lxc` is a child of `tailscale`).
*   **`host_vars/`**: Variables specific to a single host (e.g., IP address, specific configuration).
*   **`group_vars/`**: Variables shared across a group (e.g., Tailscale auth keys, common users).
*   **`proxmox_cluster/`, `pve_lxc/`, etc.**: Directories containing `hosts.yml` files that strictly list group members.



## Quick Start

### 1. Environment Setup
```bash
# Environment is set up automatically by devcontainer postCreateCommand
# For manual setup outside devcontainer:
pip install --user -r requirements.txt
cd ansible && ansible-galaxy collection install -r requirements.yml
```

### 2. Provision Infrastructure (Terraform)
```bash
# Generate secrets.auto.tfvars from Ansible Vault
scripts/get-secrets.sh

cd terraform/proxmox   # or esxi / oci
terraform init
terraform plan
terraform apply
```

### 3. Deploy Services (Ansible)
```bash
# Sync Terraform state to local (required for dynamic inventory)
scripts/refresh-terraform-state.sh

cd ansible/
ansible-playbook playbooks/<service>.yml

# Run verification only
ansible-playbook playbooks/<service>.yml --tags verify
```

### 4. Netbox Integration (Roadmap)
> Netbox as SSOT is a planned future direction. Currently managed via `terraform/netbox-integration/`.
```bash
cd terraform/netbox-integration
terraform init
terraform apply
```

## Deployment Verification

All services include automated verification steps:
- ✅ Port availability checks (`wait_for`)
- ✅ Service status validation (`systemd`, Docker health)
- ✅ HTTP endpoint testing (`uri`)
- ✅ Database connectivity (`pg_isready`)
- ✅ Functional tests (e.g., Samba share listing)

**Example output**:
```
TASK [Display deployment summary] ************************************
ok: [netbox-01] => {
    "msg": [
        "✅ Netbox Deployment Successful",
        "Web Interface: http://192.168.1.104:8080",
        "Superuser: admin",
        "Password: admin",
        "Healthy Containers: 6"
    ]
}
```

See [Verification Pattern Documentation](docs/learningnotes/2025-11-30-ansible-deployment-verification.md) for details.


## Documentation

### NetBox 集成概述
Terraform 正在将当前管理的物理节点、虚拟机 (QEMU)、LXC、接口、IP、服务端口以及二层桥接连接推送进 NetBox，形成“物理 → 虚拟 → 服务 → 拓扑”分层模型。当前阶段为单向写入 (push)；未来计划加入受控读取 (pull)（仅采集非权威字段如标签/备注），并通过比对检测漂移。

分层文件结构（详见 `terraform/netbox-integration/README.md`）：
```
main.tf / pvecluster.tf      # Site / Cluster
infrastructure.tf            # 物理设备与桥 (vmbr0/vmbr1)
vm.tf / containers.tf        # 虚拟机与 LXC + 接口/IP
services.tf                  # 服务与端口
connections.tf               # Cable：vmbr1 ↔ eth0
```
字段所有权当前策略：规格与存在性由 Terraform 权威；标签、描述等可由 NetBox 补充。后期 pull 功能上线时不覆盖人工字段，只做校验。更多细节参见子目录说明文档。

### Deployment Guides
- [Netbox Deployment](docs/deployment/netbox-deployment.md) - Docker Compose setup with health checks
- [Proxmox VM Provisioning](docs/deployment/proxmox-vm-deployment.md) - Terraform module usage
- [Immich Deployment](docs/deployment/immich-deployment.md) - Photo management + ML stack

### Learning Notes
- [Verification Pattern Guide](docs/learningnotes/2025-11-30-ansible-deployment-verification.md) - Automated health checks
- [Anki Sync Server Deployment](docs/learningnotes/2025-11-30-anki-sync-server-deployment.md) - LXC and systemd service
- [All Learning Notes](docs/learningnotes/INDEX.md)

## Version Control & Security

**Files excluded via `.gitignore`**:
- `*.tfstate*` - Terraform state (contains sensitive data)
- `*.tfvars` - Credentials (use `*.tfvars.example` as template)
- `.terraform/` - Provider plugins
- `.venv/` - Python virtual environment
- `.agent/` - AI agent artifacts

**Best practices**:
- Use Terraform remote backend for team collaboration
- Store secrets in environment variables or secret management tools
- Never commit `terraform.tfvars` directly

## Prerequisites
- Proxmox VE 8.x cluster
- Ansible 2.16+
- Terraform 1.14+
- Python 3.8+ (for virtual environment)
- SSH key-based authentication to Proxmox and VMs

## Troubleshooting

### Terraform Provider Issues

**Proxmox Provider Version**: Use `3.0.2-rc04`
```hcl
terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc04"
    }
  }
}
```

**Common issues**:
- `v3.0.2-rc05`: Contains regression causing crashes
- `v2.9.14`: Incompatible with Proxmox VE 8+ permissions
- Use API tokens instead of password authentication

**Quick fix**:
```bash
rm -rf .terraform .terraform.lock.hcl
terraform init -upgrade
```

### Ansible Verification Failures

Run verification independently to diagnose issues:
```bash
ansible-playbook playbooks/deploy-service.yml --tags verify
```

Check logs on target system:
```bash
# systemd services
journalctl -u service-name -n 50

# Docker containers
docker compose logs -f

# Port status
ss -tlnp | grep PORT_NUMBER
```

See individual service documentation for specific troubleshooting steps.

## NetBox Custom Fields Quick Reference

**核心字段** (必填):
- `infrastructure_platform`: `proxmox` | `esxi` | `physical`
- `automation_level`: `fully_automated` | `requires_approval` | `manual_only`

**Proxmox 专用字段**:
- `proxmox_node`: `pve0` | `pve1` | `pve2`
- `proxmox_vmid`: 100-999

**Ansible 集成字段**:
- `ansible_groups`: 多选 (`pve_lxc`, `docker`, `tailscale`, ...)
- `playbook_name`: 可选，默认根据 `ansible_groups` 推导

**详细文档**: [Custom Fields Reference](docs/netbox-custom-fields-reference.md)