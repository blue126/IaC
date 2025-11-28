# Terraform Modules

Reusable Terraform modules for infrastructure components.

## Available Modules

### `proxmox-vm/`
Creates Proxmox VMs with standardized configurations.

**Inputs**: `vm_name`, `target_node`, `template_name`, `cores`, `memory`, `storage_pool`, `disk_size`, `network_bridge`, `cicustom_path`
**Outputs**: `vm_id`, `default_ip`

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
