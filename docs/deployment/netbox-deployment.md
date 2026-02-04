# Netbox Deployment Documentation

## Overview
This document details the deployment architecture and management procedures for the Netbox IPAM/DCIM system in our infrastructure.

## Architecture

### Components
- **Application**: Netbox v4.1.11 (Docker Image: `netboxcommunity/netbox:v4.1.11`)
- **Orchestration**: Docker Compose (via `netbox-docker` v3.0.2)
- **Database**: Postgres 16
- **Cache**: Redis 7
- **Infrastructure Management**: Terraform (`e-breuninger/netbox` provider)
- **Configuration Management**: Ansible

### Network
- **URL**: http://192.168.1.104:8080
- **Port**: 8080 (Mapped from container port 8080)

## Deployment Workflow

### 1. Infrastructure Provisioning (Terraform)
First, provision the Virtual Machine on Proxmox.
- **Directory**: `terraform/proxmox`
- **Provider**: `telmate/proxmox`
- **Resource**: `module.netbox` (Proxmox VM)
- **Specs**: 2 Cores, 4GB RAM, 20GB Disk, IP 192.168.1.104

**Command**:
```bash
cd terraform/proxmox

# 1. Create variables file
cat > terraform.tfvars <<EOF
# --- Required Variables ---
pm_api_url   = "<PROXMOX_API_URL>"      # e.g., https://192.168.1.20:8006/api2/json
pm_user      = "<PROXMOX_USER>"         # e.g., root@pam
pm_password  = "<PROXMOX_PASSWORD>"
sshkeys      = "<SSH_PUBLIC_KEY>"       # e.g., ssh-rsa AAA...

# --- Optional Variables (Defaults shown) ---
target_node  = "<TARGET_NODE>"          # Default: pve0
vmid         = <VM_ID>                  # Default: 0 (auto-assign)
storage_pool = "<STORAGE_POOL>"         # Default: vmdata
vm_name      = "<VM_NAME>"              # Default: dev-vm-01
cores        = <CORES>                  # Default: 2
memory       = <MEMORY_MB>              # Default: 4096
disk_size    = "<DISK_SIZE>"            # Default: "20G"
ip_config    = "<IP_CONFIG>"            # Default: "ip=dhcp"
EOF

# 2. VM Configuration (Optional)
# To modify VM specs (Cores, Memory, Disk, IP), edit terraform/proxmox/main.tf:
# - cores: Number of CPU cores
# - memory: RAM in MB
# - disk_size: Disk size (e.g., "20G")
# - ip_address: Static IP configuration (e.g., "ip=192.168.1.104/24,gw=192.168.1.1")

# 3. Provision
terraform init
terraform apply
```

### 2. Application Deployment (Ansible)
Once the VM is running, deploy the Netbox application stack.
- **Playbook**: `ansible/playbooks/deploy-netbox.yml`
- **Role**: `ansible/roles/netbox`
- **Key Features**:
  - Clones `netbox-docker` repository (v3.0.2)
  - Configures `docker-compose.override.yml` for version pinning and port mapping
  - Sets up automatic superuser creation (`SKIP_SUPERUSER=false`)
  - Handles long-running database migrations with async tasks

**Command**:
```bash
# Option 1: Run with defaults
ansible-playbook ansible/playbooks/deploy-netbox.yml

# Option 2: Override variables (Recommended for production)
ansible-playbook ansible/playbooks/deploy-netbox.yml -e "
netbox_superuser_password=StrongPassword123
netbox_superuser_api_token=YourSecureTokenHere
netbox_port=8080
"
```

#### Configuration Variables
You can override these defaults in `ansible/roles/netbox/defaults/main.yml` or via `-e`.

| Variable | Default | Description |
|----------|---------|-------------|
| `netbox_git_version` | `"3.0.2"` | netbox-docker version (controls docker-compose structure) |
| `netbox_image` | `"netboxcommunity/netbox:v4.1.11"` | Netbox application image version |
| `netbox_port` | `8080` | Host port to expose Netbox on |
| `netbox_install_dir` | `"/opt/netbox-docker"` | Installation directory on target |
| `netbox_superuser_name` | `"admin"` | Admin username |
| `netbox_superuser_email` | `"admin@example.com"` | Admin email |
| `netbox_superuser_password` | `"admin"` | **[Sensitive]** Admin password |
| `netbox_superuser_api_token` | `"0123..."` | **[Sensitive]** API Token for Terraform |

### 3. Verification & Initial Population (Terraform)
This section covers the configuration of Netbox resources (Sites, Clusters, Devices, VMs, IPs) using Terraform. This ensures that Netbox is populated with the correct data representing your infrastructure.

### 1. Initialize Terraform
Navigate to the `terraform/netbox-integration` directory and initialize Terraform:

```bash
cd terraform/netbox-integration
terraform init
```
- **Managed Resources**:
  - Sites (e.g., HomeLab)
  - Clusters (e.g., Proxmox)
  - Virtual Machines
  - IP Addresses & Interfaces
  - Services

**Command**:
```bash
cd terraform/netbox-integration

# 1. Create variables file
cat > terraform.tfvars <<EOF
netbox_url      = "http://192.168.1.104:8080"
netbox_token    = "<NETBOX_API_TOKEN>"      # e.g., 0123456789abcdef...
EOF

# 2. Provision
terraform init
terraform apply
```

## Troubleshooting

### Common Issues
- **Timeout during startup**: The initial database migration takes time. The Ansible playbook uses `async: 600` to allow up to 10 minutes for startup.
- **Superuser not created**: Ensure `SKIP_SUPERUSER=false` is set in `docker-compose.override.yml`.
- **Terraform Tag Error**: There is a known bug in the provider where creating a VM with tags fails due to race conditions. Workaround: Create VM without tags first, or use `depends_on` (though Terraform handles dependencies automatically, this specific provider issue persists).

## Credentials
- **Admin User**: `admin` / `admin` (Default, change in production)
- **API Token**: `0123456789abcdef0123456789abcdef01234567`
