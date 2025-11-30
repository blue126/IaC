module "samba" {
  source = "../modules/proxmox-vm"

  vm_name      = "samba"
  target_node  = "pve0"
  vmid         = 102
  cores        = 1
  memory       = 512
  disk_size    = "50G"
  
  # Legacy VM Settings
  # full_clone   = false
  bios         = "ovmf"
  machine      = "q35"
  cicustom     = "user=local:snippets/ubuntu-password.yml"
  ip_address   = "ip=192.168.1.102/24,gw=192.168.1.1"
  
  # Global settings
  storage_pool = var.storage_pool
  sshkeys      = var.sshkeys
}

output "samba_ip" {
  value = module.samba.default_ip
}
