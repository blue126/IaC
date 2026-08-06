module "fileserver" {
  source = "../modules/proxmox-lxc"

  providers = {
    proxmox = proxmox.root
  }

  lxc_name       = "fileserver"
  target_node    = "pve1"
  vmid           = 111
  ostemplate     = "local:vztmpl/debian-12-turnkey-fileserver_18.0-1_amd64.tar.gz"
  cores          = 1
  memory         = 512
  swap           = 512
  rootfs_storage = "vmdata"
  rootfs_size    = "8G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.111/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  ostype         = "debian"

  bind_mounts = [
    {
      volume = "/tank/timemachine"
      path   = "/srv/timemachine"
    }
  ]

  sshkeys = var.sshkeys
}

output "fileserver_ip" {
  value = module.fileserver.lxc_ip
}

resource "ansible_host" "fileserver" {
  name   = "fileserver"
  groups = ["pve_lxc"]
  variables = {
    ansible_host = "192.168.1.111"
  }
}
