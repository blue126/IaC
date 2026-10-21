#!/usr/bin/env python3
"""Credential preflight and actual WireGuard address handler in an offline netns."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/employee-access'


def run(*args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=True, **kwargs)


def main():
    if os.geteuid() != 0 or sys.argv[1:] not in [['--run-isolated-runtime'], ['--inside']]:
        raise SystemExit('Use root in the approved Sandbox with --run-isolated-runtime')
    if sys.argv[1] != '--inside':
        return subprocess.call(['unshare', '--net', '--fork', sys.executable, str(Path(__file__).resolve()), '--inside'])
    results = []

    def record(label, ok):
        results.append({'case': label, 'passed': bool(ok)})
        print(json.dumps(results[-1]), flush=True)
        assert ok, label

    with tempfile.TemporaryDirectory(prefix='employee-runtime-') as temp:
        base = Path(temp)
        spec = importlib.util.spec_from_file_location('credential', ROLE / 'files/validate-credentials.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = json.loads(Path(__file__).with_name('fixture.json').read_text())
        config['wireguard_private_key'] = base64.b64encode(os.urandom(32)).decode()
        config['private_keys'] = {}
        for name in config['devices']:
            key = base / name
            run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key))
            config['private_keys'][name] = key.read_text()
        module.validate(config)
        record('valid-required-system-credentials', True)
        for label, mutation in [
            ('missing-system-key', lambda c: c['private_keys'].pop('ed-alice-laptop')),
            ('invalid-system-key', lambda c: c['private_keys'].update({'ed-alice-laptop': 'BROKEN-PRIVATE-KEY'})),
            ('duplicate-system-key', lambda c: c['private_keys'].update({'ed-alice-laptop': c['private_keys']['ed-alice-spare']})),
            ('missing-wireguard-key', lambda c: c.pop('wireguard_private_key')),
            ('invalid-wireguard-key', lambda c: c.update(wireguard_private_key='BROKEN-WG')),
        ]:
            invalid = copy.deepcopy(config)
            mutation(invalid)
            process = subprocess.run([sys.executable, str(ROLE / 'files/validate-credentials.py')], input=json.dumps(invalid), text=True, capture_output=True)
            record(label + '-rejected-without-secret-output', process.returncode != 0 and 'PRIVATE KEY' not in process.stdout + process.stderr and 'BROKEN-' not in process.stdout + process.stderr)
        # Execute actual deploy preflight tasks: missing keys must fail before any write.
        tasks = yaml.safe_load((ROLE / 'tasks/deploy.yml').read_text())
        cutoff = next(i for i, task in enumerate(tasks) if task['name'] == 'Install gateway software for an authorized deployment')
        values = {'employee_access_' + key: value for key, value in config.items()}
        for task in tasks[:cutoff]:
            if task.get('ansible.builtin.include_tasks') == 'validate-network.yml':
                task['ansible.builtin.include_tasks'] = str(ROLE / 'tasks/validate-network.yml')
        values.update(role_path=str(ROLE), employee_access_vmid=config['gateway_vmid'], employee_access_pve_host='pve', employee_access_admin_user='ubuntu')
        values['employee_access_private_keys'] = {}
        inventory = base / 'inventory.yml'
        inventory.write_text(yaml.safe_dump({'all': {'hosts': {'gateway': {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable}, 'pve': {'ansible_connection': 'local'}}}}))
        preflight = base / 'preflight.yml'
        preflight.write_text(yaml.safe_dump([{'hosts': 'gateway', 'gather_facts': False, 'vars': values, 'tasks': tasks[:cutoff]}]))
        env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'tests/ci/fixtures/ansible.cfg'))
        process = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(preflight)], text=True, input='', capture_output=True, env=env)
        record('actual-ansible-preflight-fails-before-mutation', process.returncode != 0 and 'changed=0' in process.stdout and 'censored' in process.stdout and 'PRIVATE KEY' not in process.stdout)
        # Peer synchronization is a transport stub; address reconciliation uses real ip.
        run('ip', 'link', 'add', 'wg-employee', 'type', 'veth', 'peer', 'name', 'wg-test-peer')
        run('ip', 'link', 'set', 'wg-employee', 'up')
        run('ip', 'address', 'add', '10.230.0.1/24', 'dev', 'wg-employee')
        binaries = base / 'bin'
        binaries.mkdir()
        (binaries / 'wg').write_text(f"#!/bin/bash\nif [[ -f {base}/fail-peer-sync ]]; then exit 42; fi\ncat > {base}/applied-peers\n")
        (binaries / 'wg-quick').write_text(f"#!/bin/bash\ncat {base}/wg.conf\n")
        for path in binaries.iterdir():
            path.chmod(0o755)
        for operation in ('deploy', 'disable'):
            operation_tasks = yaml.safe_load((ROLE / ('tasks/' + operation + '.yml')).read_text())
            start_name = 'Deploy WireGuard peer configuration' if operation == 'deploy' else 'Reconcile WireGuard peers after revocation'
            template = copy.deepcopy(next(task for task in operation_tasks if task['name'] == start_name))
            template['ansible.builtin.template']['src'] = str(ROLE / 'templates/wireguard.conf.j2')
            template['ansible.builtin.template']['dest'] = str(base / 'wg.conf')
            sync = copy.deepcopy(next(task for task in operation_tasks if task.get('ansible.builtin.include_tasks') == 'sync-wireguard.yml'))
            sync['ansible.builtin.include_tasks'] = str(ROLE / 'tasks/sync-wireguard.yml')
            state = copy.deepcopy(config)
            if operation == 'disable':
                state['devices']['ed-alice-laptop']['enabled'] = False
            values = {'employee_access_' + key: value for key, value in state.items()}
            values['employee_access_wireguard_address'] = '10.230.0.9/24'
            play = base / 'address.yml'
            play.write_text(yaml.safe_dump([{'hosts': 'gateway', 'gather_facts': False, 'vars': values, 'environment': {'PATH': str(binaries) + ':' + os.environ['PATH']}, 'tasks': [template, sync]}]))
            (base / 'fail-peer-sync').touch()
            failed = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(play)], text=True, input='', capture_output=True, env=env)
            record(operation + '-first-peer-sync-fails', failed.returncode != 0 and (base / 'wg.conf').exists())
            expected = (base / 'wg.conf').read_text()
            (base / 'fail-peer-sync').unlink()
            run('/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(play), env=env, input='')
            addresses = json.loads(run('ip', '-j', '-4', 'address', 'show', 'dev', 'wg-employee').stdout)[0]['addr_info']
            record(operation + '-unchanged-file-retry-syncs-peers-and-address', (base / 'wg.conf').read_text() == expected and (base / 'applied-peers').read_text() == expected and [(a['local'], a['prefixlen']) for a in addresses] == [('10.230.0.9', 24)])
        guard = next(task for task in yaml.safe_load((ROLE / 'tasks/deploy.yml').read_text()) if task['name'] == 'Reject wildcard administrator listeners or extra authorized users')
        for label, lines, expected in [('exact', ['allowusers ubuntu'], True), ('extra', ['allowusers ubuntu attacker'], False), ('prefix', ['allowusers ubuntu-admin'], False), ('pattern', ['allowusers ubuntu *'], False), ('multiple', ['allowusers ubuntu', 'allowusers root'], False)]:
            play.write_text(yaml.safe_dump([{'hosts': 'gateway', 'gather_facts': False, 'vars': {'employee_access_admin_user': 'ubuntu', 'employee_admin_sshd': {'stdout': '\n'.join(lines), 'stdout_lines': lines}}, 'tasks': [guard]}]))
            result = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(play)], text=True, input='', capture_output=True, env=env)
            record('allowusers-' + label, (result.returncode == 0) == expected)
        # Run the real boundary preflight without host keys; a sentinel stands in for PVE mutation.
        boundary_role = base / 'roles/employee-access'
        import shutil
        shutil.copytree(ROLE, boundary_role, ignore=shutil.ignore_patterns('__pycache__'))
        (boundary_role / 'tasks/pve.yml').write_text(yaml.safe_dump([{'name': 'Record reaching boundary mutation', 'ansible.builtin.copy': {'dest': str(base / 'boundary-reached'), 'content': 'yes', 'mode': '0600'}}]))
        boundary_vars = {'employee_access_' + key: value for key, value in config.items()}
        boundary_vars.update(employee_access_host_keys={}, employee_access_vmid=config['gateway_vmid'])
        env['ANSIBLE_ROLES_PATH'] = str(base / 'roles')
        for label in ('valid', 'invalid'):
            if label == 'invalid':
                (base / 'boundary-reached').unlink()
                boundary_vars['employee_access_networks']['alice']['gateway_nic'] = 9
            play.write_text(yaml.safe_dump([{'hosts': 'gateway', 'gather_facts': False, 'vars': boundary_vars, 'tasks': [{'name': 'Run real boundary entry', 'ansible.builtin.include_role': {'name': 'employee-access', 'tasks_from': 'boundary'}}]}]))
            result = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(play)], text=True, input='', capture_output=True, env=env)
            record('boundary-preflight-' + label, (result.returncode == 0) == (label == 'valid') and (base / 'boundary-reached').exists() == (label == 'valid'))
    print(json.dumps({'passed': len(results), 'scope': 'real preflight and ip address tasks; WG peer transport stubbed, no handshake claim'}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
