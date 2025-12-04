# Dynamic Provisioning based on Netbox Data

module "netbox_vm" {
  source = "../modules/proxmox-vm"

  for_each = { for vm in var.netbox_provisioned_vms : vm.name => vm }

  vm_name        = each.value.name
  target_node    = each.value.target_node
  vmid           = each.value.vmid
  
  # Map template names to actual template IDs/Files if necessary, 
  # or just use the value from Netbox if it matches Proxmox template names
  # Here we assume the tag in Netbox matches the template name in Proxmox
  template_name  = each.value.template 
  
  cores          = each.value.cores
  memory         = each.value.memory
  disk_size      = each.value.disk_size
  
  # Construct IP config. 
  # If ip_address is provided (CIDR), use it. Otherwise DHCP.
  # Note: This simple logic assumes /24 and .1 gateway for static IPs.
  # A more robust solution would parse the CIDR properly.
  ip_address     = each.value.ip_address
  storage_pool   = var.storage_pool
  cloudinit_slot = each.value.cloudinit_slot
  
  sshkeys        = var.sshkeys
}
