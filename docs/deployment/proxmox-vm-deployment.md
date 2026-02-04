# Proxmox VM Deployment Documentation

## Overview
This document outlines the management of Proxmox Virtual Environment (PVE) resources using Terraform. It serves as the foundation for deploying virtual machines and containers in the HomeLab environment.

## Architecture

### Components
- **Hypervisors**: Proxmox VE Nodes (pve0, pve1, pve2, pve3)
- **Management Tool**: Terraform
- **Provider**: `telmate/proxmox`
- **Infrastructure Code**: `terraform/proxmox`

### Managed Resources
- Virtual Machines (LXC/QEMU)
- Cloud-Init configurations (Users, SSH Keys, IP)
- Network settings

## Deployment Workflow

### 1. Configuration
Before running Terraform, you must configure the environment variables in `terraform.tfvars`.

**Command**:
```bash
cd terraform/proxmox

# Create variables file
cat > terraform.tfvars <<EOF
# --- Required Variables ---
pm_api_url   = "<PROXMOX_API_URL>"      # e.g., https://192.168.1.20:8006/api2/json
pm_user      = "<PROXMOX_USER>"         # e.g., root@pam
pm_password  = "<PROXMOX_PASSWORD>"
sshkeys      = "<SSH_PUBLIC_KEY>"       # e.g., ssh-rsa AAA...

# --- Optional Variables (Defaults shown) ---
target_node  = "<TARGET_NODE>"          # Default: pve0
vmid         = <VM_ID>                  # Default: 0 (auto-assign)
storage_pool = "<STORAGE_POOL>"         # Default: vmdata
vm_name      = "<VM_NAME>"              # Default: dev-vm-01
cores        = <CORES>                  # Default: 2
memory       = <MEMORY_MB>              # Default: 4096
disk_size    = "<DISK_SIZE>"            # Default: "20G"
ip_config    = "<IP_CONFIG>"            # Default: "ip=dhcp"
EOF
```

### 2. Provisioning
Once configured, use Terraform to plan and apply changes.

**Command**:
```bash
# Initialize Terraform (download providers)
terraform init

# Preview changes
terraform plan

# Apply changes (provision VMs)
terraform apply
```

## Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `pm_api_url` | **Required** | Proxmox API Endpoint |
| `pm_user` | **Required** | Proxmox User (e.g., root@pam) |
| `pm_password` | **Required** | **[Sensitive]** Proxmox Password |
| `sshkeys` | **Required** | **[Sensitive]** SSH Public Keys for Cloud-Init |
| `target_node` | `"pve0"` | Target Proxmox Node name |
| `vmid` | `0` | VM ID (0 = auto-assign) |
| `storage_pool` | `"vmdata"` | Storage pool for VM disks |
| `vm_name` | `"dev-vm-01"` | Name of the VM |
| `cores` | `2` | Number of CPU cores |
| `memory` | `4096` | RAM in MB |
| `disk_size` | `"20G"` | Disk size (e.g., "20G") |
| `ip_config` | `"ip=dhcp"` | Cloud-Init IP config (e.g., "ip=1.2.3.4/24,gw=...") |

## Best Practices
- **Cloud-Init**: Always use Cloud-Init (`sshkeys`, `ip_config`) to bootstrap VMs.
- **State Management**: Keep `terraform.tfstate` secure.
- **Modules**: Use the `modules/proxmox-vm` for standardized VM deployments.
