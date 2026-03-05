# Network Security Group for unified-proxy (HTTP/HTTPS ingress)
# This NSG is attached to the OCI instance's VNIC (see compute.tf).
# OCI Security List rules (port 80/443) must also be open in the VCN console
# if the subnet uses a default security list — NSGs are evaluated in addition to,
# not instead of, security lists.

data "oci_core_subnet" "main" {
  subnet_id = "ocid1.subnet.oc1.ap-sydney-1.aaaaaaaal2432iozkhc324kjnrlxfmtoa5dz7v37m62xlkceb5lypbp3kbmq"
}

resource "oci_core_network_security_group" "unified_proxy" {
  compartment_id = var.tenancy_ocid
  vcn_id         = data.oci_core_subnet.main.vcn_id
  display_name   = "unified-proxy-nsg"
}

resource "oci_core_network_security_group_security_rule" "allow_http" {
  network_security_group_id = oci_core_network_security_group.unified_proxy.id
  direction                 = "INGRESS"
  protocol                  = "6" # TCP

  source      = "0.0.0.0/0"
  source_type = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

resource "oci_core_network_security_group_security_rule" "allow_https" {
  network_security_group_id = oci_core_network_security_group.unified_proxy.id
  direction                 = "INGRESS"
  protocol                  = "6" # TCP

  source      = "0.0.0.0/0"
  source_type = "CIDR_BLOCK"

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

output "unified_proxy_nsg_id" {
  value       = oci_core_network_security_group.unified_proxy.id
  description = "NSG ID for unified-proxy (attached to oracle-cloud-ubuntu2404 VNIC)"
}
