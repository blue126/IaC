output "lxc_id" {
  description = "The ID of the LXC container"
  value       = proxmox_virtual_environment_container.lxc.vm_id
}

output "lxc_hostname" {
  description = "The hostname of the LXC container"
  # Use input variable directly; bpg provider may not export initialization attributes
  value = var.lxc_name
}

output "lxc_ip" {
  description = "The IP configuration of the LXC container"
  value       = "ip=${var.ip_address},gw=${var.gateway} (LXC)"
}
