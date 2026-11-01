#!/usr/bin/python3
"""Compile and enforce HAPI-only PVE bridge boundaries; no guest or router NAT."""
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path('/etc/hapi-network')
STATE = Path('/var/lib/hapi-network')
PRIVATE = [ipaddress.ip_network(x) for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
RESERVED = ['0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
            '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
            '192.168.0.0/16', '198.18.0.0/15', '198.51.100.0/24',
            '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4']


def require(test, message):
    if not test:
        raise ValueError(message)


def address(value):
    require(isinstance(value, str), 'Canonical IPv4 string required')
    return str(ipaddress.IPv4Address(value))


def private(value):
    result = address(value)
    require(any(ipaddress.ip_address(result) in net for net in PRIVATE), 'RFC1918 address required')
    return result


def validate(c):
    base = {'version', 'node', 'bridge', 'control_address', 'admin_addresses',
            'dns_addresses', 'protected_networks', 'workspaces'}
    require(base <= set(c) <= base | {'attachment', 'trusted_peers', 'hook_file_id'}, 'Unexpected manifest fields')
    access_bridge = c.get('attachment', 'vlan') == 'access-bridge'
    require(c.get('attachment', 'vlan') in ('vlan', 'access-bridge'), 'Unknown attachment type')
    require(re.fullmatch(r'[a-zA-Z0-9_-]+:snippets/hapi-network-hook.py',
                         c.get('hook_file_id', 'local:snippets/hapi-network-hook.py')), 'Invalid hook storage binding')
    require(c['version'] == 1, 'Unsupported manifest version')
    require(re.fullmatch(r'[a-z][a-z0-9-]{0,31}', c['node']), 'Invalid PVE node')
    require(re.fullmatch(r'vmbr[0-9]{1,4}', c['bridge']), 'Invalid reviewed trunk bridge')
    private(c['control_address'])
    for key in ('admin_addresses', 'dns_addresses', 'protected_networks', 'workspaces'):
        require(isinstance(c[key], list) and c[key], 'Nonempty list required: ' + key)
    for ip in c['admin_addresses']:
        private(ip)
    for ip in c['dns_addresses']:
        address(ip)
    for net in c['protected_networks']:
        ipaddress.IPv4Network(net, strict=True)
    seen = {key: set() for key in ('id', 'vmid', 'vnet', 'vlan', 'mac', 'address')}
    networks = []
    for w in c['workspaces']:
        require(set(w) == {'id', 'vmid', 'vnet', 'vlan', 'mac', 'address', 'gateway',
                           'gateway_mac', 'enabled'}, 'Unexpected workspace fields')
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,31}', w['id']), 'Invalid workspace ID')
        require(type(w['vmid']) is int and 503 <= w['vmid'] <= 999999999, 'Reserved/invalid VMID')
        require(w['vnet'] == c['bridge'] if access_bridge else re.fullmatch(r'ha[a-z0-9]{1,6}', w['vnet']),
                'Invalid reviewed VM bridge binding')
        require(w['vlan'] is None if access_bridge else type(w['vlan']) is int and 2 <= w['vlan'] <= 4094,
                'Do not assign a VLAN to an untagged access bridge')
        require(type(w['enabled']) is bool, 'Explicit enabled boolean required')
        for field in ('mac', 'gateway_mac'):
            require(re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', w[field]), 'Canonical MAC required')
            require(int(w[field][:2], 16) & 1 == 0 and w[field] != '00:00:00:00:00:00', 'Unicast MAC required')
        require(w['mac'] != w['gateway_mac'], 'Guest and gateway MAC must differ')
        interface = ipaddress.IPv4Interface(w['address'])
        require(w['address'] == str(interface), 'Canonical address/prefix required')
        net = interface.network
        require(24 <= net.prefixlen <= 30, 'Use reviewed /24 through /30 workspace subnets')
        private(str(interface.ip))
        private(str(net.network_address))
        gw = ipaddress.ip_address(private(w['gateway']))
        require(gw in net and gw not in (interface.ip, net.network_address, net.broadcast_address), 'Invalid gateway')
        require(interface.ip not in (net.network_address, net.broadcast_address), 'Invalid guest host address')
        require(access_bridge or all(not net.overlaps(other) for other in networks), 'Overlapping workspace subnets')
        require(access_bridge or all(ipaddress.ip_address(ip) not in net for ip in [c['control_address']] + c['admin_addresses'] + c['dns_addresses']),
                'Control/admin must be routed outside workspace subnets')
        networks.append(net)
        for key in seen:
            if access_bridge and key in ('vnet', 'vlan'):
                continue
            value = str(interface.ip) if key == 'address' else w[key]
            require(value not in seen[key], 'Duplicate allocation: ' + key)
            seen[key].add(value)
    if access_bridge:
        peers = c.get('trusted_peers', [])
        required = set([c['control_address']] + c['admin_addresses'] + [w['gateway'] for w in c['workspaces']])
        require(isinstance(peers, list) and len(peers) == len(required), 'Explicit trusted peer bindings required')
        require({p['address'] for p in peers} == required, 'Trusted peers must match gateway, control and admin sources')
        for p in peers:
            require(set(p) == {'address', 'mac', 'ports'}, 'Unexpected trusted peer fields')
            address(p['address'])
            require(re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', p['mac']) and
                    int(p['mac'][:2], 16) & 1 == 0 and p['mac'] != '00:00:00:00:00:00', 'Invalid peer MAC')
            require(isinstance(p['ports'], list) and p['ports'] and all(
                re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', port) for port in p['ports']), 'Fixed trusted ingress ports required')
            require(not any(port == 'tap' + str(w['vmid']) + 'i0' for w in c['workspaces'] for port in p['ports']),
                    'Employee ports cannot be trusted uplinks')
        for w in c['workspaces']:
            peer = next(p for p in peers if p['address'] == w['gateway'])
            require(peer['mac'] == w['gateway_mac'], 'Gateway MAC differs from the trusted peer')
    return c


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result
    return validate(json.loads(Path(path).read_text(), object_pairs_hook=unique))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def compatible(c, old):
    require({k: v for k, v in c.items() if k != 'workspaces'} ==
            {k: v for k, v in old.items() if k != 'workspaces'}, 'Fabric changes require a migration plan')
    by_id = {w['id']: w for w in c['workspaces']}
    for w in old['workspaces']:
        require(w['id'] in by_id and {k: v for k, v in w.items() if k != 'enabled'} ==
                {k: v for k, v in by_id[w['id']].items() if k != 'enabled'},
                'Existing allocation cannot be removed or rebound; disable it instead')


def table(w):
    return 'hapi_' + str(w['vmid'])


def render(c, w):
    if c.get('attachment') == 'access-bridge':
        return render_access(c, w)
    tap = 'tap' + str(w['vmid']) + 'i0'
    ip = str(ipaddress.ip_interface(w['address']).ip)
    lines = [f'table bridge {table(w)} {{',
             f' comment "hapi-network-v1:{w["id"]}"',
             ' chain input { type filter hook input priority -100; policy accept;',
             f'  iifname "{tap}" drop', ' }',
             ' chain output { type filter hook output priority -100; policy accept;',
             f'  oifname "{tap}" drop', ' }',
             ' chain forward { type filter hook forward priority -100; policy accept;',
             f'  iifname "{tap}" jump guest_out',
             f'  oifname "{tap}" jump guest_in', ' }',
             ' chain guest_out {']
    if w['enabled']:
        lines += [f'  ether saddr != {w["mac"]} drop',
                  f'  ether type arp arp saddr ether {w["mac"]} arp saddr ip {ip} '
                  f'arp daddr ip {w["gateway"]} arp operation {{ request, reply }} accept',
                  f'  ether type != ip drop', f'  ether daddr != {w["gateway_mac"]} drop',
                  f'  ip saddr != {ip} drop', '  ct state invalid drop']
        for source, port in [(c['control_address'], 9443)] + [(a, 22) for a in c['admin_addresses']]:
            lines += [f'  ip daddr {source} tcp sport {port} ct state established accept']
        lines += [f'  ip daddr {c["control_address"]} tcp dport 9443 ct state {{ new, established }} ct direction original accept']
        for dns in c['dns_addresses']:
            lines += [f'  ip daddr {dns} meta l4proto {{ tcp, udp }} th dport 53 accept']
        protected = sorted(set(RESERVED + c['protected_networks']))
        lines += ['  ip daddr { ' + ', '.join(protected) + ' } drop', '  ether type ip accept']
    lines += ['  drop', ' }', ' chain guest_in {']
    if w['enabled']:
        lines += [f'  ether saddr != {w["gateway_mac"]} drop',
                  f'  ether type arp arp saddr ether {w["gateway_mac"]} arp saddr ip {w["gateway"]} '
                  f'arp daddr ip {ip} arp operation {{ request, reply }} accept',
                  '  ether type != ip drop', f'  ether daddr != {w["mac"]} drop',
                  f'  ip daddr != {ip} drop', '  ct state invalid drop',
                  '  ct state { established, related } accept',
                  f'  ip saddr {c["control_address"]} tcp dport 9443 accept']
        for admin in c['admin_addresses']:
            lines += [f'  ip saddr {admin} tcp dport 22 accept']
    return '\n'.join(lines + ['  drop', ' }', '}', ''])


def render_access(c, w):
    tap = 'tap' + str(w['vmid']) + 'i0'
    ip = str(ipaddress.ip_interface(w['address']).ip)
    peers = {p['address']: p for p in c['trusted_peers']}
    def ports(peer):
        return '{ ' + ', '.join('"' + port + '"' for port in peer['ports']) + ' }'
    lines = [f'table bridge {table(w)} {{', f' comment "hapi-network-v1:{w["id"]}"',
             ' chain ingress { type filter hook prerouting priority -300; policy accept;',
             f'  iifname "{tap}" ether saddr != {w["mac"]} drop',
             f'  iifname "{tap}" ether type {{ 8021q, 8021ad, ip6 }} drop', ' }',
             ' chain input { type filter hook input priority -100; policy accept;',
             f'  iifname "{tap}" drop', ' }',
             ' chain output { type filter hook output priority -100; policy accept;',
             f'  oifname "{tap}" drop', ' }',
             ' chain forward { type filter hook forward priority -100; policy accept;',
             f'  iifname "{tap}" jump guest_out', f'  oifname "{tap}" jump guest_in', ' }',
             ' chain guest_out {']
    if w['enabled']:
        lines += [f'  ether saddr != {w["mac"]} drop']
        for peer in peers.values():
            lines += [f'  ether type arp arp saddr ether {w["mac"]} arp saddr ip {ip} '
                      f'arp daddr ip {peer["address"]} arp operation {{ request, reply }} accept']
        lines += ['  ether type != ip drop', f'  ip saddr != {ip} drop', '  ct state invalid drop']
        for source, port in [(c['control_address'], 9443)] + [(a, 22) for a in c['admin_addresses']]:
            lines += [f'  ether daddr {peers[source]["mac"]} ip daddr {source} tcp sport {port} ct state established accept']
        control = peers[c['control_address']]
        lines += [f'  ether daddr {control["mac"]} ip daddr {c["control_address"]} tcp dport 9443 ct state {{ new, established }} ct direction original accept']
        lines += [f'  ether daddr != {w["gateway_mac"]} drop']
        for dns in c['dns_addresses']:
            lines += [f'  ip daddr {dns} meta l4proto {{ tcp, udp }} th dport 53 accept']
        lines += ['  ip daddr { ' + ', '.join(sorted(set(RESERVED + c['protected_networks']))) + ' } drop',
                  '  ether type ip accept']
    lines += ['  drop', ' }', ' chain guest_in {']
    if w['enabled']:
        for peer in peers.values():
            lines += [f'  iifname {ports(peer)} ether saddr {peer["mac"]} ether type arp '
                      f'arp saddr ether {peer["mac"]} arp saddr ip {peer["address"]} arp daddr ip {ip} '
                      'arp operation { request, reply } accept']
        lines += ['  ether type != ip drop', f'  ether daddr != {w["mac"]} drop', f'  ip daddr != {ip} drop',
                  '  ct state invalid drop']
        gw = peers[w['gateway']]
        lines += [f'  iifname {ports(gw)} ether saddr {gw["mac"]} ct state {{ established, related }} accept']
        control = peers[c['control_address']]
        lines += [f'  iifname {ports(control)} ether saddr {control["mac"]} ip saddr {c["control_address"]} tcp sport 9443 ct state established ct direction reply accept']
        for source, port in [(c['control_address'], 9443)] + [(a, 22) for a in c['admin_addresses']]:
            peer = peers[source]
            lines += [f'  iifname {ports(peer)} ether saddr {peer["mac"]} ip saddr {source} tcp dport {port} accept']
    return '\n'.join(lines + ['  drop', ' }', '}', ''])


def run(*args, input=None):
    result = subprocess.run(args, input=input, text=True, capture_output=True, check=True)
    return result.stdout


def kernel(w):
    # Handles and metainfo change across atomic reloads; all rule expressions,
    # chain attachment, priorities and policies remain part of the receipt.
    data = json.loads(run('nft', '-j', 'list', 'table', 'bridge', table(w)))
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k != 'handle'}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return clean([row for row in data['nftables'] if 'metainfo' not in row])


def atomic(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.hapi-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical(value) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def transaction(w, policy):
    tables = json.loads(run('nft', '-j', 'list', 'tables'))['nftables']
    exists = any(row.get('table', {}).get('family') == 'bridge' and
                 row['table'].get('name') == table(w) for row in tables)
    receipt = STATE / (str(w['vmid']) + '.json')
    require(not exists or receipt.exists(), 'Unowned nft table: ' + table(w))
    return (f'delete table bridge {table(w)}\n' if exists else '') + policy, exists


def preflight(c):
    for w in c['workspaces']:
        candidate, _ = transaction(w, render(c, w))
        run('nft', '--check', '-f', '-', input=candidate)


def apply(c):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Validate every candidate before changing even the first employee.
    preflight(c)
    changed = False
    for w in c['workspaces']:
        receipt = STATE / (str(w['vmid']) + '.json')
        policy = render(c, w)
        desired = hashlib.sha256(policy.encode()).hexdigest()
        old = json.loads(receipt.read_text()) if receipt.exists() else None
        require(old is None or old.get('workspace') == w['id'], 'Receipt ownership mismatch')
        candidate, exists = transaction(w, policy)
        if exists and old.get('policy') == desired and old.get('kernel') == digest(kernel(w)):
            continue
        run('nft', '-f', '-', input=candidate)
        atomic(receipt, {'policy': desired, 'kernel': digest(kernel(w)), 'workspace': w['id']})
        changed = True
    return changed


def verify(c, vmid=None):
    for w in c['workspaces']:
        if vmid is not None and w['vmid'] != vmid:
            continue
        saved = json.loads((STATE / (str(w['vmid']) + '.json')).read_text())
        require(saved == {'policy': hashlib.sha256(render(c, w).encode()).hexdigest(),
                          'kernel': digest(kernel(w)), 'workspace': w['id']}, 'Firewall missing or changed')


def binding(c, w, config):
    require(config.get('name') == 'hapi-' + w['id'], 'VM name/ownership mismatch')
    require(config.get('hookscript') == c.get('hook_file_id', 'local:snippets/hapi-network-hook.py'), 'Startup gate is not bound')
    require(str(config.get('onboot', 0)) == '0', 'Automatic boot must remain disabled')
    require(not config.get('hostpci0') and not any(re.fullmatch(r'(?:net[1-9][0-9]*|hostpci[0-9]+|usb[0-9]+)', key)
                for key in config), 'Unexpected guest network/passthrough device')
    fields = config.get('net0', '').split(',')
    expected = {'virtio': w['mac'].lower(), 'bridge': w['vnet'], 'firewall': '0'}
    actual = {}
    for field in fields:
        key, value = field.split('=', 1)
        require(key not in actual, 'Duplicate NIC property')
        actual[key] = value.lower() if key == 'virtio' else value
    actual.setdefault('firewall', '0')
    require(actual == expected, 'Guest NIC must be a fixed single access port without trunk/tag/firewall bridge')
    ipconfig = {}
    for field in config.get('ipconfig0', '').split(','):
        key, value = field.split('=', 1)
        require(key not in ipconfig, 'Duplicate cloud-init property')
        ipconfig[key] = value
    require(ipconfig == {'ip': w['address'], 'gw': w['gateway']}, 'Cloud-init network mismatch')
    require(not config.get('args'), 'Unmanaged QEMU arguments are forbidden')


def bind_hooks(c):
    existing = json.loads(run('pvesh', 'get', f'/nodes/{c["node"]}/qemu', '--output-format', 'json'))
    ids = {row['vmid'] for row in existing}
    desired = c.get('hook_file_id', 'local:snippets/hapi-network-hook.py')
    pending = []
    for w in c['workspaces']:
        if w['vmid'] not in ids:
            continue
        path = f'/nodes/{c["node"]}/qemu/{w["vmid"]}'
        config = json.loads(run('pvesh', 'get', path + '/config', '--output-format', 'json'))
        if config.get('hookscript') == desired:
            binding(c, w, config)
            continue
        require(not config.get('hookscript'), 'Refusing to replace an unknown startup hook')
        status = json.loads(run('pvesh', 'get', path + '/status/current', '--output-format', 'json'))
        require(status['status'] == 'stopped', 'Bind the gate before first start; do not repair a running unguarded VM')
        binding(c, w, config | {'hookscript': desired})
        pending.append((path, config['digest']))
    for path, config_digest in pending:
        run('pvesh', 'set', path + '/config', '--hookscript', desired, '--digest', config_digest)
    return bool(pending)


def hook(c, vmid):
    w = next(w for w in c['workspaces'] if w['vmid'] == vmid)
    require(w['enabled'], 'Workspace is disabled')
    verify(c, vmid)
    config = json.loads(run('pvesh', 'get', f'/nodes/{c["node"]}/qemu/{vmid}/config', '--output-format', 'json'))
    binding(c, w, config)
    if c.get('attachment') == 'access-bridge':
        links = json.loads(run('ip', '-d', '-j', 'link', 'show', c['bridge']))
        require(len(links) == 1 and links[0].get('linkinfo', {}).get('info_kind') == 'bridge', 'Access bridge is absent')
        return
    # Check the active VLAN interface, not only a staged SDN configuration.
    links = json.loads(run('ip', '-d', '-j', 'link', 'show', c['bridge'] + '.' + str(w['vlan'])))
    require(len(links) == 1 and links[0].get('master') == w['vnet'] and
            links[0].get('linkinfo', {}).get('info_kind') == 'vlan' and
            links[0]['linkinfo'].get('info_data', {}).get('id') == w['vlan'], 'VNet uplink is not active')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'render', 'preflight', 'apply', 'verify', 'hook', 'bind-hooks'])
    parser.add_argument('--config', default=str(ROOT / 'manifest.json'))
    parser.add_argument('--vmid', type=int)
    parser.add_argument('--previous')
    args = parser.parse_args()
    c = load(args.config)
    if args.previous and Path(args.previous).exists():
        compatible(c, load(args.previous))
    if args.action == 'check':
        print(digest(c))
    elif args.action == 'render':
        print(''.join(render(c, w) for w in c['workspaces']))
    else:
        require(os.geteuid() == 0, 'Root is required for PVE enforcement')
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (STATE / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            c = load(args.config)
            if args.action == 'preflight':
                preflight(c)
            elif args.action == 'bind-hooks':
                print('changed' if bind_hooks(c) else 'unchanged')
            elif args.action == 'apply':
                print('changed' if apply(c) else 'unchanged')
            elif args.action == 'verify':
                verify(c, args.vmid)
            else:
                require(args.vmid is not None, 'A VMID is required')
                hook(c, args.vmid)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, StopIteration, subprocess.CalledProcessError) as error:
        print('HAPI network operation refused: ' + str(error), file=sys.stderr)
        sys.exit(1)
