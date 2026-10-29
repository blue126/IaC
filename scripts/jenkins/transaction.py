#!/usr/bin/python3
"""Fixed IaC transaction executed only inside the non-root transient job unit."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tempfile
import urllib.request
from control import NoRedirect, Refused,atomic_json,canonical,digest,sha_file,verify

JOB=Path('/job')
TRUST=Path('/opt/jenkins-agent/control/trust.json')


def run(argv,cwd,allowed=(0,),env=None):
    result=subprocess.run(argv,cwd=cwd,env=os.environ.copy() if env is None else env,capture_output=True,text=True)
    if result.returncode not in allowed:raise Refused('fixed tool stage failed: '+argv[0])
    return result


def state_identity(root):
    workspace=json.loads(TRUST.read_text())['hcp_workspace_id']
    if not re.fullmatch(r'ws-[A-Za-z0-9]+',workspace):raise Refused('fixed HCP workspace ID required')
    credentials=json.loads((JOB/'secrets/hcp-credentials.json').read_text())['credentials']['app.terraform.io']['token']
    def current():
        request=urllib.request.Request('https://app.terraform.io/api/v2/workspaces/'+workspace+'/current-state-version',headers={'Authorization':'Bearer '+credentials})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=20) as response:data=json.load(response)['data']
        if data['attributes']['status']!='finalized':raise Refused('state is not finalized')
        return data['id']
    before=current()
    raw=json.loads(run(['terraform','state','pull'],root).stdout)
    if current()!=before:raise Refused('state changed while resolving transaction inputs')
    return {'lineage':raw['lineage'],'serial':raw['serial'],'state_version':before}


def lease(admission,keys):
    current=verify(json.loads((JOB/'control/lease.json').read_text()),keys,'job-lease')
    for key in ['nonce','sha','scope','credential_versions']:
        if current[key]!=admission[key]:raise Refused('source, scope, state or credential versions changed')
    return current


def approve(stage,manifest,admission,keys):
    manifest_digest=digest(canonical(manifest))
    atomic_json(JOB/'report/status.json',{'phase':stage+'-approval','manifest_digest':manifest_digest,'summary':manifest['summary']})
    deadline=manifest['expires_at']
    path=JOB/'control'/(stage+'-approval.json')
    while int(time.time())<deadline:
        lease(admission,keys)
        if path.exists():
            approval=verify(json.loads(path.read_text()),keys,'job-approval')
            if approval['digest']!=manifest_digest or approval['stage']!=stage or approval['nonce']!=admission['nonce'] or approval['sha']!=admission['sha'] or approval['credential_versions']!=admission['credential_versions']:
                raise Refused('approval does not authorize this exact transaction')
            return approval
        time.sleep(2)
    raise Refused('approval expired; recreate plan and approvals')


def inventory_address(value):
    # ansible-core 2.20's legacy inventory JSON preserves unsafe string tags.
    if isinstance(value,dict) and set(value)=={'__ansible_unsafe'}:value=value['__ansible_unsafe']
    if not isinstance(value,str):raise Refused('inventory address must be a literal string')
    return value


def inventory_scope(workspace,scope):
    # Resolve only Terraform-provided identity in a temporary inventory root.
    # Neither the checkout's ansible.cfg nor its group/host vars participate.
    with tempfile.TemporaryDirectory(prefix='inventory-',dir=JOB/'tmp') as directory:
        directory=Path(directory)
        config=directory/'ansible.cfg'
        config.write_text('[defaults]\nvars_plugins_enabled = \n[inventory]\nenable_plugins = auto, cloud.terraform.terraform_provider\nany_unparsed_is_failed = true\n')
        source=directory/'terraform.yml'
        source.write_text(json.dumps({'plugin':'cloud.terraform.terraform_provider',
                                     'project_path':str((workspace/'terraform/proxmox').resolve()),
                                     'state_file':str((workspace/'terraform/proxmox/terraform.tfstate').resolve())}))
        env={key:value for key,value in os.environ.items() if not key.startswith('ANSIBLE_')}
        if 'ANSIBLE_COLLECTIONS_PATH' in os.environ:env['ANSIBLE_COLLECTIONS_PATH']=os.environ['ANSIBLE_COLLECTIONS_PATH']
        env['ANSIBLE_CONFIG']=str(config)
        raw=json.loads(run(['ansible-inventory','-i',str(source),'--list'],directory,env=env).stdout)

    hostvars=raw.get('_meta',{}).get('hostvars',{})
    public={name:{'ansible_host':inventory_address(variables.get('ansible_host')),'groups':sorted(group for group,content in raw.items() if isinstance(content,dict) and name in content.get('hosts',[]))} for name,variables in hostvars.items()}
    allowed=scope['hosts']
    resolved={name:public[name] for name in allowed if name in public}
    if set(resolved)!=set(allowed):raise Refused('approved target missing from refreshed inventory')
    for name,host in resolved.items():
        if host['ansible_host']!=allowed[name]:raise Refused('resolved target address differs from locked scope')
    return {'inventory_sha256':digest(canonical(public)),'hosts':resolved,'playbooks':scope['playbooks'],
            'tags':scope.get('tags',[]),'limit':','.join(sorted(resolved)),
            'variables_source':scope['variables_source']}


def verify_deploy_scope(workspace,resolved):
    raw=json.loads(run(['ansible-inventory','--list','--limit',resolved['limit']],workspace/'ansible').stdout)
    hosts=raw.get('_meta',{}).get('hostvars',{})
    if set(hosts)!=set(resolved['hosts']) or any(inventory_address(hosts[name].get('ansible_host'))!=expected['ansible_host'] for name,expected in resolved['hosts'].items()):
        raise Refused('project or Vault variables changed the approved connection targets')


def validate_scope(scope,admission):
    if not isinstance(scope,dict) or not {'hosts','playbooks','variables_source'}<=set(scope):raise Refused('fixed Ansible scope is incomplete')
    if 'jenkins' in scope['hosts'] or 'deploy-jenkins.yml' in scope['playbooks'] or 'control-plane:jenkins' in admission['scope']:
        raise Refused('controller configuration uses independent maintenance')
    if ('jenkins-agent' in scope['hosts'] or 'deploy-jenkins-agent.yml' in scope['playbooks']) and 'control-plane:jenkins-agent' not in admission['scope']:
        raise Refused('agent updates require their explicit conflict domain')
    if any(not re.fullmatch(r'deploy-[a-z0-9-]+\.yml',item) for item in scope['playbooks']):raise Refused('playbook outside fixed map')


def classify_changes(changes,workspace,scope):
    if changes is None:raise Refused('controller-resolved change selection is required')
    files=[item for item in changes if not item['path'].startswith(('terraform/esxi/','terraform/modules/esxi-vm/'))]
    relevant=[item for item in files if item['path'].startswith(('terraform/','ansible/','scripts/','Jenkinsfile','ci/'))]
    terraform=any(item['path'].startswith(('terraform/proxmox/','terraform/modules/')) for item in relevant)
    selected=set();unmatched=[];broad=[]
    for item in relevant:
        path=item['path']
        if item['deleted'] and re.fullmatch(r'terraform/proxmox/[^/]+\.tf',path):continue
        if path.startswith(('ansible/roles/common/','ansible/roles/docker/','ansible/inventory/group_vars/','terraform/modules/')):
            broad.append(path);continue
        if path.startswith(('scripts/','Jenkinsfile','ci/','ansible/requirements.yml','ansible/ansible.cfg')):continue
        candidate=None
        for pattern in [r'terraform/proxmox/([^/]+)\.tf',r'ansible/roles/([^/]+)/.*',r'ansible/inventory/host_vars/([^/.]+).*']:
            match=re.fullmatch(pattern,path)
            if match:
                service=match[1]
                if path.startswith('terraform/') and service in {'versions','provider','variables','main','provisioning','pve-cluster'}:candidate='';break
                candidate='deploy-'+service+'.yml';break
        match=re.fullmatch(r'ansible/playbooks/(deploy-[^/]+\.yml)',path)
        if match:
            if item['deleted']:continue
            candidate=match[1]
        if candidate=='':continue
        if candidate and (workspace/'ansible/playbooks'/candidate).is_file():selected.add(candidate)
        else:unmatched.append(path)
    if (broad or unmatched) and scope.get('explicit_scope') is not True:
        raise Refused('broad or unmatched changes require an explicit root-reviewed operator scope')
    if not selected<=set(scope['playbooks']):raise Refused('changed playbook is outside the approved execution map')
    playbooks=scope['playbooks'] if scope.get('explicit_scope') is True else sorted(selected)
    return {'should_build':bool(relevant),'terraform':terraform,'ansible_lint':any(item['path'].startswith('ansible/') for item in relevant),
            'playbooks':playbooks,'unmatched':unmatched,'broad':broad,'changed_files':[item['path'] for item in files]}


def notion_sync(workspace,trust,admission,keys):
    config=trust.get('notion',{})
    if config.get('enabled') is not True:return 'disabled'
    if config.get('destination')!='https://api.notion.com' or 'integration:notion' not in admission['scope']:
        raise Refused('Notion destination/scope lacks explicit authorization')
    atomic_json(JOB/'report/status.json',{'phase':'notion-sync','summary':{'destination':'https://api.notion.com'}})
    deadline=time.monotonic()+60
    while not (JOB/'control/notion-ready.json').exists():
        lease(admission,keys)
        if time.monotonic()>deadline:return 'failed'
        time.sleep(.25)
    if json.loads((JOB/'control/notion-ready.json').read_text()).get('ready') is not True:return 'failed'
    env=dict(os.environ,NOTION_TOKEN=(JOB/'secrets/notion-token').read_text().strip(),
             NOTION_DATABASE_ID=(JOB/'secrets/notion-database-id').read_text().strip(),NOTION_DRY_RUN='false')
    if env['NOTION_DATABASE_ID']!=config['database_id']:raise Refused('Notion database differs from approved scope')
    vault=workspace/'ansible/.vault_pass'
    if not vault.exists():vault.symlink_to(JOB/'secrets/vault-password')
    result=run(['python3','scripts/sync-to-notion.py'],workspace,allowed=tuple(range(256)),env=env)
    return 'completed' if result.returncode==0 else 'failed'


def main():
    sha,build,nonce=sys.argv[1:]
    trust=json.loads(TRUST.read_text());keys=trust['keys']
    admission=verify(json.loads((JOB/'control/lease.json').read_text()),keys,'job-lease')
    if [sha,build,nonce]!=[admission['sha'],str(admission['build']),admission['nonce']]:raise Refused('fixed wrapper arguments differ from admission')
    if admission['profile']!='deploy':raise Refused('only the IaC deploy profile may run this transaction')
    workspace=JOB/'workspace';root=workspace/'terraform/proxmox'
    scope=trust['ansible_scopes'][admission['job']]
    validate_scope(scope,admission)
    selection=classify_changes(admission.get('changes'),workspace,scope)
    atomic_json(JOB/'report/status.json',{'phase':'starting','summary':selection})
    if not selection['should_build']:
        atomic_json(JOB/'report/status.json',{'phase':'verified','summary':{'skipped':'docs/non-IaC changes only'}});return
    scope={**scope,'playbooks':selection['playbooks']}
    integration=trust.get('notion',{'enabled':False})
    if integration.get('enabled') is True and (integration!=admission.get('notion') or integration.get('destination')!='https://api.notion.com' or 'integration:notion' not in admission['scope']):
        raise Refused('Notion integration differs from the signed authorized policy')
    os.environ.update(HOME=str(JOB/'home'),TMPDIR=str(JOB/'tmp'),TF_CLI_CONFIG_FILE='/opt/jenkins-toolchain/terraform.rc',TF_IN_AUTOMATION='1',CHECKPOINT_DISABLE='1',ANSIBLE_COLLECTIONS_PATH='/opt/jenkins-toolchain/collections')
    credentials=JOB/'home/.terraform.d';credentials.mkdir(mode=0o700)
    (credentials/'credentials.tfrc.json').symlink_to(JOB/'secrets/hcp-credentials.json')
    (root/'peer.auto.tfvars.json').symlink_to(JOB/'secrets/proxmox.auto.tfvars.json')
    version=json.loads(run(['terraform','version','-json'],root).stdout)
    if version['terraform_version']!='1.14.4':raise Refused('Terraform BOM mismatch')
    run(['terraform','init','-input=false','-lockfile=readonly'],root)
    run(['terraform','validate'],root)
    if selection['ansible_lint']:
        with tempfile.TemporaryDirectory(prefix='lint-',dir=JOB/'tmp') as temporary:
            temporary=Path(temporary)
            (temporary/'inventory.json').write_text(json.dumps({'all':{'hosts':{'fixture':{'ansible_connection':'local'}}}}))
            (temporary/'ansible.cfg').write_text('[defaults]\nvars_plugins_enabled = \n')
            env={key:value for key,value in os.environ.items() if not key.startswith('ANSIBLE_')}
            env.update(ANSIBLE_CONFIG=str(temporary/'ansible.cfg'),ANSIBLE_INVENTORY=str(temporary/'inventory.json'),ANSIBLE_COLLECTIONS_PATH='/opt/jenkins-toolchain/collections',ANSIBLE_ROLES_PATH=str(workspace/'ansible/roles'))
            if scope['playbooks']:run(['ansible-lint','--offline',*['playbooks/'+name for name in scope['playbooks']]],workspace/'ansible',env=env)
    if selection['terraform']:
        before=state_identity(root)
        saved=JOB/'tmp/approved.tfplan'
        run(['terraform','plan','-input=false','-out='+str(saved),'-detailed-exitcode'],root,allowed=(0,2))
        plan=json.loads(run(['terraform','show','-json',str(saved)],root).stdout)
        # JSON plans can contain secrets. Only address/action pairs leave this run.
        summary=[{'address':change['address'],'actions':change['change']['actions']} for change in plan.get('resource_changes',[]) if change['change']['actions']!=['no-op']]
        now=int(time.time())
        manifest={'root':'proxmox','source_sha':sha,'plan_sha256':sha_file(saved),'state':before,
                  'lock_sha256':sha_file(root/'.terraform.lock.hcl'),'credential_versions':admission['credential_versions'],
                  'scope':admission['scope'],'issued_at':now,'expires_at':now+900,'summary':summary}
        approve('terraform',manifest,admission,keys)
        lease(admission,keys)
        atomic_json(JOB/'report/status.json',{'phase':'terraform-apply','summary':summary})
        if state_identity(root)!=before or sha_file(saved)!=manifest['plan_sha256'] or sha_file(root/'.terraform.lock.hcl')!=manifest['lock_sha256']:
            raise Refused('state, provider lock or saved plan changed after approval')
        # Exactly the saved plan is applied; no intervening plan operation exists.
        run(['terraform','apply','-input=false',str(saved)],root)
    if selection['terraform'] or scope['playbooks']:
        run([str(workspace/'scripts/refresh-terraform-state.sh'),'proxmox'],workspace)
    if not scope['playbooks']:
        atomic_json(JOB/'report/status.json',{'phase':'verified','summary':selection});return
    resolved=inventory_scope(workspace,scope)
    now=int(time.time())
    ansible_manifest={'source_sha':sha,'state':state_identity(root),'scope':resolved,'integrations':{'notion':integration},
                      'credential_versions':admission['credential_versions'],'issued_at':now,'expires_at':now+900,
                      'summary':{'hosts':resolved['hosts'],'playbooks':resolved['playbooks'],'tags':resolved['tags'],'variables_source':resolved['variables_source'],'integrations':{'notion':integration}}}
    approve('ansible',ansible_manifest,admission,keys)
    lease(admission,keys)
    atomic_json(JOB/'report/status.json',{'phase':'ansible-deploy','summary':ansible_manifest['summary']})
    if inventory_scope(workspace,scope)!=resolved or state_identity(root)!=ansible_manifest['state']:
        raise Refused('inventory, state or Ansible scope changed after approval')
    os.environ['ANSIBLE_VAULT_PASSWORD_FILE']=str(JOB/'secrets/vault-password')
    os.environ['ANSIBLE_PRIVATE_KEY_FILE']=str(JOB/'secrets/ansible-ssh-key')
    verify_deploy_scope(workspace,resolved)
    for playbook in scope['playbooks']:
        if not re.fullmatch(r'deploy-[a-z0-9-]+\.yml',playbook):raise Refused('playbook outside fixed map')
        # Control-plane changes execute through the independent maintenance entry.
        if playbook=='deploy-jenkins.yml':raise Refused('control-plane changes require independent maintenance')
        arguments=['ansible-playbook','playbooks/'+playbook,'--limit',resolved['limit']]
        if scope.get('tags'):arguments+=['--tags',','.join(scope['tags'])]
        run(arguments,workspace/'ansible')
        run(['ansible-playbook','playbooks/'+playbook,'--limit',resolved['limit'],'--tags','verify'],workspace/'ansible')
    sync=notion_sync(workspace,trust,admission,keys)
    atomic_json(JOB/'report/status.json',{'phase':'verified','summary':{'source_sha':sha,'roots':['proxmox'],'selection':selection,'notion_sync':sync}})


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('fixed IaC transaction refused; create a fresh plan and approval')
