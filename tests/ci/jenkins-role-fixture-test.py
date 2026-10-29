#!/usr/bin/env python3
"""Run extracted role safety paths locally, with synthetic material and paths only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import pwd
import grp
import shutil
import subprocess
import sys
import tempfile
import unittest
import types
from importlib.machinery import SourceFileLoader
from unittest.mock import patch
import yaml
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/'scripts/jenkins'
sys.path.insert(0,str(SCRIPTS))
transaction=SourceFileLoader('role_transaction_fixture',str(SCRIPTS/'transaction.py')).load_module()


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.bin=self.base/'bin';self.bin.mkdir();self.env={key:value for key,value in os.environ.items() if not key.startswith('ANSIBLE_')}
        self.env['PATH']=str(self.bin)+':'+os.environ['PATH'];self.env['ANSIBLE_LOCAL_TEMP']=str(self.base/'ansible-tmp')
        self.env['ANSIBLE_CONFIG']=str(ROOT/'tests/ci/fixtures/ansible.cfg')
    def tasks(self,path):
        def normalize(value):
            if isinstance(value,list):return [normalize(item) for item in value]
            if isinstance(value,dict):return {key.removeprefix('ansible.builtin.'):normalize(item) for key,item in value.items()}
            return value
        return normalize(yaml.safe_load((ROOT/path).read_text()))
    def play(self,tasks,variables=None,handlers=None):
        path=self.base/'play.yml';path.write_text(yaml.safe_dump([{'name':'Synthetic role boundary fixture','hosts':'localhost','gather_facts':False,'vars':variables or {},'tasks':tasks,'handlers':handlers or []}]))
        return subprocess.run(['ansible-playbook','-i','localhost,','-c','local',str(path)],env=self.env,text=True,capture_output=True)
    def test_transaction_preapproval_lint_resolves_roles_with_isolated_config(self):
        job=self.base/'job';workspace=job/'workspace';root=workspace/'terraform/proxmox'
        root.mkdir(parents=True)
        for name in ['home','tmp','report','control','secrets']:(job/name).mkdir()
        ansible=workspace/'ansible';(ansible/'playbooks').mkdir(parents=True)
        (ansible/'roles/common/tasks').mkdir(parents=True)
        (ansible/'roles/common/tasks/main.yml').write_text('---\n- name: Check synthetic fixture\n  ansible.builtin.debug:\n    msg: synthetic\n')
        (ansible/'playbooks/deploy-fixture.yml').write_text('---\n- name: Validate synthetic fixture\n  hosts: all\n  gather_facts: false\n  roles: [common]\n')
        (ansible/'ansible.cfg').write_text('[defaults]\nvault_password_file=/must-not-load-fixture-password\n')
        payload={'profile':'deploy','sha':'a'*40,'build':1,'nonce':'fixture_nonce_1234567890','job':'fixture','scope':['root:proxmox'],
                 'changes':[{'path':'ansible/roles/fixture/tasks/main.yml','deleted':False}]}
        scope={'hosts':{},'playbooks':['deploy-fixture.yml'],'variables_source':'fixture'}
        trust=self.base/'trust.json';trust.write_text(json.dumps({'keys':{},'ansible_scopes':{'fixture':scope}}))
        (job/'control/lease.json').write_text('{}')
        real_run=transaction.run;lint_calls=[]
        class LintComplete(Exception):pass
        def run(argv,cwd,allowed=(0,),env=None):
            if argv[0]=='ansible-lint':
                lint_calls.append(argv)
                return real_run(argv,cwd,allowed=allowed,env=env)
            if argv[0].endswith('/refresh-terraform-state.sh'):raise LintComplete()
            value={'terraform_version':'1.14.4'} if argv[:2]==['terraform','version'] else {}
            return types.SimpleNamespace(returncode=0,stdout=json.dumps(value))
        with patch.object(transaction,'JOB',job),patch.object(transaction,'TRUST',trust),patch.object(transaction,'verify',return_value=payload),patch.object(transaction,'run',side_effect=run),patch.object(sys,'argv',['transaction',payload['sha'],'1',payload['nonce']]),patch.dict(os.environ):
            with self.assertRaises(LintComplete):transaction.main()
        self.assertEqual(len(lint_calls),1)

    def test_actual_verify_shell_and_boundary_script_reject_each_forbidden_group(self):
        identity=self.bin/'id';identity.write_text('#!/bin/bash\nif [[ "$1" == -u ]]; then [[ "$#" == 1 ]] && echo 0 || echo 1001; else [[ "${2:-iac-plan}" == "$MALICIOUS_TARGET" ]] && echo "$MALICIOUS_TARGET $MALICIOUS_GROUP" || echo "${2:-iac-plan}"; fi\n');identity.chmod(0o755)
        for name,body in [('stat','echo 700'),('systemctl','[[ "$*" == *MemoryMax* ]] && echo 268435456 || echo yes'),('runuser','exit 1')]:
            path=self.bin/name;path.write_text('#!/bin/bash\n'+body+'\n');path.chmod(0o755)
        playbook=self.tasks('ansible/playbooks/deploy-jenkins-agent.yml')
        shell=next(task['shell'] for play in playbook for task in play.get('tasks',[]) if task.get('name')=='Check plan identity privilege boundaries')
        script=(ROOT/'ansible/tests/jenkins-agent/verify-boundaries.sh').read_text()
        for user in ['iac-plan','iac-deploy','iac-apps']:
            for group in ['sudo','docker']:
                env={**self.env,'MALICIOUS_TARGET':user,'MALICIOUS_GROUP':group}
                with self.subTest(user=user,group=group):
                    result=subprocess.run(['bash','-c',script],env=env,capture_output=True);self.assertNotEqual(result.returncode,0)
                    if user=='iac-plan':self.assertNotEqual(subprocess.run(['bash','-c',shell],env=env,capture_output=True).returncode,0)
    def test_actual_verify_tasks_support_staged_and_active_without_starting_services(self):
        tasks=self.tasks('ansible/playbooks/deploy-jenkins-agent.yml')[1]['tasks']
        start=next(index for index,task in enumerate(tasks) if task['name']=='Check Jenkins agent service status')
        finish=next(index for index,task in enumerate(tasks) if task['name']=='Check plan identity privilege boundaries')
        tasks=tasks[start:finish]
        library=self.base/'library';library.mkdir();self.env['ANSIBLE_LIBRARY']=str(library)
        fixture=self.base/'verify-state.json';log=self.base/'verify-queries.log'
        self.env['JENKINS_VERIFY_FIXTURE']=str(fixture);self.env['JENKINS_VERIFY_LOG']=str(log)
        shared='''import json, os
from ansible.module_utils.basic import AnsibleModule
with open(os.environ['JENKINS_VERIFY_FIXTURE']) as source: fixture=json.load(source)
'''
        (library/'systemd.py').write_text(shared+'''module=AnsibleModule(argument_spec={'name':{'type':'str','required':True}})
name=module.params['name']
with open(os.environ['JENKINS_VERIFY_LOG'],'a') as output: output.write(name+'\\n')
module.exit_json(changed=False,status=fixture['services'][name])
''')
        (library/'stat.py').write_text(shared+'''module=AnsibleModule(argument_spec={'path':{'type':'str','required':True}})
module.exit_json(changed=False,stat=fixture['files'][module.params['path']])
''')
        users=['iac-plan','iac-deploy','iac-apps']
        files={path:{'exists':True,'isreg':True,'pw_name':'root','gr_name':'root','mode':mode} for path,mode in [
            ('/etc/systemd/system/jenkins-agent@.service','0644'),('/etc/systemd/system/jenkins-job-runner.service','0644'),
            ('/etc/systemd/system/jenkins-job-runner.socket','0644'),('/opt/jenkins-agent/agent.jar','0555')]}
        files['/run/jenkins-agent-remoting-ready']={'exists':False}
        staged={name:{'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','MainPID':'0','User':user}
                for user in users for name in ['jenkins-agent@'+user]}
        staged.update({name:{'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','MainPID':'0'}
                       for name in ['jenkins-job-runner.service','jenkins-job-runner.socket']})
        active=copy.deepcopy(staged)
        for user in users:active['jenkins-agent@'+user].update(ActiveState='active',SubState='running',MainPID='1001')
        cases=[('staged',False,staged,files,True),('active',True,active,files,True)]
        unloaded=copy.deepcopy(staged)
        for status in unloaded.values():status.clear();status.update(LoadState='not-found')
        cases.append(('staged-before-daemon-reload',False,unloaded,files,True))
        cases.append(('staged-running-agent',False,active,files,False))
        cases.append(('active-stopped-agent',True,staged,files,False))
        listening=copy.deepcopy(staged);listening['jenkins-job-runner.socket'].update(ActiveState='active',SubState='listening')
        cases.append(('staged-listening-admission',False,listening,files,False))
        ready=copy.deepcopy(files);ready['/run/jenkins-agent-remoting-ready']={'exists':True}
        cases.append(('staged-remoting-ready',False,staged,ready,False))
        missing=copy.deepcopy(files);missing['/opt/jenkins-agent/agent.jar']={'exists':False}
        cases.append(('staged-missing-runtime',False,staged,missing,False))
        for name,activated,services,installation,success in cases:
            fixture.write_text(json.dumps({'services':services,'files':installation}));log.write_text('')
            result=self.play(tasks,{'jenkins_agent_activate':activated})
            with self.subTest(case=name):
                self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
                # The replacement module accepts only `name`; a state/enabled
                # request would fail rather than starting any real service.
                self.assertTrue(log.read_text().splitlines())
                if activated:self.assertNotIn('jenkins-job-runner.socket',log.read_text().splitlines())

    def test_role_rescue_stops_three_agents_and_persists_both_fences(self):
        tasks=self.tasks('ansible/roles/jenkins-agent/tasks/main.yml')
        marker=copy.deepcopy(next(task for task in tasks if task['name']=='Mark agent configuration as incomplete during staging'))
        marker['copy'].update(dest=str(self.base/'agent-update-incomplete'),owner=pwd.getpwuid(os.getuid()).pw_name,group=grp.getgrgid(os.getgid()).gr_name)
        block=copy.deepcopy(next(task for task in tasks if task['name']=='Stage the peer runtime with a persistent failure fence'))
        runtime=self.base/'runtime.yml';runtime.write_text('- name: Inject staging failure\n  fail:\n    msg: Synthetic staging failure\n')
        block['block'][0]['include_tasks']=str(runtime)
        block['block'][1]['file']['path']=str(self.base/'agent-update-incomplete')
        log=self.base/'systemctl.log';systemctl=self.bin/'systemctl';systemctl.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> '+str(log)+'\n');systemctl.chmod(0o755)
        block['rescue'][0]['command']['argv'][0]=str(systemctl)
        block['rescue'][1]['copy'].update(dest=str(self.base/'quarantine.json'),owner=pwd.getpwuid(os.getuid()).pw_name,group=grp.getgrgid(os.getgid()).gr_name)
        result=self.play([marker,block]);self.assertNotEqual(result.returncode,0,result.stdout)
        self.assertEqual((self.base/'agent-update-incomplete').read_text(),'staging\n')
        self.assertIn('agent configuration failed',json.loads((self.base/'quarantine.json').read_text())['reason'])
        self.assertEqual(log.read_text().split(),['stop','jenkins-agent@iac-plan.service','jenkins-agent@iac-deploy.service','jenkins-agent@iac-apps.service'])
    def test_actual_tls_preflight_templates_accept_valid_and_reject_bad_material(self):
        ca_key=self.base/'ca.key';ca=self.base/'ca.crt'
        subprocess.run(['openssl','req','-x509','-newkey','ed25519','-nodes','-days','1','-keyout',str(ca_key),'-out',str(ca),'-subj','/CN=SyntheticCA','-addext','basicConstraints=critical,CA:TRUE'],check=True,capture_output=True)
        def certificate(name,purpose):
            key=self.base/(name+'.key');request=self.base/(name+'.csr');cert=self.base/(name+'.crt');extension=self.base/(name+'.ext')
            extension.write_text('extendedKeyUsage='+purpose+'\n'+('subjectAltName=IP:192.168.1.107\n' if purpose=='serverAuth' else ''))
            subprocess.run(['openssl','req','-new','-newkey','ed25519','-nodes','-keyout',str(key),'-out',str(request),'-subj','/CN='+name],check=True,capture_output=True)
            subprocess.run(['openssl','x509','-req','-in',str(request),'-CA',str(ca),'-CAkey',str(ca_key),'-CAcreateserial','-days','1','-out',str(cert),'-extfile',str(extension)],check=True,capture_output=True)
            return {'ca':ca.read_text(),'certificate':cert.read_text(),'key':key.read_text()}
        value=certificate('iac-peer-remoting','clientAuth');root_value=certificate('iac-peer-root','clientAuth')
        server_value=certificate('controller','serverAuth')
        clients=[{'name':name,**value} for name in ['iac-plan','iac-deploy','iac-apps']]
        roots=[{'filename':name,'value':content} for name,content in [('controller-ca.pem',root_value['ca']),('broker-ca.pem',server_value['ca']),('admission.crt',root_value['certificate']),('admission.key',root_value['key'])]]
        tasks=self.tasks('ansible/roles/jenkins-agent/tasks/runtime.yml');task=next(item for item in tasks if item['name']=='Validate all peer TLS materials before writing secrets')
        environment=Environment();environment.globals['lookup']=lambda kind,path:Path(path).read_text()
        script=environment.from_string(task['command']['argv'][2]).render(role_path=str(ROOT/'ansible/roles/jenkins-agent'))
        for changed,expected in [(None,0),('empty',1),('name',1),('path',1),('wrong-key',1),('root-as-remoting',1),('missing-broker-ca',1),('invalid-broker-ca',1),('extra-path',1)]:
            data={'kind':'agent','clients':copy.deepcopy(clients),'roots':copy.deepcopy(roots)}
            if changed=='empty':data['clients'][0]['certificate']=''
            if changed=='name':data['clients'][0]['name']='other'
            if changed=='path':data['roots'][0]['filename']='../escape'
            if changed=='wrong-key':data['clients'][0]['key']=value['certificate']
            if changed=='root-as-remoting':data['clients'][0].update(root_value)
            if changed=='missing-broker-ca':data['roots']=[item for item in data['roots'] if item['filename']!='broker-ca.pem']
            if changed=='invalid-broker-ca':data['roots'][1]['value']='invalid CA'
            if changed=='extra-path':data['roots'].append({'filename':'../escape','value':ca.read_text()})
            result=subprocess.run(['python3','-c',script],input=json.dumps(data),text=True,capture_output=True)
            with self.subTest(changed=changed):self.assertEqual(result.returncode==0,expected==0,result.stderr)
        policies=[{'certificate':'/fixture/server.crt','private_key':'/fixture/server.key','ca':'/fixture/ca.pem'}]*2
        bindings=[{'path':path,'value':content} for path,content in [('/fixture/server.crt',server_value['certificate']),('/fixture/server.key',server_value['key']),('/fixture/ca.pem',server_value['ca'])]]
        data={'kind':'gateway','policies':policies,'bindings':bindings}
        self.assertEqual(subprocess.run(['python3','-c',script],input=json.dumps(data),text=True,capture_output=True).returncode,0)
        data['bindings'][0]['value']=value['certificate'];data['bindings'][1]['value']=value['key']
        self.assertNotEqual(subprocess.run(['python3','-c',script],input=json.dumps(data),text=True,capture_output=True).returncode,0)

    def test_gateway_role_uses_server_trust_independently_of_client_peer_ca(self):
        key=self.base/'server.key';cert=self.base/'server.crt';client_key=self.base/'client-ca.key';client_ca=self.base/'client-ca.crt'
        for private,public,name in [(key,cert,'server'),(client_key,client_ca,'client')]:
            subprocess.run(['openssl','req','-x509','-newkey','ed25519','-nodes','-days','1','-subj','/CN='+name,'-addext','subjectAltName=IP:192.168.1.107','-keyout',str(private),'-out',str(public)],check=True,capture_output=True)
        bindings=[{'path':path,'value':value} for path,value in [('/fixture/server.crt',cert.read_text()),('/fixture/server.key',key.read_text()),('/fixture/server-ca.pem',cert.read_text()),('/fixture/client-ca.pem',client_ca.read_text())]]
        variables={'role_path':str(ROOT/'ansible/roles/jenkins-plan-gateway'),'jenkins_plan_gateway_tls_certificate':'/fixture/server.crt','jenkins_plan_gateway_tls_key':'/fixture/server.key','jenkins_plan_gateway_tls_ca':'/fixture/server-ca.pem','jenkins_admission_policy':{'certificate':'/fixture/server.crt','private_key':'/fixture/server.key','server_ca':'/fixture/server-ca.pem','peer_ca':'/fixture/client-ca.pem'},'jenkins_plan_gateway_secret_files':bindings}
        task=next(x for x in self.tasks('ansible/roles/jenkins-plan-gateway/tasks/main.yml') if x['name']=='Validate gateway and admission TLS before writing bindings')
        result=self.play([task],variables);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        variables['jenkins_admission_policy']['server_ca']='relative.pem';variables['jenkins_plan_gateway_secret_files'].append({'path':'relative.pem','value':cert.read_text()})
        result=self.play([task],variables);self.assertNotEqual(result.returncode,0)

    def test_watchdog_validate_branch_checks_key_pair_and_each_binding_path(self):
        task=next(item for item in self.tasks('ansible/roles/jenkins-watchdog/tasks/main.yml') if item['name']=='Validate recovery identity and binding names before writing secrets')
        environment=Environment();environment.globals['lookup']=lambda kind,path:Path(path).read_text()
        script=environment.from_string(task['command']['argv'][2]).render(role_path=str(ROOT/'ansible/roles/jenkins-watchdog'))
        keys=[]
        for number in range(2):
            key=self.base/('ssh-'+str(number))
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True,capture_output=True)
            keys.append(key)
        good={'kind':'watchdog','public':keys[0].with_suffix('.pub').read_text().strip(),'private':keys[0].read_text(),'peer_bindings':[{'filename':'peer.pem'}],'controller_bindings':[{'filename':'controller.pem'}]}
        cases=[good,{**good,'private':keys[1].read_text()}]
        for field in ['peer_bindings','controller_bindings']:cases.append({**good,field:[{'filename':'../escape'}]})
        for index,data in enumerate(cases):
            result=subprocess.run(['python3','-c',script],input=json.dumps(data),text=True,capture_output=True)
            with self.subTest(index=index):self.assertEqual(result.returncode==0,index==0,result.stderr)

    def test_activation_and_existing_runtime_reconciliation_use_real_role_conditions(self):
        source=self.tasks('ansible/roles/jenkins-agent/tasks/main.yml')
        inspect=copy.deepcopy(next(x for x in source if x['name']=='Inspect runner before staging to distinguish first activation'))
        guard=copy.deepcopy(next(x for x in source if x['name']=='Refuse staging over an active runtime without activation authorization'))
        block=copy.deepcopy(next(x['block'] for x in source if x['name']=='Stage the peer runtime with a persistent failure fence'))
        handler=copy.deepcopy(self.tasks('ansible/roles/jenkins-agent/handlers/main.yml')[0])
        pending=self.base/'agent-update-pending';incomplete=self.base/'agent-update-incomplete';log=self.base/'systemd.log';state=self.base/'states.json'
        systemctl=self.bin/'systemctl'
        systemctl.write_text('#!/usr/bin/env python3\nimport json,sys\ns=json.load(open('+repr(str(state))+'))\nsys.exit(s.get(sys.argv[-1],0))\n');systemctl.chmod(0o755)
        inspect['command']['argv'][0]=str(systemctl)
        runtime=self.base/'runtime.yml'
        block[0]['include_tasks']=str(runtime);block[1]['file']['path']=str(incomplete)
        library=self.base/'library';library.mkdir();self.env['ANSIBLE_LIBRARY']=str(library)
        (library/'systemd.py').write_text("from ansible.module_utils.basic import AnsibleModule\nm=AnsibleModule(argument_spec={'name':{'type':'str'},'state':{'type':'str'},'enabled':{'type':'bool'},'daemon_reload':{'type':'bool'}})\nwith open("+repr(str(log))+",'a') as f:f.write(m.params['name']+'\\n')\nm.exit_json(changed=True)\n")
        user=pwd.getpwuid(os.getuid()).pw_name;group=grp.getgrgid(os.getgid()).gr_name
        for task in [*block,handler]:
            if 'copy' in task:task['copy'].update(dest=str(pending),owner=user,group=group)
            if task.get('name')=='Inspect remoting services for asynchronous reconciliation':task['command']['argv'][0]=str(systemctl)
        names=['iac-plan','iac-deploy','iac-apps']
        for activated,runner_rc,agent_rc,changed,ok,expect_pending,starts in [(False,3,3,True,True,False,0),(True,3,3,True,True,False,5),(True,0,0,True,True,True,0),(True,0,3,False,True,True,0),(False,0,0,True,False,False,0)]:
            pending.unlink(missing_ok=True);log.write_text('');incomplete.write_text('staging')
            state.write_text(json.dumps({'jenkins-job-runner.service':runner_rc,**{'jenkins-agent@'+name+'.service':agent_rc for name in names}}))
            runtime.write_text(yaml.safe_dump([{'name':'Synthetic runtime change','debug':{'msg':'fixture'},'changed_when':changed,'notify':'Queue Jenkins agent maintenance'}]))
            result=self.play([inspect,guard,{'name':'Run extracted staging path','block':block}],{'jenkins_agent_activate':activated,'jenkins_agent_instances':[{'name':name} for name in names]},[handler])
            with self.subTest(activated=activated,runner_rc=runner_rc,changed=changed):
                self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
                self.assertEqual(pending.exists(),expect_pending,result.stdout)
                self.assertEqual(len(log.read_text().splitlines()),starts,result.stdout)
                if not ok:self.assertTrue(incomplete.exists())

    def test_converged_controller_rerun_skips_consumed_gate_but_changed_bytes_refuse(self):
        # Copy the real role tasks/templates, replacing only filesystem roots,
        # synthetic plugin metadata and the package query in this fixture.
        role=self.base/'project/ansible/roles/jenkins';(role/'tasks').mkdir(parents=True);(self.base/'templates').mkdir()
        for filename in ['jenkins.yaml.j2','jenkins.service.override.conf.j2']:shutil.copyfile(ROOT/'ansible/roles/jenkins/templates'/filename,self.base/'templates'/filename)
        tasks=self.tasks('ansible/roles/jenkins/tasks/config.yml')
        user=pwd.getpwuid(os.getuid()).pw_name;group=grp.getgrgid(os.getgid()).gr_name
        for task in tasks:
            if task.get('name')=='Validate desired controller mode and exclusive identities before convergence':
                task['assert']['that']=[value.replace("'/var/lib/jenkins'",repr(str(self.base/'home'))).replace("'/etc/systemd/system/jenkins.service.d'",repr(str(self.base/'service'))) for value in task['assert']['that']]
            if 'loop' in task and isinstance(task['loop'],list):
                for item in task['loop']:
                    if isinstance(item,dict):
                        if 'owner' in item:item['owner']=user
                        if 'group' in item:item['group']=group
            if task.get('name')=='Require fresh gate when deployed recovery helper bytes differ':task['when']=task['when'].replace("!= 'root'",'!= '+repr(user))
            if task.get('name')=='Inspect deployed recovery helper bytes without writing':task['stat']['path']=str(self.base/'helpers')+'/{{ item }}'
            if task.get('name')=='Read installed core before deciding no-op convergence':task['command']['argv']=['/bin/echo','2.568.3']
        (role/'tasks/config.yml').write_text(yaml.safe_dump(tasks))
        shutil.copyfile(ROOT/'ansible/roles/jenkins/tasks/config-write.yml',role/'tasks/config-write.yml')
        home=self.base/'home';(home/'casc').mkdir(parents=True,mode=0o750);(home/'plugins').mkdir()
        service=self.base/'service';service.mkdir(mode=0o755)
        plugin=home/'plugins/fixture.jpi';plugin.write_bytes(b'synthetic plugin')
        bom={'jenkins':{'core':{'package_version':'2.568.3'},'controller_executors_bootstrap':2,'managed_plugins':[{'id':'fixture','version':'1','sha256':hashlib.sha256(plugin.read_bytes()).hexdigest()}]}}
        helpers=self.base/'helpers';helpers.mkdir();sources=role.parents[2]/'scripts/jenkins';sources.mkdir(parents=True)
        for name in ['control.py','controller-maintenance.py']:
            shutil.copyfile(ROOT/'scripts/jenkins'/name,helpers/name);(helpers/name).chmod(0o500);shutil.copyfile(ROOT/'scripts/jenkins'/name,sources/name)
        ci=role.parents[2]/'ci';ci.mkdir();(ci/'toolchain-bom.yml').write_text(yaml.safe_dump(bom))
        variables={'role_path':str(role),'jenkins_home':str(home),'jenkins_casc_dir':str(home/'casc'),'jenkins_casc_config_path':str(home/'casc/jenkins.yaml'),'jenkins_systemd_override_dir':str(service),'jenkins_controller_mode':'bootstrap','jenkins_casc_nodes':[{'name':name,'description':'fixture','remote_fs':'/var/lib/jenkins-agent/'+name,'executors':1,'labels':name} for name in ['iac-plan','iac-deploy','iac-apps']],'ci_toolchain_bom':bom,'jenkins_controller_change_authorized':False,'jenkins_controller_watchdog_ready':False,'jenkins_controller_restore_tested_backup_ready':False,'jenkins_controller_change_authorization_id':'','jenkins_controller_watchdog_bundle_sha256':'','jenkins_controller_restore_test_evidence_id':''}
        setup=[]
        for source,destination,mode in [('jenkins.yaml.j2',home/'casc/jenkins.yaml','0640'),('jenkins.service.override.conf.j2',service/'10-casc.conf','0644')]:setup.append({'name':'Render synthetic existing configuration','template':{'src':source,'dest':str(destination),'mode':mode}})
        result=self.play(setup,variables);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        convergence=[{'name':'Run real convergence decision','include_tasks':str(role/'tasks/config.yml')}]
        for _ in range(2):
            result=self.play(convergence,variables);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Apply controller configuration only with a fresh one-use gate',result.stdout)
        for target,operation in [(home/'casc/jenkins.yaml','bytes'),(plugin,'bytes'),(home/'casc/jenkins.yaml','mode'),(home/'casc','mode'),(helpers/'controller-maintenance.py','bytes'),(helpers/'control.py','mode')]:
            original=target.read_bytes() if target.is_file() else None;mode=target.stat().st_mode&0o777
            if operation=='bytes':target.chmod(mode|0o200);target.write_bytes(original+b'# changed bytes\n');target.chmod(mode)
            else:target.chmod(0o777)
            result=self.play(convergence,variables)
            with self.subTest(target=str(target),operation=operation):
                self.assertNotEqual(result.returncode,0,result.stdout)
                self.assertIn('Planned Jenkins controller changes require explicit authorization',result.stdout)
            if original is not None:target.chmod(mode|0o200);target.write_bytes(original)
            target.chmod(mode)


if __name__=='__main__':unittest.main()
