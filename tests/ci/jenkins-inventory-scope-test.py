#!/usr/bin/env python3
"""Real Terraform/cloud.terraform inventory with encrypted, unavailable Vault vars."""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control
transaction=SourceFileLoader('inventory_transaction',str(ROOT/'scripts/jenkins/transaction.py')).load_module()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--terraform',required=True);parser.add_argument('--mirror',required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='peer-inventory-fixture-') as temporary:
        base=Path(temporary);workspace=base/'checkout';project=workspace/'terraform/proxmox';project.mkdir(parents=True)
        ansible=workspace/'ansible';inventory=ansible/'inventory';(inventory/'group_vars/all').mkdir(parents=True)
        (inventory/'host_vars').mkdir();(base/'tmp').mkdir()
        (project/'main.tf').write_text('terraform {\n required_providers {\n ansible = { source = "ansible/ansible", version = "1.3.0" }\n }\n}\n')
        (project/'.terraform.lock.hcl').write_text(re.search(r'provider "registry.terraform.io/ansible/ansible" \{.*?\n}',(ROOT/'terraform/proxmox/.terraform.lock.hcl').read_text(),re.S)[0]+'\n')
        (base/'terraform.rc').write_text('provider_installation { filesystem_mirror { path = '+json.dumps(args.mirror)+' } }')
        env={key:value for key,value in os.environ.items() if not key.startswith(('TF_','ANSIBLE_'))}
        env.update(PATH=str(Path(args.terraform).parent)+':'+env['PATH'],TF_CLI_CONFIG_FILE=str(base/'terraform.rc'),TF_IN_AUTOMATION='1',CHECKPOINT_DISABLE='1')
        subprocess.run([args.terraform,'init','-backend=false','-lockfile=readonly','-input=false','-no-color'],cwd=project,env=env,check=True)
        state={'version':4,'terraform_version':'1.14.4','serial':1,'lineage':'fixture','outputs':{},'resources':[{'mode':'managed','type':'ansible_host','name':'peer','provider':'provider["registry.terraform.io/ansible/ansible"]','instances':[{'schema_version':0,'attributes':{'id':'peer','name':'peer','groups':['fixture_peers'],'variables':{'ansible_host':'192.0.2.110'}}}]}]}
        (project/'terraform.tfstate').write_text(json.dumps(state))
        (inventory/'terraform.yml').write_text(json.dumps({'plugin':'cloud.terraform.terraform_provider','project_path':str(project),'state_file':str(project/'terraform.tfstate')}))
        (ansible/'ansible.cfg').write_text('[defaults]\ninventory = inventory\nvault_password_file = .vault_pass\n')
        password=base/'fixture-password';password.write_text('synthetic-fixture-password\n');password.chmod(0o600)
        encrypted=subprocess.run(['ansible-vault','encrypt','--vault-password-file',str(password),'--output','-'],input='vault_canary: SYNTHETIC_VAULT_ONLY_AFTER_APPROVAL\n',text=True,capture_output=True,env=env,check=True).stdout
        (inventory/'group_vars/all/vault.yml').write_text(encrypted)
        (inventory/'host_vars/peer.yml').write_text('checkout_canary: HOST_VARS_ONLY_AFTER_APPROVAL\n')
        missing=subprocess.run(['ansible-inventory','--list'],cwd=ansible,env=env,text=True,capture_output=True)
        assert missing.returncode!=0,'control fixture must fail without Vault password'
        scope={'hosts':{'peer':'192.0.2.110'},'playbooks':['deploy-fixture.yml'],'variables_source':'checkout'}
        contaminated=dict(env,ANSIBLE_CONFIG=str(ansible/'ansible.cfg'),ANSIBLE_VAULT_PASSWORD_FILE=str(base/'does-not-exist'))
        with patch.object(transaction,'JOB',base),patch.dict(os.environ,contaminated,clear=True):
            result=transaction.inventory_scope(workspace,scope)
            assert result['hosts']=={'peer':{'ansible_host':'192.0.2.110','groups':['fixture_peers']}},result
            assert 'CANARY' not in json.dumps(result)
            assert transaction.inventory_scope(workspace,scope)==result
            state['resources'][0]['instances'][0]['attributes']['groups']=['changed_peers'];(project/'terraform.tfstate').write_text(json.dumps(state))
            assert transaction.inventory_scope(workspace,scope)['inventory_sha256']!=result['inventory_sha256']
            try:transaction.inventory_scope(workspace,dict(scope,hosts={'peer':'192.0.2.111'}))
            except control.Refused:pass
            else:raise AssertionError('changed host address was accepted')
        # Only the post-approval invocation gets the real vars and password.
        after=subprocess.run(['ansible-inventory','--list'],cwd=ansible,env=dict(env,ANSIBLE_VAULT_PASSWORD_FILE=str(password)),text=True,capture_output=True,check=True)
        assert 'SYNTHETIC_VAULT_ONLY_AFTER_APPROVAL' in after.stdout
        assert 'HOST_VARS_ONLY_AFTER_APPROVAL' in after.stdout
        with patch.dict(os.environ,dict(env,ANSIBLE_VAULT_PASSWORD_FILE=str(password)),clear=True):
            transaction.verify_deploy_scope(workspace,result)
            (inventory/'host_vars/peer.yml').write_text('ansible_host: 192.0.2.199\n')
            try:transaction.verify_deploy_scope(workspace,result)
            except control.Refused:pass
            else:raise AssertionError('post-approval host_vars address override was accepted')
            (inventory/'host_vars/peer.yml').unlink()
            changed=subprocess.run(['ansible-vault','encrypt','--vault-password-file',str(password),'--output','-'],input='ansible_host: 192.0.2.198\n',text=True,capture_output=True,env=env,check=True).stdout
            (inventory/'host_vars/peer.yml').write_text(changed)
            try:transaction.verify_deploy_scope(workspace,result)
            except control.Refused:pass
            else:raise AssertionError('post-approval Vault address override was accepted')
        assert encrypted.startswith('$ANSIBLE_VAULT;')
        print('PASS: real Terraform/cloud.terraform public host/IP/group resolution; encrypted Vault unavailable before approval; original vars decrypted only after binding; digest and address changes detected')

if __name__=='__main__':main()
