variable "tenancy_ocid" {
  description = "OCI tenancy OCID; also used as the compartment for resources"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the OCI API user"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the OCI API signing key"
  type        = string
}

variable "private_key_path" {
  description = "Local path to the OCI API signing private key"
  type        = string
}

variable "region" {
  description = "OCI region identifier, e.g. ap-sydney-1"
  type        = string
}

variable "ssh_public_key" {
  description = "Local path to the SSH public key injected into instances"
  type        = string
}
