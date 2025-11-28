variable "vm_name" {
  description = "The name of the VM"
  type        = string
}

variable "target_node" {
  description = "The Proxmox node to deploy to"
  type        = string
}

variable "template_name" {
  description = "The template to clone from"
  type        = string
  default     = "ubuntu-24.04-template"
}

variable "full_clone" {
  description = "Whether to perform a full clone"
  type        = bool
  default     = true
}

variable "cores" {
  description = "Number of CPU cores"
  type        = number
  default     = 2
}

variable "memory" {
  description = "Amount of memory in MB"
  type        = number
  default     = 2048
}

variable "storage_pool" {
  description = "Storage pool for disks"
  type        = string
  default     = "local-zfs"
}

variable "disk_size" {
  description = "Size of the root disk"
  type        = string
  default     = "50G"
}

variable "network_bridge" {
  description = "Network bridge to attach to"
  type        = string
  default     = "vmbr1"
}

variable "ciuser" {
  description = "Cloud-Init User"
  type        = string
  default     = "ubuntu"
}

variable "sshkeys" {
  description = "SSH Public Keys"
  type        = string
  default     = null
}

variable "agent" {
  description = "Enable QEMU Guest Agent"
  type        = number
  default     = 1
}

variable "vmid" {
  description = "Proxmox VM ID"
  type        = number
  default     = 0
}

variable "ip_address" {
  description = "Static IP Address (format: ip=x.x.x.x/24,gw=x.x.x.x)"
  type        = string
  default     = null
}
