#!/usr/bin/env python3
"""Run actual Ansible copy tasks to prevent static Vault replay over managed TLS."""
import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class OwnershipTest(unittest.TestCase):
    def test_ordinary_service_roles_preserve_managed_tls_and_still_install_unmanaged_tls(self):
        if not os.environ.get('SANDBOX_ID'):
            self.skipTest('requires the approved Ansible Sandbox')
        for role, source in [('hapi-control-plane', 'main'), ('hapi-shared-hub', 'main'),
                             ('hapi-hub-client', 'main'), ('hapi-ingress', 'backend')]:
            tasks = yaml.safe_load((ROOT / 'ansible/roles' / role / 'tasks' / (source + '.yml')).read_text())
            marker = copy.deepcopy(tasks[0])
            tls = next(copy.deepcopy(task) for task in tasks if 'ansible.builtin.copy' in task and
                       isinstance(task.get('loop'), list) and any(row.get('name') == 'ca.pem' for row in task['loop'] if isinstance(row, dict)))
            for managed in [False, True]:
                with self.subTest(role=role, managed=managed), tempfile.TemporaryDirectory(prefix='hapi-pki-owner-') as folder:
                    root = Path(folder);marker['ansible.builtin.stat']['path'] = str(root / 'managed.json')
                    if managed:(root / 'managed.json').write_text('{}')
                    values = {}
                    for row in tls['loop']:
                        values[row['content'].strip('{} ')] = 'stale-vault-input'
                        (root / row['name']).write_text('current-managed-material')
                    copy_task = tls['ansible.builtin.copy']
                    copy_task['dest'] = str(root) + '/{{ item.name }}'
                    copy_task.pop('owner', None);copy_task.pop('group', None);tls.pop('notify', None)
                    play = root / 'check.yml'
                    play.write_text(yaml.safe_dump([{'name': 'Verify certificate ownership', 'hosts': 'localhost',
                        'gather_facts': False, 'vars': values, 'tasks': [marker, tls]}]))
                    env = os.environ | {'ANSIBLE_CONFIG': str(ROOT / 'tests/ci/fixtures/ansible.cfg')}
                    result = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)], env=env, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stdout.decode() + result.stderr.decode())
                    for row in tls['loop']:
                        self.assertEqual((root / row['name']).read_text(), 'current-managed-material' if managed else 'stale-vault-input')


if __name__ == '__main__':
    unittest.main()
