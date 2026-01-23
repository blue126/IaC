module "anki" {
  source = "../modules/proxmox-lxc"

  lxc_name       = "anki-sync-server"
  target_node    = "pve0"
  vmid           = 100
  ostemplate     = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
  cores          = 1
  memory         = 2048
  swap           = 2048
  rootfs_storage = "vmdata"
  rootfs_size    = "8G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.100/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  features       = ["nesting=1"]
  ostype         = "debian"
  
  sshkeys        = var.sshkeys
}

output "anki_ip" {
  value = module.anki.lxc_ip
}

resource "ansible_host" "anki" {
  name   = "anki"
  groups = ["pve_lxc"]
  variables = {
    ansible_host = "192.168.1.100"
  }
}
