mock_provider "proxmox" {}

variables {
  lxc_name       = "fileserver"
  target_node    = "pve1"
  vmid           = 111
  ostemplate     = "local:vztmpl/debian-12-turnkey-fileserver_18.0-1_amd64.tar.gz"
  rootfs_storage = "local-lvm"
  rootfs_size    = "8G"
}

run "existing_managed_volume" {
  command = plan

  variables {
    mount_points = [{
      volume = "nvme-lvm:vm-111-disk-0"
      path   = "/srv/timemachine"
      size   = "900G"
    }]
  }

  assert {
    condition     = proxmox_virtual_environment_container.lxc.disk[0].datastore_id == "local-lvm"
    error_message = "The rootfs must remain on local-lvm."
  }

  assert {
    condition = (
      proxmox_virtual_environment_container.lxc.mount_point[0].volume == "nvme-lvm:vm-111-disk-0" &&
      proxmox_virtual_environment_container.lxc.mount_point[0].path == "/srv/timemachine" &&
      proxmox_virtual_environment_container.lxc.mount_point[0].size == "900G"
    )
    error_message = "The first mount must reference the existing 900G volume, not allocate or format a new one."
  }
}

run "host_path_remains_supported" {
  command = plan

  variables {
    mount_points = [{
      volume = "/existing-host-directory"
      path   = "/data"
    }]
  }

  assert {
    condition     = proxmox_virtual_environment_container.lxc.mount_point[0].volume == "/existing-host-directory"
    error_message = "Existing bind mounts must still be accepted."
  }
}

run "managed_volume_requires_size" {
  command = plan

  variables {
    mount_points = [{
      volume = "nvme-lvm:vm-111-disk-0"
      path   = "/srv/timemachine"
    }]
  }

  expect_failures = [var.mount_points]
}
