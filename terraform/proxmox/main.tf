

module "netbox" {
  source = "../modules/proxmox-vm"

  vm_name       = "netbox"
  target_node   = var.target_node
  vmid          = 104
  ip_address    = "ip=192.168.1.104/24,gw=192.168.1.1"
  # ip_address    = "ip=dhcp"
  cores         = 2
  memory        = 4096
  disk_size     = "20G"
  storage_pool  = var.storage_pool
  sshkeys       = var.sshkeys
}

output "netbox_ip" {
  value = module.netbox.default_ip
}
