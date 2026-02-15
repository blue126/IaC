variable "vm_name" {
  type = string
}

variable "resource_pool_id" {
  type = string
}

variable "datastore_id" {
  type = string
}

variable "network_id" {
  type = string
}

variable "num_cpus" {
  type    = number
  default = 2
}

variable "memory" {
  type    = number
  default = 4096
}

variable "memory_reservation" {
  type    = number
  default = 0
}

variable "system_disk_size" {
  type    = number
  default = 40
}

variable "firmware" {
  type    = string
  default = "efi"
}

variable "guest_id" {
  type    = string
  default = "debian11_64Guest"
}

variable "network_adapter_type" {
  type    = string
  default = "vmxnet3"
}

variable "host_system_id" {
  type        = string
  description = "The ID of the host system. Required for PCI passthrough."
  default     = ""
}

variable "pci_device_ids" {
  type    = list(string)
  default = []
}

variable "power_on" {
  description = "Whether to power on the VM after creation"
  type        = bool
  default     = false
}

variable "extra_config" {
  description = "Extra VMX configuration parameters"
  type        = map(string)
  default     = {}
}

variable "template_uuid" {
  description = "UUID of the VM template to clone from. Empty string creates a blank VM."
  type        = string
  default     = ""
}

variable "customize" {
  description = "Guest customization spec for template clones. Set to null to skip customization."
  type = object({
    hostname        = string
    domain          = optional(string, "local")
    ipv4_address    = optional(string)
    ipv4_netmask    = optional(number, 24)
    ipv4_gateway    = optional(string)
    dns_server_list = optional(list(string), [])
  })
  default = null
}
