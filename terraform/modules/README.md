# Terraform Modules

Reusable Terraform modules for infrastructure components.

## Available Modules

### `proxmox-vm/`
Creates Proxmox VMs with standardized configurations.

**Inputs**: vmid, hostname, cores, memory, disk, network  
**Outputs**: vm_id, vm_ip

### `network/`
Manages network configurations (VLANs, subnets, routing).

**Purpose**: Provide network abstraction layer across Proxmox and ESXi.

## Usage

```hcl
module "my_vm" {
  source = "../modules/proxmox-vm"
  # ... parameters
}
```
