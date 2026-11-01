mock_provider "proxmox" {
  alias = "pve2"
  mock_data "proxmox_virtual_environment_vms" {
    defaults = { vms = [{ name = "approved-fixture", vm_id = 9900 }] }
  }
}
mock_provider "ansible" {}
run "defaults_preserve_existing" {
  command = plan
  assert {
    condition     = length(module.oci_hub_workspace) == 0
    error_message = "Default empty roster must introduce no new VM."
  }
}
run "new_workspaces_stopped_protected_and_hooked" {
  command = plan
  variables {
    oci_hub_workspaces = {
      alice = {
        vmid                = 601
        vnet                = "ohalice"
        address             = "10.236.1.2/30"
        gateway             = "10.236.1.1"
        mac_address         = "02:00:00:00:01:02"
        template_name       = "approved-fixture"
        baseline_id         = "fixture-v1"
        bootstrap_file      = "local:snippets/fixture.yaml"
        hook_script_file_id = "local:snippets/oci-hub-boundary.sh"
        storage_pool        = "local-zfs"
        admin_public_keys   = []
        dns_server          = "192.0.2.53"
        overlay             = "10.234.0.2/32"
      }
    }
  }
  assert {
    condition     = !module.oci_hub_workspace["alice"].startup_contract.started && !module.oci_hub_workspace["alice"].startup_contract.on_boot && module.oci_hub_workspace["alice"].startup_contract.protection && module.oci_hub_workspace["alice"].startup_contract.hook == "local:snippets/oci-hub-boundary.sh"
    error_message = "New OCI workspaces require stopped first creation, deletion protection and boundary hook."
  }
  assert {
    condition     = ansible_host.oci_hub_workspace["alice"].variables.employee_workspace_profile == "oci-hub"
    error_message = "Inventory must dispatch explicitly to the new profile."
  }
}

run "legacy_module_defaults_remain_compatible" {
  command = plan
  module {
    source = "../modules/proxmox-vm"
  }
  providers = { proxmox = proxmox.pve2 }
  variables {
    vm_name       = "legacy-fixture"
    target_node   = "pve-test"
    template_name = "approved-fixture"
  }
  assert {
    condition     = output.startup_contract.started && output.startup_contract.on_boot && !output.startup_contract.protection && output.startup_contract.hook == null
    error_message = "Existing module callers must retain default first boot and an absent hook."
  }
}

run "deferred_root_hook_is_bound_only_after_stopped_creation" {
  command = plan
  variables {
    oci_hub_workspaces = {
      alice = {
        defer_hook_binding  = true
        bios                = "seabios"
        vmid                = 601
        vnet                = "ohalice"
        address             = "10.236.1.2/30"
        gateway             = "10.236.1.1"
        mac_address         = "02:00:00:00:01:02"
        template_name       = "approved-fixture"
        baseline_id         = "fixture-v1"
        bootstrap_file      = "local:snippets/fixture.yaml"
        hook_script_file_id = "local:snippets/oci-hub-boundary.sh"
        storage_pool        = "local-zfs"
        admin_public_keys   = []
        dns_server          = "192.0.2.53"
        overlay             = "10.234.0.2/32"
      }
    }
  }
  assert {
    condition     = !module.oci_hub_workspace["alice"].startup_contract.started && !module.oci_hub_workspace["alice"].startup_contract.on_boot && module.oci_hub_workspace["alice"].startup_contract.protection && module.oci_hub_workspace["alice"].startup_contract.hook == null
    error_message = "Deferred root-owned hooks must keep the VM stopped, protected and without an API hook write."
  }
}
