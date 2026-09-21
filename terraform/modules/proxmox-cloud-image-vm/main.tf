terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

resource "proxmox_virtual_environment_download_file" "image" {
  content_type       = "iso"
  datastore_id       = var.image_datastore
  node_name          = var.target_node
  file_name          = var.image_file_name
  url                = var.image_url
  checksum           = var.image_checksum
  checksum_algorithm = var.image_checksum_algorithm
}

resource "proxmox_virtual_environment_vm" "vm" {
  name      = var.vm_name
  node_name = var.target_node
  vm_id     = var.vmid

  agent {
    enabled = true
    # Ansible installs QGA after first boot; use the static IP for bootstrap.
    timeout = "5s"
  }

  boot_order = ["scsi0"]

  bios       = var.bios
  machine    = var.machine
  on_boot    = var.on_boot
  protection = var.protection
  started    = var.started
  tags       = var.tags

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
    file_id      = proxmox_virtual_environment_download_file.image.id
    size         = var.disk_size_gb
    interface    = "scsi0"
    discard      = "on"
  }

  initialization {
    datastore_id = var.storage_pool

    ip_config {
      ipv4 {
        address = var.ip_address != null ? var.ip_address : "dhcp"
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
    ignore_changes = [
      initialization[0].user_account[0].keys,
      # Cloud-Init credentials are create-time only; Ansible owns SSH afterward.
      initialization[0].user_account[0].password,
    ]
  }
}
