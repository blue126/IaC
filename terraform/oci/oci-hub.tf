variable "oci_hub_ingress" {
  description = "Explicit Hub VCN and approved direct-device or GA2/home source CIDRs; null disables new resources"
  type = object({
    vcn_id              = string
    existing_nsg_id     = optional(string)
    ga2_sources         = optional(set(string), [])
    device_sources      = optional(set(string), [])
    device_ingress_mode = optional(string, "restricted")
    workspace_sources   = set(string)
  })
  default = null
  validation {
    condition = var.oci_hub_ingress == null ? true : (
      contains(["restricted", "dynamic"], var.oci_hub_ingress.device_ingress_mode) &&
      length(var.oci_hub_ingress.workspace_sources) > 0 && alltrue([
        for source in var.oci_hub_ingress.workspace_sources : can(cidrnetmask(source)) && try(tonumber(split("/", source)[1]) >= 24, false)
        ]) && (var.oci_hub_ingress.device_ingress_mode == "dynamic" ? (
        length(var.oci_hub_ingress.ga2_sources) == 0 && var.oci_hub_ingress.device_sources == toset(["0.0.0.0/0"])
        ) : (
        alltrue([for source in setunion(var.oci_hub_ingress.ga2_sources, var.oci_hub_ingress.device_sources) : can(cidrnetmask(source)) && try(tonumber(split("/", source)[1]) >= 24, false)]) &&
        ((length(var.oci_hub_ingress.ga2_sources) > 0) != (length(var.oci_hub_ingress.device_sources) > 0))
      ))
    )
    error_message = "Dynamic mode permits only direct IPv4 WireGuard users; workspace/GA sources remain restricted, and restricted mode requires explicit narrow sources."
  }
}
resource "oci_core_network_security_group" "oci_hub" {
  count          = var.oci_hub_ingress == null ? 0 : (var.oci_hub_ingress.existing_nsg_id == null ? 1 : 0)
  compartment_id = var.tenancy_ocid
  vcn_id         = var.oci_hub_ingress.vcn_id
  display_name   = "oci-hub"
}
locals {
  oci_hub_sources = var.oci_hub_ingress == null ? {} : merge(
    { for source in setunion(var.oci_hub_ingress.ga2_sources, var.oci_hub_ingress.device_sources) : "users:${source}" => { source = source, port = 51824 } },
    { for source in var.oci_hub_ingress.workspace_sources : "workspaces:${source}" => { source = source, port = 51825 } }
  )
}
resource "oci_core_network_security_group_security_rule" "oci_hub" {
  for_each                  = local.oci_hub_sources
  network_security_group_id = var.oci_hub_ingress.existing_nsg_id != null ? var.oci_hub_ingress.existing_nsg_id : oci_core_network_security_group.oci_hub[0].id
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
  value       = var.oci_hub_ingress == null ? null : (var.oci_hub_ingress.existing_nsg_id != null ? var.oci_hub_ingress.existing_nsg_id : oci_core_network_security_group.oci_hub[0].id)
  description = "Attach only to the explicitly approved Hub VNIC; existing VNIC membership is not changed automatically"
}
