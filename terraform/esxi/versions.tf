terraform {
  required_version = ">= 1.0.0"

  # Historical configuration only. The retired HCP workspace was deleted;
  # do not reintroduce a cloud block that could recreate it during init.

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
