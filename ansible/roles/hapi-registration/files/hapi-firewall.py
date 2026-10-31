#!/usr/bin/python3
"""Apply and verify only HAPI-owned input exceptions without changing the base policy."""
import argparse
import copy
import ipaddress
import json
from pathlib import Path
import subprocess

POLICY = Path('/etc/hapi-application/firewall.json')
PREFIX = 'hapi-application-worker-'


def need(value):
    if not value:
        raise ValueError('HAPI firewall extension differs from its owned policy')


def rule(address, server):
    for value in (address, server):
        ip = ipaddress.IPv4Address(value)
        need(any(ip in ipaddress.ip_network(n) for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']))
    need(address != server)
    return {'rule': {'family': 'inet', 'table': 'employee_access', 'chain': 'input',
        'expr': [
            {'match': {'op': '==', 'left': {'payload': {'protocol': 'ip', 'field': 'saddr'}}, 'right': address}},
            {'match': {'op': '==', 'left': {'payload': {'protocol': 'ip', 'field': 'daddr'}}, 'right': server}},
            {'match': {'op': '==', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}}, 'right': 9443}},
            {'accept': None}], 'comment': PREFIX + address}}


def expected():
    data = json.loads(POLICY.read_bytes())
    need(set(data) == {'version', 'server', 'workers'} and data['version'] == 1)
    need(len(data['workers']) == len(set(data['workers'])))
    return [rule(address, data['server']) for address in data['workers']]


def without_extension(tables):
    result = copy.deepcopy(tables)
    rows = result[0]['nftables']
    owned = [r for r in rows if r.get('rule', {}).get('comment', '').startswith(PREFIX)]
    wanted = expected()
    need(len(owned) == len(wanted) and all(row in owned for row in wanted))
    guards = []
    for index, item in enumerate(rows):
        current = item.get('rule', {})
        if (current.get('family'), current.get('table'), current.get('chain')) != ('inet', 'employee_access', 'input'):
            continue
        for operator in ['in', '==']:
            if current.get('expr') == [
                {'match': {'op': operator, 'left': {'ct': {'key': 'state'}}, 'right': 'invalid'}}, {'drop': None}]:
                guards.append(index)
    need(len(guards) == 1 and all(rows.index(row) > guards[0] for row in owned))
    result[0]['nftables'] = [r for r in rows if r not in owned]
    return result


def apply():
    snapshot = json.loads(subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'inet', 'employee_access'], text=True))
    rows = [{k: v for k, v in r['rule'].items() if k not in {'handle', 'index'}} for r in snapshot['nftables'] if 'rule' in r]
    owned = [r for r in rows if r.get('comment', '').startswith(PREFIX)]
    wanted = [r['rule'] for r in expected()]
    need(len(owned) == len({row["comment"] for row in owned}) and all(row in wanted for row in owned))
    missing = [row for row in wanted if row not in owned]
    if missing:
        body = json.dumps({'nftables': [{'add': {'rule': row}} for row in missing]})
        subprocess.run(['/usr/sbin/nft', '--check', '--json', '--file', '-'], input=body, text=True, check=True, capture_output=True)
        subprocess.run(['/usr/sbin/nft', '--json', '--file', '-'], input=body, text=True, check=True, capture_output=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['apply'])
    parser.parse_args()
    apply()
