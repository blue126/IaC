#!/usr/bin/env python3
"""Execute repaired trust boundaries using only synthetic files and services."""
import concurrent.futures
import copy
import errno
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import tarfile
import threading
import time
import types
import unittest
from importlib.machinery import SourceFileLoader
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control

def load(name):return SourceFileLoader('repair_'+name.replace('-','_'),str(ROOT/'scripts/jenkins'/name)+'.py').load_module()
runner=load('job-runner');admission=load('controller-admission');transaction=load('transaction')
maintenance=load('controller-maintenance');watchdog=load('watchdog');probe=load('isolation-probe');entry=load('job-entry');materials=load('validate-materials')


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.key=self.base/'key';self.public=self.base/'public'
        subprocess.run(['openssl','genpkey','-algorithm','ed25519','-out',str(self.key)],check=True,capture_output=True)
        subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.public)],check=True,capture_output=True)
        original=control.private_file
        self.install(control,'private_file',lambda path,owner=0:original(path,owner=os.getuid()))
        for module in [admission,maintenance,entry]:self.install(module,'private_file',lambda path,owner=0:original(path,owner=os.getuid()))
        self.install(runner,'REMOTING_READY',self.base/'runner-remoting-ready')
        self.install(watchdog,'REMOTING_READY',self.base/'watchdog-remoting-ready')
        self.keys={'current':str(self.public)}
    def install(self,obj,name,value):
        item=patch.object(obj,name,value);item.start();self.addCleanup(item.stop);return item
    def sign(self,purpose,**values):
        now=int(time.time());return control.sign({'purpose':purpose,'nonce':'synthetic_nonce_123456789','issued_at':now,'expires_at':now+120,**values},'current',self.key)


