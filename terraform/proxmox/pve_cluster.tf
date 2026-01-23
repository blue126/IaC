resource "ansible_host" "pve0" {
  name   = "pve0"
  groups = ["proxmox_cluster"]
  variables = {
    ansible_host     = "192.168.1.50"
    ansible_user     = "root"
    ansible_ssh_pass = "Admin123..."
    proxmox_api_host = "{{ ansible_host }}"
    proxmox_api_port = 8006
    proxmox_api_user = "root@pam"
  }
}

resource "ansible_host" "pve1" {
  name   = "pve1"
  groups = ["proxmox_cluster"]
  variables = {
    ansible_host     = "192.168.1.51"
    ansible_user     = "root"
    ansible_ssh_pass = "Admin123..."
    proxmox_api_host = "{{ ansible_host }}"
    proxmox_api_port = 8006
    proxmox_api_user = "root@pam"
  }
}

resource "ansible_host" "pve2" {
  name   = "pve2"
  groups = ["proxmox_cluster"]
  variables = {
    ansible_host     = "192.168.1.52"
    ansible_user     = "root"
    ansible_ssh_pass = "Admin123..."
    proxmox_api_host = "{{ ansible_host }}"
    proxmox_api_port = 8006
    proxmox_api_user = "root@pam"
  }
}
