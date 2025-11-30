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
  name         = "netbox-01"
  cluster_id   = netbox_cluster.homelab.id
  status       = "active"
  vcpus        = 2
  memory_mb    = 4096
  disk_size_mb = 20480

  # TODO: Re-enable after VM is created (workaround for tag retrieval bug)
  # tags = [
  #   netbox_tag.terraform.id
  # ]
}

# 4. 定义网络接口
resource "netbox_interface" "eth0" {
  name               = "eth0"
  virtual_machine_id = netbox_virtual_machine.netbox_01.id
}

# 5. 定义 IP 地址
resource "netbox_ip_address" "netbox_ip" {
  ip_address   = "192.168.1.104/24"
  status       = "active"
  interface_id = netbox_interface.eth0.id
  object_type  = "virtualization.vminterface"
}

# 6. 定义服务
resource "netbox_service" "netbox_app" {
  name               = "Netbox"
  protocol           = "tcp"
  ports              = [8080]
  virtual_machine_id = netbox_virtual_machine.netbox_01.id
}
