# Infrastructure Configuration
vsphere_server     = "192.168.1.250" # vCenter IP
vsphere_user       = "administrator@willfan.top"
vsphere_password   = "CHANGE_ME" # Use secrets bridge or Terraform Cloud variables
vsphere_datacenter = "Roseville"
vsphere_host       = "192.168.1.251" # [esxi-host]

# VM Configuration
vm_template  = "ubuntu2404"
vm_network   = "VM Network"
vm_datastore = "SamsungSSDEVO8701T-2"

# ==========================================
# PBS Configuration
# ==========================================

# VM Basic Settings
pbs_vm_name    = "proxmox-backup-server"
pbs_ip_address = "192.168.1.249"

# Hardware Resources
pbs_num_cpus       = 8
pbs_memory_mb      = 16384
pbs_system_disk_gb = 80

# PCIe Passthrough Devices
# Note: Currently managed manually via ESXi (not by Terraform)

# LSI 3008 HBA: 0000:01:00.0 (Fusion-MPT 12GSAS SAS3008 PCI-Express)
# Status: Enabled in ESXi, provides /dev/sdb and /dev/sdc to PBS VM
pbs_hba_pci_id = "0000:01:00.0"

# NVMe Devices: Currently disabled
# - Samsung SM963 (2x 256GB): PCIe bifurcation not available (need BIOS support or PLX switch card)
# - Intel Optane Memory (2x 16GB): Incompatible (firmware has no namespace support)
# pbs_nvme_pci_ids = [
#   "0000:08:00.0",
#   "0000:0b:00.0"
# ]

# ==========================================
# Windows Server Configuration (Veeam Host)
# ==========================================

windows_vm_name        = "windows-server"
windows_ip_address     = "192.168.1.248"
windows_num_cpus       = 4
windows_memory_mb      = 16384
windows_system_disk_gb = 60
