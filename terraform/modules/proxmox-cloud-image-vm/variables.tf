variable "vm_name" {
  description = "Name of the VM"
  type        = string
}

variable "target_node" {
  description = "Proxmox node hosting the VM and downloaded image"
  type        = string
}

variable "vmid" {
  description = "Proxmox VM ID"
  type        = number
}

variable "image_datastore" {
  description = "Datastore used to cache the downloaded cloud image"
  type        = string
  default     = "local"
}

variable "image_file_name" {
  description = "Filename for the downloaded cloud image"
  type        = string
}

variable "image_url" {
  description = "Pinned URL of the cloud image"
  type        = string
}

variable "image_checksum" {
  description = "SHA-256 checksum of the cloud image"
  type        = string
}

variable "cores" {
  description = "Number of CPU cores"
  type        = number
  default     = 2
}

variable "cpu_type" {
  description = "CPU type"
  type        = string
  default     = "host"
}

variable "memory" {
  description = "Memory in MB"
  type        = number
  default     = 4096
}

variable "balloon_memory" {
  description = "Balloon memory in MB, or null to match dedicated memory"
  type        = number
  default     = null
  nullable    = true
}

variable "storage_pool" {
  description = "Datastore used for the VM disks"
  type        = string
  default     = "vmdata"
}

variable "disk_size_gb" {
  description = "Root disk size in GB"
  type        = number
  default     = 20
}

variable "network_bridge" {
  description = "Network bridge to attach to"
  type        = string
  default     = "vmbr1"
}

variable "ciuser" {
  description = "Cloud-Init user"
  type        = string
  default     = "ubuntu"
}

variable "bootstrap_password" {
  description = "Initial Cloud-Init password; Ansible disables SSH password login after key verification"
  type        = string
  sensitive   = true
  default     = null
}

variable "sshkeys" {
  description = "SSH public keys passed to Cloud-Init"
  type        = list(string)
}

variable "ip_address" {
  description = "Static IP address with CIDR, or null for DHCP"
  type        = string
  default     = null
  nullable    = true
}

variable "gateway" {
  description = "IPv4 gateway for a static address"
  type        = string
  default     = "192.168.1.1"
}

variable "nameserver" {
  description = "DNS nameserver"
  type        = string
  default     = "192.168.1.1"
}

variable "bios" {
  description = "Firmware type"
  type        = string
  default     = "ovmf"
}

variable "machine" {
  description = "QEMU machine type"
  type        = string
  default     = "q35"
}

variable "efidisk_storage" {
  description = "Datastore for EFI disk, or null to use storage_pool"
  type        = string
  default     = null
  nullable    = true
}

variable "on_boot" {
  description = "Whether to start the VM on host boot"
  type        = bool
  default     = true
}

variable "vga_type" {
  description = "VGA type"
  type        = string
  default     = "serial0"
}

variable "tags" {
  description = "Proxmox VM tags"
  type        = list(string)
  default     = []
}
