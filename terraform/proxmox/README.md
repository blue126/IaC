# Proxmox Infrastructure

Terraform configurations for managing Proxmox VE cluster resources.

## Purpose

- Provision VMs on Proxmox cluster (pve0, pve1, pve2)
- Manage storage, networking, and compute resources
- Call reusable modules from `../modules/`

## Usage

```bash
terraform init
terraform plan
terraform apply
```

## Configuration

Define VM resources using the `proxmox-vm` module:

```hcl
module "example_vm" {
  source = "../modules/proxmox-vm"
  
  vmid     = 103
  hostname = "example"
  cores    = 2
  memory   = 2048
}
```