class RunnerTests(Fixture):
    def execute_fixture(self,notion_error=None,complete_error=None,profile_name='deploy'):
        service=runner.Runner(self.base,{'keys':self.keys,'profiles':{},'evidence_key_id':'current','evidence_signing_key':str(self.key)})
        payload={'nonce':'lifecycle_fixture_123456','build':1,'sha':'a'*40,'scope':[],'credential_versions':{},'job':'fixture','profile_sha256':'b'*64}
        archive=self.base/'source.tar'
        with tarfile.open(archive,'w') as target:
            item=tarfile.TarInfo('fixture.txt');item.size=7;target.addfile(item,io.BytesIO(b'fixture'))
        payload['bundle_sha256']=control.sha_file(archive)
        profile={'name':profile_name,'user':'iac-plan' if profile_name=='plan' else 'iac-deploy','scope':[],'timeout':60,'executable':'/opt/jenkins-agent/control/job-entry.py'}
        ca=self.base/'broker-ca.pem'
        if profile_name=='plan':subprocess.run(['openssl','req','-x509','-newkey','ed25519','-nodes','-days','1','-subj','/CN=SyntheticBroker','-keyout',str(self.base/'broker.key'),'-out',str(ca)],check=True,capture_output=True)
        executable=self.base/'entry.py';executable.write_text('# synthetic entry');executable.chmod(0o500)
        actual_chmod=os.chmod
        def chmod(path,mode,**kwargs):
            if not str(path).startswith('/run/jenkins-control-canary-'):actual_chmod(path,mode,**kwargs)
        calls=[];events=iter([{'phase':'isolation-verified'},{'phase':'starting' if profile_name=='plan' else 'notion-sync'},{'phase':'verified'},{'phase':'verified'}]);ticks=[0]
        def transport(operation,data,stream=None):
            if operation=='bundle':stream.write_bytes(archive.read_bytes())
            elif operation=='secrets':
                if notion_error:raise notion_error
                return {}
            elif operation=='complete':
                self.assertTrue((self.base/('result-'+payload['nonce']+'.json')).exists())
                if complete_error:raise complete_error
            elif operation=='finalize':return self.sign('plan-result',nonce=payload['nonce'],status='fresh')
            return {}
        def command(argv):
            calls.append(argv)
            if argv[:2]==['systemctl','show']:
                if 'MainPID' in argv:return '123'
                ticks[0]+=1
                return 'SubState='+('exited' if ticks[0]>=3 else 'running')+'\nExecMainStatus=0\nResult=success'
            return ''
        with patch.object(runner,'validate_admission',return_value=(payload,profile)),patch.object(runner,'private_file',side_effect=lambda path:ca if str(path)=='/etc/jenkins-agent/control/broker-ca.pem' else executable),patch.object(runner.os,'chown'),patch.object(runner.os,'chmod',side_effect=chmod),patch.object(runner.os,'readlink',return_value='synthetic-namespace'),patch.object(runner.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_gid=os.getgid())),patch.object(runner.shutil,'disk_usage',return_value=types.SimpleNamespace(free=10*1024**3)),patch.object(runner.socket,'socket') as sockets,patch.object(runner,'command',side_effect=command),patch.object(service,'controller',side_effect=transport),patch.object(service,'start_network',return_value='/run/netns/synthetic'),patch.object(service,'prepare_proc_probe',side_effect=lambda record,_:record.update(remoting_pid=123,remoting_canary='/synthetic/canary')),patch.object(service,'refresh_lease'),patch.object(service,'release_initial_secrets'),patch.object(service,'cleanup'),patch.object(service.cancelled,'wait',return_value=False),patch.object(runner,'read_job_report',side_effect=lambda *args:next(events)):
            sockets.return_value.getsockname.return_value=('127.0.0.1',12345)
            result=service.execute({},os.getuid())
        unit=next(argv for argv in calls if argv[0]=='systemd-run')
        self.assertIn('PrivateUsers=yes',unit)
        directory=self.base/('job-'+payload['nonce'])
        self.assertIn('user',json.loads((directory/'control/isolation.json').read_text())['host_namespaces'])
        return result,directory

    def test_plan_ca_staging_and_execute_hook_use_public_readable_certificate(self):
        import ssl
        service=runner.Runner(self.base,{'keys':{},'profiles':{}});job=self.base/'plan';(job/'control').mkdir(parents=True)
        ca=self.base/'ca.pem'
        subprocess.run(['openssl','req','-x509','-newkey','ed25519','-nodes','-days','1','-subj','/CN=SyntheticCA','-keyout',str(self.base/'ca.key'),'-out',str(ca)],check=True,capture_output=True)
        def source(path):
            self.assertEqual(str(path),'/etc/jenkins-agent/control/broker-ca.pem');return ca
        target=job/'control/broker-ca.pem'
        with patch.object(runner,'private_file',side_effect=source):service.prepare_plan_ca(job,{'name':'plan'})
        self.assertEqual(target.read_bytes(),ca.read_bytes());self.assertEqual(target.stat().st_mode&0o777,0o444)
        ssl.create_default_context(cafile=str(target));target.unlink()
        with patch.object(runner,'private_file') as read:
            service.prepare_plan_ca(job,{'name':'deploy'});read.assert_not_called()
        ca.write_text('invalid certificate')
        with patch.object(runner,'private_file',side_effect=source),self.assertRaises(ssl.SSLError):service.prepare_plan_ca(job,{'name':'plan'})
        self.assertFalse(target.exists())
        with FixtureContext(self):
            result,directory=self.execute_fixture(profile_name='plan')
            self.assertEqual(result['status'],'completed')
            staged=directory/'control/broker-ca.pem';self.assertEqual(staged.stat().st_mode&0o777,0o444)
            self.assertEqual(staged.read_bytes(),(self.base/'broker-ca.pem').read_bytes())

    def test_execute_persists_success_before_failed_completion_notification(self):
        result,_=self.execute_fixture(complete_error=OSError('synthetic controller unavailable'))
        self.assertEqual(result['status'],'completed');self.assertEqual(result['exit_code'],0)
        self.assertTrue(control.verify(result['evidence'],self.keys,'job-run-evidence')['isolation_verified'])

    def test_optional_notion_transport_failure_preserves_deploy_but_binding_mismatch_refuses(self):
        result,directory=self.execute_fixture(notion_error=OSError('synthetic unavailable'))
        self.assertEqual(result['status'],'completed')
        self.assertEqual(json.loads((directory/'control/notion-ready.json').read_text()),{'ready':False})
        with FixtureContext(self):
            with self.assertRaisesRegex(control.Refused,'version changed'):self.execute_fixture(notion_error=control.Refused('version changed'))

    def test_plan_command_uses_root_projected_broker_ca_in_clean_environment(self):
        task=load('plan-task');workspace=self.base/'workspace';workspace.mkdir()
        (workspace/'terraform/proxmox').mkdir(parents=True)
        manifest=self.sign('plan-snapshot',source_sha='a'*40,files={},coverage={'status':'partial'})
        control.atomic_json(workspace/'manifest.json',manifest)
        trust=self.base/'trust.json';control.atomic_json(trust,{'keys':self.keys})
        report=self.base/'report.json';actual=Path
        def paths(value):
            return {'/job/workspace':workspace,'/opt/jenkins-agent/control/trust.json':trust,'/job/report/status.json':report}.get(str(value),actual(value))
        calls=[];actual_run=subprocess.run
        def run(argv,**kwargs):
            if argv[0]!='terraform':return actual_run(argv,**kwargs)
            calls.append((argv,kwargs));return types.SimpleNamespace(returncode=0,stdout='{"resource_changes":[]}')
        with patch.object(task,'Path',side_effect=paths),patch.object(task.sys,'argv',['plan-task.py','a'*40,'1','synthetic_nonce_123456789']),patch.object(task.subprocess,'run',side_effect=run),patch.dict(os.environ,{'SSL_CERT_FILE':'/untrusted/caller-ca.pem'},clear=True):task.main()
        self.assertEqual(len(calls),3)
        for argv,values in calls:
            self.assertEqual(values['env']['SSL_CERT_FILE'],'/job/control/broker-ca.pem')
            self.assertEqual(values['cwd'],workspace/'terraform/proxmox')
        self.assertEqual(json.loads(report.read_text())['phase'],'prediction-finished')

    def test_bounded_job_report_rejects_fifo_links_owner_size_and_types(self):
        path=self.base/'report'
        os.mkfifo(path)
        started=time.monotonic()
        with self.assertRaises(control.Refused):control.read_job_report(path,os.getuid())
        self.assertLess(time.monotonic()-started,.5);path.unlink()
        target=self.base/'target';target.write_text('{}');path.symlink_to(target)
        with self.assertRaises(control.Refused):control.read_job_report(path,os.getuid())
        path.unlink();path.write_text('x'*65537)
        with self.assertRaises(control.Refused):control.read_job_report(path,os.getuid())
        path.write_text('{"phase":')
        self.assertIsNone(control.read_job_report(path,os.getuid()))
        path.write_text('[]')
        with self.assertRaises(control.Refused):control.read_job_report(path,os.getuid())
        path.write_text('{"phase":"starting"}')
        with self.assertRaises(control.Refused):control.read_job_report(path,os.getuid()+1)
        self.assertEqual(control.read_job_report(path,os.getuid()),{'phase':'starting'})
    def test_reservation_persists_before_status_and_allows_only_one_start(self):
        service=runner.Runner(self.base,{'keys':{},'profiles':{}})
        payload={'nonce':'reserved_nonce_123456789','build':1,'sha':'a'*40,'scope':[],'credential_versions':{}}
        profile={'name':'plan'}
        with patch.object(runner,'validate_admission',return_value=(payload,profile)):
            def start(_):
                try:return service.reserve({},os.getuid())
                except control.Refused:return None
            with concurrent.futures.ThreadPoolExecutor(2) as workers:results=list(workers.map(start,range(2)))
        self.assertEqual(sum(result is not None for result in results),1)
        self.assertTrue((self.base/('run-'+payload['nonce']+'.json')).exists())
        self.assertEqual(service.status(payload['nonce'],os.getuid()),{'phase':'starting'})
    def test_cleanup_skips_stop_only_for_proved_not_found(self):
        service=runner.Runner(self.base,{'keys':{},'profiles':{}})
        nonce='absent_unit_nonce_123456'
        record={'nonce':nonce,'unit':'iac-job-'+nonce+'.service','directory':str(self.base/('job-'+nonce)),'profile':'plan'}
        for state in ['not-found','unknown','']:
            calls=[]
            with patch.object(runner,'command',side_effect=lambda argv:calls.append(argv) or state),patch.object(runner.subprocess,'run'):
                if state=='not-found':service.cleanup(record)
                else:
                    with self.assertRaises(control.Refused):service.cleanup(record)
            self.assertFalse(any(argv[:2]==['systemctl','stop'] for argv in calls))
    def test_slow_local_request_does_not_block_status(self):
        service=runner.Runner(self.base,{'keys':{},'profiles':{}})
        nonce='slow_request_nonce_123456'
        control.atomic_json(self.base/('used-'+nonce+'.json'),{'uid':os.getuid()})
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(self.base/'socket'));listener.listen(16)
        real_socket=socket.socket
        def sockets(*args,**kwargs):return listener if kwargs.get('fileno')==3 else real_socket(*args,**kwargs)
        with patch.object(runner.socket,'socket',side_effect=sockets),patch.dict(os.environ,{'LISTEN_FDS':'1','LISTEN_PID':str(os.getpid())},clear=True),patch.object(service,'reconcile'),patch.object(service,'resume_agents'),patch.object(runner.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=os.getuid())):
            thread=threading.Thread(target=runner.serve,args=(service,));thread.start()
            slow=real_socket(socket.AF_UNIX,socket.SOCK_STREAM);slow.connect(str(self.base/'socket'));slow.sendall(b'{')
            fast=real_socket(socket.AF_UNIX,socket.SOCK_STREAM);fast.settimeout(1);fast.connect(str(self.base/'socket'))
            start=time.monotonic();fast.sendall(control.canonical({'operation':'status','nonce':nonce})+b'\n')
            self.assertEqual(json.loads(fast.recv(1024)),{'phase':'starting'});self.assertLess(time.monotonic()-start,.8)
            fast.close();slow.close();service.stopping.set();thread.join(2)
            self.assertFalse(thread.is_alive())
        listener.close()
    def test_selector_tolerates_stale_events_and_transient_accept_errors(self):
        service=runner.Runner(self.base,{'keys':{},'profiles':{}});listener=unittest.mock.MagicMock();listener.accept.side_effect=[BlockingIOError(),ConnectionAbortedError()]
        stale=object();rounds=[0]
        selector=unittest.mock.MagicMock()
        def select(timeout):
            rounds[0]+=1
            if rounds[0]>2:service.stopping.set();return []
            return [(types.SimpleNamespace(fileobj=listener),1),(types.SimpleNamespace(fileobj=stale),1)]
        selector.select.side_effect=select
        with patch.object(service,'reconcile'),patch.object(service,'resume_agents'),patch.object(runner.socket,'socket',return_value=listener),patch.object(runner.selectors,'DefaultSelector',return_value=selector),patch.object(runner.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=os.getuid())),patch.dict(os.environ,{'LISTEN_FDS':'1','LISTEN_PID':str(os.getpid())},clear=True):runner.serve(service)
        self.assertEqual(listener.accept.call_count,2)

    def test_non_owner_approval_is_rejected_before_consuming_rpc_capacity(self):
        service=runner.Runner(self.base,{'keys':{},'profiles':{}});service.active={'uid':os.getuid()+1,'nonce':'active_nonce_12345678'}
        listener=unittest.mock.MagicMock();connection=unittest.mock.MagicMock();listener.accept.return_value=(connection,None)
        connection.getsockopt.return_value=__import__('struct').pack('3i',os.getpid(),os.getuid(),os.getgid())
        connection.recv.return_value=control.canonical({'operation':'approval','nonce':'active_nonce_12345678','stage':'terraform','digest':'a'*64})+b'\n'
        rounds=[0];selector=unittest.mock.MagicMock()
        def select(timeout):
            rounds[0]+=1
            if rounds[0]==1:return [(types.SimpleNamespace(fileobj=listener),1)]
            if rounds[0]==2:return [(types.SimpleNamespace(fileobj=connection),1)]
            service.active=None;service.stopping.set();return []
        selector.select.side_effect=select
        with patch.object(service,'reconcile'),patch.object(service,'resume_agents'),patch.object(runner.socket,'socket',return_value=listener),patch.object(runner.selectors,'DefaultSelector',return_value=selector),patch.object(runner.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=os.getuid())),patch.object(runner,'ThreadPoolExecutor') as workers,patch.dict(os.environ,{'LISTEN_FDS':'1','LISTEN_PID':str(os.getpid())},clear=True):
            runner.serve(service);workers.return_value.__enter__.return_value.submit.assert_not_called()
        self.assertEqual(json.loads(connection.sendall.call_args.args[0]),{'status':'refused'})

    def test_remoting_resume_requires_no_persistent_fence(self):
        service=runner.Runner(self.base,{'keys':{},'profiles':{}})
        with patch.object(runner,'command') as call:
            for fence in ['quarantine.json','maintenance.json','agent-update-incomplete','agent-update-pending']:
                (self.base/fence).touch();service.resume_agents();(self.base/fence).unlink()
            call.assert_not_called();self.assertFalse(runner.REMOTING_READY.exists())
            service.resume_agents();self.assertEqual(call.call_count,3);self.assertTrue(runner.REMOTING_READY.exists())
            (self.base/'maintenance.json').touch();service.resume_agents();self.assertFalse(runner.REMOTING_READY.exists())

    def test_cleanup_removes_only_this_runs_same_uid_probe_canary(self):
        service=runner.Runner(self.base,{'profiles':{},'keys':{}})
        nonce='cleanup_proc_nonce_123456789';directory=self.base/('job-'+nonce);directory.mkdir()
        homes=self.base/'homes';home=homes/'iac-plan';home.mkdir(parents=True)
        canary=home/('.proc-boundary-'+nonce);canary.write_text('synthetic-remoting-boundary:'+nonce)
        sibling=home/'keep-remoting-state';sibling.write_text('preserve')
        record={'nonce':nonce,'unit':'iac-job-'+nonce+'.service','directory':str(directory),'profile':'plan','unix_user':'iac-plan','uid':os.getuid(),'remoting_canary':str(canary)}
        original=Path
        def paths(value,*parts):return homes if str(value)=='/var/lib/jenkins-agent' else original(value,*parts)
        with patch.object(runner,'Path',side_effect=paths),patch.object(runner,'command',return_value='not-found'),patch.object(runner.subprocess,'run'):
            service.cleanup(record)
        self.assertFalse(canary.exists());self.assertFalse(directory.exists());self.assertEqual(sibling.read_text(),'preserve')
        os.mkfifo(canary)
        started=time.monotonic()
        with patch.object(runner,'Path',side_effect=paths),patch.object(runner,'command',return_value='not-found'),patch.object(runner.subprocess,'run'):
            with self.assertRaises(control.Refused):service.cleanup(record)
        self.assertLess(time.monotonic()-started,.5)



