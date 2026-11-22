# LaaS isolated SDN network on pve2 (standalone PVE 9.2).
#
# Long-lived network slots for PNETLab VMs cloned from template VM250. LaaS
# creates and removes the test VMs itself; only the network lives here. The
# zone is separate from the hand-built `ocihub` zone on the same node, which
# is not managed by Terraform and must stay untouched.
#
# Zone `laas`: simple zone, PVE IPAM, dnsmasq DHCP, no uplink (nothing is
# bridged to vmbr0), SNAT disabled on every subnet.
#
# | VNet   | Tenant | Use        | CIDR            | Gateway (host) | DHCP range                  |
# |--------|--------|------------|-----------------|----------------|-----------------------------|
# | laasam | A      | management | 10.240.10.0/24  | 10.240.10.1    | 10.240.10.100-10.240.10.199 |
# | laasal | A      | lab        | 10.240.11.0/24  | none           | none                        |
# | laasbm | B      | management | 10.240.20.0/24  | 10.240.20.1    | 10.240.20.100-10.240.20.199 |
# | laasbl | B      | lab        | 10.240.21.0/24  | none           | none                        |
#
# Only management subnets carry a gateway, because PVE's dnsmasq serves DHCP
# from the gateway address on the VNet bridge. That address lives on pve2
# itself; pve2 has net.ipv4.ip_forward=1 and no laas-specific firewall rules,
# so the zone does not by itself block routed traffic between the management
# VNets or towards pve2. LaaS connectivity tests must cover that path.
#
# Prerequisite outside Terraform: the dnsmasq package must be installed on
# pve2 (with its default service disabled) before DHCP can work.

locals {
  laas_sdn_vnet_aliases = {
    laasam = "laas tenant A management"
    laasal = "laas tenant A lab"
    laasbm = "laas tenant B management"
    laasbl = "laas tenant B lab"
  }
}

resource "proxmox_sdn_zone_simple" "laas" {
  provider = proxmox.pve2

  id    = "laas"
  nodes = ["pve2"]
  ipam  = "pve"
  dhcp  = "dnsmasq"
}

resource "proxmox_sdn_vnet" "laas" {
  provider = proxmox.pve2
  for_each = local.laas_sdn_vnet_aliases

  id    = each.key
  zone  = proxmox_sdn_zone_simple.laas.id
  alias = each.value
}

resource "proxmox_sdn_subnet" "laasam" {
  provider = proxmox.pve2

  vnet    = proxmox_sdn_vnet.laas["laasam"].id
  cidr    = "10.240.10.0/24"
  gateway = "10.240.10.1"
  snat    = false

  dhcp_range = {
    start_address = "10.240.10.100"
    end_address   = "10.240.10.199"
  }
}

resource "proxmox_sdn_subnet" "laasal" {
  provider = proxmox.pve2

  vnet = proxmox_sdn_vnet.laas["laasal"].id
  cidr = "10.240.11.0/24"
  snat = false
}

resource "proxmox_sdn_subnet" "laasbm" {
  provider = proxmox.pve2

  vnet    = proxmox_sdn_vnet.laas["laasbm"].id
  cidr    = "10.240.20.0/24"
  gateway = "10.240.20.1"
  snat    = false

  dhcp_range = {
    start_address = "10.240.20.100"
    end_address   = "10.240.20.199"
  }
}

resource "proxmox_sdn_subnet" "laasbl" {
  provider = proxmox.pve2

  vnet = proxmox_sdn_vnet.laas["laasbl"].id
  cidr = "10.240.21.0/24"
  snat = false
}

# PVE stages SDN edits as pending until a cluster-wide SDN apply. This applies
# all pending SDN configuration on pve2, so confirm nothing else is pending
# (`pvesh get /cluster/sdn/zones --pending 1`) before applying.
resource "proxmox_sdn_applier" "laas" {
  provider = proxmox.pve2

  depends_on = [
    proxmox_sdn_zone_simple.laas,
    proxmox_sdn_vnet.laas,
    proxmox_sdn_subnet.laasam,
    proxmox_sdn_subnet.laasal,
    proxmox_sdn_subnet.laasbm,
    proxmox_sdn_subnet.laasbl,
  ]

  lifecycle {
    replace_triggered_by = [
      proxmox_sdn_zone_simple.laas,
      proxmox_sdn_vnet.laas["laasam"],
      proxmox_sdn_vnet.laas["laasal"],
      proxmox_sdn_vnet.laas["laasbm"],
      proxmox_sdn_vnet.laas["laasbl"],
      proxmox_sdn_subnet.laasam,
      proxmox_sdn_subnet.laasal,
      proxmox_sdn_subnet.laasbm,
      proxmox_sdn_subnet.laasbl,
    ]
  }
}
