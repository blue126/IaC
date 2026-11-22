# RouterOS CHR gateway configuration - DRAFT, not applied anywhere.
# Companion to docs/planning/2026-11-17-gateway-routeros-migration.md
#
# Status: written from the 2026-11-17/22 read-only inventory. Verify every
# command against the target RouterOS 7.x version before use (container and
# veth syntax changed across 7.x releases). Rehearse on an isolated test CHR.
#
# Placeholders (never commit real values):
#   <TS_AUTHKEY>     Tailscale auth key, enter on the router only
#   <MAC_*>          static lease MAC addresses, copy from `uci show dhcp`
#   <KMS_IMAGE>      vlmcsd image, pinned by digest after review
#
# PVE side (not RouterOS):
#   net0 virtio -> vmbr_wan, MAC cloned from old eth0       => ether1
#   net1 virtio -> vmbr0 (VLAN-aware, trunk: 1u,20,30,40,50) => ether2
#   net2 virtio -> vmbr_svc (internal, business VM)          => ether3
#   scsi1       -> data disk for containers (ext4)           => disk1

# ---------------------------------------------------------------- identity
/system identity set name=gateway
/system clock set time-zone-name=Australia/Sydney
/interface ethernet
set [find default-name=ether1] name=ether1-wan
set [find default-name=ether2] name=ether2-trunk
set [find default-name=ether3] name=ether3-svc

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
add name=SVC
add name=CONTAINERS
/interface list member
add list=WAN interface=ether1-wan
add list=HOME interface=br-lan
add list=REMOTECC interface=vlan20-remotecc
add list=LAAS interface=vlan30-laas
add list=GUEST interface=vlan40-guest
add list=IOT interface=vlan50-iot
add list=SVC interface=ether3-svc
add list=CONTAINERS interface=br-containers

# ---------------------------------------------------------------- addressing
/ip address
add interface=br-lan address=192.168.1.1/24 comment=HOME
add interface=vlan20-remotecc address=192.168.20.1/24 comment=REMOTECC
add interface=vlan30-laas address=192.168.30.1/24 comment=LAAS
add interface=vlan40-guest address=192.168.40.1/24 comment=GUEST
add interface=vlan50-iot address=192.168.50.1/24 comment=IOT
add interface=ether3-svc address=192.168.10.1/24 comment=SVC
add interface=br-containers address=172.17.0.1/24 comment=CONTAINERS

/ip dhcp-client add interface=ether1-wan use-peer-dns=no use-peer-ntp=no add-default-route=yes
# IPv6 stays off for now (old gateway filtered AAAA). Enable deliberately later.
/ipv6 settings set disable-ipv6=yes

# ---------------------------------------------------------------- routes
# Phase 1: OCI hub return path via pve2 on HOME.
/ip route add dst-address=10.236.0.0/16 gateway=192.168.1.52 comment="oci-hub return (phase 1)"
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
add address=192.168.1.0/24 gateway=192.168.1.1 dns-server=192.168.1.1 domain=willfan.me ntp-server=192.168.1.1
add address=192.168.40.0/24 gateway=192.168.40.1 dns-server=192.168.40.1
add address=192.168.50.0/24 gateway=192.168.50.1 dns-server=192.168.50.1 ntp-server=192.168.50.1
# REMOTECC, LAAS and SVC use static addressing only.

# Static leases: migrate the 11 live entries from `uci show dhcp` (12 minus
# the retired ax3000t-ap1). Example:
# /ip dhcp-server lease add server=dhcp-home mac-address=<MAC_AP> address=192.168.1.3 comment=GL-MT3000

# ---------------------------------------------------------------- DNS
# Clients -> RouterOS DNS (cache + local names) -> AdGuard Home container.
/ip dns set servers=172.17.0.2 allow-remote-requests=yes cache-size=4096KiB
# Local names previously served by dnsmasq (expandhosts, domain willfan.me):
# /ip dns static add name=pve0.willfan.me address=192.168.1.50

# Register HOME DHCP hostnames as <host>.willfan.me (replaces dnsmasq expandhosts).
/system script add name=dhcp-dns-sync policy=read,write source={
    :local domain "willfan.me"
    :local host [:pick $"lease-hostname" 0 63]
    :if ([:len $host] = 0) do={ :return "" }
    :local fqdn ($host . "." . $domain)
    /ip dns static remove [find comment="dhcp" name=$fqdn]
    :if ($leaseBound = "1") do={
        /ip dns static add name=$fqdn address=$leaseActIP ttl=5m comment="dhcp"
    }
}

# AdGuard Home failover: fall back to public resolvers when the container stops answering.
/tool netwatch add host=172.17.0.2 type=tcp-conn port=53 interval=10s \
    down-script="/ip dns set servers=1.1.1.1,9.9.9.9" \
    up-script="/ip dns set servers=172.17.0.2" comment="adguard failover"

# ---------------------------------------------------------------- containers
# Requires the container package and a one-time confirmation:
#   /system/device-mode/update container=yes   (then hard power-cycle the CHR VM)
/disk set [find slot=disk1] fs=ext4
/container config set registry-url=https://registry-1.docker.io tmpdir=disk1/tmp

/interface veth
add name=veth-adguard address=172.17.0.2/24 gateway=172.17.0.1
add name=veth-kms address=172.17.0.3/24 gateway=172.17.0.1
add name=veth-tailscale address=172.17.0.4/24 gateway=172.17.0.1
/interface bridge port
add bridge=br-containers interface=veth-adguard
add bridge=br-containers interface=veth-kms
add bridge=br-containers interface=veth-tailscale

