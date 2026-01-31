terraform {
  required_version = ">= 1.0.0"

  cloud {
    organization = "homelab-roseville"
    workspaces {
      name = "iac-esxi-lab"
    }
  }

  required_providers {
    vsphere = {
      source  = "vmware/vsphere"
      version = "~> 2.6"
    }
    ansible = {
      source  = "ansible/ansible"
      version = "~> 1.3.0"
    }
  }
}
