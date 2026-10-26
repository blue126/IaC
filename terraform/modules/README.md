# Terraform Modules

Reusable Terraform modules for infrastructure components.

## Available Modules

### `proxmox-vm/`
Creates Proxmox VMs with standardized configurations. The system disk comes from one of two sources:

- **Local template** (default): clones `template_name`; Cloud-Init user data comes from the `cicustom` snippet.
- **Cloud image**: set `image_url`, `image_file_name` and `image_checksum`; the module downloads the pinned image to `image_datastore` and imports it as the disk. Pass `cicustom = null` to use native Cloud-Init (`bootstrap_password`, `sshkeys`).

**Inputs**: `vm_name`, `target_node`, `template_name` or `image_url`, `cores`, `memory`, `storage_pool`, `disk_size`, `network_bridge`, `cicustom`
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
