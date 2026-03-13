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
| **Dev Environment** | VS Code devcontainer (Ubuntu 24.04) |

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

### 1. Environment Setup

```bash
# Recommended: use the devcontainer (everything pre-installed)
# Manual setup:
pip install --user -r requirements.txt
cd ansible && ansible-galaxy collection install -r requirements.yml
```

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

The [`docs/`](docs/) directory contains 100+ pages of technical documentation:

- **[Architecture Design](docs/designs/homelab-iac-architecture.md)** — Comprehensive system design
- **[Deployment Guides](docs/deployment/)** — Step-by-step service deployment
- **[Troubleshooting](docs/troubleshooting/)** — Common issues and solutions
- **[Learning Notes](docs/learningnotes/INDEX.md)** — Technical deep-dives and lessons learned

## License

This project is for personal homelab use. Feel free to reference the patterns and configurations for your own infrastructure.
