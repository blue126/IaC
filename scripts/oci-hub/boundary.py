#!/usr/bin/env python3
"""Scoped nftables boundary and exact live-policy startup verification."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shlex
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


def user_sources(c):
    """Keep GA policies compatible while making direct ingress explicit."""
    fields = [name for name in ('ga2_sources', 'device_sources') if name in c]
    if len(fields) != 1:
        raise ValueError('choose exactly one device or GA ingress source list')
    return c[fields[0]]


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
        if 'uplink' in c:
            token(c['uplink'])
            if c['uplink'] in ('lo', 'wg-users', 'wg-workspaces'):
                raise ValueError('explicit external uplink required for host ingress')
        if set(c['interfaces']) != {'wg-users', 'wg-workspaces'}:
            raise ValueError('explicit managed interface addresses required')
        for address in c['interfaces'].values():
            ipaddress.IPv4Interface(address)
        if len({p['device'] for p in c['pairs']}) != len(c['pairs']):
            raise ValueError('device has multiple workspace targets')
        mosh_ranges = {}
        for p in c['pairs']:
            ip(p['device']); ip(p['workspace'])
            if 'mosh_ports' in p:
                ports = p['mosh_ports']
                if (not isinstance(ports, list) or len(ports) != 2 or
                        any(type(port) is not int for port in ports) or
                        not 60000 <= ports[0] <= ports[1] <= 61000):
                    raise ValueError('invalid Mosh port range')
                allocated = mosh_ranges.setdefault(p['workspace'], [])
                if any(ports[0] <= end and start <= ports[1] for start, end in allocated):
                    raise ValueError('overlapping Mosh ports on the same workspace')
                allocated.append(ports)
        sources = user_sources(c)
        if not isinstance(sources, list) or not isinstance(c['workspace_sources'], list):
            raise ValueError('ingress sources must be lists')
        mode = c.get('device_ingress_mode', 'restricted')
        if mode not in ('restricted', 'dynamic'):
            raise ValueError('invalid device ingress mode')
        if mode == 'dynamic' and ('ga2_sources' in c or sources != ['0.0.0.0/0']):
            raise ValueError('dynamic ingress requires explicit direct IPv4 WireGuard sources')
        for source in (sources if mode == 'restricted' else []) + c['workspace_sources']:
            n = ipaddress.IPv4Network(source, strict=True)
            if n.prefixlen < 24:
                raise ValueError('source too broad')
        if not sources or not c['workspace_sources']:
            raise ValueError('empty ingress source list')
    return c


def render(c):
    validate(c)
    lines = ['table inet oci_hub {', ' chain input { type filter hook input priority -200; policy accept;']
    if c['kind'] == 'hub':
        lines += ['  iifname { "wg-users", "wg-workspaces" } drop']
        for sources, port in [(user_sources(c), 51824), (c['workspace_sources'], 51825)]:
            lines += [f'  ip saddr {{ {", ".join(sources)} }} udp dport {port} accept', f'  udp dport {port} drop']
    else:
        for v in c['workspaces']:
            lines += [f'  iifname "{v["vnet"]}" drop']
    lines += [' }', ' chain forward { type filter hook forward priority -200; policy accept;']
    if c['kind'] == 'hub':
        for p in c['pairs']:
            lines += [f'  iifname "wg-users" oifname "wg-workspaces" ip saddr {p["device"]} ip daddr {p["workspace"]} tcp dport {{ 22, 8443 }} ct state {{ new, established }} accept',
                      f'  iifname "wg-workspaces" oifname "wg-users" ip saddr {p["workspace"]} ip daddr {p["device"]} tcp sport {{ 22, 8443 }} ct state established accept']
            if 'mosh_ports' in p:
                start, end = p['mosh_ports']
                lines += [f'  iifname "wg-users" oifname "wg-workspaces" ip saddr {p["device"]} ip daddr {p["workspace"]} udp dport {start}-{end} ct state {{ new, established }} ct direction original accept',
                          f'  iifname "wg-workspaces" oifname "wg-users" ip saddr {p["workspace"]} ip daddr {p["device"]} udp sport {start}-{end} ct state established ct direction reply accept']
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
                # Public diagnostics stay behind the protected-destination deny.
                lines += [f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {destination} tcp dport {{ 22, 53, 80, 443 }} accept',
                          f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {destination} udp dport {{ 53, 33434-33534 }} accept',
                          f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {destination} ip protocol icmp icmp type echo-request accept']
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


def host_ingress_rules(c):
    if c['kind'] != 'hub' or 'uplink' not in c:
        return []
    rules = []
    for sources, port in ((user_sources(c), 51824), (c['workspace_sources'], 51825)):
        for source in sources:
            rules.append(([] if source == '0.0.0.0/0' else ['-s', source]) + ['-i', c['uplink'], '-p', 'udp', '-m', 'udp', '--dport', str(port),
                          '-m', 'comment', '--comment', 'oci-hub-ingress-' + str(port), '-j', 'ACCEPT'])
    return rules


def host_input_rules():
    return [shlex.split(line)[2:] for line in run('iptables', '-w', '5', '-S', 'INPUT').splitlines()
            if line.startswith('-A INPUT ')]


def owned_ingress(rule):
    return ('--comment' in rule and rule[rule.index('--comment') + 1] in
            ('oci-hub-ingress-51824', 'oci-hub-ingress-51825'))


def verify_host_ingress(c):
    expected = host_ingress_rules(c)
    if not expected:
        return
    run('ip', '-j', 'link', 'show', 'dev', c['uplink'])
    actual = host_input_rules()
    owned = [rule for rule in actual if owned_ingress(rule)]
    if sorted(owned) != sorted(expected):
        raise ValueError('host WireGuard ingress differs from approved sources')
    first_deny = next((i for i, rule in enumerate(actual)
                       if '-j' in rule and rule[rule.index('-j') + 1] in ('DROP', 'REJECT')), len(actual))
    if any(i >= first_deny for i, rule in enumerate(actual) if owned_ingress(rule)):
        raise ValueError('host WireGuard ingress is behind an existing rejection')


def sync_host_ingress(c):
    expected = host_ingress_rules(c)
    if not expected:
        return
    run('ip', '-j', 'link', 'show', 'dev', c['uplink'])
    try:
        verify_host_ingress(c)
        return
    except ValueError:
        pass
    # Keep every foreign rule and its relative order. The scoped nft policy is
    # already live, so source changes remain restricted during reconciliation.
    for rule in host_input_rules():
        if owned_ingress(rule):
            run('iptables', '-w', '5', '-D', 'INPUT', *rule)
    for rule in reversed(expected):
        run('iptables', '-w', '5', '-I', 'INPUT', '1', *rule)
    verify_host_ingress(c)


def host_forward_rules(c):
    if c['kind'] != 'hub' or 'uplink' not in c:
        return []
    rules = []
    for pair in c['pairs']:
        for reverse in (False, True):
            source, target = (pair['workspace'], pair['device']) if reverse else (pair['device'], pair['workspace'])
            incoming, outgoing = ('wg-workspaces', 'wg-users') if reverse else ('wg-users', 'wg-workspaces')
            base = ['-s', source + '/32', '-d', target + '/32', '-i', incoming, '-o', outgoing]
            state = 'ESTABLISHED' if reverse else 'NEW,ESTABLISHED'
            direction = 'REPLY' if reverse else 'ORIGINAL'
            for protocol in ('tcp', 'udp'):
                if protocol == 'udp' and 'mosh_ports' not in pair:
                    continue
                if protocol == 'tcp':
                    ports = ['-m', 'multiport', '--sports' if reverse else '--dports', '22,8443']
                else:
                    ports = ['-m', 'udp', '--sport' if reverse else '--dport', ':'.join(str(p) for p in pair['mosh_ports'])]
                rules.append(base + ['-p', protocol] + ports +
                             ['-m', 'conntrack', '--ctstate', state, '--ctdir', direction,
                              '-m', 'comment', '--comment', 'oci-hub-forward-' + pair['device'] + '-' + protocol + ('-reply' if reverse else '-original'), '-j', 'ACCEPT'])
    return rules


def host_forward_chain():
    return [shlex.split(line)[2:] for line in run('iptables', '-w', '5', '-S', 'FORWARD').splitlines()
            if line.startswith('-A FORWARD ')]


def owned_forward(rule):
    return '--comment' in rule and rule[rule.index('--comment') + 1].startswith('oci-hub-forward-')


def canonical_host_rule(rule):
    result = list(rule)
    if '--ctstate' in result:
        index = result.index('--ctstate') + 1
        result[index] = ','.join(sorted(result[index].split(',')))
    return result


def verify_host_forward(c):
    if c['kind'] != 'hub' or 'uplink' not in c:
        return
    actual = host_forward_chain()
    expected = host_forward_rules(c)
    owned = [r for r in actual if owned_forward(r)]
    if sorted(map(canonical_host_rule, owned)) != sorted(map(canonical_host_rule, expected)):
        raise ValueError('host WireGuard forwarding differs from the exact Hub mappings')
    deny = next((i for i, r in enumerate(actual) if '-j' in r and r[r.index('-j') + 1] in ('DROP', 'REJECT')), len(actual))
    if any(i >= deny for i, r in enumerate(actual) if owned_forward(r)):
        raise ValueError('host WireGuard forwarding is behind an existing rejection')


def sync_host_forward(c):
    if c['kind'] != 'hub' or 'uplink' not in c:
        return
    try:
        verify_host_forward(c)
        return
    except ValueError:
        pass
    for rule in host_forward_chain():
        if owned_forward(rule):
            run('iptables', '-w', '5', '-D', 'FORWARD', *rule)
    actual = host_forward_chain()
    index = next((i for i, r in enumerate(actual) if '-j' in r and r[r.index('-j') + 1] in ('DROP', 'REJECT')), len(actual)) + 1
    for rule in reversed(host_forward_rules(c)):
        run('iptables', '-w', '5', '-I', 'FORWARD', str(index), *rule)
    verify_host_forward(c)


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
        sync_host_ingress(c)
        sync_host_forward(c)
        Path(a.receipt).write_text(json.dumps({'policy': digest(c), 'rules': digest(live(c))}))
        # Never enable routing until the scoped ACL transaction has succeeded.
        run('sysctl', '-w', 'net.ipv4.ip_forward=1')
        verify_forwarding()
    else:
        receipt = json.loads(Path(a.receipt).read_text())
        if receipt != {'policy': digest(c), 'rules': digest(live(c))}:
            raise ValueError('live boundary mismatch')
        verify_host_ingress(c)
        verify_host_forward(c)
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
