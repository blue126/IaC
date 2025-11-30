# Infrastructure as Code (IaC)

This repository contains Infrastructure as Code for managing a Proxmox VE homelab using Terraform and Ansible.

## Project Overview
- **Terraform**: VM/LXC provisioning on Proxmox
- **Ansible**: Application configuration management with automated deployment verification
- **Netbox**: IPAM and DCIM source of truth

### Architecture
```
Terraform (Provision) → Ansible (Configure) → Verify (Health Check)
```

**Separation of Concerns**:
- **Provisioning (Terraform)**: Creates VMs/LXCs (CPU, memory, disk, network)
- **Configuration (Ansible)**: Installs and configures services using roles
- **Verification (Ansible)**: Automated health checks and deployment validation

## Repository Structure
```
├── ansible/
│   ├── inventory/
│   │   ├── pve-vms/         # VM inventory (Netbox, Samba, Immich)
│   │   └── pve-lxc/         # LXC inventory (Anki Sync Server)
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

## Current Infrastructure

### Virtual Machines
| Service | IP | Type | Description |
|---------|------|------|-------------|
| Netbox | 192.168.1.104 | VM | IPAM/DCIM (6 Docker containers) |
| Immich | 192.168.1.101 | VM | Photo management (4 Docker containers) |
| Samba | 192.168.1.102 | VM | File sharing (smbd/nmbd) |

### LXC Containers
| Service | IP | Type | Description |
|---------|------|------|-------------|
| Anki Sync Server | 192.168.1.100 | LXC | Flashcard synchronization (Python/systemd) |

## Quick Start

### 1. Environment Setup
```bash
# Initialize Python virtual environment
./scripts/setup_env.sh
source .venv/bin/activate
```

### 2. Provision Infrastructure (Terraform)
```bash
cd terraform/proxmox
terraform init
terraform apply
```

### 3. Deploy & Verify Services (Ansible)
```bash
cd ansible/

# Full deployment with verification
ansible-playbook playbooks/deploy-netbox.yml
ansible-playbook playbooks/deploy-samba.yml
ansible-playbook playbooks/deploy-immich.yml
ansible-playbook playbooks/deploy-anki.yml

# Run verification only (health check)
ansible-playbook playbooks/deploy-netbox.yml --tags verify
```

### 4. Manage Netbox Resources (Terraform)
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
- [Netbox Deployment](docs/deployment/netbox_deployment.md) - Docker Compose setup with health checks
- [Proxmox VM Provisioning](docs/deployment/proxmox_vm_deployment.md) - Terraform module usage
- [Samba File Server](docs/deployment/SAMBA_VM_DEPLOYMENT.md) - SMB/NetBIOS configuration
- [Immich Deployment](docs/deployment/immich_deployment.md) - Photo management + ML stack

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