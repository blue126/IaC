mock_provider "proxmox" {}
mock_provider "proxmox" {
  alias = "pve2"
  mock_resource "proxmox_virtual_environment_file" {
    defaults = {
      id = "local:snippets/employee-fixture.yaml"
    }
  }
}
mock_provider "ansible" {}
variables {
  employee_access = {
    node               = "pve-test"
    pve_inventory_host = "pve-test"
    vmid               = 500
    template_id        = 9000
    storage_pool       = "local-zfs"
    uplink_bridge      = "vmbr1"
    uplink_address     = "192.168.50.2/24"
    uplink_gateway     = "192.168.50.1"
    uplink_mac         = "02:00:00:00:00:01"
    dns_server         = "1.1.1.1"
    admin_public_keys  = []
  }
  employee_workspaces = {
    alice = {
      nic_slot    = 1
      vmid        = 501
      bridge      = "vmbr501"
      address     = "10.231.1.2/30"
      gateway     = "10.231.1.1"
      mac_address = "02:00:00:00:01:02"
      gateway_mac = "02:00:00:00:01:01"
    }
  }
}
run "retired_workspace_keeps_network_allocation_without_vm" {
  command = apply
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { retired = true, disabled = true, start_ready = false, hook_bound = false })
    }
  }
  assert {
    condition     = !contains(keys(proxmox_virtual_environment_vm.employee_workspace), "alice") && !contains(keys(ansible_host.employee_workspace), "alice") && !contains(keys(proxmox_virtual_environment_file.employee_boundary_hook), "alice") && length(terraform_data.employee_retirement) == 1 && length(terraform_data.employee_slot) == 1 && length(proxmox_virtual_environment_network_linux_bridge.employee) == 1
    error_message = "Retirement must not recreate a VM or release its permanent network slot."
  }
}
run "reject_retired_workspace_ready_to_start" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { retired = true, disabled = true, start_ready = true, hook_bound = false })
    }
  }
  expect_failures = [var.employee_workspaces]
}
