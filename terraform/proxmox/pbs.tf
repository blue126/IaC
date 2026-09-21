# Existing VM on the standalone node; never create a replacement backup server.
# Raw hostpci IDs have API-token write limitations in bpg 0.70.0. Import/plan
# is not proof that subsequent apply is supported; review that boundary first.
# bpg 0.70.0 can reboot a running VM after agent/boot/keyboard changes even when
# reboot=false. Treat any such update as maintenance, not state-only adoption.
import {
  to = proxmox_virtual_environment_vm.pbs
  id = "pve2/100"
}

resource "proxmox_virtual_environment_vm" "pbs" {
  provider = proxmox.pve2

  name       = "proxmox-backup-server"
  node_name  = "pve2"
  vm_id      = 100
  bios       = "ovmf"
  machine    = "q35"
  boot_order = ["scsi0"]
  on_boot    = true
  started    = true

  agent {
    enabled = true
  }

  cpu {
    cores   = 4
    sockets = 1
  }

  memory {
    dedicated = 16384
  }

  operating_system {
    type = "l26"
  }

  scsi_hardware = "virtio-scsi-single"

  efi_disk {
    datastore_id      = "local-lvm"
    type              = "4m"
    pre_enrolled_keys = false
  }

  disk {
    datastore_id = "mainpool"
    interface    = "scsi0"
    size         = 80
  }

  network_device {
    model       = "virtio"
    bridge      = "vmbr0"
    firewall    = true
    mac_address = "BC:24:11:00:01:13"
  }

  # One HBA and two NVMe devices; their address-to-device mapping is unverified.
  hostpci {
    device = "hostpci0"
    id     = "0000:01:00.0"
    pcie   = true
    rombar = true
  }

  hostpci {
    device = "hostpci1"
    id     = "0000:0d:00.0"
    pcie   = true
    rombar = true
  }

  hostpci {
    device = "hostpci2"
    id     = "0000:10:00.0"
    pcie   = true
    rombar = true
  }

  serial_device {
    device = "socket"
  }

  vga {
    type = "serial0"
  }

  smbios {
    uuid = "de3d8b94-f4fb-45aa-a123-fad255bed501"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [efi_disk]
  }
}

resource "ansible_host" "pbs" {
  name   = "pbs"
  groups = ["pbs"]
  variables = {
    ansible_host = "192.168.1.249"
    ansible_user = "root"
  }
}
