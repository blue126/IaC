module "n8n" {
  source = "../modules/proxmox-lxc"

  lxc_name       = "n8n"
  target_node    = "pve0"
  vmid           = 106
  ostemplate     = "local:vztmpl/debian-12-turnkey-nodejs_18.0-1_amd64.tar.gz"
  cores          = 2
  memory         = 2048
  swap           = 512
  rootfs_storage = "vmdata"
  rootfs_size    = "8G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.106/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  features       = ["nesting=1"]
  ostype         = "debian"
  
  sshkeys        = var.sshkeys
}

output "n8n_ip" {
  value = module.n8n.lxc_ip
}

resource "ansible_host" "n8n" {
  name   = "n8n"
  groups = ["pve_lxc"]
  variables = {
    ansible_host = "192.168.1.106"
  }
}
