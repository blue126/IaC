variable "pm_api_url" {
  description = "Proxmox API URL"
  type        = string
}

variable "pm_api_token_id" {
  description = "Proxmox API Token ID"
  type        = string
  sensitive   = true
  default     = null
}

variable "pm_api_token_secret" {
  description = "Proxmox API Token Secret"
  type        = string
  sensitive   = true
  default     = null
}

variable "pm_api_url_pve2" {
  description = "Proxmox API URL for the standalone pve2 node"
  type        = string
}

variable "pm_api_token_id_pve2" {
  description = "Proxmox API Token ID for the standalone pve2 node"
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.pm_api_token_id_pve2)) > 0
    error_message = "Provide the standalone pve2 token ID through the approved Vault bridge before planning."
  }
}

variable "pm_api_token_secret_pve2" {
  description = "Proxmox API Token Secret for the standalone pve2 node"
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.pm_api_token_secret_pve2)) > 0
    error_message = "Provide the standalone pve2 token secret through the approved Vault bridge before planning."
  }
}

variable "storage_pool" {
  description = "Proxmox Storage Pool"
  type        = string
  default     = "vmdata"
}

variable "sshkeys" {
  description = "SSH Public Keys"
  type        = list(string)
}