/container mounts
add name=adguard-conf src=/disk1/adguard/conf dst=/opt/adguardhome/conf
add name=adguard-work src=/disk1/adguard/work dst=/opt/adguardhome/work
add name=tailscale-state src=/disk1/tailscale dst=/var/lib/tailscale

# AdGuard Home: copy the old adguardhome.yaml + work/data into /disk1/adguard first;
# set its DNS listener to 0.0.0.0:53 and keep the existing upstreams and AAAA policy.
/container add remote-image=adguard/adguardhome:v0.107.57 interface=veth-adguard \
    root-dir=disk1/images/adguard mounts=adguard-conf,adguard-work \
    start-on-boot=yes logging=yes hostname=adguard comment=adguard
/container add remote-image=<KMS_IMAGE> interface=veth-kms root-dir=disk1/images/kms \
    start-on-boot=yes logging=yes hostname=kms comment=kms
# Tailscale in userspace mode (no /dev/net/tun needed). Confirm the routes the old
# gateway advertised before filling TS_ROUTES.
/container envs
add name=tailscale key=TS_AUTHKEY value=<TS_AUTHKEY>
add name=tailscale key=TS_STATE_DIR value=/var/lib/tailscale
add name=tailscale key=TS_USERSPACE value=true
add name=tailscale key=TS_HOSTNAME value=gateway
add name=tailscale key=TS_ROUTES value=192.168.1.0/24
/container add remote-image=tailscale/tailscale:stable interface=veth-tailscale \
    root-dir=disk1/images/tailscale mounts=tailscale-state envs=tailscale \
    start-on-boot=yes logging=yes hostname=gateway-ts comment=tailscale

# ---------------------------------------------------------------- firewall: address lists
/ip firewall address-list
add list=svc-vm address=192.168.10.10 comment="business VM (xiaozhi, hermes, codex-proxy, cn-proxy)"
add list=pve2 address=192.168.1.52
add list=laas-controller address=192.168.30.10 comment="placeholder, set at LaaS M0"
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
add chain=input action=accept protocol=udp dst-port=53,67,123 in-interface-list=!WAN comment="in: dns/dhcp/ntp from internal zones"
add chain=input action=accept protocol=tcp dst-port=53 in-interface-list=!WAN comment="in: dns tcp from internal zones"
add chain=input action=drop log=yes log-prefix="in-drop" comment="in: drop rest"

# ---------------------------------------------------------------- firewall: forward
add chain=forward action=fasttrack-connection connection-state=established,related hw-offload=yes comment="fwd: fasttrack"
add chain=forward action=accept connection-state=established,related,untracked comment="fwd: established"
add chain=forward action=drop connection-state=invalid comment="fwd: invalid"
# Employee VNets arrive on br-lan (HOME) during phase 1, so drop them before the HOME accept.
add chain=forward action=drop log=yes log-prefix="fwd-vnet-internal" src-address-list=employee-vnets dst-address-list=rfc1918 comment="fwd: employee vnets to internal"
add chain=forward action=accept in-interface-list=HOME comment="fwd: HOME to anywhere"
add chain=forward action=accept connection-nat-state=dstnat in-interface-list=IOT dst-address-list=svc-vm comment="fwd: IOT to xiaozhi ports"
add chain=forward action=accept src-address-list=laas-controller dst-address-list=pve2 protocol=tcp dst-port=8006 comment="fwd: LaaS controller to pve2 API"
add chain=forward action=accept in-interface=br-containers src-address=172.17.0.4 dst-address=192.168.1.0/24 comment="fwd: tailscale subnet router to HOME"
add chain=forward action=drop log=yes log-prefix="fwd-to-internal" dst-address-list=rfc1918 in-interface-list=!HOME comment="fwd: non-HOME zones to any internal net"
add chain=forward action=accept out-interface-list=WAN comment="fwd: internal zones to internet"
add chain=forward action=drop log=yes log-prefix="fwd-drop" comment="fwd: drop rest"

# ---------------------------------------------------------------- NAT
/ip firewall nat
add chain=srcnat action=masquerade out-interface-list=WAN comment="masquerade (covers employee vnets)"
# Keep clients and ESP32 devices pointed at 192.168.1.1; forward to the business VM.
# Only HOME and IOT may use these; nothing is published on WAN.
add chain=dstnat action=dst-nat dst-address=192.168.1.1 protocol=tcp dst-port=8000,8002,8003,8642,9900,9119,8787,1883,8007,7890 in-interface-list=HOME to-addresses=192.168.10.10 comment="svc-vm (HOME)"
add chain=dstnat action=dst-nat dst-address=192.168.1.1 protocol=udp dst-port=8884 in-interface-list=HOME to-addresses=192.168.10.10 comment="svc-vm mqtt udp (HOME)"
add chain=dstnat action=dst-nat dst-address=192.168.1.1 protocol=tcp dst-port=8000,8003,1883,8007 in-interface-list=IOT to-addresses=192.168.10.10 comment="xiaozhi (IOT)"
add chain=dstnat action=dst-nat dst-address=192.168.1.1 protocol=udp dst-port=8884 in-interface-list=IOT to-addresses=192.168.10.10 comment="xiaozhi udp (IOT)"
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
