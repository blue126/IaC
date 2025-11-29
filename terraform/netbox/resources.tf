# 1. 定义集群类型 (比如 Proxmox, VMware, Kubernetes)
resource "netbox_cluster_type" "proxmox" {
  name = "Proxmox"
  slug = "proxmox"
}

# 2. 定义具体的集群
resource "netbox_cluster" "homelab" {
  name            = "HomeLab Cluster"
  cluster_type_id = netbox_cluster_type.proxmox.id # 引用上面定义的类型
  site_id         = netbox_site.homelab.id         # 引用 main.tf 里定义的站点
}

# 3. 定义虚拟机
resource "netbox_virtual_machine" "netbox_01" {
  name       = "netbox-01"
  cluster_id = netbox_cluster.homelab.id           # 归属于上面的集群
  status     = "active"
  
  tags = [
    netbox_tag.terraform.id                        # 打上 "Managed by Terraform" 标签
  ]
}
