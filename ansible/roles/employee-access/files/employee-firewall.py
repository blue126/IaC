#!/usr/bin/env python3
"""Load only employee tables, gate routing, and verify the applied kernel policy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

POLICY = Path('/etc/employee-access.nft')
APPLIED = Path('/etc/employee-access.applied.json')
OCI_EXTENSION_UNIT = Path('/etc/systemd/system/employee-firewall.service.d/oci-backhaul.conf')
BROWSER_EXTENSION_UNIT = Path('/etc/systemd/system/employee-firewall.service.d/zz-browser.conf')
OCI_EXTENSION_RULE = {'rule': {
    'family': 'inet', 'table': 'employee_access', 'chain': 'input',
    'comment': 'employee-oci-home-ssh',
    'expr': [
        {'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'wg-oci-home'}},
        {'match': {'op': '==', 'left': {'payload': {'protocol': 'ip', 'field': 'saddr'}}, 'right': '10.233.1.1'}},
        {'match': {'op': '==', 'left': {'payload': {'protocol': 'ip', 'field': 'daddr'}}, 'right': '10.233.1.2'}},
        {'match': {'op': '==', 'left': {'payload': {'protocol': 'tcp', 'field': 'dport'}}, 'right': 22}},
        {'accept': None},
    ],
}}

BROWSER_EXTENSION_RULE = json.loads(json.dumps(OCI_EXTENSION_RULE))
BROWSER_EXTENSION_RULE['rule']['comment'] = 'employee-oci-home-browser'
BROWSER_EXTENSION_RULE['rule']['expr'][3]['match']['right'] = 8443


def routing(enabled):
    subprocess.run(['/usr/sbin/sysctl', '-q', '-w', 'net.ipv4.ip_forward=' + str(int(enabled))], check=True)


def normalize(value):
    if isinstance(value, list):
        return [normalize(item) for item in value if not isinstance(item, dict) or 'metainfo' not in item]
    if isinstance(value, dict):
        return {key: (0 if key in ('packets', 'bytes') else normalize(item)) for key, item in value.items() if key not in ('handle', 'index')}
    return value


def snapshot(gateway):
    tables = [('inet', 'employee_access'), ('ip', 'employee_nat')] if gateway else [('bridge', 'employee_boundary')]
    return [normalize(json.loads(subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', family, name], text=True))) for family, name in tables]


def invalid_input_guard(item):
    rule = item.get('rule', {})
    if (rule.get('family'), rule.get('table'), rule.get('chain')) != ('inet', 'employee_access', 'input'):
        return False
    expr = rule.get('expr', [])
    if len(expr) != 2 or expr[1] != {'drop': None}:
        return False
    match = expr[0].get('match', {})
    return (match.get('left', {}).get('ct', {}).get('key') == 'state'
            and match.get('op') in ('==', 'in') and match.get('right') == 'invalid')


def without_known_extension(tables, gateway, extension_enabled, browser_enabled=False):
    if not gateway:
        return tables
    rules = tables[0]['nftables']
    for enabled, expected in ((extension_enabled, OCI_EXTENSION_RULE), (browser_enabled, BROWSER_EXTENSION_RULE)):
        extension = [item for item in rules if item.get('rule', {}).get('comment') == expected['rule']['comment']]
        if enabled and extension != [expected]:
            raise RuntimeError('Firewall extension is missing or differs from its approved rule')
        if enabled:
            guards = [index for index, item in enumerate(rules) if invalid_input_guard(item)]
            if len(guards) != 1 or rules.index(extension[0]) <= guards[0]:
                raise RuntimeError('Firewall extension must follow the invalid-state drop')
            rules = [item for item in rules if item not in extension]
    tables[0]['nftables'] = rules
    return tables


def verify(gateway):
    expected = json.loads(APPLIED.read_text())
    actual = without_known_extension(snapshot(gateway), gateway, OCI_EXTENSION_UNIT.is_file(), BROWSER_EXTENSION_UNIT.is_file())
    if expected['sha256'] != hashlib.sha256(POLICY.read_bytes()).hexdigest() or expected['tables'] != actual:
        raise RuntimeError('Applied employee policy differs from the configured or kernel policy')
    if gateway and Path('/proc/sys/net/ipv4/ip_forward').read_text().strip() != '1':
        raise RuntimeError('Gateway routing is disabled')


def apply(gateway):
    if gateway:
        routing(False)
    # A failure from this point leaves gateway forwarding disabled.
    subprocess.run(['/usr/sbin/nft', '-f', str(POLICY)], check=True)
    record = {'sha256': hashlib.sha256(POLICY.read_bytes()).hexdigest(), 'tables': snapshot(gateway)}
    temporary = APPLIED.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, sort_keys=True))
    temporary.chmod(0o600)
    temporary.replace(APPLIED)
    if gateway:
        routing(True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['apply', 'verify'])
    parser.add_argument('--routing', action='store_true')
    args = parser.parse_args()
    if args.operation == 'apply':
        apply(args.routing)
    else:
        verify(args.routing)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('Employee firewall failed: ' + str(exc), file=sys.stderr)
        sys.exit(1)
