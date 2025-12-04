# LXC Containers

# Anki Sync Server LXC
resource "netbox_virtual_machine" "anki" {
  name         = "anki-sync-server"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  role_id      = netbox_device_role.lxc.id
  vcpus        = 1        # 来源: terraform/proxmox/anki.tf cores=1
  memory_mb    = 2048     # 来源: terraform/proxmox/anki.tf memory=2048
  disk_size_mb = 8192     # 8G => 8*1024 MB, 来源: rootfs_size="8G"
  comments     = "Anki Sync (LXC) bridge=vmbr1 target_node=pve0"

  lifecycle {
    ignore_changes = [
      vcpus,
      memory_mb,
      disk_size_mb,
      comments
    ]
  }
}

resource "netbox_interface" "anki_eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.anki.id
}

resource "netbox_ip_address" "anki_ip" {
  ip_address   = "192.168.1.100/24"
  status       = "active"
  interface_id = netbox_interface.anki_eth0.id
  object_type  = "virtualization.vminterface"
}

# Homepage LXC
resource "netbox_virtual_machine" "homepage" {
  name         = "homepage"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  role_id      = netbox_device_role.lxc.id
  vcpus        = 2
  memory_mb    = 4096
  disk_size_mb = 4096
  comments     = "Homepage Dashboard (LXC) bridge=vmbr1 target_node=pve0"

  lifecycle {
    ignore_changes = [
      vcpus,
      memory_mb,
      disk_size_mb,
      comments
    ]
  }
}

resource "netbox_interface" "homepage_eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.homepage.id
}

resource "netbox_ip_address" "homepage_ip" {
  ip_address   = "192.168.1.103/24"
  status       = "active"
  interface_id = netbox_interface.homepage_eth0.id
  object_type  = "virtualization.vminterface"
}

# Caddy LXC
resource "netbox_virtual_machine" "caddy" {
  name         = "caddy"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  role_id      = netbox_device_role.lxc.id
  vcpus        = 1
  memory_mb    = 512
  disk_size_mb = 51200
  comments     = "Caddy Reverse Proxy & WebDAV (LXC) bridge=vmbr1 target_node=pve0"

  lifecycle {
    ignore_changes = [
      vcpus,
      memory_mb,
      disk_size_mb,
      comments
    ]
  }
}

resource "netbox_interface" "caddy_eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.caddy.id
}

resource "netbox_ip_address" "caddy_ip" {
  ip_address   = "192.168.1.105/24"
  status       = "active"
  interface_id = netbox_interface.caddy_eth0.id
  object_type  = "virtualization.vminterface"
}
