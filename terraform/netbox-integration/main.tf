provider "netbox" {
  server_url = var.netbox_url
  api_token  = var.netbox_token
}

resource "netbox_site" "homelab" {
  name   = "HomeLab"      # 创建一个名为 "HomeLab" 的站点
  slug   = "homelab"      # URL 友好的标识符
  status = "active"
}

resource "netbox_tag" "terraform" {
  name        = "Managed by Terraform" # 创建一个标签
  slug        = "terraform"
  description = "Resources managed by Terraform"
}
