resource "ansible_host" "pve0" {
  name   = "pve0"
  groups = ["proxmox_cluster"]
  variables = {
    ansible_host     = "192.168.1.50"
    ansible_user     = "root"
    ansible_ssh_pass = var.proxmox_ssh_password
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
    ansible_ssh_pass = var.proxmox_ssh_password
    proxmox_api_host = "{{ ansible_host }}"
    proxmox_api_port = 8006
    proxmox_api_user = "root@pam"
  }
}

# pve2 is NOT a member of HomePVECluster -- it has no corosync.conf and its
# VMID space is its own (its VM 100 is unrelated to pve0's LXC 100). It sits in
# proxmox_cluster anyway because that group carries host-level PVE config
# (tailscale_accept_dns and friends), not corosync membership.
#
# Its management IP lives on vmbr0, the reverse of pve0/pve1 where vmbr0 is
# management (.20/.21) and vmbr1 carries guests (.50/.51).
resource "ansible_host" "pve2" {
  name   = "pve2"
  groups = ["proxmox_cluster"]
  variables = {
    ansible_host = "192.168.1.52"
    ansible_user = "root"
    # Use an explicitly supplied SSH key/agent or --ask-pass; do not assume
    # this standalone node shares the cluster's root password.
    proxmox_api_host = "{{ ansible_host }}"
    proxmox_api_port = 8006
    proxmox_api_user = "root@pam"
  }
}
