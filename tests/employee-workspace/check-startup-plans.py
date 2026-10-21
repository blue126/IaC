#!/usr/bin/env python3
"""Assert runtime flags from terraform test -json -verbose, not source strings."""
import json
import sys

expected = {'bootstrap': False, 'ready': True, 'disabled': False}
seen = set()
empty_seen = False
for row in map(json.loads, open(sys.argv[1])):
    if 'test_plan' not in row:
        continue
    name = row['@testrun']
    changes = row['test_plan'].get('resource_changes', [])
    if name == 'empty':
        assert not [change for change in changes if change['mode'] == 'managed']
        empty_seen = True
    if name not in expected:
        continue
    for change in changes:
        if change['address'].startswith('proxmox_virtual_environment_vm.employee_workspace') and change['type'] == 'proxmox_virtual_environment_vm':
            after = change['change']['after']
            assert after['started'] == expected[name], (name, 'started')
            assert after['on_boot'] == expected[name], (name, 'on_boot')
            assert after['network_device'][0]['disconnected'] == (name == 'disabled'), (name, 'disconnected')
            seen.add(name)
            print(json.dumps({'case': name, 'started': after['started'], 'on_boot': after['on_boot'], 'disconnected': after['network_device'][0]['disconnected']}))
assert empty_seen and seen == set(expected), 'Missing planned scenario'
