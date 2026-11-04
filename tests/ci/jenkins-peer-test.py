#!/usr/bin/env python3
"""Offline fault tests. No production credentials, API, service or state access."""
import copy
import fcntl
import io
import tarfile
import time
from importlib.machinery import SourceFileLoader
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control

def load(name):return SourceFileLoader(name.replace('-','_'),str(ROOT/'scripts/jenkins'/name)+'.py').load_module()
projection=load('proxmox-projection')
gateway=load('plan-gateway')
runner=load('job-runner')
maintenance=load('controller-maintenance')
watchdog=load('watchdog')
snapshot=load('plan-snapshot')
preflight=load('peer-preflight')
toolchain=load('toolchain')


class SignatureTests(unittest.TestCase):
    def setUp(self):
        original_private_file=control.private_file
        self.file_patch=patch.object(control,'private_file',lambda path,owner=0:original_private_file(path,owner=os.getuid()))
        self.file_patch.start()
        self.addCleanup(self.file_patch.stop)
        for module in [maintenance,snapshot]:
            alias=patch.object(module,'private_file',lambda path:original_private_file(path,owner=os.getuid()))
            alias.start();self.addCleanup(alias.stop)
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        self.key=self.directory/'key.pem';self.public=self.directory/'public.pem'
        subprocess.run(['openssl','genpkey','-algorithm','ed25519','-out',str(self.key)],check=True,capture_output=True)
        subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.public)],check=True,capture_output=True)
        self.payload={'purpose':'job-admission','nonce':'a'*24,'issued_at':100,'expires_at':160,'scope':['root:proxmox']}
    def tearDown(self):self.temp.cleanup()
    def test_signature_and_expiry(self):
        envelope=control.sign(self.payload,'current',self.key)
        self.assertEqual(control.verify(envelope,{'current':self.public},'job-admission',101),self.payload)
        with self.assertRaises(control.Refused):control.verify(envelope,{'current':self.public},'job-admission',160)
        with self.assertRaises(control.Refused):control.verify(envelope,{},'job-admission',101)
        with self.assertRaises(control.Refused):control.verify(envelope,{'current':self.public},'controller-maintenance',101)
        envelope['payload']['scope']=['service:other']
        with self.assertRaises(control.Refused):control.verify(envelope,{'current':self.public},'job-admission',101)
    def test_gate_rejects_boolean_or_missing_real_evidence(self):
        with self.assertRaises(control.Refused):maintenance.validate_evidence({'ready':True},{'keys':{}},now=101)
        payload=dict(self.payload,purpose='controller-recovery-evidence',target='CT107/jenkins',drill_target='CT110',tuple={'core':'wrong'},authorization_id='approved')
        envelope=control.sign(payload,'current',self.key)
        policy={'keys':{'current':self.public},'tuple':{'core':'2.568.3'},'authorization_id':'approved'}
        with self.assertRaises(control.Refused):maintenance.validate_evidence(envelope,policy,now=101)

    def test_world_readable_signing_key_rejected(self):
        self.key.chmod(0o644)
        with self.assertRaises(control.Refused):control.sign(self.payload,'current',self.key)

    def test_admission_binds_uid_scope_source_and_disabled_profile(self):
        payload=dict(self.payload,job='IaC-ReadOnly-Plan',profile='plan',uid=1001,unix_user='iac-plan',sha='a'*40,credential_versions={})
        profile={'name':'plan','user':'iac-plan','scope':['root:proxmox'],'enabled':True,'dns':False,'secrets':[]}
        config={'keys':{'current':self.public},'profiles':{'IaC-ReadOnly-Plan':profile}}
        envelope=control.sign(payload,'current',self.key)
        identity=type('Identity',(),{'pw_uid':1001})()
        with patch.object(runner.pwd,'getpwnam',return_value=identity):
            runner.validate_admission(envelope,config,1001,101)
            with self.assertRaises(control.Refused):runner.validate_admission(envelope,config,1002,101)
            for modify in [lambda p:p.update(scope=['service:other']),lambda p:p.update(sha='main'),lambda p:p.update(uid=0)]:
                candidate=copy.deepcopy(payload);modify(candidate)
                with self.assertRaises(control.Refused):runner.validate_admission(control.sign(candidate,'current',self.key),config,1001,101)
            profile['enabled']=False
            with self.assertRaises(control.Refused):runner.validate_admission(envelope,config,1001,101)
            profile['enabled']=True;profile['secrets']=['mutation']
            with self.assertRaises(control.Refused):runner.validate_admission(envelope,config,1001,101)

    def valid_recovery(self):
        backup=self.directory/'backup.tar';backup.write_bytes(b'synthetic backup')
        records=self.directory/'records.json';records.write_text('{"actual_fixture":true}')
        required={'stop','archive_verify','namespace_isolation','config_parse','plugin_load','health','gitea_unchanged'}
        payload=dict(self.payload,purpose='controller-recovery-evidence',target='CT107/jenkins',drill_target='CT110',
                     tuple={'core':'2.568.3'},authorization_id='authorized',backup_sha256=control.sha_file(backup),
                     evidence_files={'records.json':control.sha_file(records)},commands=[{'name':name,'exit_code':0} for name in required])
        armed=dict(self.payload,purpose='controller-watchdog-armed',backup_sha256=control.sha_file(backup),old_tuple=payload['tuple'])
        attestation=self.directory/'armed.json';attestation.write_text(json.dumps(control.sign(armed,'current',self.key)))
        policy={'keys':{'current':self.public},'tuple':payload['tuple'],'authorization_id':'authorized',
                'backup':str(backup),'evidence_dir':str(self.directory),'watchdog_attestation':str(attestation)}
        return payload,policy

    def test_gate_requires_matching_backup_files_and_armed_tuple(self):
        payload,policy=self.valid_recovery()
        envelope=control.sign(payload,'current',self.key)
        maintenance.validate_evidence(envelope,policy,101)
        with self.assertRaises(control.Refused):maintenance.validate_evidence(envelope,policy,101,zero=True)
        (self.directory/'backup.tar').write_bytes(b'tampered')
        with self.assertRaises(control.Refused):maintenance.validate_evidence(envelope,policy,101)
        (self.directory/'backup.tar').write_bytes(b'synthetic backup')
        (self.directory/'records.json').write_text('tampered')
        with self.assertRaises(control.Refused):maintenance.validate_evidence(envelope,policy,101)

    def test_signed_producer_uses_current_native_source_and_public_state(self):
        fixture=ProjectionTests();fixture.setUp();raw=fixture.public_state()
        schema=self.directory/'schema.json';schema.write_bytes((ROOT/'ci/agent-provider-schema.json').read_bytes());schema.chmod(0o600)
        lock=self.directory/'lock.hcl';lock.write_bytes((ROOT/'terraform/proxmox/.terraform.lock.hcl').read_bytes());lock.chmod(0o600)
        policy=dict(fixture.policy,enabled=True,provider_schema=str(schema),provider_lock=str(lock),source_sha='a'*40,key_id='current',signing_key=str(self.key))
        policy['broker']['bridges']={'pve2':{'pve2':['vmbr501']}}
        hcp=type('HCP',(),{'current':lambda self:{'id':'sv-synthetic'},'state':lambda self,version:raw})()
        destination=self.directory/'bundle'
        with patch.object(snapshot,'HCP',return_value=hcp):manifest=snapshot.produce(policy,ROOT,'n'*24,destination)
        signed=control.verify(json.loads((destination/'manifest.json').read_text()),{'current':self.public},'plan-snapshot')
        self.assertEqual(signed,manifest);self.assertEqual(manifest['coverage']['status'],'partial')
        self.assertTrue(manifest['files']);self.assertNotIn('SECRET_CANARY', ''.join(path.read_text() for path in destination.rglob('*') if path.is_file()))
        for index,scope in enumerate([None,{}, {'pve2':{'pve2':[]}}, {'pve2':{'pve2':['vmbr999']}}]):
            candidate=copy.deepcopy(policy)
            if scope is None:candidate['broker'].pop('bridges')
            else:candidate['broker']['bridges']=scope
            refused=self.directory/f'refused-scope-{index}'
            with patch.object(snapshot,'HCP',return_value=hcp):
                with self.assertRaises(control.Refused):snapshot.produce(candidate,ROOT,'n'*24,refused)
            self.assertFalse((refused/'manifest.json').exists())
        raw['outputs']['openbao_testbed_identifiers']['value']['bao']['private']='SECRET_CANARY'
        refused=self.directory/'refused-bundle'
        with patch.object(snapshot,'HCP',return_value=hcp):
            with self.assertRaises(control.Refused):snapshot.produce(policy,ROOT,'n'*24,refused)
        self.assertFalse((refused/'manifest.json').exists())

    def test_snapshot_finalization_marks_updated_state_stale(self):
        now=int(time.time())
        payload={'purpose':'plan-snapshot','nonce':'n'*24,'issued_at':now-1,'expires_at':now+100,
                 'state_version':'sv-old','source_sha':'a'*40,'coverage':{'status':'partial'}}
        policy={'keys':{'current':self.public},'key_id':'current','signing_key':str(self.key)}
        hcp=type('HCP',(),{'current':lambda self:{'id':'sv-new'}})()
        with patch.object(snapshot,'HCP',return_value=hcp):
            result=snapshot.finalize(policy,control.sign(payload,'current',self.key))
        self.assertEqual(control.verify(result,policy['keys'],'plan-result')['status'],'stale')


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((ROOT/'ci/proxmox-plan-policy.json').read_text())
        self.schema=json.loads((ROOT/'ci/agent-provider-schema.json').read_text())
    def test_current_native_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            changes=projection.project_source(ROOT/'terraform',Path(directory),self.policy)
            self.assertTrue(changes)
            provider=(Path(directory)/'proxmox/provider.tf').read_text()
            self.assertNotIn('var.pm_api_token',provider)
            self.assertNotIn('ssh {',provider)
            self.assertNotIn('cloud {',(Path(directory)/'proxmox/versions.tf').read_text())
            inventory=(Path(directory)/'proxmox/pve-cluster.tf').read_text()
            self.assertIn('192.168.1.50',inventory)
            self.assertNotIn('var.proxmox_ssh_password',inventory)
    def test_secret_cardinality_rejected(self):
        text='resource "ansible_host" "bad" { count = length(var.proxmox_ssh_password) }'
        with self.assertRaises(control.Refused):projection.project_file(text,'bad.tf',self.policy)
        for text in ['data "external" "x" {}','module "x" { source = "https://bad" }', 'resource "x" "y" { provisioner "local-exec" { command = "bad" } }']:
            with self.assertRaises(control.Refused):projection.project_file(text,'bad.tf',self.policy)
    def state(self):
        return {'version':4,'serial':1,'lineage':'fixture','resources':[{'mode':'managed','type':'ansible_host','name':'pve0','provider':'provider["registry.terraform.io/ansible/ansible"]','instances':[{'schema_version':self.schema['provider_schemas']['registry.terraform.io/ansible/ansible']['resource_schemas']['ansible_host']['version'],'attributes':{'id':'pve0','name':'pve0','groups':['proxmox_cluster'],'variables':{'ansible_host':'192.0.2.1','ansible_ssh_pass':'SECRET_CANARY_ONLY_IN_RAW_STATE'}}}]}],'outputs':{}}
    def test_mixed_map_secret_removed_public_preserved(self):
        raw=self.state();result,_=projection.project_state(raw,self.schema)
        serialized=json.dumps(result)
        self.assertNotIn('SECRET_CANARY',serialized)
        self.assertIn('192.0.2.1',serialized)
        self.assertIn('SECRET_CANARY',json.dumps(raw))
        self.assertEqual(result['resources'][0]['instances'][0]['attributes']['variables']['ansible_ssh_pass'],projection.sentinel('variable:proxmox_ssh_password'))
    def test_unknown_private_schema_output_or_map_fails(self):
        for modify in [lambda s:s['resources'][0]['instances'][0].update(private='b3BhcXVl'),
                       lambda s:s['resources'][0]['instances'][0].update(schema_version=999),
                       lambda s:s['resources'][0]['instances'][0].update(identity_schema_version=1),
                       lambda s:s['resources'][0]['instances'][0]['attributes']['variables'].update(new_secret='CANARY'),
                       lambda s:s.update(outputs={'nested':{'sensitive':True,'value':{'token':'CANARY'}}})]:
            state=self.state();modify(state)
            with self.assertRaises(control.Refused):projection.project_state(state,self.schema)
    def test_backend_rewrite_ignores_quoted_braces_and_comments(self):
        native='terraform {\n # }\n cloud { organization="fixture" workspaces { name="x" } }\n required_version="1.14.4"\n}\nvariable "x" { default = "{ bracket }" }'
        result,_=projection.project_file(native,'fixture.tf',self.policy)
        self.assertIn('backend "local"',result)
        self.assertIn('"{ bracket }"',result)

    def public_state(self):
        raw=self.state()
        def resource(kind,name,attrs,index=None):
            definitions=self.schema['provider_schemas']['registry.terraform.io/bpg/proxmox']['resource_schemas']
            instance={'schema_version':definitions[kind]['version'] if kind in definitions else 0,'attributes':attrs}
            if index is not None:instance['index_key']=index
            raw['resources'].append({'mode':'managed','type':kind,'name':name,'provider':'provider["registry.terraform.io/bpg/proxmox"]' if kind!='terraform_data' else 'provider["terraform.io/builtin/terraform"]','instances':[instance]})
        allocation={'nic_slot':1,'node':'pve2','bridge':'vmbr501','address':'10.0.0.2/30','gateway':'10.0.0.1','mac_address':'02:00:00:00:00:02','gateway_mac':'02:00:00:00:00:01','dns_server':'1.1.1.1'}
        payload={'value':allocation,'type':['object',projection.ALLOCATION_FIELDS]}
        resource('terraform_data','employee_slot',{'id':'slot','input':payload,'output':payload,'triggers_replace':None},'pilot')
        resource('proxmox_virtual_environment_file','hook',{'id':'local:snippets/hook.py','source_raw':[{'data':'SECRET_CANARY_SNIPPET','file_name':'hook.py','resize':0}]})
        resource('proxmox_virtual_environment_network_linux_bridge','employee',{'id':'pve2:vmbr501','name':'vmbr501','node_name':'pve2','comment':'SECRET_CANARY_COMMENT'})
        raw['resources'][-1]['provider']='provider["registry.terraform.io/bpg/proxmox"].pve2'
        raw['resources'][0]['instances'][0]['attributes']['variables'].update(employee_workspace_admin_public_keys_json='["SECRET_CANARY_KEY"]',employee_access_networks_json=json.dumps({'pilot':{'vmid':501,'bridge':'vmbr501'}}))
        fields={'ip':'string','name':'string','vmid':'number'}
        raw['outputs']={'openbao_testbed_identifiers':{'sensitive':False,'type':['object',{'bao':['object',fields],'trusted_control':['object',fields]}],'value':{'bao':{'ip':'192.0.2.1','name':'bao','vmid':112},'trusted_control':{'ip':'192.0.2.2','name':'control','vmid':113}}}}
        return raw

    def test_public_structured_state_redactions_and_types(self):
        raw=self.public_state();projected,_=projection.project_state(raw,self.schema)
        self.assertNotIn('SECRET_CANARY',json.dumps(projected))
        self.assertEqual(projected['resources'][1]['instances'][0]['attributes']['input']['value']['nic_slot'],1)
        for modify in [lambda s:s['resources'][1]['instances'][0]['attributes']['input']['type'][1].update(nic_slot='string'),
                       lambda s:s['resources'][0]['instances'][0]['attributes']['variables'].update(employee_access_networks_json='{"pilot":{"private":"CANARY"}}'),
                       lambda s:s['outputs']['openbao_testbed_identifiers']['value']['bao'].update(private='CANARY'),
                       lambda s:s['resources'][2]['instances'][0]['attributes'].update(source_file=[{'path':'https://bad'}]),
                       lambda s:s['resources'][1]['instances'][0].update(private='b3BhcXVl'),
                       lambda s:s['resources'][2]['instances'][0]['attributes']['source_raw'][0].update(file_name={'nested':'CANARY'})]:
            candidate=copy.deepcopy(raw);modify(candidate)
            with self.assertRaises(control.Refused):projection.project_state(candidate,self.schema)

    def test_current_inputs_keep_cardinality_and_source_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            projection.project_source(ROOT/'terraform',directory,self.policy)
            inputs=json.loads((Path(directory)/'proxmox/projection.auto.tfvars.json').read_text())
            # Employee workspaces, VM500 and ws-executor live in terraform/remotecc, which Jenkins never reads.
            for name in ('oci_hub_workspaces','employee_workspaces','employee_access'):self.assertNotIn(name,inputs)
            self.assertFalse((Path(directory)/'proxmox/oci-hub-workspace.tf').exists())
            for file in (ROOT/'terraform/proxmox').glob('*.tf'):
                original=projection.blocks(file.read_text());projected=projection.blocks((Path(directory)/'proxmox'/file.name).read_text())
                self.assertEqual([(b['kind'],b['labels']) for b in original],[(b['kind'],b['labels']) for b in projected])

    def test_source_input_template_and_link_changes_fail_closed(self):
        for relative in ['proxmox/provisioning.auto.tfvars.json','proxmox/main.tf']:
            with tempfile.TemporaryDirectory() as directory:
                source=Path(directory)/'source';destination=Path(directory)/'out'
                for name in self.policy['source_files']:
                    target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'terraform'/name,target)
                (source/relative).write_text((source/relative).read_text()+'\n# UNREVIEWED_CANARY')
                with self.assertRaises(control.Refused):projection.project_source(source,destination,self.policy)
                (source/relative).unlink();(source/relative).symlink_to(ROOT/'terraform'/relative)
                with self.assertRaises(control.Refused):projection.project_source(source,destination,self.policy)
        with self.assertRaises(control.Refused):projection.project_file('resource "proxmox_virtual_environment_file" "bad" { source_file { path = "/private" } }','bad.tf',self.policy)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.json';path.write_text('{"netbox_provisioned_vms":[],"private":"CANARY"}')
            with self.assertRaises(control.Refused):projection.public_inputs(path,'proxmox/provisioning.auto.tfvars.json')
            path.write_text('{"netbox_provisioned_vms":[],"oci_hub_workspaces":{}}')
            with self.assertRaises(control.Refused):projection.public_inputs(path,'proxmox/provisioning.auto.tfvars.json')


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((ROOT/'ci/proxmox-plan-policy.json').read_text())['broker']
        self.policy['vmids']={'primary':{'pve0':[110]}}
    def test_read_routes_and_query_adaptation(self):
        alias,path,adapter=gateway.route('/primary/api2/json/nodes/pve0/lxc/110/config',self.policy)
        self.assertEqual(alias,'primary')
        response=gateway.filter_value({'data':{'cores':2,'memory':2048,'unreviewed_token':'CANARY'}},adapter['response'])
        self.assertEqual(response,{'data':{'cores':2,'memory':2048}})
        from urllib.parse import urlencode
        query=urlencode(self.policy['download_probes'][0]['query'])
        self.assertEqual(gateway.route('/primary/api2/json/nodes/pve0/query-url-metadata?'+query,self.policy)[2]['adaptation'],'fixed-image-head')
    def test_invalid_routes_fail_closed(self):
        for path in ['https://evil/api2/json','/primary/api2/json/nodes/pve2/lxc/110/config',
                     '/primary/api2/json/nodes/pve0/lxc/111/config','/primary/api2/json/access/ticket',
                     '/primary/api2/json/nodes/pve0/lxc/110/status/start','/primary/api2/json/nodes/pve0/lxc/110/config?x=1',
                     '/primary/api2/json/nodes/pve0/lxc/110/config?x=1&x=2',
                     '/primary/api2/json/nodes/pve0/query-url-metadata?url=https%3A%2F%2Fevil',
                     '/primary/api2/json/nodes/pve0/network/vmbr999',
                     '/primary/api2/json/nodes/pve0/%2e%2e/access']:
            with self.subTest(path=path),self.assertRaises((control.Refused,ValueError)):gateway.route(path,self.policy)
    def test_redirects_and_response_schema_mismatch_fail(self):
        with self.assertRaises(control.Refused):gateway.NoRedirect().redirect_request(None,None,None,None,None,None)
        with self.assertRaises(control.Refused):gateway.filter_value({'data':{'cores':{'secret':'CANARY'}}},{'type':'object','properties':{'data':{'type':'object','properties':{'cores':{'type':'scalar'}}}}})


