# Virtual Machines (Proxmox VMs)

# Netbox VM
resource "netbox_virtual_machine" "netbox" {
  name         = "netbox"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  role_id      = netbox_device_role.vm.id
  vcpus        = 2        # 来源: terraform/proxmox/netbox.tf cores=2
  memory_mb    = 4096     # 来源: terraform/proxmox/netbox.tf memory=4096
  disk_size_mb = 20480    # 20G => 20*1024 MB, 来源: disk_size="20G"
  comments     = "Netbox IPAM/DCIM (6 containers) bridge=vmbr1 target_node=pve0"

  lifecycle {
    ignore_changes = [
      vcpus,
      memory_mb,
      disk_size_mb,
      comments
    ]
  }
}

resource "netbox_interface" "netbox_eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.netbox.id
}

resource "netbox_ip_address" "netbox_ip" {
  ip_address   = "192.168.1.104/24"
  status       = "active"
  interface_id = netbox_interface.netbox_eth0.id
  object_type  = "virtualization.vminterface"
}

# Immich VM
resource "netbox_virtual_machine" "immich" {
  name         = "immich"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  role_id      = netbox_device_role.vm.id
  vcpus        = 2         # 来源: terraform/proxmox/immich.tf cores=2
  memory_mb    = 8192      # 来源: terraform/proxmox/immich.tf memory=8192
  disk_size_mb = 307200    # 300G => 300*1024 MB, 来源: disk_size="300G"
  comments     = "Immich (4 containers) bridge=vmbr1 target_node=pve0"

  lifecycle {
    ignore_changes = [
      vcpus,
      memory_mb,
      disk_size_mb,
      comments
    ]
  }
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


