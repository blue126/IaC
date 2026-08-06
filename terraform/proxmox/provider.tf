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
