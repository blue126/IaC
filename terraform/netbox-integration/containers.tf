# LXC Containers

# Anki Sync Server LXC
resource "netbox_virtual_machine" "anki" {
  name         = "anki-sync-server"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  vcpus        = 1        # 来源: terraform/proxmox/anki.tf cores=1
  memory_mb    = 2048     # 来源: terraform/proxmox/anki.tf memory=2048
  disk_size_mb = 8192     # 8G => 8*1024 MB, 来源: rootfs_size="8G"
  comments     = "Anki Sync (LXC) bridge=vmbr1 target_node=pve0"
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
