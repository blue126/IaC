variable "pm_api_url" {
  description = "Proxmox API URL"
  type        = string
}

variable "pm_user" {
  description = "Proxmox User"
  type        = string
}

variable "pm_password" {
  description = "Proxmox Password"
  type        = string
  sensitive   = true
}

variable "target_node" {
  description = "Target Proxmox Node"
  type        = string
  default     = "pve0"
}

variable "storage_pool" {
  description = "Proxmox Storage Pool"
  type        = string
  default     = "vmdata"
}

variable "vm_name" {
  description = "Name of the VM to deploy"
  type        = string
  default     = "dev-vm-01"
}

variable "sshkeys" {
  description = "SSH Public Keys"
  type        = string
}
