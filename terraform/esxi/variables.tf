variable "vsphere_server" {
  description = "vSphere Server IP or Hostname"
  type        = string
}

variable "vsphere_host" {
  description = "ESXi Host IP or Name (as shown in vCenter)"
  type        = string
}

variable "vsphere_user" {
  description = "vSphere username"
  type        = string
  default     = "root"
}

variable "vsphere_password" {
  description = "vSphere password"
  type        = string
  sensitive   = true
}

variable "vsphere_datacenter" {
  description = "vSphere Datacenter Name"
  type        = string
  default     = "ha-datacenter"
}

variable "vm_datastore" {
  description = "Datastore used for the VM"
  type        = string
}

variable "vm_network" {
  description = "Network used for the VM"
  type        = string
  default     = "VM Network"
}

variable "vm_template" {
  description = "Template name to clone"
  type        = string
  default     = "ubuntu2404"
}

# ==========================================
# PBS VM Configuration
# ==========================================

variable "pbs_vm_name" {
  type    = string
  default = "proxmox-backup-server"
}

variable "pbs_ip_address" {
  type = string
}

variable "pbs_num_cpus" {
  type    = number
  default = 8
}

variable "pbs_memory_mb" {
  type    = number
  default = 16384
}

variable "pbs_system_disk_gb" {
  type    = number
  default = 80
}

variable "pbs_hba_pci_id" {
  type        = string
  description = "LSI 3008 HBA PCI ID - informational only, passthrough managed via ESXi"
  default     = ""
}

variable "pbs_nvme_pci_ids" {
  type        = list(string)
  description = "NVMe PCI IDs - currently unused (bifurcation not available)"
  default     = []
}

# ==========================================
# Windows Server VM Configuration
# ==========================================

variable "windows_vm_name" {
  description = "Windows Server VM name"
  type        = string
  default     = "windows-server"
}

variable "windows_ip_address" {
  description = "Windows Server static IP address"
  type        = string
}

variable "windows_num_cpus" {
  description = "Number of vCPUs for Windows Server"
  type        = number
  default     = 4
}

variable "windows_memory_mb" {
  description = "Memory in MB for Windows Server"
  type        = number
  default     = 16384
}

variable "windows_system_disk_gb" {
  description = "System disk size in GB for Windows Server"
  type        = number
  default     = 60
}
