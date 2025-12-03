terraform {
  required_providers {
    proxmox = {
      source = "telmate/proxmox"
    }
  }
}

resource "proxmox_lxc" "lxc" {
  hostname     = var.lxc_name
  target_node  = var.target_node
  vmid         = var.vmid != 0 ? var.vmid : null
  ostemplate   = var.ostemplate
  unprivileged = var.unprivileged
  onboot       = var.onboot
  start        = var.start
  ostype       = var.ostype
  password     = var.password
  
  # Resources
  cores  = var.cores
  memory = var.memory
  swap   = var.swap

  # Root filesystem
  rootfs {
    storage = var.rootfs_storage
    size    = var.rootfs_size
  }

  # Network
  network {
    name     = "eth0"
    bridge   = var.network_bridge
    ip       = var.ip_address
    gw       = var.gateway
    firewall = true
  }

  # SSH Keys
  ssh_public_keys = var.sshkeys

  # DNS
  nameserver = var.nameserver

  # Features (nesting, fuse, etc.)
  features {
    nesting = contains(var.features, "nesting=1")
    fuse    = contains(var.features, "fuse=1")
  }

  lifecycle {
    ignore_changes = [
      # Ignore template changes after container creation
      ostemplate,
    ]
  }
}
