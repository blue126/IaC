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
}

