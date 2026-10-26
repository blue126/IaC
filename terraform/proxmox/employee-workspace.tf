variable "employee_workspaces" {
  description = "Persistent employee roster; disable, never remove, an allocated entry"
  type = map(object({
    nic_slot       = number
    vmid           = number
    bridge         = string
    address        = string
    gateway        = string
    mac_address    = string
    gateway_mac    = string
    cores          = optional(number, 2)
    memory         = optional(number, 4096)
    disk_size      = optional(string, "50G")
    disabled       = optional(bool, false)
    start_ready    = optional(bool, true)
    template_id    = optional(number)
    baseline_id    = optional(string)
    bootstrap_file = optional(string)
  }))
  default = {}
  validation {
    condition = alltrue([for vm in values(var.employee_workspaces) :
      (vm.template_id == null && vm.baseline_id == null && vm.bootstrap_file == null) || try(
        vm.template_id >= 100 && floor(vm.template_id) == vm.template_id && vm.template_id != vm.vmid &&
        can(regex("^[a-z][a-z0-9-]+$", vm.baseline_id)) &&
      can(regex("^[a-z0-9-]+:snippets/[a-z0-9-]+[.]yaml$", vm.bootstrap_file)), false)
    ])
    error_message = "A baked workspace requires a distinct template ID, baseline ID, and lightweight bootstrap file together."
  }
  validation {
    condition = alltrue([for id, vm in var.employee_workspaces :
      can(regex("^[a-z][a-z0-9-]{0,19}$", id)) &&
      can(regex("^vmbr[0-9]+$", vm.bridge)) &&
      can(cidrnetmask(vm.address)) && can(cidrhost("${vm.gateway}/32", 0)) &&
      can(regex("^[1-9][0-9]*G$", vm.disk_size)) &&
      vm.nic_slot >= 1 && vm.nic_slot <= 10 && floor(vm.nic_slot) == vm.nic_slot &&
      vm.vmid >= 100 && vm.vmid <= 999999999 &&
      can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", vm.mac_address)) &&
      can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", vm.gateway_mac))
    ]) && length(distinct([for vm in values(var.employee_workspaces) : vm.bridge])) == length(var.employee_workspaces) && length(distinct([for vm in values(var.employee_workspaces) : vm.vmid])) == length(var.employee_workspaces)
    error_message = "Use valid unique VMIDs/bridges, IPv4 addresses, MACs, short employee IDs and a positive whole GiB disk size such as 50G."
  }
  validation {
    condition     = sort([for vm in values(var.employee_workspaces) : tostring(vm.nic_slot)]) == sort([for slot in range(1, length(var.employee_workspaces) + 1) : tostring(slot)])
    error_message = "Allocate unique contiguous permanent NIC slots starting at 1; append new employees at the next slot."
  }
  validation {
    condition = alltrue([for vm in values(var.employee_workspaces) : try(
      tonumber(split("/", vm.address)[1]) >= 24 && tonumber(split("/", vm.address)[1]) <= 30 &&
      cidrhost(vm.address, 0) == cidrhost("${vm.gateway}/${split("/", vm.address)[1]}", 0) &&
      !contains([cidrhost(vm.address, 0), cidrhost(vm.address, -1), split("/", vm.address)[0]], vm.gateway) &&
      !contains([cidrhost(vm.address, 0), cidrhost(vm.address, -1)], split("/", vm.address)[0]), false)
    ])
    error_message = "Employee address/gateway must be distinct usable hosts in the same /24 to /30 IPv4 subnet."
  }
  validation {
    condition = alltrue(flatten([for id, vm in var.employee_workspaces : [for other_id, other in var.employee_workspaces : id == other_id || try(
      cidrhost("${split("/", vm.address)[0]}/${min(tonumber(split("/", vm.address)[1]), tonumber(split("/", other.address)[1]))}", 0) !=
      cidrhost("${split("/", other.address)[0]}/${min(tonumber(split("/", vm.address)[1]), tonumber(split("/", other.address)[1]))}", 0), false)
    ]]))
    error_message = "Employee subnets must not overlap."
  }

}

locals {
  employee_allocations = { for id, vm in var.employee_workspaces : id => {
    nic_slot    = vm.nic_slot
    node        = var.employee_access.node
    bridge      = vm.bridge
    address     = vm.address
    gateway     = vm.gateway
    mac_address = lower(vm.mac_address)
    gateway_mac = lower(vm.gateway_mac)
    dns_server  = var.employee_access.dns_server
  } }
}

