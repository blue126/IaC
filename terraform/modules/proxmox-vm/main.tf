terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
    }
  }
}

resource "proxmox_vm_qemu" "vm" {
  name        = var.vm_name
  target_node = var.target_node
  vmid        = var.vmid
  clone       = var.template_name
  full_clone  = var.full_clone

  # System Settings
  bios    = var.bios
  machine = var.machine
  agent   = var.agent
  onboot  = var.onboot

  # Serial Console for Copy-Paste
  serial {
    id   = 0
    type = "socket"
  }

  cpu {
    cores = var.cores
  }

  memory = var.memory
  scsihw = "virtio-scsi-pci"

  # Network
  network {
    id     = 0
    model  = "virtio"
    bridge = var.network_bridge
  }



  # Cloud-Init Disk
  disk {
    slot    = var.cloudinit_slot
    type    = "cloudinit"
    storage = var.storage_pool
  }

  # Disk
  disk {
    storage = var.storage_pool
    type    = "disk"
    size    = var.disk_size
    slot    = "scsi0"
    discard = true
    format  = "raw" //to avoid cosmetic drift status of terraform
  }

  # Cloud-Init Settings
  os_type    = "cloud-init"
  ciuser     = var.ciuser
  cicustom   = var.cicustom
  sshkeys    = var.sshkeys
  ipconfig0  = var.ip_address != null ? "ip=${var.ip_address},gw=${var.gateway}" : "ip=dhcp"
  nameserver = var.nameserver

  lifecycle {
    ignore_changes = [
      clone,
      full_clone,
      efidisk,
      # Ignore SSH key changes to avoid requiring VM shutdown
      sshkeys,
      # Ignore tags drift (Proxmox returns " " instead of null)
      tags,
    ]
  }
}
