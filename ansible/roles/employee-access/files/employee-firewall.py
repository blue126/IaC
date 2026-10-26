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


def verify(gateway):
    expected = json.loads(APPLIED.read_text())
    if expected['sha256'] != hashlib.sha256(POLICY.read_bytes()).hexdigest() or expected['tables'] != snapshot(gateway):
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
