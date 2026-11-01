#!/usr/bin/env python3
"""Execute the actual Spoke task/handler graph against a synthetic systemctl."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml

ROOT=Path(__file__).resolve().parents[2]
SYSTEMCTL=r'''#!/usr/bin/env python3
import json,os,pathlib,sys
root=pathlib.Path(os.environ['SPOKE_FIXTURE']);path=root/'kernel.json'
state=json.loads(path.read_text());args=sys.argv[1:]
if 'show' in args:
 print('LoadState=loaded\nActiveState='+('active' if state['active'] else 'inactive')+'\nSubState=running\nUnitFileState='+('enabled' if state['enabled'] else 'disabled'))
elif 'is-enabled' in args:
 print('enabled' if state['enabled'] else 'disabled');sys.exit(0 if state['enabled'] else 1)
elif 'is-active' in args:sys.exit(0 if state['active'] else 3)
elif 'enable' in args:state['enabled']=True
elif 'start' in args or 'restart' in args:
 config=(root/'wireguard/wg-workspace.conf').read_text()
 allowed=next(line.split('=',1)[1].strip() for line in config.splitlines() if line.startswith('AllowedIPs'))
 state['active']=True;state['allowed_ips']=sorted(v.strip() for v in allowed.split(','))
 state['routes']=list(state['allowed_ips']);state['activations']+=1
else:
 print('Unexpected synthetic systemctl call: '+repr(args),file=sys.stderr);sys.exit(1)
path.write_text(json.dumps(state))
'''


def main():
    with tempfile.TemporaryDirectory(prefix='oci-hub-spoke-review1-') as directory:
        base=Path(directory);role=base/'roles/fixture-spoke'
        for name in ('tasks','handlers','templates'):(role/name).mkdir(parents=True)
        tasks=yaml.safe_load((ROOT/'ansible/roles/oci-hub-spoke/tasks/vpn.yml').read_text())
        end=next(i for i,t in enumerate(tasks) if t.get('ansible.builtin.meta')=='flush_handlers')+1
        # Redirect only the destination into this fixture; execute original logic.
        for task in tasks[:end]:
            for key,value in task.items():
                if isinstance(value,dict):
                    for field in ('path','dest'):
                        if field in value:value[field]=value[field].replace('/etc/wireguard',str(base/'wireguard'))
        (role/'tasks/main.yml').write_text(yaml.safe_dump(tasks[:end],sort_keys=False))
        shutil.copy2(ROOT/'ansible/roles/oci-hub-spoke/handlers/main.yml',role/'handlers/main.yml')
        shutil.copy2(ROOT/'ansible/roles/oci-hub-spoke/templates/wg-workspace.conf.j2',role/'templates/wg-workspace.conf.j2')
        (base/'bin').mkdir();stub=base/'bin/systemctl';stub.write_text(SYSTEMCTL);stub.chmod(0o755)
        (base/'kernel.json').write_text(json.dumps(dict(active=False,enabled=False,allowed_ips=[],routes=[],activations=0)))
        play=[{'name':'Exercise the deployed Spoke lifecycle','hosts':'localhost','gather_facts':False,'environment':{'PATH':str(base/'bin')+':'+os.environ['PATH'],'SPOKE_FIXTURE':str(base)},'roles':['fixture-spoke']}]
        (base/'play.yml').write_text(yaml.safe_dump(play))
        variables=dict(employee_workspace_profile='oci-hub',oci_hub_spoke_address='10.234.0.2/32',oci_hub_spoke_private_key='a'*43+'=',oci_hub_spoke_hub_public_key='b'*43+'=',oci_hub_spoke_endpoint='198.51.100.9:51825')
        env=os.environ.copy();env.update(ANSIBLE_CONFIG=str(ROOT/'tests/ci/fixtures/ansible.cfg'),ANSIBLE_ROLES_PATH=str(base/'roles'))
        def apply(addresses):
            variables['oci_hub_spoke_device_addresses']=addresses
            (base/'vars.json').write_text(json.dumps(variables))
            result=subprocess.run(['ansible-playbook','-i','localhost,','-c','local',str(base/'play.yml'),'-e','@'+str(base/'vars.json')],env=env,capture_output=True,text=True)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
            return json.loads((base/'kernel.json').read_text())
        first=apply(['10.235.0.2/32'])
        same=apply(['10.235.0.2/32']);assert same['activations']==first['activations'],'unchanged config restarted'
        added=apply(['10.235.0.2/32','10.235.0.3/32'])
        assert added['allowed_ips']==added['routes']==['10.235.0.2/32','10.235.0.3/32']
        assert added['activations']==same['activations']+1
        removed=apply(['10.235.0.3/32'])
        assert removed['allowed_ips']==removed['routes']==['10.235.0.3/32']
        assert removed['activations']==added['activations']+1
        print('PASS: actual Ansible tasks notify handler on device addition/removal; unchanged rerun does not restart')
        print('Synthetic systemctl models wg-quick restart routes/AllowedIPs; this is not a real WireGuard kernel test')


if __name__=='__main__':main()
