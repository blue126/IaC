#!/usr/bin/env python3
"""Execute the real Verify play using synthetic controller state and local-only tools."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[2]
ROLE=ROOT/'ansible/roles/employee-access'
FIXTURE=json.loads(Path(__file__).with_name('fixture.json').read_text())

class MoshVerifyTests(unittest.TestCase):
    def run_verify(self, active=True, drift=False, old_controller=False, invalid=False, disabled=False):
        with tempfile.TemporaryDirectory(prefix='mosh-verify-offline-') as directory:
            base=Path(directory);playdir=base/'ansible/playbooks';playdir.mkdir(parents=True)
            shutil.copytree(ROLE,base/'ansible/roles/employee-access')
            source=ROLE/'files/employee-firewall.py'
            installed=base/'installed-controller.py';installed.write_bytes(b'old-controller' if old_controller else source.read_bytes())
            spec=importlib.util.spec_from_file_location('firewall_fixture',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            guard={'rule':{'family':'inet','table':'employee_access','chain':'input','expr':[{'match':{'op':'==','left':{'ct':{'key':'state'}},'right':'invalid'}},{'drop':None}]}}
            expected=[{'nftables':[guard]},{'nftables':[{'table':{'family':'ip','name':'employee_nat'}}]}]
            actual=copy.deepcopy(expected);actual[0]['nftables'].append(copy.deepcopy(m.OCI_EXTENSION_RULE))
            if drift:actual[1]['nftables']=[]
            (base/'actual.json').write_text(json.dumps(actual));(base/'oci.conf').touch()
            (base/'policy.nft').write_text('synthetic-offline-policy')
            (base/'applied.json').write_text(json.dumps({'sha256':hashlib.sha256((base/'policy.nft').read_bytes()).hexdigest(),'tables':expected}))
            wrapper=base/'verify-controller.py'
            wrapper.write_text("import importlib.util,json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"+
                "s=importlib.util.spec_from_file_location('fw',"+repr(str(source))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"+
                "b=Path("+repr(str(base))+")\n"+
                "m.POLICY=b/'policy.nft';m.APPLIED=b/'applied.json';m.OCI_EXTENSION_UNIT=b/'oci.conf';m.BROWSER_EXTENSION_UNIT=b/'absent-browser.conf'\n"+
                "m.snapshot=lambda gateway:json.loads((b/'actual.json').read_text())\n"+
                "m.Path=lambda name:SimpleNamespace(read_text=lambda:'1') if name=='/proc/sys/net/ipv4/ip_forward' else Path(name)\n"+
                "(b/'full-verify-called').touch();m.verify(True)\n")
            binary=base/'mosh-server'
            if active and not disabled:
                binary.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nPath('+repr(str(base/'version-called'))+').touch()\nprint("mosh-server synthetic")\n');binary.chmod(0o755)
            play=yaml.safe_load((ROOT/'ansible/playbooks/deploy-employee-mosh-pilot.yml').read_text())[1]
            play.update(hosts='fixture',connection='local',become=False)
            values={'employee_access_'+k:v for k,v in copy.deepcopy(FIXTURE).items()}
            values['employee_access_vmid']=FIXTURE['gateway_vmid']
            if not active:values['employee_access_mosh_devices']={}
            if disabled:
                for device in values['employee_access_devices'].values():device['enabled']=False
            if invalid:values['employee_access_mosh_devices']['ed-alice-laptop']['port_start']=1
            play['vars']=values
            for task in play['tasks']:
                if 'ansible.builtin.stat' in task:task['ansible.builtin.stat']['path']=str(installed)
                if 'ansible.builtin.command' in task:
                    command=task['ansible.builtin.command']
                    if 'employee-firewall.py' in command:task['ansible.builtin.command']={'argv':[sys.executable,str(wrapper),'verify','--routing']}
                    elif 'mosh-server' in command:task['ansible.builtin.command']={'argv':[str(binary),'--version']}
            file=playdir/'verify.yml';file.write_text(yaml.safe_dump([play],sort_keys=False))
            inventory=base/'inventory.yml';inventory.write_text(yaml.safe_dump({'all':{'hosts':{'fixture':{'ansible_connection':'local','ansible_python_interpreter':sys.executable}}}}))
            env=dict(os.environ,ANSIBLE_CONFIG=str(ROOT/'tests/ci/fixtures/ansible.cfg'),ANSIBLE_ROLES_PATH=str(base/'ansible/roles'))
            env.pop('ANSIBLE_VAULT_PASSWORD_FILE',None)
            r=subprocess.run(['/opt/iac-venv/bin/ansible-playbook','-i',str(inventory),str(file),'--tags','verify'],env=env,text=True,capture_output=True,timeout=90)
            return r.returncode,(base/'full-verify-called').exists(),(base/'version-called').exists(),r.stdout+r.stderr

    def test_extension_still_receives_full_verification(self):
        rc,full,version,output=self.run_verify();self.assertEqual(rc,0,output);self.assertTrue(full and version)
    def test_empty_mosh_list_does_not_require_mosh_binary(self):
        rc,full,version,output=self.run_verify(active=False);self.assertEqual(rc,0,output);self.assertTrue(full);self.assertFalse(version)
    def test_disabled_entries_can_retain_ports_without_mosh_binary(self):
        rc,full,version,output=self.run_verify(disabled=True);self.assertEqual(rc,0,output);self.assertTrue(full);self.assertFalse(version)
    def test_nat_drift_is_rejected_even_with_extension(self):
        rc,full,version,output=self.run_verify(drift=True);self.assertNotEqual(rc,0,output);self.assertTrue(full);self.assertFalse(version)
    def test_old_controller_is_rejected_before_verification(self):
        rc,full,version,output=self.run_verify(old_controller=True);self.assertNotEqual(rc,0,output);self.assertFalse(full or version)
    def test_invalid_ports_are_rejected_before_runtime_checks(self):
        rc,full,version,output=self.run_verify(invalid=True);self.assertNotEqual(rc,0,output);self.assertFalse(full or version)

if __name__=='__main__':unittest.main(verbosity=2)
