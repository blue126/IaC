# Cable connections: VM/LXC eth0 to pve0 vmbr1 bridge
# 说明: 使用 netbox_cable 建模二层连接，termination_a 为物理设备接口（dcim.interface），
# termination_b 为虚拟机接口（virtualization.vminterface）。

resource "netbox_cable" "netbox_eth0_pve0_vmbr1" {
  termination_a_type = "dcim.interface"
  termination_a_id   = netbox_device_interface.pve0_vmbr1.id
  termination_b_type = "virtualization.vminterface"
  termination_b_id   = netbox_interface.netbox_eth0.id
  status             = "connected"
  description        = "Netbox eth0 -> pve0 vmbr1"
}

resource "netbox_cable" "immich_eth0_pve0_vmbr1" {
  termination_a_type = "dcim.interface"
  termination_a_id   = netbox_device_interface.pve0_vmbr1.id
  termination_b_type = "virtualization.vminterface"
  termination_b_id   = netbox_interface.immich_eth0.id
  status             = "connected"
  description        = "Immich eth0 -> pve0 vmbr1"
}

resource "netbox_cable" "samba_eth0_pve0_vmbr1" {
  termination_a_type = "dcim.interface"
  termination_a_id   = netbox_device_interface.pve0_vmbr1.id
  termination_b_type = "virtualization.vminterface"
  termination_b_id   = netbox_interface.samba_eth0.id
  status             = "connected"
  description        = "Samba eth0 -> pve0 vmbr1"
}

resource "netbox_cable" "anki_eth0_pve0_vmbr1" {
  termination_a_type = "dcim.interface"
  termination_a_id   = netbox_device_interface.pve0_vmbr1.id
  termination_b_type = "virtualization.vminterface"
  termination_b_id   = netbox_interface.anki_eth0.id
  status             = "connected"
  description        = "Anki eth0 -> pve0 vmbr1"
}
