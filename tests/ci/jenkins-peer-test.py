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
