module "remotecc_ops" {
  source = "../modules/proxmox-vm"

  vm_name     = "remotecc-ops"
  target_node = "pve0"
  vmid        = 116
  cores       = 2
  memory      = 4096
  disk_size   = "32G"
  # Matches the running disk; changing it is an in-place update with no benefit here.
  disk_discard = "ignore"
  ip_address   = "192.168.1.116/24"

  storage_pool = var.storage_pool
  sshkeys      = var.sshkeys
}

output "remotecc_ops_ip" {
  value = module.remotecc_ops.default_ip
}

resource "ansible_host" "remotecc_ops" {
  name   = "remotecc-ops"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.116"
  }
}

moved {
  from = module.ws_executor
  to   = module.remotecc_ops
}

moved {
  from = ansible_host.ws_executor
  to   = ansible_host.remotecc_ops
}
