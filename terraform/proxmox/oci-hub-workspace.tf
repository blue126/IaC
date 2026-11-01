# SDN objects are owned exclusively by the oci-hub-pve Ansible role.
variable "oci_hub_workspaces" {
  description = "Independent, explicitly allocated OCI Hub workspace roster"
  type = map(object({
    vmid                = number
    vnet                = string
    address             = string
    gateway             = string
    mac_address         = string
    template_name       = string
    baseline_id         = string
    bootstrap_file      = string
    hook_script_file_id = string
    defer_hook_binding  = optional(bool, false)
    storage_pool        = string
    admin_public_keys   = list(string)
    dns_server          = string
    overlay             = string
    cores               = optional(number, 2)
    memory              = optional(number, 8192)
    balloon_memory      = optional(number)
    onboot              = optional(bool, false)
    disk_size           = optional(string, "50G")
    bios                = optional(string, "ovmf")
    machine             = optional(string)
    bootstrap_mode      = optional(string, "user")
  }))
  default = {}
  validation {
    condition = alltrue([for id, vm in var.oci_hub_workspaces :
      can(regex("^[a-z][a-z0-9-]{0,19}$", id)) && vm.vmid >= 100 && vm.vmid != 500 &&
      can(regex("^oh[a-z0-9]{1,6}$", vm.vnet)) && can(cidrnetmask(vm.address)) &&
      can(cidrnetmask(vm.overlay)) && endswith(vm.overlay, "/32") &&
      length(vm.template_name) > 0 && length(vm.baseline_id) > 0 &&
      can(regex("^[a-z0-9-]+:snippets/oci-hub-[a-z0-9.-]+$", vm.hook_script_file_id)) &&
      can(regex("^[a-z0-9-]+:snippets/[a-z0-9.-]+$", vm.bootstrap_file)) &&
      can(regex("^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", vm.mac_address)) &&
      try(cidrhost(vm.address, 0) == cidrhost("${vm.gateway}/${split("/", vm.address)[1]}", 0) && split("/", vm.address)[0] != vm.gateway, false)
    ]) && length(distinct([for vm in values(var.oci_hub_workspaces) : vm.vmid])) == length(var.oci_hub_workspaces) && length(distinct([for vm in values(var.oci_hub_workspaces) : vm.vnet])) == length(var.oci_hub_workspaces)
    error_message = "Supply unique new VMIDs/VNets, explicit approved baseline/template, hook, IPv4 addresses and MACs."
  }
  validation {
    condition = alltrue(flatten([for id, vm in var.oci_hub_workspaces : [for old_id, existing in var.employee_workspaces : try(
      ((vm.vmid != existing.vmid && lower(vm.mac_address) != lower(existing.mac_address)) ||
      (id == old_id && existing.oci_hub_managed && vm.vmid == existing.vmid && lower(vm.mac_address) == lower(existing.mac_address))) &&
      cidrhost("${split("/", vm.address)[0]}/${min(tonumber(split("/", vm.address)[1]), tonumber(split("/", existing.address)[1]))}", 0) !=
      cidrhost("${split("/", existing.address)[0]}/${min(tonumber(split("/", vm.address)[1]), tonumber(split("/", existing.address)[1]))}", 0), false)
    ]]))
    error_message = "OCI Hub VMIDs, MAC addresses and physical subnets must be independent of existing workspaces."
  }
  validation {
    condition = alltrue([for vm in values(var.oci_hub_workspaces) : try(
      floor(vm.vmid) == vm.vmid && tonumber(split("/", vm.address)[1]) == 30 &&
      !contains([cidrhost(vm.address, 0), cidrhost(vm.address, -1)], split("/", vm.address)[0]) &&
      !contains([cidrhost(vm.address, 0), cidrhost(vm.address, -1)], vm.gateway), false)
    ]) && length(distinct([for vm in values(var.oci_hub_workspaces) : vm.overlay])) == length(var.oci_hub_workspaces)
    error_message = "Use distinct usable /30 hosts and unique VM overlay /32s."
  }

}

module "oci_hub_workspace" {
  source              = "../modules/proxmox-vm"
  providers           = { proxmox = proxmox.pve2 }
  for_each            = var.oci_hub_workspaces
  vm_name             = "oci-hub-${each.key}"
  target_node         = "pve2"
  vmid                = each.value.vmid
  template_name       = each.value.template_name
  cicustom            = each.value.bootstrap_mode == "vendor" ? null : each.value.bootstrap_file
  vendor_data_file_id = each.value.bootstrap_mode == "vendor" ? each.value.bootstrap_file : null
  network_bridge      = each.value.vnet
  network_mac_address = each.value.mac_address
  ip_address          = each.value.address
  gateway             = each.value.gateway
  nameserver          = each.value.dns_server
  storage_pool        = each.value.storage_pool
  sshkeys             = each.value.admin_public_keys
  cores               = each.value.cores
  memory              = each.value.memory
  balloon_memory      = each.value.balloon_memory
  bios                = each.value.bios
  machine             = each.value.machine
  disk_size           = each.value.disk_size
  hook_script_file_id = each.value.defer_hook_binding ? null : each.value.hook_script_file_id
  initial_started     = false
  onboot              = each.value.onboot
  protection          = true
  tags                = ["oci-hub", each.key]
}

resource "ansible_host" "oci_hub_workspace" {
  for_each = var.oci_hub_workspaces
  name     = "oci-hub-${each.key}"
  groups   = ["oci_hub_workspaces"]
  variables = {
    ansible_host                              = split("/", each.value.address)[0]
    ansible_user                              = "ubuntu"
    employee_workspace_profile                = "oci-hub"
    employee_workspace_id                     = each.key
    employee_workspace_baseline_id            = each.value.baseline_id
    employee_workspace_admin_public_keys_json = jsonencode(each.value.admin_public_keys)
    oci_hub_spoke_address                     = each.value.overlay
  }
}