class AdmissionTests(Fixture):
    def service(self):
        service=admission.Admission.__new__(admission.Admission);service.base=self.base
        profile={'name':'deploy','user':'iac-deploy','scope':['root:proxmox'],'enabled':True,'secrets':{}}
        service.policy={'profiles':{'fixture':profile},'keys':self.keys,'key_id':'current','signing_key':str(self.key)}
        service.versions=lambda profile:{}
        metadata={'source_binding':{'kind':'fixture'},'sha':'a'*40,'approvals':{'TF-'+'a'*64:'operator','ANSIBLE-'+'b'*64:'operator'}}
        service.metadata=lambda *args,**kwargs:copy.deepcopy(metadata)
        payload={'job':'fixture','build':1,'nonce':'a'*48,'sha':'a'*40,'source_binding':metadata['source_binding'],
                 'profile_sha256':control.digest(control.canonical(profile)),'credential_versions':{}}
        control.atomic_json(self.base/('a'*48+'.json'),{'admission':{'payload':payload},'approvals':{},'deadline':int(time.time())+600,'terminal':False})
        return service
    def test_execution_timeout_is_consistent_and_refuses_non_integer_or_over_budget(self):
        profile={'name':'deploy','user':'iac-deploy','enabled':True,'uid':os.getuid(),'scope':[],'secrets':{}}
        policy={'registry':str(self.base/'registry'),'signing_key':str(self.key),'input_digest_key':str(self.key),'jenkins_api_credentials':str(self.key),'keys':self.keys,'profiles':{'fixture':profile}}
        payload={'job':'fixture','uid':os.getuid(),'unix_user':'iac-deploy','profile':'deploy','scope':[],'sha':'a'*40}
        for timeout in [0,3601,True,'60',None]:
            profile['timeout']=timeout
            with self.subTest(timeout=timeout):
                with self.assertRaises(control.Refused):admission.Admission(policy)
                with patch.object(runner,'verify',return_value=payload),patch.object(runner.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=os.getuid())):
                    with self.assertRaises(control.Refused):runner.validate_admission({}, {'keys':{},'profiles':{'fixture':profile}},os.getuid())
        profile['timeout']=3600;admission.Admission(policy)
        with patch.object(runner,'verify',return_value=payload),patch.object(runner.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=os.getuid())):
            self.assertEqual(runner.validate_admission({}, {'keys':{},'profiles':{'fixture':profile}},os.getuid())[1]['timeout'],3600)

    def test_total_request_read_deadline_closes_stalled_reader_and_releases_slot(self):
        import ssl
        key=self.base/'tls.key';cert=self.base/'tls.crt'
        subprocess.run(['openssl','req','-x509','-newkey','ed25519','-nodes','-days','1','-subj','/CN=fixture','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
        completed=threading.Event()
        class Reader(admission.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                try:self.rfile.read(int(self.headers['Content-Length']))
                except OSError:pass
                finally:completed.set()
        server=admission.AdmissionServer(('127.0.0.1',0),Reader,context)
        server.control=types.SimpleNamespace(collect_expired=lambda **kwargs:None)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        client_context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);client_context.check_hostname=False;client_context.verify_mode=ssl.CERT_NONE
        try:
            with client_context.wrap_socket(socket.create_connection(server.server_address),server_hostname='fixture') as connection:
                connection.sendall(b'POST / HTTP/1.0\r\nContent-Length: 100\r\n\r\n')
                start=time.monotonic()
                for _ in range(10):
                    if completed.wait(.5):break
                    try:connection.sendall(b'x')
                    except OSError:break
                self.assertTrue(completed.wait(.5));self.assertLess(time.monotonic()-start,6)
                self.assertEqual(connection.recv(1),b'')
            self.assertTrue(server.slots.acquire(timeout=1));server.slots.release()
        finally:server.shutdown();thread.join();server.server_close()

    def test_parallel_approvals_preserve_both_stages_and_are_idempotent(self):
        service=self.service()
        def approve(stage):return service.request('approval',{'nonce':'a'*48,'stage':stage,'digest':('a' if stage=='terraform' else 'b')*64},True)
        with concurrent.futures.ThreadPoolExecutor(2) as workers:results=list(workers.map(approve,['terraform','ansible']))
        record=json.loads((self.base/('a'*48+'.json')).read_text())
        self.assertEqual(set(record['approvals']),{'terraform','ansible'})
        self.assertEqual(approve('terraform')['payload'],results[0]['payload'])
    def test_active_archive_survives_gc_then_terminal_or_expired_is_reclaimed(self):
        service=self.service();nonce='a'*48
        for suffix in ['.tar','-source.tar','-snapshot.json']:(self.base/(nonce+suffix)).write_text('synthetic')
        projection=self.base/(nonce+'-projection');projection.mkdir();(projection/'synthetic-state').write_text('synthetic')
        service.collect_expired();self.assertTrue((self.base/(nonce+'.tar')).exists());self.assertTrue(projection.exists())
        service.request('complete',{'nonce':nonce},True)
        for suffix in ['.tar','-source.tar','-snapshot.json']:self.assertFalse((self.base/(nonce+suffix)).exists())
        self.assertFalse(projection.exists())
        record=json.loads((self.base/(nonce+'.json')).read_text());self.assertEqual(set(record),{'terminal','deadline','nonce'})
        nonce='b'*48
        control.atomic_json(self.base/(nonce+'.json'),{'terminal':False,'deadline':int(time.time())-1,'preparing':True})
        (self.base/(nonce+'.tar')).touch();service.collect_expired();self.assertFalse((self.base/(nonce+'.tar')).exists())
    def test_failed_sign_and_failed_projection_remove_exact_run_files(self):
        service=self.service();service.base=self.base/'registry';service.base.mkdir()
        profile=service.policy['profiles']['fixture'];profile.update(uid=os.getuid(),application_inputs={})
        service.metadata=lambda *args,**kwargs:{'source_binding':{'kind':'fixture'},'sha':'a'*40}
        service.resolve_source=lambda metadata,profile:(self.base,'a'*40)
        service.changed_paths=lambda *args:[]
        policy=self.base/'projection-policy.json';policy.write_text('{}');service.policy['projection_policy']=str(policy)
        keep=service.base/'unrelated';keep.write_text('preserve')
        def archive(argv,**kwargs):
            if '--output' in argv:
                import tarfile
                with tarfile.open(argv[argv.index('--output')+1],'w'):pass
            return types.SimpleNamespace(returncode=0)
        with patch.object(admission.subprocess,'run',side_effect=archive),patch.object(admission,'sign',side_effect=control.Refused('synthetic signing failure')):
            with self.assertRaises(control.Refused):service.admit('fixture',1)
        profile['name']='plan'
        fake_projection=types.SimpleNamespace(produce=lambda *args:(_ for _ in ()).throw(control.Refused('synthetic projection failure')))
        fake_unpack=types.SimpleNamespace(check_archive=lambda source:None)
        def loader(name,path):return types.SimpleNamespace(load_module=lambda:fake_projection if name=='snapshot_admission' else fake_unpack)
        with patch.object(admission.subprocess,'run',side_effect=archive),patch('importlib.machinery.SourceFileLoader',side_effect=loader):
            with self.assertRaises(control.Refused):service.admit('fixture',1)
        self.assertEqual(sorted(path.name for path in service.base.iterdir()),['registry.lock','unrelated']);self.assertEqual(keep.read_text(),'preserve')
    def test_binding_rechecks_the_exact_bytes_after_version_resolution(self):
        service=self.service();profile=service.policy['profiles']['fixture']
        secret=self.base/'synthetic-credential';secret.write_bytes(b'synthetic-v1')
        digest_key=self.base/'synthetic-digest-key';digest_key.write_bytes(b'synthetic-hmac-only')
        service.policy.update(input_digest_key=str(digest_key),input_digest_key_id='fixture')
        profile['secrets']={'terraform':{'token':{'version':'v1','path':str(secret)}}}
        service.versions=admission.Admission.versions.__get__(service)
        path=self.base/('a'*48+'.json');record=json.loads(path.read_text())
        record['admission']['payload'].update(credential_versions=service.versions(profile),
                                             profile_sha256=control.digest(control.canonical(profile)))
        control.atomic_json(path,record)
        bound=service.request('secrets',{'nonce':'a'*48,'stage':'terraform'},True)
        self.assertEqual(admission.base64.b64decode(bound['token']['value']),b'synthetic-v1')
        original_existing=service.existing
        def rotate_after_resolution(nonce):
            result=original_existing(nonce)
            secret.write_bytes(b'synthetic-v2')
            return result
        with patch.object(service,'existing',side_effect=rotate_after_resolution):
            with self.assertRaisesRegex(control.Refused,'credential bytes changed'):
                service.request('secrets',{'nonce':'a'*48,'stage':'terraform'},True)

    def test_notion_binding_requires_enabled_scope_and_current_ansible_approval(self):
        service=self.service();profile=service.policy['profiles']['fixture'];profile['notion']={'enabled':True}
        path=self.base/('a'*48+'.json');record=json.loads(path.read_text())
        record['admission']['payload'].update(scope=['integration:notion'],profile_sha256=control.digest(control.canonical(profile)))
        control.atomic_json(path,record)
        with self.assertRaises(control.Refused):service.request('secrets',{'nonce':'a'*48,'stage':'notion'},True)
        record['approvals']['ansible']={'expires_at':int(time.time())-1};control.atomic_json(path,record)
        with self.assertRaises(control.Refused):service.request('secrets',{'nonce':'a'*48,'stage':'notion'},True)
        record['approvals']['ansible']['expires_at']=int(time.time())+100;control.atomic_json(path,record)
        self.assertEqual(service.request('secrets',{'nonce':'a'*48,'stage':'notion'},True),{})
        record['admission']['payload']['scope']=[];control.atomic_json(path,record)
        with self.assertRaises(control.Refused):service.request('secrets',{'nonce':'a'*48,'stage':'notion'},True)
    def test_slow_source_preparation_does_not_block_another_run_lease(self):
        service=self.service();entered=threading.Event();release=threading.Event()
        def prepare(*args):
            entered.set();release.wait(5);raise control.Refused('synthetic source preparation stopped')
        service.resolve_source=prepare
        with concurrent.futures.ThreadPoolExecutor(3) as workers:
            preparing=workers.submit(service.request,'admit',{'job':'fixture','build':2})
            try:
                self.assertTrue(entered.wait(1))
                renewal=workers.submit(service.request,'lease',{'nonce':'a'*48},True)
                lease=renewal.result(timeout=1)
                self.assertEqual(control.verify(lease,service.policy['keys'],'job-lease')['nonce'],'a'*48)
                current=workers.submit(service.existing,'a'*48).result(timeout=1)
                self.assertEqual(current[1]['sha'],'a'*40)
            finally:release.set()
            with self.assertRaises(control.Refused):preparing.result(timeout=1)
        self.assertEqual(sum(not json.loads(path.read_text()).get('terminal') for path in self.base.glob('*.json')),1)
    def test_source_preparation_reserves_quota_before_releasing_the_global_lock(self):
        service=self.service();release=threading.Event();entered=threading.Condition();count=0
        def prepare(*args):
            nonlocal count
            with entered:count+=1;entered.notify_all()
            release.wait(5);raise control.Refused('synthetic source preparation stopped')
        service.resolve_source=prepare
        with concurrent.futures.ThreadPoolExecutor(10) as workers:
            requests=[workers.submit(service.request,'admit',{'job':'fixture','build':index+2}) for index in range(10)]
            try:
                with entered:self.assertTrue(entered.wait_for(lambda:count==7,timeout=2))
                # The existing run plus seven preparations exhaust the same
                # eight-run budget while their slow source work is in progress.
                self.assertEqual(sum(not json.loads(path.read_text()).get('terminal') for path in self.base.glob('*.json')),8)
                with self.assertRaisesRegex(control.Refused,'retention or disk budget'):service.request('admit',{'job':'fixture','build':99})
            finally:release.set()
            for request in requests:
                with self.assertRaises(control.Refused):request.result(timeout=1)
        self.assertEqual(count,7)
    def test_accept_loop_gc_never_waits_for_a_registry_lock_or_slow_collection(self):
        service=self.service()
        server=admission.AdmissionServer(('127.0.0.1',0),admission.Handler,None);server.control=service
        try:
            with service.registry_lock():
                server.last_gc=time.monotonic()-61
                started=time.monotonic();server.service_actions()
                self.assertLess(time.monotonic()-started,.2)
                server.gc_future.result(timeout=1)  # Nonblocking GC skips the held lock.
            entered=threading.Event();release=threading.Event()
            def collect(blocking=True):entered.set();release.wait(5)
            with patch.object(service,'collect_expired',side_effect=collect):
                try:
                    server.last_gc=time.monotonic()-61;started=time.monotonic();server.service_actions()
                    self.assertLess(time.monotonic()-started,.2);self.assertTrue(entered.wait(1))
                    first=server.gc_future;server.last_gc=time.monotonic()-61;server.service_actions()
                    self.assertIs(server.gc_future,first)  # Exactly one bounded GC worker.
                finally:release.set();server.gc_future.result(timeout=1)
        finally:server.server_close()
    def test_tls_stall_does_not_block_another_accepted_connection(self):
        tls=types.SimpleNamespace(wrap_socket=lambda request,**kwargs:request)
        class SlowSocket:
            def settimeout(self,value):self.timeout=value
            def do_handshake(self):time.sleep(.2);raise ssl.SSLError('synthetic timeout')
            def close(self):pass
        import ssl
        server=admission.AdmissionServer(('127.0.0.1',0),admission.Handler,tls)
        seen=threading.Event()
        def handler(request,address):seen.set()
        # Run the actual bounded handshake worker for a stalled connection while
        # another worker progresses independently.
        with patch.object(server,'audit'),patch.object(admission.ThreadingHTTPServer,'process_request_thread',side_effect=handler):
            first=SlowSocket();server.slots.acquire()
            thread=threading.Thread(target=server.process_request_thread,args=(first,('127.0.0.1',1)));thread.start()
            second=SlowSocket();second.do_handshake=lambda:None;server.slots.acquire()
            server.process_request_thread(second,('127.0.0.1',2));self.assertTrue(seen.is_set());thread.join()
        self.assertEqual(first.timeout,3);server.server_close()
    def test_stream_failure_emits_one_http_status_and_safe_audit(self):
        service=self.service();nonce='a'*48;(self.base/(nonce+'.tar')).write_bytes(b'fixture')
        handler=admission.Handler.__new__(admission.Handler);handler.connection=types.SimpleNamespace(settimeout=lambda value:None,getpeercert=lambda:{'subject':[(('commonName','iac-peer-root'),)]},request_read_timer=types.SimpleNamespace(cancel=lambda:None))
        handler.client_address=('192.168.1.110',1);raw=control.canonical({'nonce':nonce,'token':'DO_NOT_LOG'})
        handler.headers={'Content-Length':str(len(raw))};handler.rfile=io.BytesIO(raw);handler.wfile=io.BytesIO();handler.path='/bundle'
        audits=[];handler.server=types.SimpleNamespace(control=service,audit=lambda *args:audits.append(args))
        with patch.object(handler,'send_response') as response,patch.object(handler,'send_header'),patch.object(handler,'end_headers'),patch.object(handler,'send_error') as error,patch.object(admission.shutil,'copyfileobj',side_effect=OSError('DO_NOT_LOG')):
            handler.do_POST()
        response.assert_called_once_with(200);error.assert_not_called();self.assertTrue(handler.close_connection)
        self.assertNotIn('DO_NOT_LOG',str(audits))


class TransactionTests(Fixture):
    def setup_transaction(self):
        workspace=self.base/'workspace';root=workspace/'terraform/proxmox';root.mkdir(parents=True)
        (workspace/'ansible/playbooks').mkdir(parents=True);(workspace/'ansible/playbooks/deploy-n8n.yml').touch()
        (self.base/'home').mkdir();(self.base/'tmp').mkdir();(self.base/'report').mkdir();(self.base/'control').mkdir();(self.base/'secrets').mkdir()
        (root/'.terraform.lock.hcl').write_text('fixture lock')
        scope={'hosts':{'n8n':'192.0.2.106'},'playbooks':['deploy-n8n.yml'],'variables_source':'fixture'}
        payload={'profile':'deploy','sha':'a'*40,'build':1,'nonce':'synthetic_nonce_123456789','job':'fixture','scope':['root:proxmox'],
                 'credential_versions':{},'changes':[{'path':'terraform/proxmox/n8n.tf','deleted':False}]}
        lease=self.sign('job-lease',**payload);control.atomic_json(self.base/'control/lease.json',lease)
        trust=self.base/'trust.json';control.atomic_json(trust,{'keys':self.keys,'ansible_scopes':{'fixture':scope}})
        self.install(transaction,'JOB',self.base);self.install(transaction,'TRUST',trust)
        self.install(sys,'argv',['transaction',payload['sha'],'1',payload['nonce']])
        calls=[]
        def run(argv,cwd,allowed=(0,),env=None):
            calls.append(argv)
            value={}
            if argv[:2]==['terraform','version']:value={'terraform_version':'1.14.4'}
            if argv[:2]==['terraform','plan']:(self.base/'tmp/approved.tfplan').write_text('fixture plan')
            return types.SimpleNamespace(returncode=0,stdout=json.dumps(value))
        self.install(transaction,'run',run);self.install(transaction,'state_identity',lambda root:{'lineage':'fixture','serial':1,'state_version':'sv-fixture'})
        return payload,scope,root,calls
    def test_terraform_only_apply_refreshes_state_before_returning_without_ansible(self):
        payload,scope,root,calls=self.setup_transaction()
        payload['changes'][0]['deleted']=True
        control.atomic_json(self.base/'control/lease.json',self.sign('job-lease',**payload))
        approved=[]
        with patch.object(transaction,'approve',side_effect=lambda stage,*args:approved.append(stage)),patch.object(transaction,'inventory_scope') as inventory,patch.object(transaction,'verify_deploy_scope') as targets:
            transaction.main();inventory.assert_not_called();targets.assert_not_called()
        apply=next(index for index,argv in enumerate(calls) if argv[:2]==['terraform','apply'])
        refresh=next(index for index,argv in enumerate(calls) if argv[0].endswith('/scripts/refresh-terraform-state.sh'))
        self.assertLess(apply,refresh);self.assertEqual(approved,['terraform'])
        self.assertFalse(any(argv[0]=='ansible-playbook' for argv in calls))
        report=json.loads((self.base/'report/status.json').read_text())
        self.assertEqual(report['phase'],'verified');self.assertEqual(report['summary']['playbooks'],[])

    def test_changed_plan_lock_or_state_after_approval_never_applies(self):
        for mutation in ['plan','lock','state']:
            with self.subTest(mutation=mutation),FixtureContext(self):
                payload,scope,root,calls=self.setup_transaction()
                original=transaction.state_identity(root)
                def approve(*args):
                    if mutation=='plan':(self.base/'tmp/approved.tfplan').write_text('changed')
                    elif mutation=='lock':(root/'.terraform.lock.hcl').write_text('changed')
                    else:transaction.state_identity=lambda root:{**original,'serial':2}
                with patch.object(transaction,'approve',side_effect=approve):
                    with self.assertRaises(control.Refused):transaction.main()
                self.assertFalse(any(argv[:2]==['terraform','apply'] for argv in calls))
    def test_controller_and_unapproved_agent_scope_refuse_before_tools(self):
        payload,scope,root,calls=self.setup_transaction()
        for hosts,playbooks in [({'jenkins':'192.0.2.107'},[]),({},['deploy-jenkins.yml']),({'jenkins-agent':'192.0.2.110'},[]),({},['deploy-jenkins-agent.yml'])]:
            trust=json.loads(transaction.TRUST.read_text());trust['ansible_scopes']['fixture']={**scope,'hosts':hosts,'playbooks':playbooks};control.atomic_json(transaction.TRUST,trust)
            with self.subTest(playbooks=playbooks),self.assertRaises(control.Refused):transaction.main()
            self.assertEqual(calls,[])
    def test_success_uses_one_saved_plan_and_separate_scope_approvals(self):
        payload,scope,root,calls=self.setup_transaction();approved=[]
        resolved={'hosts':scope['hosts'],'playbooks':scope['playbooks'],'tags':[],'limit':'n8n','variables_source':'fixture'}
        with patch.object(transaction,'approve',side_effect=lambda stage,*args:approved.append(stage)),patch.object(transaction,'inventory_scope',return_value=resolved),patch.object(transaction,'verify_deploy_scope'):
            transaction.main()
        plans=[argv for argv in calls if argv[:2]==['terraform','plan']];applies=[argv for argv in calls if argv[:2]==['terraform','apply']]
        self.assertEqual(len(plans),1);self.assertEqual(len(applies),1);self.assertEqual(plans[0][3],'-out='+applies[0][-1]);self.assertEqual(approved,['terraform','ansible'])
    def test_notion_is_disabled_by_default_and_runs_only_with_fixed_destination(self):
        payload,scope,root,calls=self.setup_transaction();workspace=root.parents[1]
        self.assertEqual(transaction.notion_sync(workspace,{},payload,self.keys),'disabled')
        with self.assertRaises(control.Refused):transaction.notion_sync(workspace,{'notion':{'enabled':True,'destination':'https://other.invalid'}},payload,self.keys)
        (self.base/'secrets/notion-token').write_text('synthetic\n')
        (self.base/'secrets/notion-database-id').write_text('fixture-database\n')
        control.atomic_json(self.base/'control/notion-ready.json',{'ready':True})
        trust={'notion':{'enabled':True,'destination':'https://api.notion.com','database_id':'fixture-database'}}
        with patch.object(transaction,'run',return_value=types.SimpleNamespace(returncode=0)) as execute:
            self.assertEqual(transaction.notion_sync(workspace,trust,{**payload,'scope':['integration:notion']},self.keys),'completed')
            self.assertEqual(execute.call_args.args[0],['python3','scripts/sync-to-notion.py'])
            self.assertEqual(execute.call_args.kwargs['env']['NOTION_DATABASE_ID'],'fixture-database')
        calls.clear();config=json.loads(transaction.TRUST.read_text());config['notion']=trust['notion'];control.atomic_json(transaction.TRUST,config)
        with self.assertRaises(control.Refused):transaction.main()
        self.assertEqual(calls,[])
    def test_optional_notion_timeout_or_explicit_denial_reports_failure(self):
        payload,scope,root,calls=self.setup_transaction();workspace=root.parents[1]
        trust={'notion':{'enabled':True,'destination':'https://api.notion.com','database_id':'fixture'}}
        admission_payload={**payload,'scope':['integration:notion']}
        control.atomic_json(self.base/'control/lease.json',self.sign('job-lease',**admission_payload))
        with patch.object(transaction.time,'monotonic',side_effect=[0,61]):
            self.assertEqual(transaction.notion_sync(workspace,trust,admission_payload,self.keys),'failed')
        control.atomic_json(self.base/'control/notion-ready.json',{'ready':False})
        self.assertEqual(transaction.notion_sync(workspace,trust,admission_payload,self.keys),'failed')
        self.assertFalse((self.base/'secrets/notion-token').exists())

    def test_classification_retains_deletions_and_rejects_broad_unmapped_changes(self):
        payload,scope,root,calls=self.setup_transaction();workspace=root.parents[1]
        selected=transaction.classify_changes([{'path':'terraform/proxmox/n8n.tf','deleted':True}],workspace,scope)
        self.assertTrue(selected['terraform']);self.assertEqual(selected['playbooks'],[])
        self.assertFalse(transaction.classify_changes([{'path':'docs/example.md','deleted':False}],workspace,scope)['should_build'])
        for path in ['terraform/modules/proxmox-lxc/main.tf','ansible/unknown.yml']:
            with self.assertRaises(control.Refused):transaction.classify_changes([{'path':path,'deleted':False}],workspace,scope)


class FixtureContext:
    """Create isolated subcase paths while preserving unittest patch cleanups."""
    def __init__(self,test):self.test=test
    def __enter__(self):
        self.previous=self.test.base;self.test.base=self.previous/str(time.monotonic_ns());self.test.base.mkdir()
    def __exit__(self,*args):self.test.base=self.previous


class WatchdogTests(Fixture):
    def test_agent_update_fences_until_strictly_new_connections(self):
        self.install(watchdog,'BASE',self.base);(self.base/'agent-update-pending').touch()
        names=['iac-plan','iac-deploy','iac-apps'];calls=[];connections=[1,1,2]
        def request(policy,payload,stream=None):
            value=connections.pop(0);return {name:{'offline':False,'connect_time':value} for name in names}
        def command(argv):
            calls.append(argv)
            if argv[:2]==['systemctl','restart']:self.assertTrue((self.base/'maintenance.json').exists())
            return ''
        with patch.object(watchdog,'request',side_effect=request),patch.object(watchdog,'command',side_effect=command),patch.object(watchdog.time,'sleep'):
            watchdog.update_agents({})
        self.assertFalse((self.base/'agent-update-pending').exists());self.assertFalse((self.base/'maintenance.json').exists());self.assertEqual(connections,[])
        self.assertEqual(sum(argv[:2]==['systemctl','stop'] for argv in calls),3)
        self.assertLess(calls.index(['systemctl','daemon-reload']),calls.index(['systemctl','restart','jenkins-job-runner.service']))
    def test_agent_update_failure_stops_all_and_keeps_pending_quarantine(self):
        self.install(watchdog,'BASE',self.base);(self.base/'agent-update-pending').touch()
        names=['iac-plan','iac-deploy','iac-apps']
        def command(argv):
            if argv[:2]==['systemctl','restart']:raise control.Refused('synthetic restart failure')
            return ''
        with patch.object(watchdog,'request',return_value={name:{'offline':False,'connect_time':1} for name in names}),patch.object(watchdog,'command',side_effect=command),patch.object(watchdog.subprocess,'run') as stopped:
            with self.assertRaises(control.Refused):watchdog.update_agents({})
        self.assertEqual(stopped.call_count,3);self.assertTrue((self.base/'quarantine.json').exists());self.assertTrue((self.base/'agent-update-pending').exists())
        with patch.object(watchdog,'request') as request:watchdog.update_agents({});request.assert_not_called()


class IsolationTests(Fixture):
    def test_ipv6_unsupported_is_denied_but_unknown_errors_fail_closed(self):
        with patch.object(probe.socket,'socket',side_effect=OSError(errno.EAFNOSUPPORT,'unsupported')):probe.rejected('::1',80,socket.AF_INET6)
        with patch.object(probe.socket,'socket',side_effect=OSError(errno.EMFILE,'files')):
            with self.assertRaises(control.Refused):probe.rejected('::1',80,socket.AF_INET6)
    def test_actual_probe_rejects_privileges_and_each_foreign_home_access_bit(self):
        proof=self.base/'proof.json';control.atomic_json(proof,{'host_namespaces':{'net':'host','mnt':'host','ipc':'host','user':'host'},'other_identity_pids':[],'other_identities':['other'],'unix_canary':'missing','loopback_port':1,'profile':'deploy'})
        status=self.base/'status';real_path=Path
        def paths(value):return proof if str(value)=='/job/control/isolation.json' else status if str(value)=='/proc/self/status' else real_path(value)
        with patch.object(probe,'Path',side_effect=paths),patch.object(probe.os,'readlink',return_value='job'):
            for no_new,caps in [('0','0'),('1','1')]:
                status.write_text('NoNewPrivs:\t'+no_new+'\nCapEff:\t'+caps+'\n')
                with self.assertRaises(control.Refused):probe.check()
            status.write_text('NoNewPrivs:\t1\nCapEff:\t0\n')
            for bit in [os.R_OK,os.X_OK]:
                with patch.object(probe.os,'access',side_effect=lambda path,mode:mode==bit):
                    with self.assertRaises(control.Refused):probe.check()
    def test_user_namespace_must_differ_even_when_other_namespaces_are_isolated(self):
        proof=self.base/'proof.json';control.atomic_json(proof,{'host_namespaces':{kind:'host-'+kind for kind in ['net','ipc','mnt','user']}})
        actual=Path
        with patch.object(probe,'Path',side_effect=lambda value:proof if str(value)=='/job/control/isolation.json' else actual(value)),patch.object(probe.os,'readlink',side_effect=lambda path:'host-user' if path.endswith('/user') else 'isolated'):
            with self.assertRaisesRegex(control.Refused,'isolated namespace'):probe.check()
    def test_actual_process_root_probe_requires_both_read_and_write_denial(self):
        for outcomes in [[PermissionError(errno.EACCES,'denied'),PermissionError(errno.EPERM,'denied')],
                         [FileNotFoundError(errno.ENOENT,'hidden'),FileNotFoundError(errno.ENOENT,'hidden')]]:
            with patch.object(probe.os,'open',side_effect=outcomes) as opened:
                probe.proc_access_denied('/proc/123/root/canary')
                self.assertEqual(opened.call_count,2)
                self.assertTrue(all(call.args[1]&os.O_NONBLOCK and call.args[1]&os.O_NOFOLLOW for call in opened.call_args_list))
        for outcomes in [[123],[PermissionError(errno.EACCES,'denied'),123],[OSError(errno.EIO,'unexpected')]]:
            with patch.object(probe.os,'open',side_effect=outcomes),patch.object(probe.os,'close'):
                with self.assertRaises(control.Refused):probe.proc_access_denied('/proc/123/root/canary')
    def test_root_checks_process_liveness_and_both_canaries_before_binding_secrets(self):
        service=runner.Runner(self.base,{'profiles':{},'keys':{}})
        nonce='proc_boundary_nonce_123456789';directory=self.base/('job-'+nonce)
        (directory/'report').mkdir(parents=True);(directory/'control').mkdir()
        remoting=self.base/'remoting-canary';remoting.write_text('synthetic-remoting-boundary:'+nonce)
        (directory/'report'/('proc-boundary-'+nonce)).write_text('synthetic-job-boundary:'+nonce)
        record={'nonce':nonce,'uid':os.getuid(),'unit':'iac-job-'+nonce+'.service','directory':str(directory),'remoting_pid':1300,'remoting_canary':str(remoting)}
        profile={'user':'iac-deploy','initial_secret_stage':'terraform'}
        for changed,same_namespace,success in [(False,False,True),(True,False,False),(False,True,False)]:
            phase={'helper':False}
            def command(argv):
                if argv[0]=='runuser':
                    phase['helper']=True
                    self.assertEqual(argv[:7],['runuser','-u','iac-deploy','--','setpriv','--no-new-privs','/usr/bin/python3'])
                    return ''
                if argv[2]==record['unit']:return '1200'
                return '1301' if changed and phase['helper'] else '1300'
            ready=directory/'control/secrets-ready.json';ready.unlink(missing_ok=True)
            with patch.object(runner,'command',side_effect=command),patch.object(runner.os,'readlink',side_effect=lambda path:'host' if same_namespace or path=='/proc/self/ns/user' else 'job'),patch.object(runner.os,'kill') as alive,patch.object(runner,'private_file',side_effect=Path),patch.object(service,'bind_secrets') as bind,patch.object(runner.subprocess,'run') as stopped:
                if success:
                    service.release_initial_secrets(record,profile);bind.assert_called_once_with(record,'terraform')
                    self.assertTrue(ready.exists());self.assertEqual(alive.call_count,4)
                else:
                    with self.assertRaisesRegex(control.Refused,'before secret binding'):service.release_initial_secrets(record,profile)
                    bind.assert_not_called();self.assertFalse(ready.exists());self.assertEqual(stopped.call_count,3)
                    self.assertTrue((self.base/'quarantine.json').exists())
    def test_entry_requires_current_bound_lease_and_reviewed_apps_hash(self):
        job=self.base/'job';(job/'control').mkdir(parents=True);(job/'report').mkdir()
        wrapper=self.base/'wrapper.py';wrapper.write_text('reviewed')
        payload={'sha':'a'*40,'build':1,'nonce':'synthetic_nonce_123456789','profile':'apps-validation','application_inputs':{'wrapper_sha256':control.sha_file(wrapper)}}
        expired=self.sign('job-admission',issued_at=int(time.time())-200,expires_at=int(time.time())-100,**payload)
        control.atomic_json(job/'control/admission.json',expired)
        current=self.sign('job-lease',**payload);control.atomic_json(job/'control/lease.json',current)
        trust=self.base/'trust.json';control.atomic_json(trust,{'keys':self.keys,'application_wrappers':{'apps-validation':control.sha_file(wrapper)}})
        real_path=Path
        def paths(value):
            path=real_path(value)
            if str(path).startswith('/job'):return job/str(path).removeprefix('/job/')
            if str(path)=='/opt/jenkins-agent/control/trust.json':return trust
            return path
        probe_stub=types.SimpleNamespace(check=lambda:{'fixture':True});(job/'control/secrets-ready.json').touch()
        with patch.object(entry,'Path',side_effect=paths),patch.object(entry,'private_file',return_value=wrapper),patch.object(entry,'SourceFileLoader',return_value=types.SimpleNamespace(load_module=lambda:probe_stub)),patch.object(entry.os,'execv') as execute,patch.object(sys,'argv',['entry','a'*40,'1',payload['nonce']]):
            entry.main();execute.assert_called_once();execute.reset_mock()
            wrapper.write_text('unreviewed')
            with self.assertRaises(control.Refused):entry.main()
            execute.assert_not_called();wrapper.write_text('reviewed')
            control.atomic_json(job/'control/lease.json',self.sign('job-lease',issued_at=int(time.time())-200,expires_at=int(time.time())-100,**payload))
            with self.assertRaises(control.Refused):entry.main()
            execute.assert_not_called()


class ConfigurationTests(Fixture):
    def test_tuple_ignores_runtime_xml_and_covers_casc_jobs_nodes_and_overrides(self):
        home=self.base/'home';home.mkdir();service=self.base/'service';service.mkdir()
        for name in ['config.xml','scriptApproval.xml','com.fixture.xml','io.fixture.xml','queue.xml','nodeMonitors.xml','jobs/example/config.xml','nodes/peer/config.xml','casc/jenkins.yaml']:
            path=home/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('initial')
        (service/'10-casc.conf').write_text('initial')
        with patch.object(maintenance,'SERVICE_CONFIG',service),patch.object(maintenance,'command',return_value='2.568.3'),patch.object(maintenance.subprocess,'run',return_value=types.SimpleNamespace(stderr='java 25\n')):
            initial=maintenance.tuple_for(home)
            (home/'queue.xml').write_text('queue runtime changed');(home/'nodeMonitors.xml').write_text('monitor changed')
            (service/'editor.swp').write_text('not a systemd override');(home/'casc/cache.json').write_text('not JCasC YAML')
            self.assertEqual(maintenance.tuple_for(home),initial)
            for path in [home/'config.xml',home/'scriptApproval.xml',home/'com.fixture.xml',home/'io.fixture.xml',home/'jobs/example/config.xml',home/'nodes/peer/config.xml',home/'casc/jenkins.yaml',service/'10-casc.conf']:
                path.write_text('new configuration')
                self.assertNotEqual(maintenance.tuple_for(home)['config'],initial['config'])
                path.write_text('initial')
    def test_materials_reject_multiple_keys_and_unsafe_binding_names(self):
        private=self.base/'ssh';subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(private)],check=True)
        public=private.with_suffix('.pub').read_text().strip();secret=private.read_text()
        materials.ssh_material(public,secret)
        for value in [public+'\n'+public,public+'\n',public+'\r',public+' '+public]:
            with self.assertRaises((control.Refused,subprocess.SubprocessError)):materials.ssh_material(value,secret)
        for value in ['../escape','nested/file','',None]:
            with self.assertRaises(control.Refused):materials.basename(value)
        with self.assertRaises(control.Refused):materials.validate({'kind':'agent','clients':[{'name':'other'}],'roots':[]})


