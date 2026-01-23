module "devcontainer" {
  source = "../modules/proxmox-vm"

  vm_name        = "devcontainer"
  target_node    = "pve0"
  vmid           = 102
  template_name  = "ubuntu-24.04-template"
  
  cores          = 4
  memory         = 8192
  disk_size      = "50G"
  
  ip_address     = "192.168.1.102/24"
  gateway        = "192.168.1.1" # Explicitly setting gateway locally to be safe, though module default is same
  
  sshkeys        = var.sshkeys
  storage_pool   = var.storage_pool
}

resource "ansible_host" "devcontainer" {
  name   = "devcontainer"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.102"
  }
}


output "devcontainer_ip" {
  value = "192.168.1.102"
}
