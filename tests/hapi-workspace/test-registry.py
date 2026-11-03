#!/usr/bin/env python3
"""VM500 registry rendering (story 5.24): the owner pilot is kept, everything else is the D1 list."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('registry', ROOT / 'ansible/roles/hapi-registry/files/hapi-registry.py')
registry = importlib.util.module_from_spec(spec); spec.loader.exec_module(registry)

OWNER_ROUTE = {'workspace_id': 'vm502', 'email': 'owner@example.test', 'subject': 'fixed', 'enabled': True, 'generation': 1,
               'backend_address': '10.236.2.2', 'backend_name': 'vm502.hapi.internal', 'namespace': 'default'}
CONFIG = {'origin': 'https://hapi.example.test', 'issuer': 'https://team.example', 'audience': 'aud', 'shared_hub': True,
          'routes': [OWNER_ROUTE, {**OWNER_ROUTE, 'workspace_id': 'gone', 'email': 'gone@example.test', 'backend_address': '10.236.9.2',
                                   'backend_name': 'gone.hapi.internal', 'namespace': 'gone'}]}
CREDENTIALS = {'version': 1, 'credentials': [{'id': 'vm502', 'token': 'o' * 40, 'namespace': 'default', 'generation': 1, 'enabled': True},
                                             {'id': 'gone', 'token': 'g' * 40, 'namespace': 'gone', 'generation': 1, 'enabled': True}]}
AGENTS = {'version': 1, 'agents': [{'id': 'vm502', 'address': '10.236.2.2', 'namespace': 'default', 'credential_id': 'vm502'},
                                   {'id': 'gone', 'address': '10.236.9.2', 'namespace': 'gone', 'credential_id': 'gone'}]}


class Registry(unittest.TestCase):
    def test_owner_kept_retired_dropped_employees_added_with_unbound_subjects(self):
        desired = {'static_ids': ['vm502'], 'employees': [{'id': 'casey', 'email': 'casey@example.test', 'address': '10.236.9.2', 'token': 'c' * 40}]}
        config, credentials, agents, tokens = registry.render(desired, CONFIG, CREDENTIALS, AGENTS)
        self.assertEqual([r['workspace_id'] for r in config['routes']], ['vm502', 'casey'])
        self.assertEqual(config['routes'][0], OWNER_ROUTE)
        self.assertEqual(config['routes'][1], {'workspace_id': 'casey', 'email': 'casey@example.test', 'subject': '', 'enabled': True,
                                               'generation': 1, 'backend_address': '10.236.9.2', 'backend_name': 'casey.hapi.internal', 'namespace': 'casey'})
        self.assertEqual({k: config[k] for k in ('origin', 'issuer', 'audience', 'shared_hub')}, {k: CONFIG[k] for k in ('origin', 'issuer', 'audience', 'shared_hub')})
        self.assertEqual([r['id'] for r in credentials['credentials']], ['vm502', 'casey'])
        self.assertEqual([r['namespace'] for r in credentials['credentials']], ['default', 'casey'])
        self.assertEqual(credentials['credentials'][0]['token'], 'o' * 40)
        self.assertEqual([(a['id'], a['address']) for a in agents['agents']], [('vm502', '10.236.2.2'), ('casey', '10.236.9.2')])
        self.assertEqual(tokens, {'casey': 'c' * 40})


if __name__ == '__main__': unittest.main()
