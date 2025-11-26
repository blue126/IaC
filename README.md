# Infrastructure as Code (IaC)

This repository contains Infrastructure as Code for managing a Proxmox VE cluster using Ansible, with preparation for future Terraform integration and ESXi support.

## Project Overview
- **Ansible**: Configuration management for Proxmox VMs and applications
- **Terraform**: (Planned) Infrastructure provisioning for Proxmox and ESXi
- **Multi-platform**: Current Proxmox support, future ESXi integration

## Repository Structure
```
├── ansible/              # Ansible configuration management
│   ├── ansible.cfg      # Ansible configuration
│   ├── inventory/       # Host and VM inventory
│   │   ├── hosts.yml   # Main inventory (Proxmox cluster + VM groups)
│   │   ├── group_vars/ # Shared group variables
│   │   ├── host_vars/  # Per-host variables
│   │   └── vms/        # VM-specific inventory files
│   ├── playbooks/       # Ansible playbooks
│   ├── roles/           # Custom Ansible roles
│   ├── templates/       # Jinja2 templates
│   └── files/           # Static files (cloud-init, configs)
├── terraform/           # (Future) Terraform infrastructure code
│   ├── proxmox/        # Proxmox infrastructure
│   ├── esxi/           # ESXi infrastructure
│   └── modules/        # Reusable Terraform modules
├── docs/                # Documentation
│   └── devices/        # Manual device configurations
└── scripts/             # Helper scripts
```

## Quick Start

### Ansible Operations
All Ansible commands should be run from the `ansible/` directory:

```bash
cd ansible/

# Test connectivity
ansible proxmox_cluster -m ping
ansible samba -m ping

# Deploy VMs
ansible-playbook playbooks/deploy-samba.yml
ansible-playbook playbooks/deploy-immich.yml

# Create VM template
ansible-playbook playbooks/create-vm-template.yml
```

## Current Infrastructure
- **Proxmox Cluster**: 3 nodes (pve0, pve1, pve2)
- **Application VMs**:
  - Immich (192.168.1.101): Photo management with Docker
  - Samba (192.168.1.102): Network file sharing

## Prerequisites
- Proxmox VE cluster configured and accessible
- Ansible 2.16+ installed
- SSH access to Proxmox nodes
- Ubuntu 24.04 VM template (ID 9000)

## Documentation
- [Samba VM Deployment](docs/SAMBA_VM_DEPLOYMENT.md): Complete deployment guide with troubleshooting