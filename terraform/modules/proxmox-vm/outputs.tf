output "vm_id" {
  description = "The ID of the VM"
  value       = proxmox_vm_qemu.vm.id
}

output "default_ip" {
  description = "The default IP address of the VM"
  value       = proxmox_vm_qemu.vm.default_ipv4_address
}
