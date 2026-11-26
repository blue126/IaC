# RouterOS CHR gateway configuration - DRAFT, not applied anywhere.
# Companion to docs/planning/2026-11-17-gateway-routeros-migration.md
#
# Status: written from the 2026-11-17/22 read-only inventory. Verify every
# command against the target RouterOS 7.x version before use (container and
# veth syntax changed across 7.x releases). Rehearse on an isolated test CHR.
#
# Placeholders (never commit real values):
#   <MAC_*>          static lease MAC addresses, copy from `uci show dhcp`
#   <KMS_IMAGE>      vlmcsd image, pinned by digest after review
#
# PVE side (not RouterOS):
#   net0 virtio -> vmbr_wan, MAC cloned from old eth0       => ether1
#   net1 virtio -> vmbr0 (VLAN-aware, trunk: 1u,20,30,40,50) => ether2
#   scsi1       -> data disk for containers (ext4)           => disk1

# ---------------------------------------------------------------- identity
/system identity set name=gateway
/system clock set time-zone-name=Australia/Sydney
/interface ethernet
set [find default-name=ether1] name=ether1-wan
set [find default-name=ether2] name=ether2-trunk

# ---------------------------------------------------------------- bridge / VLANs
# HOME is untagged VLAN 1 on the trunk; other zones are tagged.
# vlan-filtering is enabled last (see end of file) to avoid lockout.
/interface bridge add name=br-lan vlan-filtering=no protocol-mode=none
/interface bridge port add bridge=br-lan interface=ether2-trunk pvid=1
/interface bridge vlan add bridge=br-lan vlan-ids=20,30,40,50 tagged=br-lan,ether2-trunk

/interface vlan
add interface=br-lan vlan-id=20 name=vlan20-remotecc
add interface=br-lan vlan-id=30 name=vlan30-laas
add interface=br-lan vlan-id=40 name=vlan40-guest
add interface=br-lan vlan-id=50 name=vlan50-iot

/interface bridge add name=br-containers protocol-mode=none

/interface list
add name=WAN
add name=HOME
add name=REMOTECC
add name=LAAS
add name=GUEST
add name=IOT
add name=CONTAINERS
/interface list member
add list=WAN interface=ether1-wan
add list=HOME interface=br-lan
add list=REMOTECC interface=vlan20-remotecc
add list=LAAS interface=vlan30-laas
add list=GUEST interface=vlan40-guest
add list=IOT interface=vlan50-iot
add list=CONTAINERS interface=br-containers

# ---------------------------------------------------------------- addressing
/ip address
add interface=br-lan address=192.168.1.1/24 comment=HOME
add interface=vlan20-remotecc address=192.168.20.1/24 comment=REMOTECC
add interface=vlan30-laas address=192.168.30.1/24 comment=LAAS
add interface=vlan40-guest address=192.168.40.1/24 comment=GUEST
add interface=vlan50-iot address=192.168.50.1/24 comment=IOT
add interface=br-containers address=172.17.0.1/24 comment=CONTAINERS

/ip dhcp-client add interface=ether1-wan use-peer-dns=no use-peer-ntp=no add-default-route=yes
# IPv6 stays off for now (old gateway filtered AAAA). Enable deliberately later.
/ipv6 settings set disable-ipv6=yes

# ---------------------------------------------------------------- routes
# Phase 1: OCI hub return path via pve2 on HOME.
/ip route add dst-address=10.236.0.0/16 gateway=192.168.1.52 comment="oci-hub return (phase 1)"
# LaaS: tenants and controllers sit behind the FortiGate (outside 192.168.30.2, fixed).
# RouterOS routes both /18s to it and is the only NAT point for them.
/ip route add dst-address=172.30.0.0/18 gateway=192.168.30.2 comment="laas behind fortigate"
/ip route add dst-address=172.30.64.0/18 gateway=192.168.30.2 comment="laas behind fortigate"
# Phase 3 (REMOTECC VLAN live): replace with
# /ip route set [find comment~"oci-hub"] gateway=192.168.20.52 comment="oci-hub return (remotecc vlan)"

# ---------------------------------------------------------------- DHCP
/ip pool
add name=pool-home ranges=192.168.1.150-192.168.1.246
add name=pool-guest ranges=192.168.40.100-192.168.40.250
add name=pool-iot ranges=192.168.50.100-192.168.50.250
/ip dhcp-server
add name=dhcp-home interface=br-lan address-pool=pool-home lease-time=1d lease-script=dhcp-dns-sync
add name=dhcp-guest interface=vlan40-guest address-pool=pool-guest lease-time=4h
add name=dhcp-iot interface=vlan50-iot address-pool=pool-iot lease-time=1d
/ip dhcp-server network
add address=192.168.1.0/24 gateway=192.168.1.1 dns-server=192.168.1.53 domain=willfan.me ntp-server=192.168.1.1
add address=192.168.40.0/24 gateway=192.168.40.1 dns-server=192.168.1.53
add address=192.168.50.0/24 gateway=192.168.50.1 dns-server=192.168.1.53 ntp-server=192.168.50.1
# REMOTECC and LAAS use static addressing only.

