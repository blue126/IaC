module "netbox" {
  source = "../modules/proxmox-vm"

  vm_name       = "netbox"
  target_node   = "pve0"
  vmid          = 104
  ip_address    = "192.168.1.104/24"
  cores         = 2
  memory        = 4096
  disk_size     = "20G"
  storage_pool  = var.storage_pool
  sshkeys        = var.sshkeys
  cicustom       = null
  cloudinit_slot = "ide2"
}

output "netbox_ip" {
  value = module.netbox.default_ip
}
