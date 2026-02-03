# Jenkins CI/CD Server
# LXC container for running Jenkins with Terraform and Ansible

module "jenkins" {
  source = "../modules/proxmox-lxc"

  lxc_name       = "jenkins"
  target_node    = "pve0"
  vmid           = 107
  ostemplate     = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
  cores          = 2
  memory         = 2048
  swap           = 1024
  rootfs_storage = "vmdata"
  rootfs_size    = "16G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.107/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  features       = ["nesting=1"]
  ostype         = "debian"

  sshkeys = var.sshkeys
}

output "jenkins_ip" {
  value = module.jenkins.lxc_ip
}

resource "ansible_host" "jenkins" {
  name   = "jenkins"
  groups = ["pve_lxc", "jenkins"]
  variables = {
    ansible_host = "192.168.1.107"
  }
}
