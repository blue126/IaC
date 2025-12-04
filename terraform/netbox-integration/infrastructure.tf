# Physical Infrastructure - Proxmox Cluster Nodes

# 1. Manufacturer & Device Type
resource "netbox_manufacturer" "generic" {
  name = "Generic"
  slug = "generic"
}

resource "netbox_device_type" "server" {
  model            = "Server"
  slug             = "server"
  manufacturer_id  = netbox_manufacturer.generic.id
  u_height         = 1
}

# 2. Device Role
resource "netbox_device_role" "server" {
  name      = "Server"
  slug      = "server"
  color_hex = "0000ff" # Blue
}

resource "netbox_device_role" "vm" {
  name      = "Virtual Machine"
  slug      = "vm"
  color_hex = "00ffff" # Cyan
  vm_role   = true     # Allow this role to be assigned to VMs
}

resource "netbox_device_role" "lxc" {
  name      = "LXC Container"
  slug      = "lxc"
  color_hex = "ff8000" # Orange
  vm_role   = true     # Allow this role to be assigned to VMs
}

# 3. Physical Devices (Proxmox Nodes)
resource "netbox_device" "pve0" {
  name           = "pve0"
  device_type_id = netbox_device_type.server.id
  role_id        = netbox_device_role.server.id
  site_id        = netbox_site.homelab.id
  cluster_id     = netbox_cluster.homelab.id
  status         = "active"
}

resource "netbox_device_interface" "pve0_vmbr0" {
  name      = "vmbr0"
  device_id = netbox_device.pve0.id
  type      = "virtual"
}

resource "netbox_device_interface" "pve0_vmbr1" {
  name        = "vmbr1"
  device_id   = netbox_device.pve0.id
  type        = "virtual"
  description = "Primary VM bridge"
}

resource "netbox_ip_address" "pve0_vmbr1_ip" {
  ip_address   = "192.168.1.50/24"
  status       = "active"
  interface_id = netbox_device_interface.pve0_vmbr1.id
  object_type  = "dcim.interface"
  description  = "Bridge vmbr1 management IP"
}

resource "netbox_ip_address" "pve0_ip" {
  ip_address   = "192.168.1.20/24"
  status       = "active"
  interface_id = netbox_device_interface.pve0_vmbr0.id
  object_type  = "dcim.interface"
}

resource "netbox_device" "pve1" {
  name           = "pve1"
  device_type_id = netbox_device_type.server.id
  role_id        = netbox_device_role.server.id
  site_id        = netbox_site.homelab.id
  cluster_id     = netbox_cluster.homelab.id
  status         = "active"
}

resource "netbox_device_interface" "pve1_vmbr0" {
  name      = "vmbr0"
  device_id = netbox_device.pve1.id
  type      = "virtual"
}

resource "netbox_device_interface" "pve1_vmbr1" {
  name        = "vmbr1"
  device_id   = netbox_device.pve1.id
  type        = "virtual"
  description = "Primary VM bridge"
}

resource "netbox_ip_address" "pve1_vmbr1_ip" {
  ip_address   = "192.168.1.51/24"
  status       = "active"
  interface_id = netbox_device_interface.pve1_vmbr1.id
  object_type  = "dcim.interface"
  description  = "Bridge vmbr1 management IP"
}

resource "netbox_ip_address" "pve1_ip" {
  ip_address   = "192.168.1.21/24"
  status       = "active"
  interface_id = netbox_device_interface.pve1_vmbr0.id
  object_type  = "dcim.interface"
}

resource "netbox_device" "pve2" {
  name           = "pve2"
  device_type_id = netbox_device_type.server.id
  role_id        = netbox_device_role.server.id
  site_id        = netbox_site.homelab.id
  cluster_id     = netbox_cluster.homelab.id
  status         = "active"
}

resource "netbox_device_interface" "pve2_vmbr0" {
  name      = "vmbr0"
  device_id = netbox_device.pve2.id
  type      = "virtual"
}

resource "netbox_device_interface" "pve2_vmbr1" {
  name        = "vmbr1"
  device_id   = netbox_device.pve2.id
  type        = "virtual"
  description = "Primary VM bridge"
}

resource "netbox_ip_address" "pve2_vmbr1_ip" {
  ip_address   = "192.168.1.52/24"
  status       = "active"
  interface_id = netbox_device_interface.pve2_vmbr1.id
  object_type  = "dcim.interface"
  description  = "Bridge vmbr1 management IP"
}

resource "netbox_ip_address" "pve2_ip" {
  ip_address   = "192.168.1.22/24"
  status       = "active"
  interface_id = netbox_device_interface.pve2_vmbr0.id
  object_type  = "dcim.interface"
}