class EvidenceTests(Fixture):
    def recovery(self):
        backup=self.base/'backup.tar';backup.write_bytes(b'fixture')
        jobs={};files={};inputs={};self.receipts={}
        for index,job in enumerate(sorted(maintenance.EXPECTED_JOBS)):
            name='job-'+str(index)+'.json'
            if job=='Webhook-Router':
                receipt=self.sign('router-run-evidence',job=job,build=1,source_sha='a'*40,script_sha256='b'*64,no_workspace=True,no_shell_or_secret_binding=True,result='SUCCESS')
                inputs[job]={'build':1,'source_sha':'a'*40,'script_sha256':'b'*64}
            else:
                node='iac-plan' if job=='IaC-ReadOnly-Plan' else 'iac-deploy' if job=='IaC-Homelab-Pipeline' else 'iac-apps'
                receipt=self.sign('job-run-evidence',job=job,build=1,source_sha='a'*40,node=node,uid=1001,scope=['root:fixture'],credential_versions={},runner_sha256='c'*64,profile_sha256='d'*64,isolation_verified=True,exit_code=0,cleanup={name:True for name in maintenance.CLEANUP_FIELDS})
                inputs[job]={'build':1,'source_sha':'a'*40,'uid':1001,'scope':['root:fixture'],'credential_versions':{},'profile_sha256':'d'*64}
            control.atomic_json(self.base/name,receipt);files[name]=control.sha_file(self.base/name);self.receipts[job]=(name,receipt)
            jobs[job]={field:name for field in ['scheduling_evidence','cleanup_evidence','credential_scope_evidence']}
        required={'stop','archive_verify','namespace_isolation','config_parse','plugin_load','health','gitea_unchanged','agent_reconnect','second_ansible_run','normal_plan','normal_deploy','oom_budget','failed_maintenance_restore'}
        evidence=self.sign('controller-recovery-evidence',target='CT107/jenkins',drill_target='CT110',tuple={'core':'fixture'},authorization_id='fixture',backup_sha256=control.sha_file(backup),evidence_files=files,commands=[{'name':name,'exit_code':0} for name in required],jobs=jobs)
        armed=self.sign('controller-watchdog-armed',backup_sha256=control.sha_file(backup),old_tuple={'core':'fixture'})
        control.atomic_json(self.base/'armed.json',armed)
        policy={'keys':self.keys,'tuple':{'core':'fixture'},'authorization_id':'fixture','backup':str(backup),'evidence_dir':str(self.base),'watchdog_attestation':str(self.base/'armed.json'),'migration_inputs':inputs,'router_script_sha256':'b'*64,'runner_sha256':'c'*64}
        return evidence,policy
    def test_router_failure_empty_cleanup_and_migration_version_changes_refuse(self):
        envelope,policy=self.recovery();maintenance.validate_evidence(envelope,policy,zero=True)
        for job,modify in [('Webhook-Router',{'result':'FAILURE'}),('IaC-Homelab-Pipeline',{'cleanup':{}}),('IaC-Homelab-Pipeline',{'cleanup':{name:1 for name in maintenance.CLEANUP_FIELDS}}),('n8n-rental',{'build':True}),('n8n-rental',{'uid':1002}),('n8n-rental',{'profile_sha256':'e'*64}),('n8n-rental',{'scope':[]})]:
            name,receipt=self.receipts[job];updated=self.sign(receipt['payload']['purpose'],**{key:value for key,value in receipt['payload'].items() if key not in {'purpose','issued_at','expires_at'}},**{})
            updated['payload'].update(modify);updated=control.sign(updated['payload'],'current',self.key)
            control.atomic_json(self.base/name,updated)
            payload=copy.deepcopy(envelope['payload']);payload['evidence_files'][name]=control.sha_file(self.base/name)
            with self.subTest(modify=modify),self.assertRaises(control.Refused):maintenance.validate_evidence(control.sign(payload,'current',self.key),policy,zero=True)
            control.atomic_json(self.base/name,receipt)


if __name__=='__main__':unittest.main()
