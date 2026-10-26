terraform {
  cloud {
    organization = "homelab-roseville"

    workspaces {
      name = "iac-oci"
    }
  }

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "8.3.0"
    }
  }
}
