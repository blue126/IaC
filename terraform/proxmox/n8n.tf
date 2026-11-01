module "n8n" {
  source = "../modules/proxmox-vm"

  vm_name        = "n8n"
  target_node    = "pve0"
  vmid           = 106
  template_name  = "ubuntu-24.04-template"
  cores          = 2
  memory         = 4096
  disk_size      = "20G"
  storage_pool   = "vmdata"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.106/24"
  gateway        = "192.168.1.1"
  nameserver     = "192.168.1.1"
  bios           = "ovmf"
  machine        = "q35"
  cicustom       = "user=local:snippets/cloud-init-ubuntu.yml"
  cloudinit_slot = "ide2"
  onboot         = true
  agent          = 1
  vga_type       = "serial0"

  sshkeys = var.sshkeys
}

output "n8n_ip" {
  value = module.n8n.default_ip
}

resource "ansible_host" "n8n" {
  name   = "n8n"
  groups = ["pve_vms"]
  variables = {
    ansible_host = "192.168.1.106"
    ansible_user = "ubuntu"
  }
}
