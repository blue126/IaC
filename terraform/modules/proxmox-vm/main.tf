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
  
  # Serial Console for Copy-Paste
  serial {
    id   = 0
    type = "socket"
  }

  cpu {
    cores = var.cores
  }
  
  memory  = var.memory
  scsihw  = "virtio-scsi-pci"

  # Network
  network {
    id     = 0
    model  = "virtio"
    bridge = var.network_bridge
  }



  # Disk
  disk {
    storage = var.storage_pool
    type    = "disk"
    size    = var.disk_size
    slot    = "scsi0"
    discard = true
  }

  # EFI Disk (Only for OVMF)
  dynamic "efidisk" {
    for_each = var.bios == "ovmf" ? [1] : []
    content {
      efitype = "4m"
      storage = var.efidisk_storage != null ? var.efidisk_storage : var.storage_pool
    }
  }

  # Cloud-Init Disk
  disk {
    slot    = "scsi1"
    type    = "cloudinit"
    storage = var.storage_pool
  }

  # Cloud-Init Settings
  os_type   = "cloud-init"
  ciuser    = var.ciuser
  cicustom  = var.cicustom
  sshkeys   = var.sshkeys
  ipconfig0 = var.ip_address != null ? "ip=${var.ip_address},gw=${var.gateway}" : "ip=dhcp"
  nameserver = var.nameserver

  lifecycle {
    ignore_changes = [
      clone,
      full_clone,
      efidisk,
    ]
  }
}
