#!/usr/bin/env python3
"""Print a secret-free HAPI network change plan without contacting any service."""
import importlib.util
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('network', ROOT / 'ansible/roles/hapi-network/files/hapi-network.py')
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('manifest')
parser.add_argument('--snapshot', help='Minimized PVE allocation snapshot for offline collision checks')
parser.add_argument('--previous', help='Reviewed current manifest; omit only for a fresh HAPI network')
args = parser.parse_args()
c = network.load(args.manifest)
previous = network.load(args.previous) if args.previous else None
if previous is not None:
    network.compatible(c, previous)
snapshot_digest = None
if args.snapshot:
    spec = importlib.util.spec_from_file_location('allocation', ROOT / 'ansible/roles/hapi-network/files/hapi-preflight.py')
    allocation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(allocation)
    snapshot_digest = allocation.check(c, json.loads(Path(args.snapshot).read_text()))
print(json.dumps({'manifest_sha256': network.digest(c), 'node': c['node'], 'trunk': c['bridge'],
                  'expected_current_manifest_sha256': network.digest(previous) if previous is not None else 'absent',
                  'pve_allocations_checked': snapshot_digest is not None,
                  'pve_snapshot_sha256': snapshot_digest,
                  'zone': None if c.get('attachment') == 'access-bridge' else 'hapi', 'steps': ['review-existing-fabric-and-resource-ownership',
                    'reconcile-vnets-and-external-boundaries', 'create-protected-vms-stopped',
                    'verify-start-gate', 'start-and-run-two-workspace-acceptance',
                    'deploy-private-services', 'enable-entry-after-acceptance'],
                  'workspaces': c['workspaces'],
                  'policy': ''.join(network.render(c, w) for w in c['workspaces']),
                  'public_entry_ready': False}, indent=2))
