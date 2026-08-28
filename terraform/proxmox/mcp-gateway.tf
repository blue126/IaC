module "mcp_gateway" {
  source = "../modules/proxmox-vm"

  vm_name     = "mcp-gateway"
  target_node = "pve0"
  vmid        = 109
  cores       = 2
  memory      = 4096
  disk_size   = "32G"
  ip_address  = "192.168.1.109/24"

  storage_pool = var.storage_pool
  sshkeys      = var.sshkeys
}

output "mcp_gateway_ip" {
  value = module.mcp_gateway.default_ip
}

resource "ansible_host" "mcp_gateway" {
  name   = "mcp-gateway"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.109"
  }
}
