#!/usr/bin/env python3
"""Exercise filesystem registration, base-firewall coexistence and overwrite guards."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


registration = load('registration_safety', ROOT / 'ansible/roles/hapi-registration/files/hapi-registration.py')
firewall = load('hapi_firewall_safety', ROOT / 'ansible/roles/hapi-registration/files/hapi-firewall.py')
base = load('employee_firewall_safety', ROOT / 'ansible/roles/employee-access/files/employee-firewall.py')


class SafetyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hapi-registration-safety-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.policy = self.root / 'hapi-firewall.json'
        self.policy.write_text(json.dumps({'version': 1, 'server': '10.77.0.1', 'workers': ['10.77.0.4']}))
        self.addCleanup(patch.stopall)
        patch.object(firewall, 'POLICY', self.policy).start()
        self.guard = {'rule': {'family': 'inet', 'table': 'employee_access', 'chain': 'input', 'expr': [
            {'match': {'op': 'in', 'left': {'ct': {'key': 'state'}}, 'right': 'invalid'}}, {'drop': None}]}}
        self.before = [{'nftables': [self.guard]}, {'nftables': []}]

    def test_extension_apply_is_idempotent_and_does_not_write_base_policy(self):
        snapshot = copy.deepcopy(self.before[0])
        with patch.object(firewall.subprocess, 'check_output', side_effect=lambda *a, **k: json.dumps(snapshot)), \
                patch.object(firewall.subprocess, 'run') as run:
            firewall.apply()
            self.assertEqual(run.call_count, 2)
            body = json.loads(run.call_args.kwargs['input'])
            snapshot['nftables'].append(body['nftables'][0]['add'])
            run.reset_mock();firewall.apply();run.assert_not_called()
        self.assertEqual(firewall.without_extension([snapshot, {'nftables': []}]), self.before)
        self.assertEqual(json.loads(self.policy.read_text())['workers'], ['10.77.0.4'])

    def test_extension_cannot_hide_a_modified_extra_or_misordered_rule(self):
        good = firewall.rule('10.77.0.4', '10.77.0.1')
        cases = [[good, self.guard], [self.guard], [self.guard, good, good],
                 [self.guard, firewall.rule('10.77.0.99', '10.77.0.1')]]
        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                firewall.without_extension([{'nftables': rows}])

    def test_forward_chain_invalid_guard_is_not_confused_with_input_ordering(self):
        forward = copy.deepcopy(self.guard);forward['rule']['chain'] = 'forward'
        rows = [self.guard, firewall.rule('10.77.0.4', '10.77.0.1'), forward]
        self.assertEqual(firewall.without_extension([{'nftables': rows}]), [{'nftables': [self.guard, forward]}])

    def test_base_verify_keeps_its_original_digest_and_ignores_only_exact_extension(self):
        policy = self.root / 'employee-access.nft';policy.write_text('synthetic immutable nft text')
        applied = self.root / 'applied.json'
        applied.write_text(json.dumps({'sha256': base.hashlib.sha256(policy.read_bytes()).hexdigest(), 'tables': self.before}))
        actual = copy.deepcopy(self.before);actual[0]['nftables'] += [firewall.rule('10.77.0.4', '10.77.0.1')]
        with patch.object(base, 'POLICY', policy), patch.object(base, 'APPLIED', applied), \
                patch.object(base, 'hapi_extension', return_value=firewall), patch.object(base, 'snapshot', return_value=actual), \
                patch.object(base.Path, 'read_text', autospec=True, side_effect=lambda p, *a, **k:
                    '1' if str(p) == '/proc/sys/net/ipv4/ip_forward' else p.read_bytes().decode()):
            base.verify(True)
            actual[0]['nftables'][0]['rule']['chain'] = 'changed'
            with self.assertRaises((ValueError, RuntimeError)):
                base.verify(True)

    def test_base_reload_replays_extension_after_recording_the_unchanged_baseline(self):
        policy = self.root / 'employee-access.nft';policy.write_text('immutable base policy')
        applied = self.root / 'applied.json'
        extension = unittest.mock.Mock()
        def replay():
            saved = json.loads(applied.read_text())
            self.assertEqual(saved['tables'], self.before)
            self.assertEqual(saved['sha256'], base.hashlib.sha256(policy.read_bytes()).hexdigest())
        extension.apply.side_effect = replay
        with patch.object(base, 'POLICY', policy), patch.object(base, 'APPLIED', applied), \
                patch.object(base, 'snapshot', return_value=self.before), patch.object(base, 'routing') as routing, \
                patch.object(base, 'hapi_extension', return_value=extension), patch.object(base.subprocess, 'run'):
            base.apply(True)
            extension.apply.assert_called_once()
            self.assertEqual(routing.call_args_list, [unittest.mock.call(False), unittest.mock.call(True)])
        self.assertEqual(policy.read_text(), 'immutable base policy')

    def test_hapi_failure_after_base_reload_does_not_disable_wireguard_forwarding(self):
        policy = self.root / 'base.nft';policy.write_text('immutable base policy')
        extension = unittest.mock.Mock();extension.apply.side_effect = ValueError('invalid HAPI extension')
        with patch.object(base, 'POLICY', policy), patch.object(base, 'APPLIED', self.root / 'applied.json'), \
                patch.object(base, 'snapshot', return_value=self.before), patch.object(base, 'routing') as routing, \
                patch.object(base, 'hapi_extension', return_value=extension), patch.object(base.subprocess, 'run'):
            with contextlib.redirect_stderr(io.StringIO()) as error:
                base.apply(True)
            self.assertIn('HAPI firewall extension failed', error.getvalue())
            self.assertEqual(routing.call_args_list, [unittest.mock.call(False), unittest.mock.call(True)])
        tasks = yaml.safe_load((ROOT / 'ansible/roles/hapi-registration/tasks/main.yml').read_text())
        self.assertFalse(any(task.get('ansible.builtin.copy', {}).get('dest') == '/usr/local/lib/employee-firewall.py'
                             for task in tasks))
        self.assertTrue(any(task.get('ansible.builtin.stat', {}).get('path') == '/usr/local/lib/employee-firewall.py'
                            for task in tasks))

    def test_real_process_exit_is_successful_only_when_the_base_policy_loaded(self):
        # The service has ExecStopPost=ip_forward=0: a successful base start must exit zero.
        controller = ROOT / 'ansible/roles/employee-access/files/employee-firewall.py'
        script = """import importlib.util,json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('controller',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=Path(sys.argv[2]);mode=sys.argv[3]
m.POLICY=root/'base.nft';m.POLICY.write_text('synthetic base policy');m.APPLIED=root/'applied.json'
m.APPLIED.write_text(json.dumps({'sha256':m.hashlib.sha256(m.POLICY.read_bytes()).hexdigest(),'tables':[{'nftables':[]}]}))
forward=root/'forward';forward.write_text('1')
def routing(enabled):forward.write_text(str(int(enabled)))
def fail():raise ValueError('synthetic extension failure')
extension=SimpleNamespace(apply=fail,without_extension=lambda value:fail())
def nft(*a,**k):
 if mode=='base-failure':raise subprocess.CalledProcessError(1,['synthetic-nft'])
with patch.object(m,'routing',side_effect=routing),patch.object(m,'snapshot',return_value=[{'nftables':[]}]),patch.object(m,'hapi_extension',return_value=extension),patch.object(m.subprocess,'run',side_effect=nft):
 sys.argv=['controller','verify' if mode=='verify' else 'apply','--routing'];m.main()
"""
        for mode, success, forwarding in [('extension-failure', True, '1'), ('base-failure', False, '0'), ('verify', False, '1')]:
            folder = self.root / mode;folder.mkdir()
            result = subprocess.run(['/opt/iac-venv/bin/python', '-c', script, str(controller), str(folder), mode], capture_output=True)
            self.assertEqual(result.returncode == 0, success, result.stderr.decode())
            self.assertEqual((folder / 'forward').read_text(), forwarding)
            if success:
                self.assertIn(b'HAPI firewall extension failed', result.stderr)

    def test_both_static_roles_refuse_before_any_write_when_application_is_owned(self):
        for role in ['hapi-shared-hub', 'hapi-control-plane']:
            folder = self.root / role;folder.mkdir();(folder / 'alice.json').write_text('{}')
            tasks = yaml.safe_load((ROOT / 'ansible/roles' / role / 'tasks/main.yml').read_text())[0:2]
            tasks[0]['ansible.builtin.find']['paths'] = str(folder)
            sentinel = folder / 'overwritten'
            tasks.append({'name': 'Would overwrite the live registry', 'ansible.builtin.copy': {'dest': str(sentinel), 'content': 'bad'}})
            play = self.root / (role + '.yml')
            play.write_text(yaml.safe_dump([{'name': 'Verify overwrite guard', 'hosts': 'localhost', 'gather_facts': False, 'tasks': tasks}]))
            result = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)], capture_output=True)
            self.assertNotEqual(result.returncode, 0, result.stdout.decode())
            self.assertIn(b'Application-managed registrations exist', result.stdout)
            self.assertFalse(sentinel.exists())

    def test_controller_mismatch_blocks_registration_but_not_failure_cleanup(self):
        role = ROOT / 'ansible/roles/hapi-registration'
        source = ROOT / 'ansible/roles/employee-access/files/employee-firewall.py'
        tasks = yaml.safe_load((role / 'tasks/main.yml').read_text())
        guards = [copy.deepcopy(task) for task in tasks if task['name'] in [
            'Inspect the separately deployed shared firewall controller for registration',
            'Require the approved extension-aware firewall controller without replacing it']]
        first_copy = next(i for i, task in enumerate(tasks) if 'ansible.builtin.copy' in task)
        self.assertLess(tasks.index(guards[1]), first_copy)
        controller = self.root / 'controller.py'
        guards[0]['ansible.builtin.stat']['path'] = str(controller)
        for action, contents, expected in [('register', 'older deployed controller', False),
                                           ('register', source.read_text(), True), ('block', 'older deployed controller', True)]:
            controller.write_text(contents)
            play = self.root / 'controller-check.yml'
            play.write_text(yaml.safe_dump([{'name': 'Check shared controller ownership', 'hosts': 'localhost',
                'gather_facts': False, 'vars': {'role_path': str(role), 'hapi_registration_command': {'action': action}},
                'tasks': guards}]))
            result = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)], capture_output=True)
            self.assertEqual(result.returncode == 0, expected, result.stdout.decode() + result.stderr.decode())
            self.assertEqual(controller.read_text(), contents)

    def test_real_registration_main_preserves_base_file_and_retries_filesystem_merge(self):
        hub = self.root / 'hub';gateway = self.root / 'gateway';owners = self.root / 'owners'
        hub.mkdir();gateway.mkdir()
        config = {'origin': 'https://hapi.example.invalid', 'issuer': 'issuer', 'audience': 'aud', 'shared_hub': True, 'routes': []}
        (gateway / 'config.json').write_text(json.dumps(config))
        bob = {'id': 'hapi-bob', 'namespace': 'workspace_bob', 'token': 'b' * 64, 'generation': 1, 'enabled': True}
        (hub / 'credentials.json').write_text(json.dumps({'version': 1, 'credentials': [bob]}))
        (hub / 'agents.json').write_text(json.dumps({'version': 1, 'agents': []}))
        (hub / 'nginx.conf').write_text(''.join('    map "$remote_addr|$ssl_client_s_dn" $' + var + ' {\n        default "";\n    }\n' for var in ['hapi_namespace', 'hapi_credential']))
        for folder in [hub, gateway]:
            for name in ['ca.pem', 'crl.pem']:
                (folder / name).write_text('')
        owner = {'request_id': 'a' * 32, 'workspace_id': 'alice', 'vmid': 550, 'address': '10.77.0.4', 'namespace': 'workspace_alice'}
        row = {'id': 'hapi-alice', 'namespace': 'workspace_alice', 'token': 'a' * 64, 'generation': 1, 'enabled': True}
        command = config | {'kind': 'hapi-application-on-vm500', 'vmid': 500, 'action': 'register', 'owner': owner,
            'email': 'alice@example.invalid', 'server_address': '10.77.0.1', 'credential': row,
            'material': {'owner': owner, 'api_token': row['token'], 'ca': '', 'crl': ''},
            'registry_rows': {r['id']: registration.digest(r) for r in [bob, row]}}
        path = self.root / 'command.json';path.write_text(json.dumps(command))
        auth = self.root / 'auth.py';auth.write_text('import json\ndef load_config(path): return json.loads(path.read_bytes())\n')
        original_spec = registration.importlib.util.spec_from_file_location
        def spec(name, location):
            if name == 'hapi_firewall':
                return SimpleNamespace(name=name, loader=SimpleNamespace(exec_module=lambda module: None))
            return original_spec(name, auth if str(location).endswith('hapi-auth.py') else location)
        # Exercise real atomic writes and merge logic, replacing only privileged subprocess/ownership operations.
        with patch.object(registration, 'HUB', hub), patch.object(registration, 'GATEWAY', gateway), \
                patch.object(registration, 'OWNERS', owners), patch.object(registration, 'run'), \
                patch.object(registration.os, 'chown'), patch.object(registration.sys, 'argv', ['register', str(path)]), \
                patch.object(registration.importlib.util, 'spec_from_file_location', side_effect=spec), \
                patch.object(registration.importlib.util, 'module_from_spec', wraps=registration.importlib.util.module_from_spec) as module:
            real_module = module._mock_wraps
            def make(specification):
                if specification.name == 'hapi_firewall':
                    return firewall
                return real_module(specification)
            module.side_effect = make
            # The fixed production policy location is substituted only at the Path boundary.
            real_path = registration.Path
            with patch.object(registration, 'Path', side_effect=lambda p: self.policy if str(p) == '/etc/hapi-application/firewall.json' else real_path(p)), \
                    patch.object(firewall, 'apply') as apply, contextlib.redirect_stdout(io.StringIO()):
                registration.main();registration.main()
                self.assertEqual(apply.call_count, 2)
        self.assertEqual(json.loads((hub / 'credentials.json').read_text())['credentials'], [bob, row])
        self.assertEqual(json.loads((owners / 'alice.json').read_text()), owner)
        self.assertEqual(json.loads(self.policy.read_text())['workers'], ['10.77.0.4'])


if __name__ == '__main__':
    unittest.main()
