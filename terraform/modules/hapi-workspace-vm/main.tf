terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

# The independent HAPI executor owns the caller's state. This module must not
# be instantiated in the WireGuard employee roster or VM500 resource state.
module "vm" {
  source = "../proxmox-vm"

  vm_name             = "hapi-${var.workspace_id}"
  vmid                = var.network.vmid
  target_node         = var.node
  template_name       = var.template_name
  bios                = var.bios
  cores               = var.cores
  memory              = var.memory
  disk_size           = var.disk_size
  storage_pool        = var.storage_pool
  network_bridge      = var.network.vnet
  network_mac_address = var.network.mac
  ip_address          = var.network.address
  gateway             = var.network.gateway
  nameserver          = var.nameserver
  ciuser              = "employee"
  sshkeys             = var.admin_public_keys
  cicustom            = null
  initial_started     = false
  onboot              = false
  protection          = true
  hook_script_file_id = var.hook_script_file_id
  tags                = ["hapi-workspace"]
}
