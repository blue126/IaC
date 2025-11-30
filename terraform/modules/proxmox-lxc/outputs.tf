output "lxc_id" {
  description = "The ID of the LXC container"
  value       = proxmox_lxc.lxc.id
}

output "lxc_hostname" {
  description = "The hostname of the LXC container"
  value       = proxmox_lxc.lxc.hostname
}

output "lxc_ip" {
  description = "The IP configuration of the LXC container"
  value       = "ip=${var.ip_address},gw=${var.gateway} (LXC)"
}
