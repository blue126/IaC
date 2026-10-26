# Existing testbed ownership is retained while each guest is adopted after migration.
locals {
  openbao_testbed_adopted = {
    openbao_testbed_bao = {
      name = "openbao-testbed-bao"
      vmid = 112
      ip   = "192.168.1.112"
      mac  = "BC:24:11:0F:1E:50"
      disk = "vm-112-disk-1"
    }
    openbao_testbed_control = {
      name = "openbao-testbed-control"
      vmid = 113
      ip   = "192.168.1.113"
      mac  = "BC:24:11:BE:93:4C"
      disk = "vm-113-disk-1"
    }
  }
}

resource "proxmox_virtual_environment_vm" "openbao_testbed" {
  for_each = local.openbao_testbed_adopted
  provider = proxmox.root

  name      = each.value.name
  node_name = "pve0"
  vm_id     = each.value.vmid
  started   = true
  on_boot   = true

  bios          = "ovmf"
  machine       = "q35"
  boot_order    = ["scsi0"]
  scsi_hardware = "virtio-scsi-pci"
  tags          = ["iac", "openbao-testbed", "test-only", "will-29"]

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
    numa    = false
  }

  memory {
    dedicated = 4096
    floating  = 4096
  }

  disk {
    datastore_id      = "vmdata"
    interface         = "scsi0"
    path_in_datastore = each.value.disk
    size              = 20
    file_format       = "raw"
    aio               = "io_uring"
    cache             = "none"
    discard           = "on"
    backup            = true
    replicate         = true
    iothread          = false
    ssd               = false
  }

  efi_disk {
    datastore_id      = "vmdata"
    file_format       = "raw"
    type              = "4m"
    pre_enrolled_keys = true
  }

  network_device {
    bridge      = "vmbr1"
    model       = "virtio"
    mac_address = each.value.mac
    firewall    = false
  }

  serial_device {
    device = "socket"
  }

  vga {
    type   = "serial0"
    memory = 16
  }

  operating_system {
    type = "other"
  }

  initialization {
    datastore_id = "vmdata"
    interface    = "ide2"

    dns {
      servers = ["192.168.1.1"]
    }

    ip_config {
      ipv4 {
        address = "${each.value.ip}/24"
        gateway = "192.168.1.1"
      }
    }

    user_account {
      username = "debian"
    }
  }

  lifecycle {
    prevent_destroy = true
    # Existing Cloud-Init credentials belong to the original initialization.
    ignore_changes = [
      efi_disk[0].pre_enrolled_keys,
      initialization[0].user_account[0].keys,
      initialization[0].user_account[0].password,
    ]
  }
}

resource "terraform_data" "openbao_testbed_authorization" {}

resource "ansible_host" "openbao_testbed" {
  for_each   = local.openbao_testbed_adopted
  depends_on = [proxmox_virtual_environment_vm.openbao_testbed]

  name   = each.value.name
  groups = ["openbao_testbed"]
  variables = {
    ansible_host = each.value.ip
    ansible_user = "debian"
  }
}

output "openbao_testbed_identifiers" {
  value = {
    bao = {
      ip   = local.openbao_testbed_adopted.openbao_testbed_bao.ip
      name = proxmox_virtual_environment_vm.openbao_testbed["openbao_testbed_bao"].name
      vmid = proxmox_virtual_environment_vm.openbao_testbed["openbao_testbed_bao"].vm_id
    }
    trusted_control = {
      ip   = local.openbao_testbed_adopted.openbao_testbed_control.ip
      name = proxmox_virtual_environment_vm.openbao_testbed["openbao_testbed_control"].name
      vmid = proxmox_virtual_environment_vm.openbao_testbed["openbao_testbed_control"].vm_id
    }
  }
}
