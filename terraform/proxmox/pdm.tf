# Proxmox Datacenter Manager VM
# PDM is installed separately with a one-off Ansible playbook.
module "proxmox_datacenter_manager" {
  source = "../modules/proxmox-cloud-image-vm"

  providers = {
    proxmox = proxmox.root
  }

  vm_name     = "proxmox-datacenter-manager"
  target_node = "pve1"
  vmid        = 117

  image_datastore          = "local"
  image_file_name          = "debian-13-genericcloud-amd64.img"
  image_url                = "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2"
  image_checksum           = "95e110dfcdbd0ed8a82a75ed9579802f9950cabf51a810dcc6388e81bc778188713878b9f28d583a0ea602fbf48b35996ae9ad37f584166d8fbd6489df248f53"
  image_checksum_algorithm = "sha512"

  cores          = 2
  memory         = 4096
  disk_size_gb   = 40
  storage_pool   = "local-lvm"
  network_bridge = "vmbr1"
  bios           = "seabios"
  ciuser         = "debian"
  ip_address     = "192.168.1.117/24"
  gateway        = "192.168.1.1"
  nameserver     = "192.168.1.1"
  sshkeys        = var.sshkeys
}

resource "ansible_host" "proxmox_datacenter_manager" {
  depends_on = [module.proxmox_datacenter_manager]

  name   = "proxmox-datacenter-manager"
  groups = ["pve_vms"]
  variables = {
    ansible_host = "192.168.1.117"
    ansible_user = "debian"
  }
}
