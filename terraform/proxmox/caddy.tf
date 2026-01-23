module "caddy" {
  source = "../modules/proxmox-lxc"

  lxc_name       = "caddy"
  target_node    = "pve0"
  vmid           = 105
  ostemplate     = "local:vztmpl/alpine-3.22-default_20250617_amd64.tar.xz"
  cores          = 1
  memory         = 512
  swap           = 512
  rootfs_storage = "vmdata"
  rootfs_size    = "100G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.105/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  features       = ["nesting=1"]
  ostype         = "alpine"
  
  sshkeys        = var.sshkeys
}

output "caddy_ip" {
  value = module.caddy.lxc_ip
}

resource "ansible_host" "caddy" {
  name   = "caddy"
  groups = ["pve_lxc"]
  variables = {
    ansible_user = "root"
    ansible_host = "192.168.1.105"
  }
}
