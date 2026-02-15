# LLM Server VM Definition

data "vsphere_virtual_machine" "ubuntu_template" {
  name          = var.vm_template
  datacenter_id = data.vsphere_datacenter.dc.id
}

module "llm_server" {
  source = "../modules/esxi-vm"

  # Basic Configuration
  vm_name          = var.llm_server_vm_name
  resource_pool_id = data.vsphere_host.host.resource_pool_id
  datastore_id     = data.vsphere_datastore.datastore.id
  network_id       = data.vsphere_network.network.id
  host_system_id   = data.vsphere_host.host.id

  # Clone from template with guest customization
  template_uuid = data.vsphere_virtual_machine.ubuntu_template.id
  customize = {
    hostname        = var.llm_server_vm_name
    ipv4_address    = var.llm_server_ip_address
    ipv4_netmask    = 24
    ipv4_gateway    = "192.168.1.1"
    dns_server_list = ["192.168.1.1"]
  }

  # Hardware Resources
  num_cpus           = var.llm_server_num_cpus
  memory             = var.llm_server_memory_mb
  memory_reservation = var.llm_server_memory_mb # Required for GPU Passthrough
  system_disk_size   = var.llm_server_system_disk_gb

  # Firmware & Guest OS
  firmware = "efi"
  guest_id = data.vsphere_virtual_machine.ubuntu_template.guest_id

  # GPU Passthrough
  # Currently managed manually via ESXi Web UI (not by Terraform)
  # to avoid VM recreation (vSphere provider v2.15.0 bug).
  # Same pattern as PBS HBA passthrough.
  # Actual passthrough config on ESXi:
  #   - RTX 3090 #1: 0000:xx:00.0 (toggle passthrough in ESXi UI)
  #   - RTX 3090 #2: 0000:xx:00.0 (toggle passthrough in ESXi UI)
  pci_device_ids = []

  # VMX extra config for dual GPU passthrough
  extra_config = {
    "pciPassthru.use64bitMMIO"    = "TRUE"
    "pciPassthru.64bitMMIOSizeGB" = tostring(var.llm_server_mmio_size_gb)
    "mem.hotadd"                  = "FALSE"
  }
}

# Register to Ansible Inventory
resource "ansible_host" "llm_server" {
  name   = "llm-server"
  groups = ["esxi_vms"]

  variables = {
    ansible_user                 = "ubuntu"
    ansible_host                 = var.llm_server_ip_address
    ansible_ssh_private_key_file = "~/.ssh/id_ed25519"
  }

  depends_on = [module.llm_server]
}

# Outputs
output "llm_server_vm_id" {
  value       = module.llm_server.vm_id
  description = "LLM Server VM Managed Object ID"
}

output "llm_server_ip" {
  value       = var.llm_server_ip_address
  description = "LLM Server IP Address"
}
