module "immich" {
  source = "../modules/proxmox-vm"

  vm_name      = "immich"
  target_node  = "pve0"
  vmid         = 101
  cores        = 2
  memory       = 8192
  disk_size    = "300G"
  
  # Legacy VM Settings
  bios            = "ovmf"
  machine         = "pc"
  efidisk_storage = var.storage_pool
  cicustom        = "user=local:snippets/cloud-init-ubuntu.yml"
  ip_address   = "192.168.1.101/24"
  
  # Global settings
  storage_pool   = var.storage_pool
  sshkeys        = var.sshkeys
  cloudinit_slot = "ide2"
}

output "immich_ip" {
  value = module.immich.default_ip
}
