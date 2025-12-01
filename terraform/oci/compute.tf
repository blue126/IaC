resource "oci_core_instance" "oracle_cloud_ubuntu2404" {
  availability_domain = "clRZ:AP-SYDNEY-1-AD-1"
  compartment_id      = var.tenancy_ocid
  display_name        = "oracle-cloud-ubuntu2404"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    memory_in_gbs = 24
    ocpus         = 4
  }

  source_details {
    source_id   = "ocid1.image.oc1.ap-sydney-1.aaaaaaaay46dnss2xv46ueh6osq5q6u33h5bateig3az4e6eo24ru2vb4zea"
    source_type = "image"
    boot_volume_size_in_gbs = 200
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key)
  }

  create_vnic_details {
    assign_public_ip = true
    subnet_id        = "ocid1.subnet.oc1.ap-sydney-1.aaaaaaaal2432iozkhc324kjnrlxfmtoa5dz7v37m62xlkceb5lypbp3kbmq"
  }

  lifecycle {
    ignore_changes = [metadata, defined_tags, freeform_tags, create_vnic_details[0].defined_tags]
  }
}
