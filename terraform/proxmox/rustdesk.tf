module "rustdesk" {
  source = "../modules/proxmox-vm"

  vm_name      = "rustdesk"
  target_node  = "pve0"
  vmid         = 102
  cores        = 2
  memory       = 4096
  disk_size    = "50G"
  
  ip_address   = "192.168.1.102/24"
  
  # Global settings
  storage_pool   = var.storage_pool
  sshkeys        = var.sshkeys
  cicustom       = null
  cloudinit_slot = "ide2"
}

output "rustdesk_ip" {
  value = module.rustdesk.default_ip
}

resource "ansible_host" "rustdesk" {
  name   = "rustdesk"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.102"
  }
}