# Static leases: 13 in `uci show dhcp` (2026-11-22). Migrate 11; drop ax3000t-ap1 (.2,
# retired; .2 becomes the N100 PVE host) and qnetd-witness (.53, retired with QDevice).
# MAC values stay out of Git: fill them on the router from the inventory. Example:
# /ip dhcp-server lease add server=dhcp-home mac-address=<MAC_AP> address=192.168.1.3 comment=GL-MT3000

# ---------------------------------------------------------------- DNS
# Clients use AdGuard Home (192.168.1.53) directly; DHCP hands out only .53.
# RouterOS DNS keeps four jobs: its own lookups, DHCP hostnames under willfan.me,
# hosts that hard-code 192.168.1.1, and failover when AdGuard is down.
# Manual records (pve0/pve1/pve2/gateway, ise.ccie.local, _vlmcs._tcp SRV) live in
# AdGuard DNS rewrites, not here. AdGuard upstreams must include:
#   [/willfan.me/]192.168.1.1     and private reverse DNS -> 192.168.1.1
/ip dns set servers=192.168.1.53 allow-remote-requests=yes cache-size=4096KiB
# willfan.me names RouterOS does not know go straight to public DNS, never back to
# AdGuard, which prevents a forwarding loop. Must stay the LAST willfan.me entry.
/ip dns static add name=willfan.me match-subdomain=yes type=FWD forward-to=1.1.1.1 comment="willfan.me catch-all"

# Register HOME DHCP hostnames as <host>.willfan.me (replaces dnsmasq expandhosts),
# inserted before the catch-all so they win.
/system script add name=dhcp-dns-sync policy=read,write source={
    :local domain "willfan.me"
    :local host [:pick $"lease-hostname" 0 63]
    :if ([:len $host] = 0) do={ :return "" }
    :local fqdn ($host . "." . $domain)
    /ip dns static remove [find comment="dhcp" name=$fqdn]
    :if ($leaseBound = "1") do={
        /ip dns static add name=$fqdn address=$leaseActIP ttl=5m comment="dhcp" \
            place-before=[find comment="willfan.me catch-all"]
    }
}

# AdGuard failover for RouterOS itself and for hosts using 192.168.1.1. Clients that
# use .53 directly have no fallback (accepted single point, 2026-11-22 decision).
/tool netwatch add host=192.168.1.53 type=tcp-conn port=53 interval=10s \
    down-script="/ip dns set servers=1.1.1.1,9.9.9.9" \
    up-script="/ip dns set servers=192.168.1.53" comment="adguard failover"

# ---------------------------------------------------------------- containers
# Requires the container package and a one-time confirmation:
#   /system/device-mode/update container=yes   (then hard power-cycle the CHR VM)
/disk set [find slot=disk1] fs=ext4
/container config set registry-url=https://registry-1.docker.io tmpdir=disk1/tmp

/interface veth
# AdGuard sits on HOME (VLAN 1) with its own LAN address so clients reach it directly.
add name=veth-adguard address=192.168.1.53/24 gateway=192.168.1.1
add name=veth-kms address=172.17.0.3/24 gateway=172.17.0.1
/interface bridge port
add bridge=br-lan interface=veth-adguard pvid=1
add bridge=br-containers interface=veth-kms

/container mounts
add name=adguard-conf src=/disk1/adguard/conf dst=/opt/adguardhome/conf
add name=adguard-work src=/disk1/adguard/work dst=/opt/adguardhome/work

# AdGuard Home: copy the old adguardhome.yaml + work/data into /disk1/adguard first;
# set its DNS listener to 0.0.0.0:53, keep the existing DoH upstreams and AAAA policy,
# add [/willfan.me/]192.168.1.1 and private reverse DNS 192.168.1.1, and move the
# old dnsmasq domain records and the _vlmcs._tcp SRV record into DNS rewrites.
/container add remote-image=adguard/adguardhome:v0.107.57 interface=veth-adguard \
    root-dir=disk1/images/adguard mounts=adguard-conf,adguard-work \
    start-on-boot=yes logging=yes hostname=adguard comment=adguard
/container add remote-image=<KMS_IMAGE> interface=veth-kms root-dir=disk1/images/kms \
    start-on-boot=yes logging=yes hostname=kms comment=kms

# ---------------------------------------------------------------- firewall: address lists
/ip firewall address-list
add list=svc-vm address=192.168.1.121 comment="business VM 121 on HOME (xiaozhi, hermes, codex-proxy, cn-proxy)"
add list=pve2 address=192.168.1.52
add list=laas-controller address=172.30.0.2 comment="LaaS controller"
add list=laas-controller address=172.30.100.2 comment="LaaS controller"
add list=laas-nets address=172.30.0.0/18
add list=laas-nets address=172.30.64.0/18
add list=fortigate address=192.168.30.2 comment="FortiGate outside, static"
add list=employee-vnets address=10.236.0.0/16
add list=rfc1918 address=10.0.0.0/8
add list=rfc1918 address=172.16.0.0/12
add list=rfc1918 address=192.168.0.0/16

