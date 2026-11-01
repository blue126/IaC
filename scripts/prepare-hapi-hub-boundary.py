#!/usr/bin/env python3
"""Prepare a narrow Hub egress extension while preserving the installed PVE helper."""
import argparse
import ast
import hashlib
import ipaddress
import json
from pathlib import Path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(helper, service_policy, hub, vmids):
    destination = ipaddress.IPv4Address(hub)
    if not any(destination in ipaddress.ip_network(cidr) for cidr in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']):
        raise ValueError('An exact private Hub address is required')
    if not vmids or len(set(vmids)) != len(vmids) or any(type(v) is not int or v < 100 or v == 500 for v in vmids):
        raise ValueError('Explicit unique worker VMIDs are required')
    if not set(service_policy) <= {'cloudflare_tunnel_vmids', 'hapi_ingress_grants'}:
        raise ValueError('Review changed service policy before extending it')
    if 'hapi_hub_grants' in helper:
        raise ValueError('Installed helper already contains Hub egress support; inspect it instead')
    changes = [(
        "\n        for grant in c.get('hapi_ingress_grants', []):",
        '''
        hub_grants = c.get('hapi_hub_grants', [])
        if not isinstance(hub_grants, list):
            raise ValueError('HAPI Hub grants must be a list')
        seen_hub_grants = set()
        for grant in hub_grants:
            if (not isinstance(grant, dict) or set(grant) != {'destination', 'vmid'} or
                    type(grant['vmid']) is not int or grant['vmid'] not in {v['vmid'] for v in c['workspaces']}):
                raise ValueError('HAPI Hub egress must name an allocated worker')
            target = ipaddress.IPv4Network(grant['destination'], strict=True)
            private = any(target.subnet_of(ipaddress.IPv4Network(cidr)) for cidr in
                          ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'])
            pair = (grant['vmid'], str(target))
            if target.prefixlen != 32 or not private or target.overlaps(ipaddress.IPv4Network(c['aggregate'])) or pair in seen_hub_grants:
                raise ValueError('HAPI Hub requires a unique exact private destination outside worker networks')
            seen_hub_grants.add(pair)
        for grant in c.get('hapi_ingress_grants', []):'''), (
        "            for access in c.get('management_access',[]):",
        '''            for grant in c.get('hapi_hub_grants', []):
                if grant['vmid'] != v['vmid'] or v.get('disabled', True):
                    continue
                target = str(ipaddress.IPv4Network(grant['destination']))
                lines += [f'  iifname "{n}" oifname "{c["uplink"]}" ip saddr {addr} ip daddr {target} tcp dport 9443 ct state {{ new, established }} ct direction original accept',
                          f'  iifname "{c["uplink"]}" oifname "{n}" ip saddr {target} ip daddr {addr} tcp sport 9443 ct state established ct direction reply accept']
            for access in c.get('management_access',[]):'''), (
        "{'cloudflare_tunnel_vmids', 'hapi_ingress_grants'}",
        "{'cloudflare_tunnel_vmids', 'hapi_ingress_grants', 'hapi_hub_grants'}")]
    for old, new in changes:
        if helper.count(old) != 1:
            raise ValueError('Installed helper context changed; review a fresh baseline')
        helper = helper.replace(old, new)
    ast.parse(helper)
    policy = {**service_policy, 'hapi_hub_grants': [{'vmid': v, 'destination': str(destination) + '/32'} for v in sorted(vmids)]}
    return helper, policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--service-policy', required=True, type=Path)
    parser.add_argument('--expected-helper-sha256', required=True)
    parser.add_argument('--expected-service-sha256', required=True)
    parser.add_argument('--hub', required=True)
    parser.add_argument('--vmid', required=True, action='append', type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, policy = args.helper.read_bytes(), args.service_policy.read_bytes()
    if digest(source) != args.expected_helper_sha256 or digest(policy) != args.expected_service_sha256:
        raise ValueError('Installed boundary baseline digest changed')
    helper, candidate = prepare(source.decode(), json.loads(policy), args.hub, args.vmid)
    args.output.mkdir(mode=0o700, parents=False)
    (args.output / 'boundary.py').write_text(helper)
    (args.output / 'service-egress.json').write_text(json.dumps(candidate, indent=2) + '\n')
    receipt = {'previous_helper_sha256': digest(source), 'previous_service_sha256': digest(policy),
               'candidate_helper_sha256': digest(helper.encode()),
               'candidate_service_sha256': digest((args.output / 'service-egress.json').read_bytes()),
               'hub': args.hub, 'worker_vmids': args.vmid, 'applied': False}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
