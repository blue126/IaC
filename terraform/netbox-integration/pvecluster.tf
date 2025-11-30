// Proxmox 集群相关资源 (与 Ansible 中组 proxmox_cluster 对齐)
// 说明: 仅定义 NetBox cluster 类型与集群实例；虚拟机、物理设备、服务等拆分至其他文件。

# 1. 集群类型定义 (Proxmox)
resource "netbox_cluster_type" "proxmox" {
  name = "Proxmox"
  slug = "proxmox"
}

# 2. 集群实例 (Homelab Proxmox Cluster)
resource "netbox_cluster" "homelab" {
  name            = "HomeLab Cluster"
  cluster_type_id = netbox_cluster_type.proxmox.id
  site_id         = netbox_site.homelab.id
}

// 虚拟机相关定义迁移到 vm.tf / containers.tf
// 服务定义迁移到 services.tf
// 物理节点与网桥在 infrastructure.tf
// 接口连接关系在 connections.tf