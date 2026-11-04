# Clean, never-booted image source for the standalone employee pilot.
resource "proxmox_virtual_environment_vm" "employee_template" {
  provider   = proxmox.pve2
  count      = var.employee_access == null ? 0 : 1
  name       = "employee-ubuntu-2604-template"
  node_name  = var.employee_access.node
  vm_id      = var.employee_access.template_id
  template   = true
  started    = false
  on_boot    = false
  boot_order = ["scsi0"]
  cpu {
    cores = 2
    type  = "host"
  }
  memory { dedicated = 1024 }
  disk {
    datastore_id = var.employee_access.storage_pool
    file_id      = "local:iso/ubuntu-26.04-server-cloudimg-amd64.img"
    interface    = "scsi0"
    size         = 20
    discard      = "on"
  }
  network_device {
    bridge       = var.employee_access.uplink_bridge
    disconnected = true
  }
  initialization {
    datastore_id = var.employee_access.storage_pool
    user_account {
      username = "ubuntu"
      keys     = var.employee_access.admin_public_keys
    }
  }
  serial_device { device = "socket" }
  vga { type = "serial0" }
  tags = ["employee-template"]
  lifecycle { prevent_destroy = true }
}

resource "proxmox_virtual_environment_file" "employee_guest_bootstrap" {
  provider     = proxmox.pve2
  count        = var.employee_access == null ? 0 : 1
  node_name    = var.employee_access.node
  datastore_id = var.employee_access.snippet_datastore
  content_type = "snippets"
  source_raw {
    file_name = "employee-guest-bootstrap.yaml"
    data      = <<-CLOUD
      #cloud-config
      package_update: true
      packages:
        - qemu-guest-agent
      runcmd:
        - [systemctl, enable, --now, qemu-guest-agent]
    CLOUD
  }
}
