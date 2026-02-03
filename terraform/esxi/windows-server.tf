# =============================================================================
# Windows Server VM Definition (Veeam Host)
# =============================================================================

module "windows_server" {
  source = "../modules/esxi-vm"

  # Basic Configuration
  vm_name          = var.windows_vm_name
  resource_pool_id = data.vsphere_host.host.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  host_system_id   = data.vsphere_host.host.id

  # Hardware Resources
  num_cpus         = var.windows_num_cpus
  memory           = var.windows_memory_mb
  system_disk_size = var.windows_system_disk_gb

  # Firmware & Guest OS
  firmware = "efi"
  guest_id = "windows2022srvNext_64Guest" # Windows Server 2022

  # VMX extra config for high resolution support
  extra_config = {
    "svga.maxWidth"  = "1920"
    "svga.maxHeight" = "1080"
  }
}

# -----------------------------------------------------------------------------
# Ansible Inventory Registration
# -----------------------------------------------------------------------------

resource "ansible_host" "windows_server" {
  name   = "windows-server"
  groups = ["esxi_vms", "windows"]

  variables = {
    ansible_host = var.windows_ip_address
    ansible_user = "Administrator"

    # Windows Ansible connection (WinRM)
    ansible_connection                   = "winrm"
    ansible_winrm_transport              = "ntlm"
    ansible_winrm_server_cert_validation = "ignore"

    # iSCSI connection info (for future automation)
    iscsi_target_ip  = var.pbs_ip_address
    iscsi_target_iqn = "iqn.2026-02.lan.pbs:veeam"
  }

  depends_on = [module.windows_server]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "windows_server_vm_id" {
  value       = module.windows_server.vm_id
  description = "Windows Server VM Managed Object ID"
}

output "windows_server_ip" {
  value       = var.windows_ip_address
  description = "Windows Server IP Address"
}