# ---------------------------------------------------------------- firewall: input
/ip firewall filter
add chain=input action=accept connection-state=established,related,untracked comment="in: established"
add chain=input action=drop connection-state=invalid comment="in: invalid"
add chain=input action=accept protocol=icmp comment="in: icmp"
add chain=input action=accept in-interface-list=HOME comment="in: HOME manages router"
# Includes the FortiGate, which uses 192.168.30.1 for DNS and NTP so VLAN 30 never needs HOME.
add chain=input action=accept protocol=udp dst-port=53,67,123 in-interface-list=!WAN comment="in: dns/dhcp/ntp from internal zones"
add chain=input action=accept protocol=tcp dst-port=53 in-interface-list=!WAN comment="in: dns tcp from internal zones"
add chain=input action=drop log=yes log-prefix="in-drop" comment="in: drop rest"

# ---------------------------------------------------------------- firewall: forward
add chain=forward action=fasttrack-connection connection-state=established,related hw-offload=yes comment="fwd: fasttrack"
add chain=forward action=accept connection-state=established,related,untracked comment="fwd: established"
add chain=forward action=drop connection-state=invalid comment="fwd: invalid"
# Employee VNets arrive on br-lan (HOME) during phase 1, so drop them before the HOME accept.
add chain=forward action=drop log=yes log-prefix="fwd-vnet-internal" src-address-list=employee-vnets dst-address-list=rfc1918 comment="fwd: employee vnets to internal"
add chain=forward action=drop log=yes log-prefix="fwd-home-laas" in-interface-list=HOME dst-address-list=laas-nets comment="fwd: HOME may not open connections to LaaS"
add chain=forward action=accept in-interface-list=HOME comment="fwd: HOME to anywhere"
# Business VM is on HOME; clients connect to 192.168.1.121 directly (no .1 port forwards).
add chain=forward action=accept in-interface-list=IOT dst-address-list=svc-vm protocol=tcp dst-port=8000,8003,1883,8007 comment="fwd: IOT to xiaozhi tcp"
add chain=forward action=accept in-interface-list=IOT dst-address-list=svc-vm protocol=udp dst-port=8884 comment="fwd: IOT to xiaozhi udp"
add chain=forward action=accept dst-address=192.168.1.53 protocol=udp dst-port=53 in-interface-list=GUEST comment="fwd: GUEST dns udp to AdGuard"
add chain=forward action=accept dst-address=192.168.1.53 protocol=tcp dst-port=53 in-interface-list=GUEST comment="fwd: GUEST dns tcp to AdGuard"
add chain=forward action=accept dst-address=192.168.1.53 protocol=udp dst-port=53 in-interface-list=IOT comment="fwd: IOT dns udp to AdGuard"
add chain=forward action=accept dst-address=192.168.1.53 protocol=tcp dst-port=53 in-interface-list=IOT comment="fwd: IOT dns tcp to AdGuard"
add chain=forward action=accept in-interface=vlan30-laas src-address-list=laas-controller dst-address-list=pve2 protocol=tcp dst-port=8006 comment="fwd: LaaS controllers to pve2 API (only exception into HOME)"
add chain=forward action=drop log=yes log-prefix="fwd-to-internal" dst-address-list=rfc1918 in-interface-list=!HOME comment="fwd: non-HOME zones to any internal net"
add chain=forward action=accept out-interface-list=WAN comment="fwd: internal zones to internet"
add chain=forward action=drop log=yes log-prefix="fwd-drop" comment="fwd: drop rest"

# ---------------------------------------------------------------- NAT
/ip firewall nat
add chain=srcnat action=masquerade out-interface-list=WAN comment="masquerade (covers employee vnets and LaaS 172.30.0.0/18, 172.30.64.0/18)"
add chain=dstnat action=dst-nat dst-address=192.168.1.1 protocol=tcp dst-port=1688 in-interface-list=HOME to-addresses=172.17.0.3 comment="kms (HOME)"

# ---------------------------------------------------------------- services
/ip upnp set enabled=yes
/ip upnp interfaces
add interface=ether1-wan type=external
add interface=br-lan type=internal
/system ntp client set enabled=yes servers=0.pool.ntp.org,1.pool.ntp.org
/system ntp server set enabled=yes

# Hardening: management only from HOME.
/ip service
set telnet disabled=yes
set ftp disabled=yes
set www disabled=yes
set api disabled=yes
set api-ssl disabled=yes
set ssh address=192.168.1.0/24
set winbox address=192.168.1.0/24
set www-ssl address=192.168.1.0/24
/ip neighbor discovery-settings set discover-interface-list=HOME
/tool mac-server set allowed-interface-list=HOME
/tool mac-server mac-winbox set allowed-interface-list=HOME
/ip ssh set strong-crypto=yes

# ---------------------------------------------------------------- enable VLAN filtering last
# Only after confirming management access still works on untagged VLAN 1.
/interface bridge set br-lan vlan-filtering=yes
