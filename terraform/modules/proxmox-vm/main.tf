terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

data "proxmox_virtual_environment_vms" "template_vm" {
  node_name = var.target_node
}

locals {
  # Find the template VM ID by name.
  # Two-step lookup: first collect all matches, then safely index.
  # Direct [0] on the for-expression would crash with "Invalid index"
  # if the template name doesn't exist on the target node.
  template_matches = [
    for vm in data.proxmox_virtual_environment_vms.template_vm.vms :
    vm.vm_id
    if vm.name == var.template_name
  ]
  template_vm_id = length(local.template_matches) > 0 ? local.template_matches[0] : null

  # Parse disk size (e.g. "50G" -> 50)
  disk_size_gb = tonumber(regex("^(\\d+)", var.disk_size)[0])

  # Parse cicustom: strip "user=" prefix for bpg user_data_file_id
  # telmate format: "user=local:snippets/cloud-init-ubuntu.yml"
  # bpg format:     "local:snippets/cloud-init-ubuntu.yml"
  cicustom_file_id = (
    var.cicustom != null
    ? replace(var.cicustom, "/^user=/", "")
    : null
  )

}

resource "proxmox_virtual_environment_vm" "vm" {
  name      = var.vm_name
  node_name = var.target_node
  vm_id     = var.vmid != 0 ? var.vmid : null

  clone {
    vm_id = local.template_vm_id
    full  = var.full_clone
  }

  agent {
    enabled = var.agent == 1
  }

  bios    = var.bios
  machine = var.machine
  on_boot = var.onboot
  tags    = var.tags

  cpu {
    cores = var.cores
    type  = var.cpu_type
  }

  memory {
    dedicated = var.memory
    floating  = var.balloon_memory != null ? var.balloon_memory : var.memory
  }

  scsi_hardware = "virtio-scsi-pci"

  dynamic "efi_disk" {
    for_each = var.bios == "ovmf" ? [1] : []
    content {
      datastore_id      = var.efidisk_storage != null ? var.efidisk_storage : var.storage_pool
      file_format       = "raw"
      type              = "4m"
      pre_enrolled_keys = true
    }
  }

  serial_device {
    device = "socket"
  }

  vga {
    type = var.vga_type
  }

  network_device {
    model  = "virtio"
    bridge = var.network_bridge
  }

  disk {
    datastore_id = var.storage_pool
    size         = local.disk_size_gb
    interface    = "scsi0"
    discard      = "on"
    file_format  = "raw"
  }

  initialization {
    datastore_id      = var.storage_pool
    user_data_file_id = local.cicustom_file_id

    ip_config {
      ipv4 {
        address = var.ip_address != null ? "${var.ip_address}" : "dhcp"
        gateway = var.ip_address != null ? var.gateway : null
      }
    }

    user_account {
      keys     = var.sshkeys
      username = var.ciuser
    }

    dns {
      servers = [var.nameserver]
    }
  }

  lifecycle {
    # Fail early with a clear message if the clone template is not found
    precondition {
      condition     = local.template_vm_id != null
      error_message = "Template '${var.template_name}' not found on node '${var.target_node}'."
    }

    ignore_changes = [
      # Clone is a create-time-only parameter; Proxmox does not record
      # which template a VM was cloned from, so the API never returns it
      # and state is always empty after import. Injecting it into state
      # would also change the provider's refresh logic for 30+ other
      # attributes (len(clone)>0 skips API refresh for defaults), risking
      # hidden drift. Safe to ignore — clone source is irrelevant after
      # the VM exists.
      clone,
    ]
  }
}
