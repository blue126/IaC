#!/usr/bin/env python3
"""Exercise actual Ansible consent/proof gates and rollback member validation locally."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/hapi-internal-http'


class MigrationGuards(unittest.TestCase):
    def evaluate(self, task, variables, success):
        with tempfile.TemporaryDirectory(prefix='hapi-http-guard-', dir='/tmp') as folder:
            root = Path(folder)
            play = root / 'test.yml'
            play.write_text(yaml.safe_dump([{'name': 'Evaluate the real migration gate', 'hosts': 'localhost',
                'gather_facts': False, 'vars': variables, 'tasks': [task]}]))
            env = os.environ | {'ANSIBLE_CONFIG': str(ROOT / 'tests/ci/fixtures/ansible.cfg'),
                'ANSIBLE_LOCAL_TEMP': str(root / 'local'), 'ANSIBLE_REMOTE_TEMP': str(root / 'remote')}
            result = subprocess.run([str(ROOT / '.venv/bin/ansible-playbook'), '-i', 'localhost,', '-c', 'local', str(play)],
                capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)

    def test_retirement_requires_both_consent_and_successful_live_verification(self):
        first = yaml.safe_load((ROLE / 'tasks/retire.yml').read_text())[0]
        self.assertIn('ansible.builtin.assert', first)
        for consent, verified, expected in [(False, True, False), (True, False, False), (True, True, True)]:
            with self.subTest(consent=consent, verified=verified):
                self.evaluate(first, {'hapi_internal_http_authorized': consent, 'hapi_http_verified': verified}, expected)

    def test_control_endpoint_rejects_wildcard_or_public_listener_addresses(self):
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        task = next(t for t in tasks if t['name'] == 'Restrict the shared Hub listener to the same private control endpoint')
        for address, expected in [('192.168.1.140', True), ('0.0.0.0', False), ('203.0.113.1', False)]:
            with self.subTest(address=address):
                self.evaluate(task, {'hapi_http_is_control': True, 'hapi_shared_hub_bind_address': address,
                    'hapi_shared_hub_origin': 'https://hapi.example.invalid',
                    'hapi_control_plane_origin': 'https://hapi.example.invalid'}, expected)

    def test_root_restore_rejects_members_outside_the_fixed_hapi_file_set(self):
        tasks = yaml.safe_load((ROLE / 'tasks/rollback.yml').read_text())
        task = next(t for t in tasks if t['name'] == 'Restrict checkpoint extraction to the fixed HAPI file set')
        for members, expected in [(['etc/hapi-ingress/nginx.conf'], True), (['etc/shadow'], False),
                                  (['../etc/hapi-ingress/nginx.conf'], False), ([], False)]:
            with self.subTest(members=members):
                self.evaluate(task, {'hapi_http_checkpoint_members': {'stdout_lines': members},
                    'hapi_http_snapshot_paths': ['/etc/hapi-ingress/nginx.conf']}, expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
