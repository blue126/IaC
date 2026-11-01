#!/usr/bin/env python3
"""Run native authorization tasks without a legacy gateway fixture."""
import base64
import copy
import getpass
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/employee-workspace'
spec = importlib.util.spec_from_file_location('hub_access', ROLE / 'files/validate-hub-access.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def main():
    with tempfile.TemporaryDirectory(prefix='oci-mosh-authorization-') as directory:
        base = Path(directory)
        authorized = base / 'authorized_keys'
        keys = []
        for index in range(3):
            key = base / f'key-{index}'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
            keys.append(key.with_suffix('.pub').read_text().strip())
        devices = [{'address': '10.235.0.2', 'ssh_public_key': keys[1]},
                   {'address': '10.235.0.3', 'ssh_public_key': keys[2]}]
        validator.validate(devices)
        for change in ('newline', 'wildcard', 'duplicate', 'key_options', 'malformed_key'):
            invalid = copy.deepcopy(devices)
            if change == 'newline': invalid[0]['ssh_public_key'] += '\n' + keys[0]
            if change == 'wildcard': invalid[0]['address'] = '10.235.0.0/24'
            if change == 'duplicate': invalid[1]['address'] = invalid[0]['address']
            if change == 'key_options': invalid[0]['ssh_public_key'] = 'from="*" ' + keys[0]
            if change == 'malformed_key': invalid[0]['ssh_public_key'] = 'ssh-ed25519 ' + base64.b64encode(b'wrong').decode()
            try:
                validator.validate(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError('accepted invalid public authorization: ' + change)

        def tasks(name):
            # Execute repository task bodies, redirecting only their target file.
            text = (ROLE / 'tasks' / name).read_text()
            text = text.replace('/home/{{ employee_workspace_user }}/.ssh/authorized_keys', str(authorized))
            return yaml.safe_load(text)

        variables = dict(employee_workspace_profile='oci-hub', employee_workspace_id='alice',
                         employee_workspace_user=getpass.getuser(),oci_hub_workspace_devices=devices,role_path=str(ROLE))
        (base/'inventory.yml').write_text(yaml.safe_dump({'all':{'hosts':{'vm':{'ansible_connection':'local'}}}}))
        env=dict(os.environ,ANSIBLE_CONFIG=str(ROOT/'tests/ci/fixtures/ansible.cfg'))
        def apply(expect_success=True):
            play=[{'name':'Exercise actual native authorization','hosts':'vm','gather_facts':False,
                   'vars':variables,'tasks':tasks('authorization-preflight.yml')+tasks('authorization.yml')}]
            (base/'play.yml').write_text(yaml.safe_dump(play,sort_keys=False))
            p=subprocess.run(['ansible-playbook','-i',str(base/'inventory.yml'),str(base/'play.yml')],env=env,capture_output=True,text=True)
            if (p.returncode==0)!=expect_success:raise AssertionError(p.stdout+p.stderr)
        apply();first=authorized.read_bytes();apply();assert authorized.read_bytes()==first
        assert keys[1] in authorized.read_text() and keys[2] in authorized.read_text()
        variables['oci_hub_workspace_devices']=devices[1:];apply()
        assert keys[1] not in authorized.read_text() and keys[2] in authorized.read_text()
        saved=authorized.read_bytes();variables['oci_hub_workspace_devices']=[{'address':'0.0.0.0/0','ssh_public_key':keys[0]}];apply(False);assert authorized.read_bytes()==saved
        variables['oci_hub_workspace_devices']=[];apply();assert not any(line.strip() and not line.startswith('#') for line in authorized.read_text().splitlines())
        variables['oci_hub_workspace_devices']=devices
        for marker in ('Managed company access;','BEGIN OCI Hub parallel device access'):
            authorized.write_text('# '+marker+'\n'+keys[0]+'\n');saved=authorized.read_bytes();apply(False);assert authorized.read_bytes()==saved
        authorized.write_text('');variables['employee_workspace_profile']='existing';apply(False);assert authorized.read_text()==''
        print('PASS: native roster reconcile/idempotency, device removal, empty roster, invalid input and legacy authorization rejection')

if __name__=='__main__':main()
