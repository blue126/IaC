# Jenkins CI/CD Agent
# Peer LXC for isolated plan and deploy executor identities

module "jenkins_agent" {
  source = "../modules/proxmox-lxc"

  lxc_name       = "jenkins-agent"
  target_node    = "pve0"
  vmid           = 110
  ostemplate     = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
  cores          = 2
  memory         = 2048
  swap           = 1024
  rootfs_storage = "vmdata"
  rootfs_size    = "16G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.110/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  ostype         = "debian"

  sshkeys = var.sshkeys
}

output "jenkins_agent_ip" {
  value = module.jenkins_agent.lxc_ip
}

resource "ansible_host" "jenkins_agent" {
  name   = "jenkins-agent"
  groups = ["pve_lxc", "jenkins_agent"]
  variables = {
    ansible_host = "192.168.1.110"
  }
}
