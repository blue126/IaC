variable "netbox_url" {
  type        = string
  description = "The URL of the Netbox instance"
  default     = "http://192.168.1.104:8000" # Netbox 的地址
}

variable "netbox_token" {
  type        = string
  description = "The API token for Netbox"
  sensitive   = true                      # 标记为敏感数据，Terraform 在输出日志时会隐藏它
  default     = "0123456789abcdef0123456789abcdef01234567" # API Token (实际生产中通常通过环境变量 TF_VAR_netbox_token 传入，不写在代码里)
}
