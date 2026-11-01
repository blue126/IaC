# One-time original-disk employee adoptions; legacy allocations remain reserved.

moved {
  from = proxmox_virtual_environment_vm.employee_workspace["pilot"]
  to   = module.oci_hub_workspace["pilot"].proxmox_virtual_environment_vm.vm
}
moved {
  from = ansible_host.employee_workspace["pilot"]
  to   = ansible_host.oci_hub_workspace["pilot"]
}

moved {
  from = proxmox_virtual_environment_vm.employee_workspace["ritsuka2020"]
  to   = module.oci_hub_workspace["ritsuka2020"].proxmox_virtual_environment_vm.vm
}
moved {
  from = ansible_host.employee_workspace["ritsuka2020"]
  to   = ansible_host.oci_hub_workspace["ritsuka2020"]
}

moved {
  from = proxmox_virtual_environment_vm.employee_workspace["suixiaoyou"]
  to   = module.oci_hub_workspace["suixiaoyou"].proxmox_virtual_environment_vm.vm
}
moved {
  from = ansible_host.employee_workspace["suixiaoyou"]
  to   = ansible_host.oci_hub_workspace["suixiaoyou"]
}

moved {
  from = proxmox_virtual_environment_vm.employee_workspace["user156561205"]
  to   = module.oci_hub_workspace["user156561205"].proxmox_virtual_environment_vm.vm
}
moved {
  from = ansible_host.employee_workspace["user156561205"]
  to   = ansible_host.oci_hub_workspace["user156561205"]
}

moved {
  from = proxmox_virtual_environment_vm.employee_workspace["user181825738"]
  to   = module.oci_hub_workspace["user181825738"].proxmox_virtual_environment_vm.vm
}
moved {
  from = ansible_host.employee_workspace["user181825738"]
  to   = ansible_host.oci_hub_workspace["user181825738"]
}

moved {
  from = proxmox_virtual_environment_vm.employee_workspace["zhang171903992"]
  to   = module.oci_hub_workspace["zhang171903992"].proxmox_virtual_environment_vm.vm
}
moved {
  from = ansible_host.employee_workspace["zhang171903992"]
  to   = ansible_host.oci_hub_workspace["zhang171903992"]
}

moved {
  from = proxmox_virtual_environment_vm.employee_workspace["control"]
  to   = module.oci_hub_workspace["control"].proxmox_virtual_environment_vm.vm
}
moved {
  from = ansible_host.employee_workspace["control"]
  to   = ansible_host.oci_hub_workspace["control"]
}
