mock_provider "oci" {}

run "reuse_attached_group_without_modifying_vnic" {
  command = plan
  variables {
    oci_hub_ingress = {
      vcn_id            = "ocid1.vcn.oc1..synthetic"
      existing_nsg_id   = "ocid1.networksecuritygroup.oc1..attached"
      device_sources    = ["192.0.2.2/32"]
      workspace_sources = ["198.51.100.2/32"]
    }
  }
  assert {
    condition     = length(oci_core_network_security_group.oci_hub) == 0 && alltrue([for rule in oci_core_network_security_group_security_rule.oci_hub : rule.network_security_group_id == "ocid1.networksecuritygroup.oc1..attached"])
    error_message = "Existing Hub ingress must add only scoped rules to the attached NSG."
  }
}

variables {
  tenancy_ocid = "ocid1.tenancy.oc1..synthetic"
}

run "direct_devices_use_only_the_wireguard_user_port" {
  command = plan
  variables {
    oci_hub_ingress = {
      vcn_id            = "ocid1.vcn.oc1..synthetic"
      device_sources    = ["192.0.2.2/32"]
      workspace_sources = ["198.51.100.2/32"]
    }
  }
  assert {
    condition     = length(oci_core_network_security_group_security_rule.oci_hub) == 2
    error_message = "Only the approved device and workspace WG ingress rules should be created."
  }
  assert {
    condition     = one(oci_core_network_security_group_security_rule.oci_hub["users:192.0.2.2/32"].udp_options).destination_port_range[0].min == 51824
    error_message = "Direct client ingress must use the same user WireGuard port, without public Mosh ports."
  }
}

run "legacy_ga_sources_preserve_resource_addresses" {
  command = plan
  variables {
    oci_hub_ingress = {
      vcn_id            = "ocid1.vcn.oc1..synthetic"
      ga2_sources       = ["192.0.2.2/32"]
      workspace_sources = ["198.51.100.2/32"]
    }
  }
  assert {
    condition     = contains(keys(oci_core_network_security_group_security_rule.oci_hub), "users:192.0.2.2/32")
    error_message = "Legacy source rule addresses must remain stable."
  }
}

run "ambiguous_ingress_rejected" {
  command = plan
  variables {
    oci_hub_ingress = {
      vcn_id            = "ocid1.vcn.oc1..synthetic"
      ga2_sources       = ["192.0.2.2/32"]
      device_sources    = ["192.0.2.3/32"]
      workspace_sources = ["198.51.100.2/32"]
    }
  }
  expect_failures = [var.oci_hub_ingress]
}

run "broad_direct_ingress_rejected" {
  command = plan
  variables {
    oci_hub_ingress = {
      vcn_id            = "ocid1.vcn.oc1..synthetic"
      device_sources    = ["0.0.0.0/0"]
      workspace_sources = ["198.51.100.2/32"]
    }
  }
  expect_failures = [var.oci_hub_ingress]
}

run "dynamic_users_only_open_the_user_wireguard_port" {
 command = plan
 variables {
  oci_hub_ingress = {
   vcn_id = "ocid1.vcn.oc1..synthetic"
   device_ingress_mode = "dynamic"
   device_sources = ["0.0.0.0/0"]
   workspace_sources = ["198.51.100.2/32"]
  }
 }
 assert {
  condition = length(oci_core_network_security_group_security_rule.oci_hub) == 2 && one(oci_core_network_security_group_security_rule.oci_hub["users:0.0.0.0/0"].udp_options).destination_port_range[0].min == 51824
  error_message = "Dynamic source mode may open only UDP 51824; workspace ingress remains narrow."
 }
}
run "dynamic_does_not_allow_broad_workspace_sources" {
 command = plan
 variables {
  oci_hub_ingress = {
   vcn_id = "ocid1.vcn.oc1..synthetic"
   device_ingress_mode = "dynamic"
   device_sources = ["0.0.0.0/0"]
   workspace_sources = ["0.0.0.0/0"]
  }
 }
 expect_failures = [var.oci_hub_ingress]
}
