variable "employee_access" {
  description = "Retained VM500 control-plane host with an explicitly retired legacy gateway"
  type = object({
    node                   = string
    pve_inventory_host     = string
    vmid                   = number
    template_id            = number
    storage_pool           = string
    uplink_bridge          = string
    uplink_address         = string
    uplink_gateway         = string
    uplink_mac             = string
    dns_server             = string
    admin_public_keys      = list(string)
    boundary_ready         = optional(bool, false)
    legacy_gateway_retired = optional(bool, false)
    snippet_datastore      = optional(string, "local")
  })
  default = null
}

resource "proxmox_virtual_environment_vm" "employee_access" {
  provider   = proxmox.pve2
  count      = var.employee_access == null ? 0 : 1
  depends_on = [terraform_data.employee_slot, proxmox_virtual_environment_vm.employee_template]
  name       = "employee-access"
  node_name  = var.employee_access.node
  vm_id      = var.employee_access.vmid
  on_boot    = true
  clone {
    vm_id = var.employee_access.template_id
    full  = true
  }
  agent { enabled = true }
  vga { type = "serial0" }
  cpu {
    cores = 2
    type  = "host"
  }
  memory { dedicated = 2048 }
  disk {
    datastore_id = var.employee_access.storage_pool
    interface    = "scsi0"
    size         = 20
    discard      = "on"
  }
  network_device {
    bridge      = var.employee_access.uplink_bridge
    mac_address = var.employee_access.uplink_mac
    firewall    = false
  }
  dynamic "network_device" {
    for_each = var.employee_access.legacy_gateway_retired ? [] : [for slot in range(1, length(var.employee_workspaces) + 1) : one([for id, vm in var.employee_workspaces : merge(vm, { employee_id = id }) if vm.nic_slot == slot])]
    content {
      bridge      = proxmox_virtual_environment_network_linux_bridge.employee[network_device.value.employee_id].name
      mac_address = network_device.value.gateway_mac
      firewall    = false
    }
  }
  initialization {
    datastore_id        = var.employee_access.storage_pool
    vendor_data_file_id = proxmox_virtual_environment_file.employee_guest_bootstrap[0].id
    ip_config {
      ipv4 {
        address = var.employee_access.uplink_address
        gateway = var.employee_access.uplink_gateway
      }
    }
    dns { servers = [var.employee_access.dns_server] }
    user_account {
      username = "ubuntu"
      keys     = var.employee_access.admin_public_keys
    }
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition = !var.employee_access.legacy_gateway_retired || alltrue([
        for vm in values(var.employee_workspaces) : vm.disabled && (vm.retired || vm.oci_hub_managed)
      ])
      error_message = "Remove legacy gateway NICs only after every old workspace is migrated or retired."
    }
    ignore_changes = [clone, initialization[0].user_account[0].keys]
    precondition {
      condition = try(
        cidrhost(var.employee_access.uplink_address, 0) == cidrhost("${var.employee_access.uplink_gateway}/${split("/", var.employee_access.uplink_address)[1]}", 0) &&
      !contains([cidrhost(var.employee_access.uplink_address, 0), cidrhost(var.employee_access.uplink_address, -1), split("/", var.employee_access.uplink_address)[0]], var.employee_access.uplink_gateway), false)
      error_message = "The uplink gateway must be a distinct usable host in the uplink subnet."
    }
    precondition {
      condition = alltrue([for vm in values(var.employee_workspaces) : try(
        cidrhost("${split("/", vm.address)[0]}/${min(tonumber(split("/", vm.address)[1]), tonumber(split("/", var.employee_access.uplink_address)[1]))}", 0) !=
        cidrhost("${split("/", var.employee_access.uplink_address)[0]}/${min(tonumber(split("/", vm.address)[1]), tonumber(split("/", var.employee_access.uplink_address)[1]))}", 0), false)
      ])
      error_message = "Employee subnets must not overlap the gateway uplink subnet."
    }
    precondition {
      condition     = length(distinct([for mac in concat([var.employee_access.uplink_mac], flatten([for vm in values(var.employee_workspaces) : [vm.mac_address, vm.gateway_mac]])) : lower(mac)])) == 1 + 2 * length(var.employee_workspaces)
      error_message = "All gateway uplink, employee and internal gateway MAC addresses must be unique."
    }
    precondition {
      condition     = !contains([for vm in values(var.employee_workspaces) : vm.vmid], var.employee_access.vmid) && !contains([for vm in values(var.employee_workspaces) : vm.bridge], var.employee_access.uplink_bridge)
      error_message = "Gateway VMID/uplink bridge must differ from all employee VMIDs/bridges."
    }
  }
}

resource "ansible_host" "employee_access" {
  count  = var.employee_access == null ? 0 : 1
  name   = "employee-access"
  groups = ["employee_access"]
  variables = {
    ansible_host                           = split("/", var.employee_access.uplink_address)[0]
    ansible_user                           = "ubuntu"
    employee_access_pve_host               = var.employee_access.pve_inventory_host
    employee_access_vmid                   = tostring(var.employee_access.vmid)
    employee_access_legacy_gateway_retired = tostring(var.employee_access.legacy_gateway_retired)
    employee_access_uplink_mac             = var.employee_access.uplink_mac
    employee_access_uplink_address         = var.employee_access.uplink_address
    employee_access_uplink_gateway         = var.employee_access.uplink_gateway
    employee_access_admin_public_keys_json = jsonencode(var.employee_access.admin_public_keys)
    employee_access_dns_server             = var.employee_access.dns_server
    employee_access_networks_json = jsonencode({ for id, vm in var.employee_workspaces : id => merge(vm, {
      interface       = "emp${vm.nic_slot - 1}"
      gateway_nic     = vm.nic_slot
      ip              = split("/", vm.address)[0]
      gateway_address = "${vm.gateway}/${split("/", vm.address)[1]}"
    }) })
  }
}
