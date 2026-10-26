# Adopt the existing Proxmox Datacenter Manager and its managed Cloud-Init seed.
resource "proxmox_virtual_environment_vm" "proxmox_datacenter_manager" {
  provider = proxmox.root

  name      = "proxmox-datacenter-manager"
  node_name = "pve0"
  vm_id     = 117
  started   = true
  on_boot   = true

  bios            = "seabios"
  machine         = "q35"
  boot_order      = ["scsi0"]
  scsi_hardware   = "virtio-scsi-pci"
  keyboard_layout = "en-us"
  tablet_device   = true

  # Preserve the existing PVE setting; QGA was already absent inside the guest.
  agent {
    enabled = true
    timeout = "5s"
    trim    = false
    type    = "virtio"
  }

  cpu {
    cores   = 2
    sockets = 1
    type    = "host"
  }

  memory {
    dedicated = 4096
    floating  = 4096
  }

  disk {
    datastore_id      = "vmdata"
    path_in_datastore = "vm-117-disk-0"
    file_format       = "raw"
    interface         = "scsi0"
    size              = 40
    aio               = "io_uring"
    backup            = true
    cache             = "none"
    discard           = "on"
    iothread          = false
    replicate         = true
    ssd               = false
  }

  # Existing vmdata:vm-117-cloudinit keeps the original NoCloud instance ID.
  initialization {
    datastore_id = "vmdata"
    interface    = "ide2"

    dns {
      servers = ["192.168.1.1"]
    }

    ip_config {
      ipv4 {
        address = "192.168.1.117/24"
        gateway = "192.168.1.1"
      }
    }

    user_account {
      username = "debian"
      keys     = var.sshkeys
    }
  }

  operating_system {
    type = "other"
  }

  serial_device {
    device = "socket"
  }

  vga {
    type   = "serial0"
    memory = 16
  }

  network_device {
    bridge      = "vmbr1"
    model       = "virtio"
    mac_address = "BC:24:11:C8:86:83"
    firewall    = false
  }

  lifecycle {
    prevent_destroy = true

    # Keep the module's creation-only credential policy; Ansible owns guest SSH.
    ignore_changes = [
      initialization[0].user_account[0].keys,
      initialization[0].user_account[0].password,
    ]
  }
}

resource "ansible_host" "proxmox_datacenter_manager" {
  depends_on = [proxmox_virtual_environment_vm.proxmox_datacenter_manager]

  name   = "proxmox-datacenter-manager"
  groups = ["pve_vms"]
  variables = {
    ansible_host = "192.168.1.117"
    ansible_user = "debian"
  }
}
