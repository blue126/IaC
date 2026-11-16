#!/usr/bin/env python3
"""Run the actual login.yml browser tasks against temporary files.

The KasmVNC activation owns employee-browser.service and mode=kasmvnc; a later
employee-workspace run must not restore the legacy auth-browser.py unit.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/employee-workspace'
CONFIG = '/etc/employee-workspace-browser.json'
UNIT = '/etc/systemd/system/employee-browser.service'
TASKS = ('Read the current browser backend selection',
         'Detect whether the KasmVNC desktop owns the browser service',
         'Configure the VM-owned authorization viewer',
         'Install the employee browser service without restarting personal sessions')


def main():
    with tempfile.TemporaryDirectory(prefix='workspace-login-unit-') as directory:
        base = Path(directory)
        config, unit = base / 'browser.json', base / 'employee-browser.service'

        def tasks():
            # Execute the repository task bodies, redirecting only their targets.
            text = (ROLE / 'tasks/login.yml').read_text().replace(CONFIG, str(config)).replace(UNIT, str(unit))
            selected = [task for task in yaml.safe_load(text) if task.get('name') in TASKS]
            assert [task['name'] for task in selected] == list(TASKS), selected
            for task in selected:
                task.get('ansible.builtin.copy', {}).pop('owner', None)
                task.get('ansible.builtin.copy', {}).pop('group', None)
            return selected

        (base / 'inventory.yml').write_text(yaml.safe_dump({'all': {'hosts': {'vm': {'ansible_connection': 'local'}}}}))
        env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'tests/ci/fixtures/ansible.cfg'),
                   ANSIBLE_LOCAL_TEMP=str(base / 'ansible-tmp'), ANSIBLE_REMOTE_TEMP=str(base / 'ansible-tmp'))

        def apply():
            play = [{'name': 'Exercise actual login browser tasks', 'hosts': 'vm', 'gather_facts': False,
                     'vars': {'employee_workspace_viewer_url': 'http://192.0.2.10:8443/vnc.html'},
                     'tasks': tasks()}]
            (base / 'play.yml').write_text(yaml.safe_dump(play, sort_keys=False))
            p = subprocess.run(['ansible-playbook', '-i', str(base / 'inventory.yml'), str(base / 'play.yml')],
                               env=env, capture_output=True, text=True)
            if p.returncode:
                raise AssertionError(p.stdout + p.stderr)
            return p.stdout

        # Fresh VM: the legacy viewer config and auth-browser.py unit are installed.
        apply()
        assert json.loads(config.read_text()) == {'bind_address': '127.0.0.1', 'viewer_url': 'http://192.0.2.10:8443/vnc.html'}
        assert 'auth-browser.py' in unit.read_text(), unit.read_text()
        assert 'changed=0' in apply()

        # After KasmVNC activation both files belong to prepare-desktop.py.
        kasm_config = json.dumps({'bind_address': '127.0.0.1', 'viewer_url': 'http://192.0.2.10:8443/vnc.html',
                                  'mode': 'kasmvnc'}, indent=2) + '\n'
        kasm_unit = (ROLE / 'files/employee-browser.service').read_text()
        config.write_text(kasm_config)
        unit.write_text(kasm_unit)
        output = apply()
        assert 'changed=0' in output, output
        assert config.read_text() == kasm_config
        assert unit.read_text() == kasm_unit

        # A legacy config without a mode is still reconciled as before.
        config.write_text(json.dumps({'bind_address': '127.0.0.1', 'viewer_url': 'http://old.invalid/'}))
        apply()
        assert 'mode' not in json.loads(config.read_text())
        assert 'auth-browser.py' in unit.read_text()
    print('login browser unit ownership: ok')


if __name__ == '__main__':
    main()
