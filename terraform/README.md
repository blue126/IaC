# Terraform Infrastructure Code

This directory contains Terraform configurations for infrastructure provisioning across multiple platforms.

## Directory Structure

- **`proxmox/`** - Proxmox VE environment (calls `proxmox-vm` module)
- **`esxi/`** - VMware ESXi infrastructure definitions (planned)
- **`modules/`** - Reusable Terraform modules
  - `proxmox-vm/` - Proxmox VM creation module
  - `network/` - Network configuration module (VLANs, subnets, routing)

## Workflow

1. **Terraform** provisions the infrastructure (VMs, networks, storage)
2. **Ansible** (in `../ansible/`) configures the provisioned resources

## Usage

```bash
cd proxmox/
terraform init
terraform plan
terraform apply
```

## Future Plans

- ESXi host integration (~1 month)
- OpenWrt network device management
- Multi-platform infrastructure orchestration
