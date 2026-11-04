# Proxmox Infrastructure

Terraform configurations for managing Proxmox VE cluster resources.

## Purpose

- Provision internal homelab VMs on the Proxmox cluster (pve0, pve1); RemoteCC VMs live in `../remotecc/`
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
module "dev_vm" {
  source = "../modules/proxmox-vm"
  
  vm_name       = "dev-vm-01"
  target_node   = "pve0"
  cores         = 2
  memory        = 2048
  storage_pool  = "local-zfs"
  cicustom_path = "user=local:snippets/cloud-init-ubuntu2404.yml"
}
```
