resource "proxmox_virtual_environment_vm" "windows_server" {
  name      = "windows-server"
  node_name = "pve1"
  vm_id     = 112

  bios    = "ovmf"
  machine = "pc-q35-10.0"
  on_boot = true
  started = true

  agent {
    enabled = true
  }

  cpu {
    cores   = 4
    sockets = 1
    type    = "host"
  }

  memory {
    dedicated = 8192
    floating  = 0
  }

  operating_system {
    type = "win11"
  }

  scsi_hardware = "pvscsi"

  efi_disk {
    datastore_id      = "vmdata"
    file_format       = "raw"
    type              = "4m"
    pre_enrolled_keys = false
  }

  disk {
    datastore_id = "vmdata"
    interface    = "scsi0"
    size         = 80
    file_format  = "raw"
    discard      = "on"
    backup       = true
  }

  disk {
    datastore_id = "tank"
    interface    = "scsi1"
    size         = 2048
    file_format  = "raw"
    discard      = "on"
    backup       = true
  }

  network_device {
    model       = "vmxnet3"
    bridge      = "vmbr1"
    firewall    = true
    mac_address = "00:50:56:8f:0a:49"
  }

  smbios {
    uuid = "420f9b2a-7fc9-d05a-9290-785413c337dc"
  }

  lifecycle {
    ignore_changes = [efi_disk]
  }
}

resource "ansible_host" "windows_server" {
  name   = "windows-server"
  groups = ["pve_vms", "windows"]

  variables = {
    ansible_host                         = "192.168.1.248"
    ansible_user                         = "Administrator"
    ansible_connection                   = "winrm"
    ansible_winrm_transport              = "ntlm"
    ansible_winrm_server_cert_validation = "ignore"
  }
}
