resource "proxmox_virtual_environment_container" "fileserver" {
  provider = proxmox.root

  description   = "Managed by Terraform"
  node_name     = "pve0"
  vm_id         = 111
  unprivileged  = true
  started       = true
  start_on_boot = true

  cpu {
    architecture = "amd64"
    cores        = 1
    units        = 1024
  }

  memory {
    dedicated = 512
    swap      = 512
  }

  disk {
    datastore_id = "vmdata"
    size         = 8
  }

  mount_point {
    volume = "local-zfs:subvol-111-disk-0"
    path   = "/srv/timemachine"
    size   = "800G"
    backup = true
  }

  initialization {
    hostname = "fileserver"

    dns {
      servers = ["192.168.1.1"]
    }

    ip_config {
      ipv4 {
        address = "192.168.1.111/24"
        gateway = "192.168.1.1"
      }
    }
  }

  network_interface {
    name        = "eth0"
    bridge      = "vmbr1"
    enabled     = true
    firewall    = true
    mac_address = "BC:24:11:3B:86:8E"
  }

  operating_system {
    # Historical creation metadata required by this provider's OS schema.
    template_file_id = "local:vztmpl/debian-12-turnkey-fileserver_18.0-1_amd64.tar.gz"
    type             = "debian"
  }

  lifecycle {
    prevent_destroy = true
    # PVE never returns the creation template or initial credentials on read.
    # Keep OS type, node, disks, mount point and power state observable.
    ignore_changes = [
      description,
      operating_system[0].template_file_id,
      initialization[0].user_account,
    ]
  }
}

output "fileserver_ip" {
  value = "ip=${proxmox_virtual_environment_container.fileserver.initialization[0].ip_config[0].ipv4[0].address},gw=${proxmox_virtual_environment_container.fileserver.initialization[0].ip_config[0].ipv4[0].gateway} (LXC)"
}

resource "ansible_host" "fileserver" {
  depends_on = [proxmox_virtual_environment_container.fileserver]

  name   = "fileserver"
  groups = ["pve_lxc"]
  variables = {
    ansible_host = "192.168.1.111"
  }
}
