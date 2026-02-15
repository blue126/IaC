terraform {
  required_providers {
    vsphere = {
      source = "vmware/vsphere"
    }
  }
}

resource "vsphere_virtual_machine" "vm" {
  name             = var.vm_name
  resource_pool_id = var.resource_pool_id
  datastore_id     = var.datastore_id

  num_cpus                         = var.num_cpus
  memory                           = var.memory
  memory_reservation               = var.memory_reservation
  memory_reservation_locked_to_max = length(var.pci_device_ids) > 0 ? true : false

  firmware = var.firmware
  guest_id = var.guest_id

  dynamic "clone" {
    for_each = var.template_uuid != "" ? [1] : []
    content {
      template_uuid = var.template_uuid

      dynamic "customize" {
        for_each = var.customize != null ? [var.customize] : []
        content {
          linux_options {
            host_name = customize.value.hostname
            domain    = customize.value.domain
          }

          dynamic "network_interface" {
            for_each = customize.value.ipv4_address != null ? [1] : []
            content {
              ipv4_address = customize.value.ipv4_address
              ipv4_netmask = customize.value.ipv4_netmask
            }
          }

          ipv4_gateway    = customize.value.ipv4_gateway
          dns_server_list = customize.value.dns_server_list
        }
      }
    }
  }

  network_interface {
    network_id   = var.network_id
    adapter_type = var.network_adapter_type
  }

  disk {
    label            = "disk0"
    size             = var.system_disk_size
    thin_provisioned = true
  }

  # PCIe Passthrough Devices
  pci_device_id  = length(var.pci_device_ids) > 0 ? var.pci_device_ids : []
  host_system_id = var.host_system_id

  cdrom {
    client_device = true
  }

  wait_for_guest_net_timeout = 0
  wait_for_guest_ip_timeout  = 0

  # Do not force power on - let lifecycle scripts handle it
  force_power_off = false

  # Extra VMX configuration parameters
  extra_config = var.extra_config

  # Ignore PCI passthrough changes to avoid provider bug (v2.15.0)
  # PCI devices are managed manually via ESXi Web UI
  lifecycle {
    ignore_changes = [pci_device_id, extra_config]
  }
}

