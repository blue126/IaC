#!/usr/bin/python3
"""Apply and verify only the retained PVE retirement guard table."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

POLICY = Path('/etc/employee-access.nft')
APPLIED = Path('/etc/employee-access.applied.json')


def normalize(value):
    if isinstance(value, list):
        return [normalize(v) for v in value if not isinstance(v, dict) or 'metainfo' not in v]
    if isinstance(value, dict):
        return {k: (0 if k in ('packets', 'bytes') else normalize(v)) for k, v in value.items() if k not in ('handle', 'index')}
    return value


def snapshot():
    raw = subprocess.check_output(['/usr/sbin/nft', '-j', 'list', 'table', 'bridge', 'employee_boundary'], text=True)
    return normalize(json.loads(raw))


def apply():
    subprocess.run(['/usr/sbin/nft', '-f', str(POLICY)], check=True)
    record = {'sha256': hashlib.sha256(POLICY.read_bytes()).hexdigest(), 'tables': [snapshot()]}
    pending = APPLIED.with_suffix('.tmp')
    pending.write_text(json.dumps(record, sort_keys=True))
    pending.chmod(0o600)
    pending.replace(APPLIED)


def verify():
    record = json.loads(APPLIED.read_text())
    if record['sha256'] != hashlib.sha256(POLICY.read_bytes()).hexdigest() or record['tables'] != [snapshot()]:
        raise RuntimeError('Retired workspace policy differs from its applied kernel table')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['apply', 'verify'])
    args = parser.parse_args()
    apply() if args.operation == 'apply' else verify()
    print('Retired workspace boundary verified')


if __name__ == '__main__':
    main()
