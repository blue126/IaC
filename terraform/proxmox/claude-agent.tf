module "claude_agent" {
  source = "../modules/proxmox-lxc"

  lxc_name       = "claude-agent"
  target_node    = "pve0"
  vmid           = 108
  ostemplate     = "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
  cores          = 2
  memory         = 2048
  swap           = 512
  rootfs_storage = "vmdata"
  rootfs_size    = "10G"
  network_bridge = "vmbr1"
  ip_address     = "192.168.1.108/24"
  gateway        = "192.168.1.1"
  unprivileged   = true
  features       = ["nesting=1"]
  ostype         = "ubuntu"

  sshkeys = var.sshkeys
}

output "claude_agent_ip" {
  value = module.claude_agent.lxc_ip
}

resource "ansible_host" "claude_agent" {
  name   = "claude-agent"
  groups = ["pve_lxc"]
  variables = {
    ansible_host = "192.168.1.108"
  }
}
