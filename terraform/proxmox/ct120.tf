# Adopt the existing container after its rootfs was expanded on the host.
import {
  to = proxmox_virtual_environment_container.ct120
  id = "pve2/120"
}

resource "proxmox_virtual_environment_container" "ct120" {
  provider  = proxmox.pve2_root
  node_name = "pve2"
  vm_id     = 120

  disk {
    datastore_id = "mainpool"
    size         = 178
  }

  lifecycle {
    # bpg 0.70.0 marks disk.size as ForceNew; never replace this container.
    prevent_destroy = true

    # Only rootfs capacity is adopted here. Preserve existing GPU, bind mounts,
    # networking, resources, credentials, and lifecycle settings during import.
    ignore_changes = [
      # This version imports vm_id and timeouts as null. Bind through pve2/120
      # and resource.id instead of issuing a metadata-only container update.
      vm_id,
      timeout_clone,
      timeout_create,
      timeout_delete,
      timeout_start,
      timeout_update,
      clone,
      console,
      cpu,
      description,
      device_passthrough,
      features,
      hook_script_file_id,
      initialization,
      memory,
      mount_point,
      network_interface,
      operating_system,
      pool_id,
      protection,
      started,
      startup,
      start_on_boot,
      tags,
      template,
      unprivileged,
    ]
  }
}
