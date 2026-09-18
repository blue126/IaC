variable "ubuntu_2604_bootstrap_password" {
  description = "Initial Ubuntu password supplied from Ansible Vault at runtime"
  type        = string
  sensitive   = true
  default     = null
}

provider "proxmox" {
  alias     = "cloud_image"
  endpoint  = var.pm_api_url
  api_token = "${var.pm_api_token_id}=${var.pm_api_token_secret}"
  insecure  = true

  ssh {
    agent    = false
    username = "root"
    password = var.proxmox_ssh_password
  }
}

module "ubuntu_2604" {
  source = "../modules/proxmox-cloud-image-vm"

  providers = {
    proxmox = proxmox.cloud_image
  }

  bootstrap_password = var.ubuntu_2604_bootstrap_password

  vm_name     = "ubuntu-2604"
  target_node = "pve0"
  vmid        = 108

  image_datastore = "local"
  image_file_name = "ubuntu-26.04-server-cloudimg-amd64.img"
  image_url       = "https://cloud-images.ubuntu.com/releases/26.04/release-20260823/ubuntu-26.04-server-cloudimg-amd64.img"
  image_checksum  = "8196be9d7958059cb56c6c75c80fdf6cee8a8885bc149ea791d7db1c7ef93035"

  cores        = 4
  memory       = 32768
  disk_size_gb = 100
  storage_pool = var.storage_pool
  ip_address   = "192.168.1.108/24"
  sshkeys      = var.sshkeys
}

output "ubuntu_2604_ip" {
  value = module.ubuntu_2604.default_ip
}

resource "ansible_host" "ubuntu_2604" {
  depends_on = [module.ubuntu_2604]

  name   = "ubuntu-2604"
  groups = ["pve_vms"]
  variables = {
    ansible_user = "ubuntu"
    ansible_host = "192.168.1.108"
  }
}
