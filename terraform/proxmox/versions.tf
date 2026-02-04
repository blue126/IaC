terraform {
  cloud {
    organization = "homelab-roseville"

    workspaces {
      name = "iac-proxmox-lab"
    }
  }
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.70.0"
    }
    ansible = {
      source  = "ansible/ansible"
      version = "~> 1.3.0"
    }
  }
}
