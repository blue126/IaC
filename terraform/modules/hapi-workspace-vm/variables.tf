variable "workspace_id" {
  type        = string
  description = "Stable ID from the independent HAPI allocation"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,31}$", var.workspace_id))
    error_message = "Use the validated HAPI workspace ID."
  }
}

variable "node" {
  type        = string
  description = "Reviewed PVE node"
}

variable "network" {
  description = "Exact network allocation from the validated manifest, never auto-assigned"
  type = object({
    vmid    = number
    vnet    = string
    mac     = string
    address = string
    gateway = string
  })
  validation {
    condition = (
      var.network.vmid >= 503 && floor(var.network.vmid) == var.network.vmid &&
      can(regex("^(ha[a-z0-9]{1,6}|vmbr[0-9]{1,4})$", var.network.vnet)) &&
      can(regex("^([0-9a-f]{2}:){5}[0-9a-f]{2}$", var.network.mac)) &&
      can(cidrhost(var.network.address, 1))
    )
    error_message = "Use an independently reviewed HAPI VMID, VNet, fixed MAC and CIDR."
  }
}

variable "template_name" {
  type        = string
  description = "Approved clean HAPI baseline template"
}

variable "bios" {
  type        = string
  description = "Firmware matching the approved clean baseline"
  default     = "ovmf"
  validation {
    condition     = contains(["ovmf", "seabios"], var.bios)
    error_message = "Match the approved baseline firmware."
  }
}

variable "hook_script_file_id" {
  type        = string
  description = "Reviewed PVE snippets storage binding for the installed start gate"
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+:snippets/hapi-network-hook.py$", var.hook_script_file_id))
    error_message = "Supply the actual approved hook storage binding."
  }
}

variable "storage_pool" {
  type        = string
  description = "Approved disk datastore"
}

variable "nameserver" {
  type        = string
  description = "Resolver present in the approved network policy"
}

variable "admin_public_keys" {
  type        = list(string)
  description = "Approved administrator SSH public keys; never private keys"
  validation {
    condition     = length(var.admin_public_keys) > 0
    error_message = "At least one approved administrator public key is required."
  }
}

variable "cores" {
  type    = number
  default = 2
}

variable "memory" {
  type    = number
  default = 2048
}

variable "disk_size" {
  type    = string
  default = "50G"
}
