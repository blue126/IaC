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

# Hardware Resources

# PCIe Passthrough Devices
# Note: Currently managed manually via ESXi (not by Terraform)

# LSI 3008 HBA: 0000:01:00.0 (Fusion-MPT 12GSAS SAS3008 PCI-Express)
# Status: Enabled in ESXi, provides /dev/sdb and /dev/sdc to PBS VM

# NVMe Devices: Currently disabled
# - Samsung SM963 (2x 256GB): PCIe bifurcation not available (need BIOS support or PLX switch card)
# - Intel Optane Memory (2x 16GB): Incompatible (firmware has no namespace support)
#   "0000:08:00.0",
#   "0000:0b:00.0"
# ]

# ==========================================
# LLM Server Configuration
# ==========================================

llm_server_vm_name        = "llm-server"
llm_server_ip_address     = "192.168.1.247"
llm_server_datastore      = "Intel800GSSD"
llm_server_num_cpus       = 36
llm_server_memory_mb      = 348160 # 340 GB
llm_server_system_disk_gb = 900
llm_server_mmio_size_gb   = 128
