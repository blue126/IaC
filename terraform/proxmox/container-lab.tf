resource "proxmox_virtual_environment_vm" "containerlab" {
  provider = proxmox.pve2

  name      = "containerlab"
  node_name = "pve2"
  vm_id     = 108
  started   = false
  on_boot   = false

  bios            = "ovmf"
  machine         = "q35"
  boot_order      = ["scsi0"]
  scsi_hardware   = "virtio-scsi-pci"
  keyboard_layout = "en-us"
  tablet_device   = true

  agent {
    enabled = true
    timeout = "5s"
    trim    = false
    type    = "virtio"
  }

  cpu {
    cores   = 4
    sockets = 1
    type    = "host"
  }

  memory {
    dedicated = 32768
    floating  = 32768
  }

  # Existing EFI volume: pve2-ssd:108/vm-108-disk-0.raw.
  efi_disk {
    datastore_id      = "pve2-ssd"
    file_format       = "raw"
    type              = "4m"
    pre_enrolled_keys = true
  }

  disk {
    datastore_id      = "pve2-ssd"
    path_in_datastore = "108/vm-108-disk-1.raw"
    file_format       = "raw"
    interface         = "scsi0"
    size              = 100
    aio               = "io_uring"
    backup            = true
    cache             = "none"
    discard           = "on"
    iothread          = false
    replicate         = true
    ssd               = false
  }

  # Preserve the original NoCloud seed as a regular CD-ROM; never regenerate it.
  cdrom {
    enabled   = true
    file_id   = "local:iso/containerlab-108-frozen-seed-20261026.iso"
    interface = "ide2"
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
    bridge      = "vmbr0"
    model       = "virtio"
    mac_address = "BC:24:11:B3:C8:DE"
    firewall    = false
  }

  lifecycle {
    prevent_destroy = true

    # bpg 0.70 reads legacy creation metadata even without a managed seed disk.
    # The explicit CD-ROM owns the original NoCloud seed; never recreate it.
    ignore_changes = [initialization, efi_disk[0].pre_enrolled_keys]
  }
}

output "container_lab_ip" {
  value = proxmox_virtual_environment_vm.containerlab.initialization[0].ip_config[0].ipv4[0].address
}

resource "ansible_host" "container_lab" {
  depends_on = [proxmox_virtual_environment_vm.containerlab]

  name   = "container-lab"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.108"
  }
}

# Preserve the existing inventory resource through the service-name change.
moved {
  from = ansible_host.ubuntu_2604
  to   = ansible_host.container_lab
}
