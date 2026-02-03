# PBS VM Definition

# Data sources are defined in main.tf

module "pbs" {
  source = "../modules/esxi-vm"

  # Basic Configuration
  vm_name          = var.pbs_vm_name
  resource_pool_id = data.vsphere_host.host.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  host_system_id   = data.vsphere_host.host.id

  # Hardware Resources
  num_cpus           = var.pbs_num_cpus
  memory             = var.pbs_memory_mb
  memory_reservation = var.pbs_memory_mb # Required for PCIe passthrough
  system_disk_size   = var.pbs_system_disk_gb

  # Firmware & Guest OS
  firmware             = "efi"
  guest_id             = "debian11_64Guest" # PBS is based on Debian 11/12
  network_adapter_type = "vmxnet3"

  # PCIe Passthrough
  # Currently managed manually via ESXi Web UI (not by Terraform)
  # to avoid VM recreation. Actual passthrough config on ESXi:
  #   - LSI 3008 HBA: 0000:03:00.0 (enabled, provides /dev/sdb, /dev/sdc)
  #   - Samsung SM963 NVMe x2: 0000:08:00.0, 0000:11:00.0 (enabled, ZFS special vdev)
  #   - Intel Optane Memory: removed (incompatible, firmware has no namespace support)
  pci_device_ids = []

  # VMX extra config for Samsung NVMe FLR fix
  # Prevents VM shutdown crash due to NVMe FLR (Function Level Reset) issue
  extra_config = {
    "pciPassthru.use64bitMMIO"    = "TRUE"
    "pciPassthru.64bitMMIOSizeGB" = "64"
    "pciPassthru0.resetMethod"    = "d3d0"
    "pciPassthru1.resetMethod"    = "d3d0"
  }
}

# Register to Ansible Inventory
resource "ansible_host" "pbs" {
  name   = "pbs"
  groups = ["esxi_vms"]

  variables = {
    ansible_user                 = "root"
    ansible_host                 = var.pbs_ip_address
    ansible_ssh_private_key_file = "~/.ssh/id_ed25519"

    # PBS Specific Variables
    pbs_datastore_path = "/mnt/backup-pool/datastore"
    pbs_zfs_pool       = "backup-pool"

    # Device mapping for Ansible verification
    # Note: Device names (sdb, sdc) may vary, using by-id is recommended in production
    # but for initial setup we'll assume sdb/sdc for the HBA disks
  }

  depends_on = [module.pbs]
}

# Outputs
output "pbs_vm_id" {
  value       = module.pbs.vm_id
  description = "PBS VM Managed Object ID"
}

output "pbs_ip" {
  value       = var.pbs_ip_address
  description = "PBS Management IP"
}
