terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

resource "proxmox_virtual_environment_container" "lxc" {
  description = "Managed by Terraform"
  node_name   = var.target_node
  vm_id       = var.vmid != 0 ? var.vmid : null

  initialization {
    hostname = var.lxc_name

    ip_config {
      ipv4 {
        address = var.ip_address
        gateway = var.ip_address != "dhcp" ? var.gateway : null
      }
    }

    user_account {
      keys     = var.sshkeys
      password = var.password
    }

    dns {
      servers = [var.nameserver]
    }
  }

  network_interface {
    name     = "eth0"
    bridge   = var.network_bridge
    enabled  = true
    firewall = true
  }

  operating_system {
    template_file_id = var.ostemplate
    type             = var.ostype
  }

  cpu {
    cores = var.cores
  }

  memory {
    dedicated = var.memory
    swap      = var.swap
  }

  disk {
    datastore_id = var.rootfs_storage
    size         = tonumber(regex("^(\\d+)", var.rootfs_size)[0])
  }

  features {
    nesting = contains(var.features, "nesting=1")
    fuse    = contains(var.features, "fuse=1")
    # keyctl = contains(var.features, "keyctl=1")
    # mount  = ...
  }

  unprivileged  = var.unprivileged
  started       = var.start
  start_on_boot = var.onboot

  lifecycle {
    ignore_changes = [
      # ForceNew + not readable via API. Password and SSH keys are
      # injected at "pct create" time only; Proxmox never returns them,
      # so state is always null after import/refresh → every plan sees
      # a diff and triggers destroy/recreate. Post-creation credential
      # management is handled by Ansible.
      initialization[0].user_account,
    ]
  }
}
