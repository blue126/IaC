#!/usr/bin/env python3
"""Scoped nftables boundary and exact live-policy startup verification."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def token(value):
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,32}', value):
        raise ValueError('invalid interface identifier')
    return value


def ip(value):
    return str(ipaddress.IPv4Address(value))


def net(value):
    return str(ipaddress.IPv4Network(value, strict=True))


def validate(c):
    if c['profile'] != 'oci-hub' or c['kind'] not in ('pve', 'hub') or not isinstance(c['generation'], int) or c['generation'] < 1:
        raise ValueError('invalid policy identity')
    if c['kind'] == 'pve':
        net(c['aggregate'])
        ip(c['endpoint'])
        token(c['uplink'])
        if len({v['vmid'] for v in c['workspaces']}) != len(c['workspaces']) or len({v['vnet'] for v in c['workspaces']}) != len(c['workspaces']):
            raise ValueError('duplicate allocation')
        networks = []
        for v in c['workspaces']:
            if type(v['vmid']) is not int or v['vmid'] < 100 or v['vmid'] == 500:
                raise ValueError('unmanaged VMID')
            token(v['vnet'])
            if not re.fullmatch(r'oh[a-z0-9]{1,6}', v['vnet']):
                raise ValueError('unmanaged VNet')
            n = ipaddress.IPv4Network(v['subnet'])
            if not n.subnet_of(ipaddress.IPv4Network(c['aggregate'])) or n.prefixlen != 30:
                raise ValueError('workspace outside aggregate or not /30')
            if any(n.overlaps(other) for other in networks):
                raise ValueError('overlapping workspace')
            networks.append(n)
            if ipaddress.IPv4Address(v['address']) not in n or ipaddress.IPv4Address(v['gateway']) not in n or v['address'] == v['gateway']:
                raise ValueError('invalid workspace address')
            if not re.fullmatch(r'(?:[a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2}', v['mac']):
                raise ValueError('invalid MAC')
        for network in c['protected'] + c['development_destinations']:
            net(network)
        if not c['protected']:
            raise ValueError('explicit protected destinations required')
        access=c.get('management_access',[])
        if not isinstance(access,list):raise ValueError('management access must be an explicit list')
        seen=set()
        for entry in access:
            if set(entry)!={'source','vmid'} or type(entry['vmid']) is not int or entry['vmid'] not in {v['vmid'] for v in c['workspaces']}:
                raise ValueError('management target must be an allocated workspace')
            source=ipaddress.IPv4Network(entry['source'],strict=True)
            if source.prefixlen!=32 or source.network_address.is_unspecified or source.network_address.is_multicast or source.network_address.is_loopback or source.network_address.is_link_local or source.network_address in ipaddress.IPv4Network(c['aggregate']):
                raise ValueError('management source must be an approved remote IPv4 /32')
            pair=(str(source),entry['vmid'])
            if pair in seen:raise ValueError('duplicate management grant')
            seen.add(pair)
    else:
        if set(c['interfaces']) != {'wg-users', 'wg-workspaces'}:
            raise ValueError('explicit managed interface addresses required')
        for address in c['interfaces'].values():
            ipaddress.IPv4Interface(address)
        if len({p['device'] for p in c['pairs']}) != len(c['pairs']):
            raise ValueError('device has multiple workspace targets')
        for p in c['pairs']:
            ip(p['device']); ip(p['workspace'])
        for source in c['ga2_sources'] + c['workspace_sources']:
            n = ipaddress.IPv4Network(source, strict=True)
            if n.prefixlen < 24:
                raise ValueError('source too broad')
        if not c['ga2_sources'] or not c['workspace_sources']:
            raise ValueError('empty ingress source list')
    return c


def render(c):
    validate(c)
    lines = ['table inet oci_hub {', ' chain input { type filter hook input priority -200; policy accept;']
    if c['kind'] == 'hub':
        lines += ['  iifname { "wg-users", "wg-workspaces" } drop']
        for field, port in [('ga2_sources', 51824), ('workspace_sources', 51825)]:
            lines += [f'  ip saddr {{ {", ".join(c[field])} }} udp dport {port} accept', f'  udp dport {port} drop']
    else:
        for v in c['workspaces']:
            lines += [f'  iifname "{v["vnet"]}" drop']
    lines += [' }', ' chain forward { type filter hook forward priority -200; policy accept;']
    if c['kind'] == 'hub':
        for p in c['pairs']:
            lines += [f'  iifname "wg-users" oifname "wg-workspaces" ip saddr {p["device"]} ip daddr {p["workspace"]} tcp dport {{ 22, 8443 }} ct state {{ new, established }} accept',
                      f'  iifname "wg-workspaces" oifname "wg-users" ip saddr {p["workspace"]} ip daddr {p["device"]} tcp sport {{ 22, 8443 }} ct state established accept']
        lines += ['  iifname { "wg-users", "wg-workspaces" } drop', '  oifname { "wg-users", "wg-workspaces" } drop']
    else:
        for v in c['workspaces']:
            n = v['vnet']; addr = v['address']
            # Routed administration is scoped to an external source and one VM.
            # Check source before every exception, including established replies.
            lines += [f'  iifname "{n}" ip saddr != {addr} drop']
            for access in c.get('management_access',[]):
                if access['vmid'] != v['vmid']:continue
                source=str(ipaddress.IPv4Network(access['source']))
                lines += [f'  iifname "{c["uplink"]}" oifname "{n}" ip saddr {source} ip daddr {addr} tcp dport 22 ct state {{ new, established }} ct direction original accept',
                          f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {source} tcp sport 22 ct state established ct direction reply accept']
            for resolver in c.get('dns_servers', []):
                ip(resolver)
                lines += [f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {resolver} udp dport 53 accept', f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {resolver} tcp dport 53 accept']
            protected=list(dict.fromkeys(c['protected']+[a['source'] for a in c.get('management_access',[])]+['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','127.0.0.0/8','169.254.0.0/16','100.64.0.0/10','224.0.0.0/4','240.0.0.0/4']))
            lines += [f'  iifname "{n}" ip daddr {c["endpoint"]} udp dport 51825 accept',
                      f'  iifname "{n}" ip daddr {c["endpoint"]} drop',
                      f'  iifname "{n}" ip daddr {{ {", ".join(protected)} }} drop']
            for destination in c['development_destinations']:
                lines += [f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {destination} tcp dport {{ 22, 80, 443 }} accept']
            lines += [f'  iifname "{n}" drop', f'  oifname "{n}" ip daddr {addr} ct state established,related ct direction reply accept', f'  oifname "{n}" drop']
    lines += [' }', '}']
    if c['kind'] == 'pve':
        lines += ['table bridge oci_hub {', ' chain prerouting { type filter hook prerouting priority -300; policy accept;']
        for v in c['workspaces']:
            # Tap names are assigned by PVE and cannot be changed inside the guest.
            tap = f'tap{int(v["vmid"])}i0'
            lines += [f'  iifname "{tap}" ether saddr != {v["mac"]} drop',
                      f'  iifname "{tap}" ether type arp arp saddr ip {v["address"]} arp daddr ip {v["gateway"]} accept',
                      f'  iifname "{tap}" ether type ip ip saddr {v["address"]} accept',
                      f'  iifname "{tap}" drop']
        lines += [' }', ' chain forward { type filter hook forward priority -300; policy accept;']
        for v in c['workspaces']:
            lines += [f'  iifname "tap{int(v["vmid"])}i0" drop']
        lines += [' }', '}']
    return '\n'.join(lines) + '\n'


def canonical(value):
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items() if k not in ('handle', 'packets', 'bytes', 'metainfo')}
    if isinstance(value, list):
        return [canonical(v) for v in value if not (isinstance(v, dict) and 'metainfo' in v)]
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def live(c):
    families = ['inet', 'bridge'] if c['kind'] == 'pve' else ['inet']
    return [canonical(json.loads(run('nft', '-j', 'list', 'table', f, 'oci_hub'))) for f in families]


def verify_forwarding():
    if run('sysctl', '-n', 'net.ipv4.ip_forward').strip() != '1':
        raise ValueError('IPv4 forwarding is not enabled')


def verify_routing(c):
    interfaces = c['interfaces'] if c['kind'] == 'hub' else {
        v['vnet']: f"{v['gateway']}/{ipaddress.IPv4Network(v['subnet']).prefixlen}"
        for v in c['workspaces']
    }
    for interface, address in interfaces.items():
        expected = ipaddress.IPv4Interface(address)
        addresses = json.loads(run('ip', '-j', '-4', 'address', 'show', 'dev', interface))
        if not any(info.get('local') == str(expected.ip) and info.get('prefixlen') == expected.network.prefixlen
                   for link in addresses for info in link.get('addr_info', [])):
            raise ValueError('managed interface address is not ready')
        routes = json.loads(run('ip', '-j', '-4', 'route', 'show', 'table', 'main', 'exact', str(expected.network)))
        if not any(route.get('dev') == interface and route.get('dst') == str(expected.network)
                   for route in routes):
            raise ValueError('managed connected route is not ready')
    destinations = [(p['device'], 'wg-users') for p in c['pairs']] + [(p['workspace'], 'wg-workspaces') for p in c['pairs']] if c['kind'] == 'hub' else [(c['endpoint'], c['uplink'])]
    for destination, interface in destinations:
        routes = json.loads(run('ip', '-j', '-4', 'route', 'get', destination))
        if len(routes) != 1 or routes[0].get('dev') != interface or routes[0].get('type', 'unicast') != 'unicast':
            raise ValueError('managed destination routes through an unexpected interface')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['render', 'apply', 'verify', 'hook'])
    parser.add_argument('--config', default='/etc/oci-hub/boundary.json')
    parser.add_argument('--routing', action='store_true')
    parser.add_argument('--require-management-vmid',type=int)
    parser.add_argument('--receipt', default='/etc/oci-hub/boundary-receipt.json')
    parser.add_argument('vmid', nargs='?')
    parser.add_argument('phase', nargs='?')
    a = parser.parse_args()
    c = validate(json.loads(sys.stdin.read() if a.config=='-' else Path(a.config).read_text()))
    if a.require_management_vmid is not None and (c['kind']!='pve' or not any(rule['vmid']==a.require_management_vmid for rule in c.get('management_access',[]))):
        raise ValueError('approved management source missing for the Ansible target')
    if a.action == 'render':
        print(render(c), end=''); return
    if a.action == 'apply':
        prefix = ''
        for f in (['inet', 'bridge'] if c['kind'] == 'pve' else ['inet']):
            result = subprocess.run(['nft', 'list', 'table', f, 'oci_hub'], capture_output=True)
            if result.returncode == 0:
                prefix += f'delete table {f} oci_hub\n'
        # nft -f submits one atomic netlink transaction; old rules survive failure.
        subprocess.run(['nft', '-f', '-'], input=prefix + render(c), text=True, check=True)
        Path(a.receipt).write_text(json.dumps({'policy': digest(c), 'rules': digest(live(c))}))
        # Never enable routing until the scoped ACL transaction has succeeded.
        run('sysctl', '-w', 'net.ipv4.ip_forward=1')
        verify_forwarding()
    else:
        receipt = json.loads(Path(a.receipt).read_text())
        if receipt != {'policy': digest(c), 'rules': digest(live(c))}:
            raise ValueError('live boundary mismatch')
        verify_forwarding()
        if a.routing or (a.action == 'hook' and a.phase == 'pre-start'):
            verify_routing(c)
        if a.action == 'hook' and a.phase == 'pre-start':
            vm = next(v for v in c['workspaces'] if str(v['vmid']) == a.vmid)
            if vm.get('disabled', True):
                raise ValueError('workspace disabled')
            actual = run('qm', 'config', a.vmid)
            match = re.search(r'^net0: (.+)$', actual, re.M)
            if not match or f'bridge={vm["vnet"]}' not in match[1].split(',') or f'VIRTIO={vm["mac"].upper()}' not in match[1].upper().split(','):
                raise ValueError('VM network does not match allocation')
    print('oci-hub boundary verified')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('oci-hub boundary rejected; inspect protected policy and kernel state', file=sys.stderr)
        sys.exit(1)
