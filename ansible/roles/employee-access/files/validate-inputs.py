#!/usr/bin/env python3
"""Reject inconsistent or injectable access inventory before rendering policy."""
import base64
import binascii
import struct
import ipaddress
import json
import re
import sys


def require(value, message):
    if not value:
        raise ValueError(message)


def public_key(text):
    require(isinstance(text, str) and re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]*)?', text), 'Require a single-line Ed25519 public key')
    encoded = text.split()[1]
    try:
        wire = base64.b64decode(encoded, validate=True)
        require(base64.b64encode(wire).decode() == encoded, 'Noncanonical SSH key encoding')
        offset, fields = 0, []
        for _ in range(2):
            require(offset + 4 <= len(wire), 'Truncated SSH key length')
            size = struct.unpack('!I', wire[offset:offset + 4])[0]
            offset += 4
            require(offset + size <= len(wire), 'Truncated SSH key field')
            fields.append(wire[offset:offset + size])
            offset += size
        require(offset == len(wire) and fields[0] == b'ssh-ed25519' and len(fields[1]) == 32, 'Invalid SSH key type or wire structure')
    except (binascii.Error, struct.error) as exc:
        raise ValueError('Invalid SSH key encoding') from exc


def validate(config):
    networks = config['networks']
    devices = config['devices']
    require(0 < len(networks) <= 10, 'Expected one to ten single-node workspaces')
    wg = ipaddress.IPv4Interface(config['wireguard_address'])
    uplink = ipaddress.IPv4Interface(config['uplink_address'])
    uplink_gateway = ipaddress.IPv4Address(config['uplink_gateway'])
    require(uplink_gateway in uplink.network and uplink_gateway not in (uplink.ip, uplink.network.network_address, uplink.network.broadcast_address), 'Invalid uplink gateway')
    dns = ipaddress.IPv4Address(config['dns_server'])
    require(dns.is_global and not dns.is_multicast, 'Use an explicit public DNS resolver; no implicit internal DNS exception')
    require(not wg.network.overlaps(uplink.network), 'Overlapping WireGuard/uplink networks')
    subnets = [wg.network, uplink.network]
    uplink_mac = config['uplink_mac'].lower()
    require(re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', uplink_mac) and int(uplink_mac[:2], 16) & 1 == 0, 'Invalid uplink MAC')
    macs, bridges, vmids, addresses = {uplink_mac}, set(), {int(config['gateway_vmid'])}, set()
    require(config['maintenance_sources'] and config['home_public_ipv4'], 'Maintenance and public hairpin targets are mandatory')
    for cidr in config['maintenance_sources']:
        network = ipaddress.IPv4Network(cidr)
        require(network.prefixlen >= 24, 'Maintenance sources must be narrow explicit IPv4 ranges')
        require(not network.overlaps(wg.network), 'Employee devices cannot be maintenance sources')
    for cidr in config['protected_ipv4'] + config['home_public_ipv4']:
        ipaddress.IPv4Network(cidr)
    for cidr in config['home_public_ipv4']:
        require(ipaddress.IPv4Network(cidr).prefixlen == 32, 'Enumerate all current public hairpin IPv4 addresses as /32')
    require(sorted(net['nic_slot'] for net in networks.values()) == list(range(1, len(networks) + 1)), 'Require unique contiguous permanent NIC slots')
    for employee, net in sorted(networks.items()):
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,19}', employee), 'Invalid employee ID')
        require(type(net['disabled']) is bool, 'Disabled must be a boolean')
        require(re.fullmatch(r'vmbr[0-9]+', net['bridge']), 'Invalid bridge')
        require(type(net['nic_slot']) is int and net['interface'] == f"emp{net['nic_slot'] - 1}" and net['gateway_nic'] == net['nic_slot'], 'Unexpected gateway NIC mapping')
        require(net['bridge'] not in bridges, 'Shared employee bridge')
        bridges.add(net['bridge'])
        require(type(net['vmid']) is int and 100 <= net['vmid'] <= 999999999 and net['vmid'] not in vmids, 'Invalid or duplicate VMID')
        vmids.add(net['vmid'])
        address = ipaddress.IPv4Interface(net['address'])
        gateway = ipaddress.IPv4Interface(net['gateway_address'])
        require(str(address.ip) == net['ip'] and str(gateway.ip) == net['gateway'], 'Address mismatch')
        require(address.network == gateway.network and address.ip != gateway.ip, 'Invalid gateway subnet')
        require(address.network.prefixlen in range(24, 31), 'Use /24 to /30 employee subnets')
        require(address.ip not in (address.network.network_address, address.network.broadcast_address) and gateway.ip not in (address.network.network_address, address.network.broadcast_address), 'Invalid host address')
        require(not any(address.network.overlaps(other) for other in subnets), 'Overlapping employee/uplink/WireGuard subnets')
        require(not any(address.network.overlaps(ipaddress.IPv4Network(source)) for source in config['maintenance_sources']), 'Employee subnet cannot be a maintenance source')
        subnets.append(address.network)
        for field in ('mac_address', 'gateway_mac'):
            mac = net[field].lower()
            require(re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', mac) and mac not in macs and int(mac[:2], 16) & 1 == 0, 'Invalid/duplicate/multicast MAC')
            macs.add(mac)
        if config.get('require_host_keys', True) or employee in config.get('host_keys', {}):
            public_key(config['host_keys'][employee])
    for name, device in devices.items():
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,27}', name), 'Invalid device account')
        require(device['employee'] in networks and type(device['enabled']) is bool, 'Invalid device assignment/state')
        address = ipaddress.IPv4Address(device['address'])
        require(address in wg.network and address not in (wg.ip, wg.network.network_address, wg.network.broadcast_address) and address not in addresses, 'Invalid/duplicate device address')
        addresses.add(address)
        public_key(device['ssh_public_key'])
        require(re.fullmatch(r'[A-Za-z0-9+/]{43}=', device['wireguard_public_key']), 'Invalid WireGuard public key')
        raw_key = base64.b64decode(device['wireguard_public_key'], validate=True)
        require(len(raw_key) == 32 and raw_key != bytes(32) and base64.b64encode(raw_key).decode() == device['wireguard_public_key'], 'Invalid WireGuard key encoding')
    require(len({d['ssh_public_key'].split()[1] for d in devices.values()}) == len(devices), 'Device SSH keys must be unique')
    require(len({d['wireguard_public_key'] for d in devices.values()}) == len(devices), 'WireGuard public keys must be unique')


if __name__ == '__main__':
    try:
        validate(json.load(sys.stdin))
    except (ValueError, KeyError, TypeError) as exc:
        print('Invalid employee inventory: ' + str(exc), file=sys.stderr)
        sys.exit(1)
