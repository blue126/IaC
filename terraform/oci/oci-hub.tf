variable "oci_hub_ingress" {
  description = "Explicit new Hub VCN and approved GA2/home public source CIDRs; null disables all new resources"
  type = object({
    vcn_id            = string
    ga2_sources       = set(string)
    workspace_sources = set(string)
  })
  default = null
  validation {
    condition = var.oci_hub_ingress == null ? true : alltrue([
      for source in setunion(var.oci_hub_ingress.ga2_sources, var.oci_hub_ingress.workspace_sources) :
      can(cidrnetmask(source)) && try(tonumber(split("/", source)[1]) >= 24, false)
    ]) && length(var.oci_hub_ingress.ga2_sources) > 0 && length(var.oci_hub_ingress.workspace_sources) > 0
    error_message = "Provide nonempty approved IPv4 source lists restricted to /24 or smaller."
  }
}
resource "oci_core_network_security_group" "oci_hub" {
  count          = var.oci_hub_ingress == null ? 0 : 1
  compartment_id = var.tenancy_ocid
  vcn_id         = var.oci_hub_ingress.vcn_id
  display_name   = "oci-hub"
}
locals {
  oci_hub_sources = var.oci_hub_ingress == null ? {} : merge(
    { for source in var.oci_hub_ingress.ga2_sources : "users:${source}" => { source = source, port = 51824 } },
    { for source in var.oci_hub_ingress.workspace_sources : "workspaces:${source}" => { source = source, port = 51825 } }
  )
}
resource "oci_core_network_security_group_security_rule" "oci_hub" {
  for_each                  = local.oci_hub_sources
  network_security_group_id = oci_core_network_security_group.oci_hub[0].id
  direction                 = "INGRESS"
  protocol                  = "17"
  source                    = each.value.source
  source_type               = "CIDR_BLOCK"
  udp_options {
    destination_port_range {
      min = each.value.port
      max = each.value.port
    }
  }
}
output "oci_hub_nsg_id" {
  value       = try(oci_core_network_security_group.oci_hub[0].id, null)
  description = "Attach only to the explicitly approved Hub VNIC; existing VNIC membership is not changed automatically"
}
