output "vm_id" {
  description = "The ID of the VM"
  value       = proxmox_virtual_environment_vm.vm.vm_id
}

output "default_ip" {
  description = "The configured IP address of the VM"
  value       = var.ip_address != null ? var.ip_address : "DHCP"
}
