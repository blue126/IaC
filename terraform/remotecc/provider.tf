# remotecc-ops runs on the primary cluster; employee workspaces and VM500 run on pve2.
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
  alias     = "pve2"
  endpoint  = var.pm_api_url_pve2
  api_token = "${var.pm_api_token_id_pve2}=${var.pm_api_token_secret_pve2}"
  insecure  = true

  ssh {
    agent    = true
    username = "root"
  }
}