class ClientLayoutTests(unittest.TestCase):
    def test_clients_reject_http_redirects_without_broker_service_file(self):
        with tempfile.TemporaryDirectory() as directory:
            layout=Path(directory)
            for name in ['control','job-runner','transaction','peer-preflight','plan-snapshot']:
                shutil.copyfile(ROOT/'scripts/jenkins'/f'{name}.py',layout/f'{name}.py')
            result=subprocess.run([sys.executable,'-c',r"""
import importlib.machinery, json, pathlib, ssl, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch, Mock
import control

def load(name):
    return importlib.machinery.SourceFileLoader(name.replace('-', '_'),name+'.py').load_module()
runner, transaction, preflight, snapshot=map(load,['job-runner','transaction','peer-preflight','plan-snapshot'])
requests=[]
class Redirect(BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append((self.path,self.headers.get('Authorization')))
        self.send_response(302)
        self.send_header('Location','/redirect-target')
        self.end_headers()
    do_POST=do_GET
    def log_message(self,*args): pass
server=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
original_open=urllib.request.OpenerDirector.open

def local_open(opener,request,*args,**kwargs):
    request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/initial',
                                   data=request.data,headers=dict(request.header_items()))
    return original_open(opener,request,*args,**kwargs)

path=pathlib.Path('synthetic-token');path.write_text('SYNTHETIC');path.chmod(0o600)
trust=pathlib.Path('trust.json');trust.write_text(json.dumps({'hcp_workspace_id':'ws-fixture'}))
secret=pathlib.Path('secrets');secret.mkdir()
(secret/'hcp-credentials.json').write_text(json.dumps({'credentials':{'app.terraform.io':{'token':'SYNTHETIC'}}}))
instance=runner.Runner.__new__(runner.Runner)
instance.config={'controller':{'url':'https://192.168.1.107:9444','ca':'synthetic','certificate':'synthetic','private_key':'synthetic'}}
with patch.object(ssl,'create_default_context',return_value=Mock()), patch.object(urllib.request.OpenerDirector,'open',local_open), patch.object(snapshot,'secret_file',lambda path:pathlib.Path(path)), patch.object(transaction,'TRUST',trust), patch.object(transaction,'JOB',pathlib.Path('.')):
    hcp=snapshot.HCP({'state_token_file':str(path)})
    calls=[lambda:instance.controller('lease',{}),lambda:transaction.state_identity(pathlib.Path('.')),
           lambda:preflight.get('https://fixture.invalid/read','SYNTHETIC'),lambda:hcp.get('/api/v2/workspaces/ws-fixture')]
    for call in calls:
        try:call()
        except control.Refused:pass
        else:raise AssertionError('client followed an upstream redirect')
server.shutdown();server.server_close();thread.join()
assert len(requests)==4,requests
assert all(path=='/initial' for path,_ in requests),requests
"""],cwd=layout,text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class RunnerTests(unittest.TestCase):
    def test_dual_stack_network_default_deny(self):
        rules=runner.network_rules([{'ip':'192.0.2.1','port':9443}])
        self.assertIn('table inet',rules)
        self.assertIn('policy drop',rules)
        self.assertNotIn('udp dport 53',rules)
        self.assertNotIn('lo accept',rules)
        self.assertNotIn('8006',rules)
        with self.assertRaises(control.Refused):runner.network_rules([{'ip':'127.0.0.1','port':80}])
        with self.assertRaises(control.Refused):runner.network_rules([{'ip':'::1','port':80}])
    def test_quarantine_and_registry_block_release(self):
        with tempfile.TemporaryDirectory() as directory:
            service=runner.Runner(directory,{'profiles':{},'keys':{}})
            (Path(directory)/'run-fixture.json').write_text('{}')
            with self.assertRaises(control.Refused):service.release()
    def test_restore_resource_admission(self):
        with self.assertRaises(control.Refused):maintenance.check_resources(100,100000000000,100000,100,100,0)
        with self.assertRaises(control.Refused):maintenance.check_resources(1792*1024,1024,100000,100,100,0)
        with self.assertRaises(control.Refused):maintenance.check_resources(1792*1024,100000000000,1,100,100,0)
    def test_global_lock_and_quarantine_precede_secret_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            service=runner.Runner(directory,{'profiles':{},'keys':{}})
            payload={'nonce':'q'*24,'build':1,'sha':'a'*40,'scope':['root:proxmox']}
            with patch.object(runner,'validate_admission',return_value=(payload,{})),patch.object(service,'controller') as transport:
                with open(Path(directory)/'global.lock','a+b') as held:
                    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with self.assertRaises(control.Refused):service.execute({},1001)
                (Path(directory)/'quarantine.json').write_text('{}')
                with self.assertRaises(control.Refused):service.execute({},1001)
                transport.assert_not_called()

    def test_backup_links_and_cross_root_members_rejected(self):
        for name,kind in [('../etc/passwd',tarfile.REGTYPE),('home/link',tarfile.SYMTYPE),('home/device',tarfile.CHRTYPE)]:
            buffer=io.BytesIO()
            with tarfile.open(fileobj=buffer,mode='w') as archive:
                member=tarfile.TarInfo(name);member.type=kind;member.linkname='/etc/passwd';archive.addfile(member)
            buffer.seek(0)
            with tarfile.open(fileobj=buffer) as archive,self.assertRaises(control.Refused):maintenance.inspect_tar(archive)

    def test_new_allocation_conflicts_refuse_without_writes(self):
        templates=[{'volid':'local:vztmpl/'+preflight.TARGET['template']}]
        storage={'active':1,'avail':32*1024**3,'content':'images,rootdir'}
        preflight.validate([],{'count':0,'results':[],'next':None,'previous':None},templates,storage)
        for resources,ipam,images,pool in [([{'vmid':110}],{'count':0},templates,storage),([],{'count':1},templates,storage),([],{'count':0},[],storage),([],{'count':0},templates,dict(storage,avail=1))]:
            with self.assertRaises(control.Refused):preflight.validate(resources,ipam,images,pool)

    def test_unarmed_and_ordinary_network_loss_never_restore(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(watchdog,'BASE',Path(directory)),patch.object(watchdog,'request') as transport:
            service=watchdog.Watchdog({})
            service.tick();transport.assert_not_called()
            record={'phase':'armed','nonce':'m'*24,'expires_at':int(time.time())+60}
            (Path(directory)/'maintenance.json').write_text(json.dumps(record))
            service.tick();transport.assert_not_called()
            record['phase']='started';(Path(directory)/'maintenance.json').write_text(json.dumps(record))
            transport.side_effect=OSError('synthetic SSH outage')
            service.tick()
            self.assertEqual([call.args[1]['mode'] for call in transport.call_args_list],['status'])
            self.assertTrue((Path(directory)/'maintenance-diagnostic.json').exists())

    def test_complete_toolchain_hashes(self):
        lock=json.loads((ROOT/'ci/agent-toolchain.lock.json').read_text())
        toolchain.validate_lock(lock)
        self.assertEqual(lock['provider_lock_text'],(ROOT/lock['provider_lock']).read_text())
        self.assertEqual(lock['provider_lock_sha256'],control.sha_file(ROOT/lock['provider_lock']))
        self.assertEqual(lock['collections_lock_sha256'],control.sha_file(ROOT/lock['collections_lock']))
        lock['python_packages'][0]['hashes']=[]
        with self.assertRaises(control.Refused):toolchain.validate_lock(lock)


if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='--project-native':
        destination=Path('/tmp/jenkins-peer-native-validation');destination.mkdir(exist_ok=True)
        projection.project_source(ROOT/'terraform',destination,json.loads((ROOT/'ci/proxmox-plan-policy.json').read_text()))
        (destination/'proxmox/.terraform.lock.hcl').write_bytes((ROOT/'terraform/proxmox/.terraform.lock.hcl').read_bytes())
    else:unittest.main()
