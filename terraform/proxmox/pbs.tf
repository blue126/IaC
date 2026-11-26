# Existing VM on the standalone node; never create a replacement backup server.
# Proxmox lets only root@pam (not an API token) write raw hostpci IDs, so a
# plan that changes hostpci cannot be applied with the Terraform token.
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

  # Never let the provider restart this VM. For reboot-required changes it
  # issues a shutdown and an immediate separate start; on 2026-11-27 the start's
  # pre-start reset of the hostpci1 SM963 overlapped the old QEMU teardown and
  # the drive came back unresponsive. Restart manually with `qm reboot 100`,
  # which starts only after Proxmox has finished its stop cleanup.
  reboot_after_update = false

  agent {
    enabled = true
  }

  # Standalone node with PCI passthrough, so live migration is not a concern;
  # host exposes AES-NI and AVX2 to PBS.
  cpu {
    cores   = 8
    sockets = 1
    type    = "host"
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

  # Passthrough mapping verified on pve2 after its 2026-09-21 reboot:
  # host 0000:01:00.0 (SAS3008) -> guest 0000:01:00.0 -> tank data HDDs.
  hostpci {
    device = "hostpci0"
    id     = "0000:01:00.0"
    pcie   = true
    rombar = true
  }

  # host 0000:0d:00.0 (Samsung SM963) -> guest 0000:02:00.0
  # -> serial S34ENY0J231801 / nvme-eui.002538c2710104e2.
  hostpci {
    device = "hostpci1"
    id     = "0000:0d:00.0"
    pcie   = true
    rombar = true
  }

  # host 0000:0c:00.0 (Samsung SM963) -> guest 0000:03:00.0
  # -> serial S34ENY0J112117 / nvme-eui.002538c171009240.
  # Enumerated as 0000:0a:00.0 before; re-verified on 2026-11-16 from the live
  # VM100 config and the serial seen inside the guest.
  hostpci {
    device = "hostpci2"
    id     = "0000:0c:00.0"
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
