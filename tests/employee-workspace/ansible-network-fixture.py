#!/usr/bin/env python3
"""Run real disable tasks with namespaced modules; fake only systemd, WG and qm.

The Sandbox has no systemd/PVE. The systemctl transport executes the production
firewall controller against real kernel tables. qm deliberately fails. No rule,
task ordering, nft command, or Ansible module is mocked.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import yaml


def disable(root, names, config, after_reload=None, after_pve_failure=None, after_gateway_failure=None, after_retry=None):
    source = root / 'ansible/roles/employee-access'
    with tempfile.TemporaryDirectory(prefix='employee-disable-ansible-') as temp:
        base = Path(temp)
        role = base / 'roles/employee-access'
        shutil.copytree(source, role, ignore=shutil.ignore_patterns('__pycache__'))
        # Relocate managed files into this test directory, preserving task behavior.
        for path in role.rglob('*'):
            if not path.is_file():
                continue
            content = path.read_text().replace('/etc/employee-access.nft', str(base / ('pve.nft' if path.name == 'pve.yml' else 'gw.nft')))
            content = content.replace('/etc/systemd/system/employee-firewall.service', str(base / 'employee-firewall.service'))
            content = content.replace('/usr/local/lib/employee-firewall.py', str(base / 'installed-firewall.py'))
            content = content.replace('/etc/wireguard/wg-employee.conf', str(base / 'wg.conf'))
            path.write_text(content)
        (role / 'tasks/sync-wireguard.yml').write_text(yaml.safe_dump([{'name': 'Stub WireGuard transport only', 'ansible.builtin.command': '/bin/true', 'changed_when': False}]))
        binaries = base / 'bin'
        binaries.mkdir()
        controller = source / 'files/employee-firewall.py'
        (binaries / 'systemctl').write_text(f'''#!{sys.executable}
import importlib.util,os,pathlib,sys
args=sys.argv[1:]
if 'show' in args:
 print('LoadState=loaded\\nActiveState=active\\nSubState=exited\\nUnitFileState=enabled')
elif 'is-enabled' in args: print('enabled')
elif 'restart' in args:
 raise SystemExit('Unexpected firewall restart would stop dependent SSH services')
elif any(a in args for a in ('start','reload')):
 host=os.environ['EMPLOYEE_TEST_HOST']
 spec=importlib.util.spec_from_file_location('firewall',{str(controller)!r})
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.POLICY=pathlib.Path({str(base)!r})/(host+'.nft')
 m.APPLIED=pathlib.Path({str(base)!r})/(host+'.applied.json')
 if (pathlib.Path({str(base)!r})/('fail-'+host)).exists():
  if host=='gw': m.routing(False)
  raise SystemExit('TEST-'+host.upper()+'-LOAD-FAILURE')
 m.apply(host=='gw')
''')
        (binaries / 'systemctl').chmod(0o755)
        (binaries / 'qm').write_text(f'#!/bin/bash\ntouch "{base}/qm-called"\necho TEST-QM-FAILURE >&2\nexit 42\n')
        (binaries / 'qm').chmod(0o755)
        hosts = {}
        for host in ('gw', 'pve'):
            interpreter = base / (host + '-python')
            interpreter.write_text(f'#!/bin/bash\nexport EMPLOYEE_TEST_HOST={host}\nexec ip netns exec {names[host]} {sys.executable} "$@"\n')
            interpreter.chmod(0o755)
            hosts[host] = {'ansible_connection': 'local', 'ansible_python_interpreter': str(interpreter)}
        inventory = base / 'inventory.yml'
        inventory.write_text(yaml.safe_dump({'all': {'hosts': hosts}}))
        values = {'employee_access_' + k: v for k, v in config.items()}
        values.update(employee_access_devices={}, employee_access_vmid=config['gateway_vmid'], employee_access_pve_host='pve', employee_access_action='disable', employee_disable_kind='employee', employee_disable_id='alice', employee_access_wireguard_private_key='OFFLINE_PLACEHOLDER')
        play = [{'name': 'Run actual employee disable until simulated qm failure', 'hosts': 'gw', 'gather_facts': False, 'vars': values,
                 'environment': {'PATH': str(binaries) + ':' + os.environ['PATH']}, 'roles': ['employee-access']}]
        playbook = base / 'disable.yml'
        playbook.write_text(yaml.safe_dump(play))
        env = dict(os.environ, ANSIBLE_CONFIG=str(root / 'tests/ci/fixtures/ansible.cfg'), ANSIBLE_ROLES_PATH=str(base / 'roles'))
        # Replay the actual routine deployment task on unchanged policy first.
        original = copy.deepcopy(config)
        original['networks']['alice']['disabled'] = False
        fixture_spec = __import__('importlib.util', fromlist=['util'])
        offline_spec = fixture_spec.spec_from_file_location('offline', root / 'tests/employee-workspace/test-offline.py')
        offline = fixture_spec.module_from_spec(offline_spec)
        offline_spec.loader.exec_module(offline)
        (base / 'gw.nft').write_text(offline.render('nftables.conf.j2', original))
        deploy = yaml.safe_load((role / 'tasks/gateway-network.yml').read_text())
        reload_task = next(task for task in deploy if task['name'] == 'Start gateway firewall before configuring network')
        reload_play = base / 'reload.yml'
        reload_play.write_text(yaml.safe_dump([{'hosts': 'gw', 'gather_facts': False, 'environment': {'PATH': str(binaries) + ':' + os.environ['PATH']}, 'tasks': [reload_task]}]))
        reload_result = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(reload_play)], text=True, input='', capture_output=True, env=env)
        if reload_result.returncode:
            raise RuntimeError(reload_result.stdout + reload_result.stderr)
        if after_reload:
            after_reload()
        for host, callback in [('pve', after_pve_failure), ('gw', after_gateway_failure)]:
            marker = base / ('fail-' + host)
            marker.touch()
            failed = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(playbook)], text=True, input='', capture_output=True, env=env)
            evidence = Path('/tmp/employee-workspace-verify') / ('disable-' + host + '-failure-round2.log')
            evidence.write_text(failed.stdout + failed.stderr)
            if failed.returncode == 0 or ('TEST-' + host.upper() + '-LOAD-FAILURE') not in failed.stdout:
                raise RuntimeError(failed.stdout + failed.stderr)
            if callback:
                callback()
            marker.unlink()
        result = subprocess.run(['/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(playbook)], text=True, input='', capture_output=True, env=env)
        evidence = Path('/tmp/employee-workspace-verify/disable-actual-ansible-round2.log')
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text(result.stdout + result.stderr)
        if not (result.returncode != 0 and 'TEST-QM-FAILURE' in result.stdout and (base / 'qm-called').exists()):
            raise RuntimeError(result.stdout + result.stderr)
        if after_retry:
            after_retry()
        return True
