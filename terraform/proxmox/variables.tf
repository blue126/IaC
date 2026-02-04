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
  type        = list(string)
}

variable "vmid" {
  description = "Proxmox VM ID (set to 0 to auto-assign)"
  type        = number
  default     = 0
}

variable "cores" {
  description = "Number of CPU cores"
  type        = number
  default     = 2
}

variable "memory" {
  description = "Memory in MB"
  type        = number
  default     = 4096
}

variable "disk_size" {
  description = "Disk size (e.g., 20G)"
  type        = string
  default     = "20G"
}

variable "ip_config" {
  description = "IP configuration string (e.g., ip=1.2.3.4/24,gw=1.2.3.1)"
  type        = string
  default     = "ip=dhcp"
}

variable "proxmox_ssh_password" {
  description = "SSH password for Proxmox cluster nodes (from Ansible Vault)"
  type        = string
  sensitive   = true
}

variable "netbox_provisioned_vms" {
  description = "List of VMs to provision, fetched from Netbox"
  type = list(object({
    name           = string
    target_node    = string
    template       = string
    cores          = number
    memory         = number
    disk_size      = string
    ip_address     = string
    vmid           = number
    cloudinit_slot = string
  }))
  default = []
}
