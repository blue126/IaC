module "ws_executor" {
  source = "../modules/proxmox-vm"

  vm_name     = "ws-executor"
  target_node = "pve0"
  vmid        = 116
  cores       = 2
  memory      = 4096
  disk_size   = "32G"
  ip_address  = "192.168.1.116/24"

  storage_pool = var.storage_pool
  sshkeys      = var.sshkeys
}

output "ws_executor_ip" {
  value = module.ws_executor.default_ip
}

resource "ansible_host" "ws_executor" {
  name   = "ws-executor"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.116"
  }
}
