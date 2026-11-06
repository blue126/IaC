# Shared cloud-init user data; the proxmox-vm module defaults to this snippet.
resource "proxmox_virtual_environment_file" "cloud_init_ubuntu" {
  content_type = "snippets"
  datastore_id = "local"
  node_name    = "pve0"

  source_file {
    path = "${path.module}/files/cloud-init-ubuntu.yml"
  }
}
