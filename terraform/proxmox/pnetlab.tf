variable "pnetlab_ip_allocation_confirmed" {
  description = "Whether router and NetBox checks confirmed the PNetLab IP allocation"
  type        = bool
  default     = false
}

resource "terraform_data" "pnetlab_allocation" {
  lifecycle {
    precondition {
      condition     = var.pnetlab_ip_allocation_confirmed
      error_message = "Confirm the PNetLab IP allocation against both the router and NetBox before creating VM 250."
    }
  }
}

module "pnetlab" {
  source = "../modules/proxmox-cloud-image-vm"

  depends_on = [terraform_data.pnetlab_allocation]

  providers = {
    proxmox = proxmox.pve2_root
  }

  vm_name     = "pnetlab"
  target_node = "pve2"
  vmid        = 250

  image_datastore = "local"
  image_file_name = "ubuntu-26.04-server-cloudimg-amd64.img"
  image_url       = "https://cloud-images.ubuntu.com/releases/26.04/release-20260823/ubuntu-26.04-server-cloudimg-amd64.img"
  image_checksum  = "8196be9d7958059cb56c6c75c80fdf6cee8a8885bc149ea791d7db1c7ef93035"

  cores                 = 16
  memory                = 65536
  balloon_memory        = 0
  disk_size_gb          = 400
  storage_pool          = "mainpool"
  efidisk_storage       = "local-lvm"
  efi_pre_enrolled_keys = false
  network_bridge        = "vmbr0"
  network_mac_address   = "02:50:00:00:00:FA"
  ip_address            = "192.168.1.250/24"
  on_boot               = false
  protection            = true
  sshkeys               = var.sshkeys
  tags                  = ["iac", "network-lab", "pnetlab"]
}

output "pnetlab_ip" {
  value = module.pnetlab.default_ip
}

resource "ansible_host" "pnetlab" {
  depends_on = [module.pnetlab]

  name   = "pnetlab"
  groups = ["pnetlab"]
  variables = {
    ansible_host = "192.168.1.250"
    ansible_user = "ubuntu"
  }
}
