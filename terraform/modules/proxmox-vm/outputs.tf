output "vm_id" {
  description = "The ID of the VM"
  value       = proxmox_vm_qemu.vm.id
}

output "default_ip" {
  description = "The IP configuration of the VM"
  value       = "${var.ip_address} (Proxmox VM)"
}
