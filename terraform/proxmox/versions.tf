terraform {
  cloud {
    organization = "homelab-roseville"

    workspaces {
      name = "iac-proxmox-lab"
    }
  }
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "3.0.2-rc04"
    }
    ansible = {
      source  = "ansible/ansible"
      version = "~> 1.3.0"
    }
  }
}
