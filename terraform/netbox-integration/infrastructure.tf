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

resource "netbox_ip_address" "pve2_ip" {
  ip_address   = "192.168.1.22/24"
  status       = "active"
  interface_id = netbox_device_interface.pve2_vmbr0.id
  object_type  = "dcim.interface"
}

# 4. Virtual Machines
resource "netbox_virtual_machine" "immich" {
  name         = "immich"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  vcpus        = 2
  memory_mb    = 8192
}

resource "netbox_interface" "immich_eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.immich.id
}

resource "netbox_ip_address" "immich_ip" {
  ip_address   = "192.168.1.101/24"
  status       = "active"
  interface_id = netbox_interface.immich_eth0.id
  object_type  = "virtualization.vminterface"
}

resource "netbox_virtual_machine" "samba" {
  name         = "samba"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  vcpus        = 1
  memory_mb    = 512
  disk_size_mb = 65536 # 64GB
}

resource "netbox_interface" "samba_eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.samba.id
}

resource "netbox_ip_address" "samba_ip" {
  ip_address   = "192.168.1.102/24"
  status       = "active"
  interface_id = netbox_interface.samba_eth0.id
  object_type  = "virtualization.vminterface"
}
