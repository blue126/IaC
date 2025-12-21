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
