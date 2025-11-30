terraform {
  required_providers {
    netbox = {
      source = "e-breuninger/netbox"  # 指定使用 e-breuninger 开发的 Netbox Provider
      version = "3.10.0"              # 锁定版本，防止未来更新导致不兼容
    }
  }
}
