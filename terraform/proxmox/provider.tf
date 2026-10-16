provider "proxmox" {
  endpoint = var.pm_api_url
  # Format: USER@REALM!TOKENID=UUID
  api_token = "${var.pm_api_token_id}=${var.pm_api_token_secret}"
  insecure  = true

  ssh {
    agent = true
  }
}

provider "proxmox" {
  alias    = "root"
  endpoint = var.pm_api_url
  username = "root@pam"
  password = var.proxmox_ssh_password
  insecure = true

  ssh {
    agent = true
  }
}

# Separate provider for an endpoint outside the primary cluster.
provider "proxmox" {
  alias     = "pve2"
  endpoint  = var.pm_api_url_pve2
  api_token = "${var.pm_api_token_id_pve2}=${var.pm_api_token_secret_pve2}"
  insecure  = true

  ssh {
    agent = true
  }
}

# Some disk-import operations require explicit SSH credentials when an agent
# identity is unavailable.
provider "proxmox" {
  alias     = "pve2_root"
  endpoint  = var.pm_api_url_pve2
  api_token = "${var.pm_api_token_id_pve2}=${var.pm_api_token_secret_pve2}"
  insecure  = true

  ssh {
    agent    = false
    username = "root"
    password = var.proxmox_ssh_password
  }
}
