#!/usr/bin/python3
"""Fixed root-owned veth/NAT setup; no request-supplied addresses or commands."""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
from control import Refused, command, private_file


def names(namespace):
    if not re.fullmatch(r'iac-job-[A-Za-z0-9_-]{16,128}', namespace):
        raise Refused('invalid namespace')
    suffix = hashlib.sha256(namespace.encode()).hexdigest()[:10]
    return 'jh'+suffix, 'jn'+suffix, 'job_'+suffix


def rules(host, table, profile, uplink):
    if not re.fullmatch('[a-zA-Z0-9_.:-]{1,15}', uplink):
        raise Refused('invalid root-configured uplink')
    permits = []
    for peer in profile['peers']:
        address = ipaddress.ip_address(peer['ip'])
        if address.version != 4 or address.is_loopback or not isinstance(peer['port'], int):
            raise Refused('only fixed IPv4 peers are routed; IPv6 remains denied')
        permits.append(f'ip daddr {address} tcp dport {peer["port"]} accept')
    return f'''table inet {table} {{
 chain peers {{ {'; '.join(permits)}; drop; }}
 chain forward {{ type filter hook forward priority -10; policy accept;
  iifname "{host}" oifname "{uplink}" jump peers;
  iifname "{host}" drop;
  oifname "{host}" ct state established,related accept;
  oifname "{host}" drop;
 }}
 chain input {{ type filter hook input priority -10; policy accept; iifname "{host}" drop; }}
}}
table ip {table} {{
 chain postrouting {{ type nat hook postrouting priority srcnat; policy accept;
  ip saddr 10.252.110.2 oifname "{uplink}" masquerade;
 }}
}}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['create', 'remove'])
    parser.add_argument('namespace')
    parser.add_argument('profile')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refused('root required')
    config = json.loads(private_file('/etc/jenkins-agent/runner.json').read_text())
    profiles = [p for p in config['profiles'].values() if p['name'] == args.profile]
    if len(profiles) != 1:
        raise Refused('unknown network profile')
    profile = profiles[0]
    host, guest, table = names(args.namespace)
    if args.mode == 'remove':
        # Missing tables/links are acceptable only after successful kernel inspection.
        tables = command(['nft', '-j', 'list', 'tables'])
        for family in ['inet', 'ip']:
            if any(t.get('table', {}).get('family') == family and t['table']['name'] == table
                   for t in json.loads(tables)['nftables']):
                command(['nft', 'delete', 'table', family, table])
        links = json.loads(command(['ip', '-j', 'link', 'show']))
        if any(link['ifname'] == host for link in links):
            command(['ip', 'link', 'delete', host])
        return
    if command(['sysctl', '-n', 'net.ipv4.ip_forward']) != '1':
        raise Refused('IPv4 forwarding must be explicitly provisioned')
    # Install forwarding restrictions before exposing the veth.
    subprocess.run(['nft', '-f', '-'], input=rules(host, table, profile, config['uplink']),
                   text=True, check=True, capture_output=True, timeout=30)
    command(['ip', 'link', 'add', host, 'type', 'veth', 'peer', 'name', guest])
    command(['ip', 'link', 'set', guest, 'netns', args.namespace])
    command(['ip', 'addr', 'add', '10.252.110.1/30', 'dev', host])
    command(['ip', 'link', 'set', host, 'up'])
    for arguments in [['addr', 'add', '10.252.110.2/30', 'dev', guest],
                      ['link', 'set', guest, 'up'],
                      ['route', 'add', 'default', 'via', '10.252.110.1']]:
        command(['ip', '-n', args.namespace, *arguments])


if __name__ == '__main__':
    try:
        main()
    except (Refused, OSError, subprocess.SubprocessError):
        raise SystemExit('network lifecycle refused')
