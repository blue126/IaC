#!/usr/bin/env python3
"""Reconcile new SDN objects through the PVE API without a provider upgrade."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

# The installed helper keeps a profile-specific filename beside this script.
_boundary_name = 'boundary.py' if Path(__file__).name == 'pve-sdn.py' else 'oci-hub-boundary.py'
_spec = importlib.util.spec_from_file_location('oci_hub_boundary', Path(__file__).with_name(_boundary_name))
_boundary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_boundary)
validate = _boundary.validate

LOCK_TOKEN = None


def api(method, path, **fields):
    if LOCK_TOKEN and method in ('create','set','delete') and path != '/cluster/sdn/lock':
        fields['lock-token'] = LOCK_TOKEN
    args = ['pvesh', method, path, '--output-format', 'json']
    for k,v in fields.items():
        args += ['--' + k, str(v)]
    p = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(p.stdout or 'null')


def ensure(collection, key, identifier, desired):
    rows = api('get', collection)
    current = next((row for row in rows if row[key] == identifier or (key == 'subnet' and row[key] == 'ocihub-' + identifier.replace('/', '-'))), None)
    if current is None:
        api('create', collection, **{key:identifier}, **desired)
        return True
    # Refuse adopting preexisting objects with incompatible ownership/topology.
    if any(str(current.get(k, '0' if v == 0 else '')) != str(v) for k,v in desired.items()):
        raise ValueError('existing SDN object differs; inspect and reconcile explicitly')
    return False


if __name__ == '__main__':
    c = validate(json.loads(Path(sys.argv[1]).read_text()))
    if c['kind'] != 'pve' or c['node'] != 'pve2':
        raise ValueError('SDN node/profile mismatch')
    # Refuse unrelated pending changes and serialize all SDN writers. An older
    # API without this capability fails before any object is created.
    LOCK_TOKEN = api('create', '/cluster/sdn/lock', **{'allow-pending':0})
    try:
        changed = ensure('/cluster/sdn/zones', 'zone', 'ocihub', {'type':'simple', 'nodes':'pve2', 'ipam':'pve'})
        for vm in c['workspaces']:
            changed |= ensure('/cluster/sdn/vnets', 'vnet', vm['vnet'], {'zone':'ocihub'})
            changed |= ensure('/cluster/sdn/vnets/'+vm['vnet']+'/subnets', 'subnet', vm['subnet'], {'type':'subnet','gateway':vm['gateway'],'snat':0})
        if changed:
            api('set', '/cluster/sdn', **{'release-lock':0})
        print('changed' if changed else 'unchanged')
    finally:
        api('delete', '/cluster/sdn/lock', **{'lock-token':LOCK_TOKEN})
