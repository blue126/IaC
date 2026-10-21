mock_provider "proxmox" {}
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
run "empty" {
  command = plan
  variables {
    employee_access     = null
    employee_workspaces = {}
  }
  assert {
    condition     = length(proxmox_virtual_environment_vm.employee_access) == 0 && length(proxmox_virtual_environment_vm.employee_workspace) == 0
    error_message = "Default inputs must create zero employee resources."
  }
}
run "bootstrap" {
  command = plan
}
run "ready" {
  command = plan
  variables {
    employee_access = merge(var.employee_access, { boundary_ready = true })
  }
}
run "disabled" {
  command = plan
  variables {
    employee_access     = merge(var.employee_access, { boundary_ready = true })
    employee_workspaces = { alice = merge(var.employee_workspaces.alice, { disabled = true }) }
  }
}

run "allocated" {
  command = apply
  variables {
    employee_workspaces = {
      alice = var.employee_workspaces.alice
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
}
run "earlier_name_keeps_slots" {
  command = plan
  variables {
    employee_workspaces = {
      alice = var.employee_workspaces.alice
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
      aaron = { nic_slot = 3, vmid = 503, bridge = "vmbr503", address = "10.231.3.2/30", gateway = "10.231.3.1", mac_address = "02:00:00:00:03:02", gateway_mac = "02:00:00:00:03:01" }
    }
  }
  assert {
    condition     = proxmox_virtual_environment_vm.employee_access[0].network_device[1].mac_address == "02:00:00:00:01:01" && proxmox_virtual_environment_vm.employee_access[0].network_device[2].mac_address == "02:00:00:00:02:01" && proxmox_virtual_environment_vm.employee_access[0].network_device[3].mac_address == "02:00:00:00:03:01"
    error_message = "An alphabetically earlier employee must append its assigned NIC, leaving existing NICs stable."
  }
}
run "reject_slot_reassignment" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { nic_slot = 2 })
      bob   = { nic_slot = 1, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [terraform_data.employee_slot]
}

run "reject_disk_units" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { disk_size = "1T" })
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [var.employee_workspaces]
}

run "reject_gateway_outside_subnet" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { gateway = "10.232.1.1" })
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [var.employee_workspaces]
}

run "reject_changed_address" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { address = "10.231.1.3/29" })
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [terraform_data.employee_slot]
}

run "reject_changed_gateway" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { address = "10.231.1.2/29", gateway = "10.231.1.3" })
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [terraform_data.employee_slot]
}

run "reject_changed_mac" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { mac_address = "02:00:00:00:01:99" })
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [terraform_data.employee_slot]
}

run "reject_changed_gateway_mac" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { gateway_mac = "02:00:00:00:01:98" })
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [terraform_data.employee_slot]
}

run "reject_changed_bridge" {
  command = plan
  variables {
    employee_workspaces = {
      alice = merge(var.employee_workspaces.alice, { bridge = "vmbr601" })
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [terraform_data.employee_slot]
}

run "reject_overlapping_employee_subnets" {
  command = plan
  variables {
    employee_workspaces = {
      alice = var.employee_workspaces.alice
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.1.3/29", gateway = "10.231.1.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [var.employee_workspaces]
}
run "reject_employee_uplink_overlap" {
  command = plan
  variables {
    employee_access = merge(var.employee_access, { uplink_address = "10.231.1.5/24", uplink_gateway = "10.231.1.6" })
    employee_workspaces = {
      alice = var.employee_workspaces.alice
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  expect_failures = [proxmox_virtual_environment_vm.employee_access]
}

run "administrator_keys_reach_both_inventories" {
  command = plan
  variables {
    employee_access = merge(var.employee_access, { admin_public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB47MgYesEVqT9kYtWug/AO1N+lpdZq8V3Bd2JNGK9fO"] })
    employee_workspaces = {
      alice = var.employee_workspaces.alice
      bob   = { nic_slot = 2, vmid = 502, bridge = "vmbr502", address = "10.231.2.2/30", gateway = "10.231.2.1", mac_address = "02:00:00:00:02:02", gateway_mac = "02:00:00:00:02:01" }
    }
  }
  assert {
    condition     = tolist(jsondecode(ansible_host.employee_access[0].variables.employee_access_admin_public_keys_json)) == var.employee_access.admin_public_keys && tolist(jsondecode(ansible_host.employee_workspace["alice"].variables.employee_workspace_admin_public_keys_json)) == var.employee_access.admin_public_keys
    error_message = "Administrator key updates must be carried to both Ansible consumers."
  }
}
