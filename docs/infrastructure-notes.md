# Infrastructure Network Topology

## Proxmox Cluster
Each Proxmox node has two network interfaces with distinct roles:

### Management Interface
Used for administrative access (SSH, Proxmox GUI, Ansible).
- **Subnet**: `192.168.1.20-22`
- **pve0**: `192.168.1.20`
- **pve1**: `192.168.1.21`
- **pve2**: `192.168.1.22`

### Service/Business Interface
Used for applications, VMs, and LXC containers.
- **Subnet**: `192.168.1.50-52`
- **pve0**: `192.168.1.50`
- **pve1**: `192.168.1.51`
- **pve2**: `192.168.1.52`

> [!IMPORTANT]
> When configuring applications or services (e.g., Homepage widgets, external access), always use the **Service Interface** IPs.