resource "terraform_data" "employee_slot" {
  for_each = var.employee_workspaces
  input    = local.employee_allocations[each.key]
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [input]
    postcondition {
      condition     = self.output == local.employee_allocations[each.key]
      error_message = "Allocated employee network settings are immutable; recreate or migrate only through an explicitly approved data-preserving procedure."
    }
  }
}

resource "proxmox_virtual_environment_network_linux_bridge" "employee" {
  provider   = proxmox.pve2
  depends_on = [terraform_data.employee_slot]
  for_each   = var.employee_workspaces
  node_name  = var.employee_access.node
  name       = each.value.bridge
  ports      = []
  autostart  = true
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.employee_access != null
      error_message = "employee_access is required for a nonempty roster."
    }
  }
}

resource "proxmox_virtual_environment_file" "employee_boundary_hook" {
  provider     = proxmox.pve2
  for_each     = var.employee_workspaces
  node_name    = var.employee_access.node
  datastore_id = var.employee_access.snippet_datastore
  content_type = "snippets"
  file_mode    = "0755"
  depends_on   = [terraform_data.employee_slot]
  source_raw {
    file_name = "employee-${each.key}-boundary.py"
    data = templatefile("${path.module}/employee-boundary-hook.py.tftpl", {
      vmid        = each.value.vmid
      gateway_tap = "tap${var.employee_access.vmid}i${each.value.nic_slot}"
      disabled    = each.value.disabled
    })
  }
}

# Dedicated persistent resource: its disks cannot be destroyed or replaced by a plan.
resource "proxmox_virtual_environment_vm" "employee_workspace" {
  provider  = proxmox.pve2
  for_each  = var.employee_workspaces
  name      = "employee-${each.key}"
  node_name = var.employee_access.node
  vm_id     = each.value.vmid
  clone {
    vm_id = coalesce(each.value.template_id, var.employee_access.template_id)
    full  = true
  }
  agent { enabled = true }
  vga { type = "serial0" }
  cpu {
    cores = each.value.cores
    type  = "host"
  }
  memory { dedicated = each.value.memory }
  scsi_hardware = "virtio-scsi-pci"
  disk {
    datastore_id = var.employee_access.storage_pool
    size         = try(tonumber(trimsuffix(each.value.disk_size, "G")), 0)
    interface    = "scsi0"
    discard      = "on"
    file_format  = "raw"
  }
  network_device {
    model        = "virtio"
    bridge       = proxmox_virtual_environment_network_linux_bridge.employee[each.key].name
    mac_address  = each.value.mac_address
    firewall     = false
    disconnected = each.value.disabled
  }
  initialization {
    datastore_id        = var.employee_access.storage_pool
    vendor_data_file_id = each.value.bootstrap_file != null ? each.value.bootstrap_file : proxmox_virtual_environment_file.employee_guest_bootstrap[0].id
    ip_config {
      ipv4 {
        address = each.value.address
        gateway = each.value.gateway
      }
    }
    dns { servers = [var.employee_access.dns_server] }
    user_account {
      username = "ubuntu"
      keys     = var.employee_access.admin_public_keys
    }
  }
  on_boot             = var.employee_access.boundary_ready && each.value.start_ready && !each.value.disabled
  started             = var.employee_access.boundary_ready && each.value.start_ready && !each.value.disabled
  hook_script_file_id = proxmox_virtual_environment_file.employee_boundary_hook[each.key].id
  tags                = ["employee-workspace", each.key]
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [clone, initialization[0].user_account[0].keys]
  }
  depends_on = [terraform_data.employee_slot, proxmox_virtual_environment_vm.employee_template]
}

resource "ansible_host" "employee_workspace" {
  for_each = var.employee_workspaces
  name     = "employee-${each.key}"
  groups   = ["employee_workspaces"]
  variables = {
    ansible_host                              = split("/", each.value.address)[0]
    ansible_user                              = "ubuntu"
    employee_workspace_id                     = each.key
    employee_workspace_disabled               = tostring(each.value.disabled)
    employee_workspace_vmid                   = tostring(each.value.vmid)
    employee_workspace_pve_host               = var.employee_access.pve_inventory_host
    employee_workspace_admin_public_keys_json = jsonencode(var.employee_access.admin_public_keys)
    employee_workspace_gateway                = "employee-access"
    employee_workspace_baseline_id            = each.value.baseline_id != null ? each.value.baseline_id : ""
  }
}
