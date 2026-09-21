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

# Standalone node -- not reachable through the cluster endpoint above.
provider "proxmox" {
  alias     = "pve2"
  endpoint  = var.pm_api_url_pve2
  api_token = "${var.pm_api_token_id_pve2}=${var.pm_api_token_secret_pve2}"
  insecure  = true

  ssh {
    agent = true
  }
}

# Cloud-image disk import requires an explicit SSH password fallback because
# the standalone pve2 provider cannot consume the Sandbox SSH agent identity.
provider "proxmox" {
  alias    = "pve2_root"
  endpoint = var.pm_api_url_pve2
  username = "root@pam"
  password = var.proxmox_ssh_password
  insecure = true

  ssh {
    agent    = false
    username = "root"
    password = var.proxmox_ssh_password
  }
}
