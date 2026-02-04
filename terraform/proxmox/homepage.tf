module "homepage" {
  source = "../modules/proxmox-lxc"

  lxc_name       = "homepage"
  target_node    = "pve0"
  vmid           = 103
  ostemplate     = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
  cores          = 2
  memory         = 4096
  swap           = 2048
  rootfs_storage = "vmdata"
  rootfs_size    = "4G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.103/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  features       = ["nesting=1"]
  ostype         = "debian"

  sshkeys = var.sshkeys
}

output "homepage_ip" {
  value = module.homepage.lxc_ip
}

resource "ansible_host" "homepage" {
  name   = "homepage"
  groups = ["pve_lxc"]
  variables = {
    ansible_host = "192.168.1.103"
  }
}
