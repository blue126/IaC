terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

locals {
  # The system disk comes either from a cloud image downloaded to the node
  # (image_url set) or from a full/linked clone of a local template.
  from_image = var.image_url != null
}

resource "proxmox_virtual_environment_download_file" "image" {
  count = local.from_image ? 1 : 0

  content_type       = "iso"
  datastore_id       = var.image_datastore
  node_name          = var.target_node
  file_name          = var.image_file_name
  url                = var.image_url
  checksum           = var.image_checksum
  checksum_algorithm = var.image_checksum_algorithm
}

# These VMs were created by the former proxmox-cloud-image-vm module, where
# the image was not counted.
moved {
  from = proxmox_virtual_environment_download_file.image
  to   = proxmox_virtual_environment_download_file.image[0]
}

data "proxmox_virtual_environment_vms" "template_vm" {
  count = local.from_image ? 0 : 1

  node_name = var.target_node
}

locals {
  # Find the template VM ID by name.
  # Two-step lookup: first collect all matches, then safely index.
  # Direct [0] on the for-expression would crash with "Invalid index"
  # if the template name doesn't exist on the target node.
  template_matches = local.from_image ? [] : [
    for vm in data.proxmox_virtual_environment_vms.template_vm[0].vms :
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

  dynamic "clone" {
    for_each = local.from_image ? [] : [1]
    content {
      vm_id = local.template_vm_id
      full  = var.full_clone
    }
  }

  agent {
    enabled = var.agent == 1
    # Image-based VMs get QGA from Ansible after first boot; do not wait for it.
    timeout = local.from_image ? "5s" : null
  }

  boot_order = local.from_image ? ["scsi0"] : null

  bios                = var.bios
  machine             = var.machine
  on_boot             = var.onboot
  protection          = var.protection
  started             = var.initial_started
  hook_script_file_id = var.hook_script_file_id
  tags                = var.tags

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
      pre_enrolled_keys = var.efi_pre_enrolled_keys
    }
  }

  serial_device {
    device = "socket"
  }

  vga {
    type = var.vga_type
  }

  network_device {
    model       = "virtio"
    bridge      = var.network_bridge
    mac_address = var.network_mac_address
  }

  disk {
    datastore_id = var.storage_pool
    file_id      = local.from_image ? proxmox_virtual_environment_download_file.image[0].id : null
    size         = local.disk_size_gb
    interface    = "scsi0"
    discard      = var.disk_discard
    file_format  = local.from_image ? null : "raw"
  }

  initialization {
    datastore_id        = var.storage_pool
    user_data_file_id   = local.cicustom_file_id
    vendor_data_file_id = var.vendor_data_file_id

    ip_config {
      ipv4 {
        address = var.ip_address != null ? "${var.ip_address}" : "dhcp"
        gateway = var.ip_address != null ? var.gateway : null
      }
    }

    user_account {
      keys     = var.sshkeys
      username = var.ciuser
      password = var.bootstrap_password
    }

    dns {
      servers = [var.nameserver]
    }
  }

  lifecycle {
    # Fail early with a clear message if the clone template is not found
    precondition {
      condition     = local.from_image || local.template_vm_id != null
      error_message = "Template '${var.template_name}' not found on node '${var.target_node}'."
    }

    precondition {
      condition     = !local.from_image || (var.image_file_name != null && var.image_checksum != null)
      error_message = "image_url requires image_file_name and image_checksum."
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

      # Existing EFI key enrollment is create-time state; do not replace a VM
      # merely to match the default used when creating a new EFI disk.
      efi_disk[0].pre_enrolled_keys,

      # Cloud-init SSH keys and password are create-time credentials. Changing
      # them forces VM replacement; Ansible manages access after provisioning.
      initialization[0].user_account[0].keys,
      initialization[0].user_account[0].password,

      # Power state is operated by hand (VMs are stopped for maintenance or
      # kept off on purpose); Terraform must never start or stop a VM. A new
      # VM still boots once on creation, the provider default.
      started,

      # Root-owned boundary hooks are reconciled by the approved PVE SSH play.
      hook_script_file_id,
    ]
  }
}
