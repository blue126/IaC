# Veeam deploys and manages this transient backup worker appliance.
# Terraform tracks its state only and must not change its runtime configuration.
resource "proxmox_virtual_environment_vm" "veeam_worker" {
  name      = "veeam-worker"
  node_name = "pve0"
  vm_id     = 108

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}
