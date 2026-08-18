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

# ==========================================
# LLM Server VM Configuration
# ==========================================

variable "llm_server_vm_name" {
  description = "LLM Server VM name"
  type        = string
  default     = "llm-server"
}

variable "llm_server_ip_address" {
  description = "LLM Server static IP address"
  type        = string
}

variable "llm_server_datastore" {
  description = "Datastore containing the LLM Server VM"
  type        = string
  default     = "Intel800GSSD"
}

variable "llm_server_num_cpus" {
  description = "Number of vCPUs for LLM Server"
  type        = number
  default     = 36
}

variable "llm_server_memory_mb" {
  description = "Memory in MB for LLM Server (also used as memory reservation for GPU passthrough)"
  type        = number
  default     = 348160 # 340 GB
}

variable "llm_server_system_disk_gb" {
  description = "System disk size in GB for LLM Server, including isolated DeepSeek model-candidate capacity"
  type        = number
  default     = 900
}

variable "llm_server_mmio_size_gb" {
  description = "64-bit MMIO size in GB for GPU passthrough. Dual 3090: start with 64, increase to 128 if VM fails to boot"
  type        = number
  default     = 128
}
