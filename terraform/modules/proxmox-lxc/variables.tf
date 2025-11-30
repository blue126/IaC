variable "lxc_name" {
  description = "The name/hostname of the LXC container"
  type        = string
}

variable "target_node" {
  description = "The Proxmox node to deploy to"
  type        = string
}

variable "vmid" {
  description = "Proxmox LXC ID"
  type        = number
  default     = 0
}

variable "ostemplate" {
  description = "OS template for new containers (e.g., local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst)"
  type        = string
  default     = null
}

variable "cores" {
  description = "Number of CPU cores"
  type        = number
  default     = 1
}

variable "memory" {
  description = "Amount of memory in MB"
  type        = number
  default     = 512
}

variable "swap" {
  description = "Amount of swap in MB"
  type        = number
  default     = 512
}

variable "rootfs_storage" {
  description = "Storage pool for rootfs"
  type        = string
  default     = "local-zfs"
}

variable "rootfs_size" {
  description = "Size of the rootfs"
  type        = string
  default     = "8G"
}

variable "network_bridge" {
  description = "Network bridge to attach to"
  type        = string
  default     = "vmbr1"
}

variable "ip_address" {
  description = "Static IP Address (format: x.x.x.x/24) or 'dhcp'"
  type        = string
  default     = "dhcp"
}

variable "gateway" {
  description = "Network gateway (format: x.x.x.x)"
  type        = string
  default     = "192.168.1.1"
}

variable "sshkeys" {
  description = "SSH Public Keys"
  type        = string
  default     = null
}

variable "unprivileged" {
  description = "Whether to run as unprivileged container"
  type        = bool
  default     = true
}

variable "onboot" {
  description = "Start container on boot"
  type        = bool
  default     = true
}

variable "start" {
  description = "Start container after creation"
  type        = bool
  default     = true
}

variable "features" {
  description = "List of features (e.g., ['nesting=1', 'fuse=1'])"
  type        = list(string)
  default     = []
}

variable "ostype" {
  description = "OS type (debian, ubuntu, centos, etc.)"
  type        = string
  default     = "debian"
}

variable "password" {
  description = "Root password (only for new containers)"
  type        = string
  default     = null
  sensitive   = true
}
