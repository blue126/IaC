#!/usr/bin/env python3
"""Execute signed maintenance transitions against isolated files and fake services."""
import copy
import json
import io
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control
maintenance=SourceFileLoader('state_maintenance',str(ROOT/'scripts/jenkins/controller-maintenance.py')).load_module()
watchdog=SourceFileLoader('state_watchdog',str(ROOT/'scripts/jenkins/watchdog.py')).load_module()


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.controller_base=self.base/'controller';self.peer=self.base/'peer'
        self.controller_base.mkdir();self.peer.mkdir();self.home=self.base/'home';self.home.mkdir();self.service=self.base/'service';self.service.mkdir()
        (self.home/'config.xml').write_text('old');(self.service/'override.conf').write_text('fixed')
        self.key=self.base/'key';self.public=self.base/'public'
        subprocess.run(['openssl','genpkey','-algorithm','ed25519','-out',str(self.key)],check=True,capture_output=True)
        subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.public)],check=True,capture_output=True)
        self.credentials=self.base/'api.json';control.atomic_json(self.credentials,{'user':'synthetic','token':'fixture'})
        self.policy={'keys':{'current':str(self.public)},'key_id':'current','signing_key':str(self.key),'authorization_id':'fixture-approval','jenkins_api_credentials':str(self.credentials),'missing_runtime_bytes':0}
        original=control.private_file
        self.patches=[]
        def install(obj,name,value):
            item=patch.object(obj,name,value);item.start();self.addCleanup(item.stop)
        for module in [control,maintenance,watchdog]:install(module,'private_file',lambda path,owner=0:original(path,owner=os.getuid()))
        install(maintenance,'BASE',self.controller_base);install(maintenance,'HOME',self.home);install(maintenance,'SERVICE_CONFIG',self.service)
        install(maintenance,'FENCE',self.home/'init.groovy.d/00-peer-recovery-fence.groovy');install(watchdog,'BASE',self.peer);install(watchdog,'REMOTING_READY',self.peer/'remoting-ready')
        self.state={'ActiveState':'active','healthy':True,'quieting_down':False}
        install(maintenance,'tuple_for',self.current_tuple)
        real_command=control.command
        def fake_command(argv,*args,**kwargs):
            if argv[0]=='openssl':return real_command(argv,*args,**kwargs)
            if argv[:2]==['systemctl','stop']:self.state['ActiveState']='inactive'
            if argv[:2]==['systemctl','show'] and 'ActiveState' in argv:return self.state['ActiveState']
            if argv[:2]==['systemctl','start']:
                self.state.update(ActiveState='active',healthy=True,quieting_down=maintenance.FENCE.exists())
            return ''
        install(maintenance,'command',fake_command);install(watchdog,'command',lambda argv:'')
        self.controller=maintenance.Controller(self.policy)
        install(self.controller,'status',lambda:{**self.state,'tuple':self.current_tuple(),'gitea':{'MainPID':'42'}})
        def api(path,post=False,data=None):
            if path=='quietDown':self.state['quieting_down']=True
            if path=='cancelQuietDown':self.state['quieting_down']=False
            if path.startswith('computer/'):return b'{"computer":[]}'
            if path=='scriptText':return json.dumps({name:{'offline':False,'connect_time':1} for name in ['iac-plan','iac-deploy','iac-apps']}).encode()
            return json.dumps({'quietingDown':self.state['quieting_down']}).encode()
        install(self.controller,'api',api)
        install(watchdog,'request',self.request)
        install(maintenance.os,'chown',lambda *args:None)
        install(pwd,'getpwnam',lambda name:type('Identity',(),{'pw_uid':os.getuid(),'pw_gid':os.getgid()})())
        self.counter=0
    def current_tuple(self):
        return {'core':'2.568.3','java':'25.0.2','plugins':'fixture-plugins','config':control.sha_file(self.home/'config.xml')}
    def signed(self,purpose,**values):
        now=int(time.time());self.counter+=1
        return control.sign({'purpose':purpose,'nonce':'fixture_nonce_'+str(self.counter).zfill(16),'issued_at':now,'expires_at':now+600,**values},'current',self.key)
    def request(self,policy,payload,stream=None):
        envelope=self.signed('controller-maintenance',target='CT107/jenkins',authorization_id=policy['authorization_id'],**payload)
        if payload['mode']=='export':
            output=io.BytesIO();self.controller.export(envelope,output)
            header,archive=output.getvalue().split(b'\n',1)
            status=control.verify(json.loads(header),policy['keys'],'controller-status')
            Path(stream).write_bytes(archive);return status['result']
        return control.verify(self.controller.dispatch(envelope),policy['keys'],'controller-status')['result']
    def capture(self):
        required=['archive_verify','namespace_isolation','config_parse','plugin_load','health']
        with patch.object(watchdog,'drill',return_value=([{'name':name,'exit_code':0} for name in required],{'fixture':True})),patch.object(watchdog.maintenance,'check_resources',return_value=0):
            proof=watchdog.capture_and_drill(self.policy,self.signed('maintenance-bootstrap',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],new_tuple=self.current_tuple()))
        return proof,json.loads((self.peer/'maintenance.json').read_text())
    def assert_retained(self,record):
        backup=self.controller_base/record['backup_id']/'backup.tar'
        self.assertEqual(control.sha_file(backup),record['backup_sha256'])
        self.assertEqual(json.loads((self.controller_base/'backup-registry.json').read_text()),{'verified':record['backup_id']})
    def phase(self,mode,record):
        bundle=self.base/'bundle.json';control.atomic_json(bundle,self.signed('watchdog-'+mode,nonce=record['nonce'],backup_sha256=record['backup_sha256']))
        policy_path=self.base/'policy.json';policy=dict(self.policy,ssh_key=str(self.key),known_hosts=str(self.public));control.atomic_json(policy_path,policy)
        with patch.object(sys,'argv',['watchdog',mode,'--policy',str(policy_path),'--bundle',str(bundle)]),patch.object(watchdog.os,'geteuid',return_value=0):watchdog.main()
    def test_capture_promote_prepare_begin_complete_resume_retains_verified(self):
        _,record=self.capture()
        self.assertTrue(maintenance.FENCE.exists());self.assert_retained(record)
        self.phase('begin',record)
        self.assertEqual(json.loads((self.peer/'maintenance.json').read_text())['phase'],'started')
        self.controller.start(resume=False)
        self.phase('complete',record)
        self.assertFalse((self.peer/'maintenance.json').exists());self.assertFalse(maintenance.FENCE.exists())
        self.assertFalse(self.state['quieting_down']);self.assert_retained(record)
        self.assertEqual(json.loads((self.peer/'maintenance-result.json').read_text())['status'],'completed')
    def test_failed_fenced_controller_stops_restores_and_resumes(self):
        _,record=self.capture();self.phase('begin',record)
        (self.home/'config.xml').write_text('broken plugin configuration')
        self.state.update(ActiveState='active',healthy=False,quieting_down=True)
        watchdog.Watchdog(self.policy).tick()
        self.assertEqual((self.home/'config.xml').read_text(),'old');self.assert_retained(record)
        self.assertFalse(maintenance.FENCE.exists());self.assertFalse(self.state['quieting_down'])
        self.assertEqual(json.loads((self.peer/'maintenance-result.json').read_text())['status'],'restored')
    def test_failed_capture_candidate_can_be_discarded_without_touching_verified(self):
        _,record=self.capture();candidate='incomplete_candidate_123456'
        directory=self.controller_base/candidate;directory.mkdir();(directory/'backup.tar').write_bytes(b'incomplete')
        control.atomic_json(self.controller_base/'backup-registry.json',{'verified':record['backup_id'],'candidate':candidate})
        self.request(self.policy,{'mode':'discard-candidate','backup_id':candidate})
        self.assertFalse(directory.exists());self.assert_retained(record)
    def test_tuple_hash_signature_and_candidate_confusion_refuse_without_deletion(self):
        _,record=self.capture();backup=self.controller_base/record['backup_id']/'backup.tar'
        requests=[{'mode':'discard-candidate'}, {'mode':'prepare','old_tuple':dict(record['old_tuple'],plugins='wrong')},
                  {'mode':'restore','old_tuple':dict(record['old_tuple'],config='wrong')},
                  {'mode':'fail-stop','old_tuple':dict(record['old_tuple'],java='wrong')},
                  {'mode':'resume','expected_tuple':record['new_tuple']}]
        for values in requests:
            with self.subTest(mode=values['mode']):
                with self.assertRaises(control.Refused):self.request(self.policy,{'backup_id':record['backup_id'],'backup_sha256':record['backup_sha256'],**values})
                self.assert_retained(record)
        manifest_path=backup.parent/'manifest.json';original=manifest_path.read_bytes();envelope=json.loads(original);envelope['payload']['tuple']['plugins']='tampered';control.atomic_json(manifest_path,envelope)
        with self.assertRaises(control.Refused):self.request(self.policy,{'mode':'prepare','backup_id':record['backup_id'],'backup_sha256':record['backup_sha256'],'old_tuple':record['old_tuple']})
        manifest_path.write_bytes(original);backup.write_bytes(backup.read_bytes()+b'tamper')
        with self.assertRaises(control.Refused):self.request(self.policy,{'mode':'prepare','backup_id':record['backup_id'],'backup_sha256':record['backup_sha256'],'old_tuple':record['old_tuple']})
        self.assertTrue(backup.exists())

    def test_promotion_commits_new_reference_before_old_archive_reclamation(self):
        _,record=self.capture()
        self.state['ActiveState']='inactive'
        candidate='replacement_candidate_123456'
        manifest=self.controller.backup(candidate)
        proof=self.signed('controller-recovery-evidence',nonce=candidate,target='CT107/jenkins',drill_target='CT110',
                          authorization_id=self.policy['authorization_id'],backup_id=candidate,backup_sha256=manifest['backup_sha256'],tuple=manifest['tuple'])
        original_rmtree=shutil.rmtree
        def remove(path,*args,**kwargs):
            if Path(path)==self.controller_base/record['backup_id']:raise OSError('interrupted reclamation')
            return original_rmtree(path,*args,**kwargs)
        promote=self.signed('controller-maintenance',mode='promote',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],backup_id=candidate,evidence=proof)
        with patch.object(maintenance.shutil,'rmtree',side_effect=remove):
            with self.assertRaises(OSError):self.controller.dispatch(promote)
        registry=json.loads((self.controller_base/'backup-registry.json').read_text())
        self.assertEqual(registry['verified'],candidate)
        self.assertTrue((self.controller_base/candidate/'backup.tar').exists())
        self.assertTrue((self.controller_base/record['backup_id']/'backup.tar').exists())
        self.controller.dispatch(promote);self.controller.reclaim_retired()
        self.assertFalse((self.controller_base/record['backup_id']).exists())
        self.assertEqual(json.loads((self.controller_base/'backup-registry.json').read_text()),{'verified':candidate})
    def test_restore_tested_candidate_replaces_corrupt_old_backup_without_deleting_it(self):
        _,record=self.capture();old=self.controller_base/record['backup_id'];(old/'backup.tar').write_bytes(b'corrupt synthetic archive')
        self.state['ActiveState']='inactive';candidate='replacement_corrupt_old_1234';manifest=self.controller.backup(candidate)
        proof=self.signed('controller-recovery-evidence',nonce=candidate,target='CT107/jenkins',drill_target='CT110',authorization_id=self.policy['authorization_id'],backup_id=candidate,backup_sha256=manifest['backup_sha256'],tuple=manifest['tuple'])
        promote=self.signed('controller-maintenance',mode='promote',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],backup_id=candidate,evidence=proof)
        self.controller.dispatch(promote)
        registry=json.loads((self.controller_base/'backup-registry.json').read_text())
        self.assertEqual(registry['verified'],candidate);self.assertEqual(registry['quarantined'],[record['backup_id']])
        self.assertTrue(old.exists());self.controller.reclaim_retired();self.assertTrue(old.exists())
        self.controller.managed_backup(candidate,'verified')

    def test_start_retries_transient_http_errors_but_not_policy_refusal(self):
        import http.client
        with patch.object(self.controller,'api',side_effect=[http.client.IncompleteRead(b''),b'{}',b'{}']),patch.object(maintenance.time,'sleep'):
            self.assertTrue(self.controller.start()['healthy'])
        with patch.object(self.controller,'api',side_effect=control.Refused('policy mismatch')),patch.object(maintenance.time,'sleep') as sleep:
            with self.assertRaises(control.Refused):self.controller.start()
            sleep.assert_not_called()

    def test_home_or_service_replace_failure_rolls_back_completed_moves(self):
        _,record=self.capture()
        (self.home/'config.xml').write_text('current-before-restore')
        original=Path.rename
        for failed_name in ['home','service']:
            def rename(path,target):
                if path.name==failed_name and path.parent.name.startswith('restore-'):raise OSError('injected rename failure')
                return original(path,target)
            with self.subTest(root=failed_name),patch.object(Path,'rename',rename):
                with self.assertRaises(OSError):self.request(self.policy,{'mode':'restore','backup_id':record['backup_id'],'backup_sha256':record['backup_sha256'],'old_tuple':record['old_tuple']})
            self.assertEqual((self.home/'config.xml').read_text(),'current-before-restore')
            self.assertEqual((self.service/'override.conf').read_text(),'fixed')
            self.assert_retained(record)
    def test_export_requires_managed_candidate_stopped_tuple_and_single_nonce(self):
        self.state['ActiveState']='inactive';candidate='export_candidate_12345678'
        manifest=self.controller.backup(candidate)
        envelope=self.signed('controller-maintenance',mode='export',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],backup_id=candidate,backup_sha256=manifest['backup_sha256'])
        output=io.BytesIO();self.controller.export(envelope,output)
        header,archive=output.getvalue().split(b'\n',1)
        self.assertEqual(control.digest(archive),manifest['backup_sha256'])
        control.verify(json.loads(header),self.policy['keys'],'controller-status')
        with self.assertRaises(control.Refused):self.controller.export(envelope,io.BytesIO())
        arbitrary=self.controller_base/'unmanaged_backup_123456';arbitrary.mkdir();(arbitrary/'backup.tar').write_bytes(b'not managed')
        for values in [{'backup_id':arbitrary.name,'backup_sha256':control.digest(b'not managed')},{'backup_id':candidate,'backup_sha256':'0'*64}]:
            with self.assertRaises(control.Refused):self.controller.export(self.signed('controller-maintenance',mode='export',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],**values),io.BytesIO())
        (self.home/'config.xml').write_text('changed-after-backup')
        with self.assertRaises(control.Refused):self.controller.export(self.signed('controller-maintenance',mode='export',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],backup_id=candidate,backup_sha256=manifest['backup_sha256']),io.BytesIO())

    def test_interrupted_restore_journal_recovers_each_directory_move_and_retries(self):
        _,record=self.capture();original=Path.rename
        for failed_name in ['home','service']:
            (self.home/'config.xml').write_text('current-before-interruption')
            self.state['ActiveState']='inactive'
            envelope=self.signed('controller-maintenance',mode='restore',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],backup_id=record['backup_id'],backup_sha256=record['backup_sha256'],old_tuple=record['old_tuple'])
            def rename(path,target):
                if path.name==failed_name and path.parent.name.startswith('restore-staging-'):raise KeyboardInterrupt('simulated process death')
                return original(path,target)
            with self.subTest(root=failed_name),patch.object(Path,'rename',rename):
                with self.assertRaises(KeyboardInterrupt):self.controller.dispatch(envelope)
            self.assertTrue((self.controller_base/'restore-journal.json').exists())
            self.controller.recover_restore();self.controller.recover_restore()
            self.assertEqual((self.home/'config.xml').read_text(),'current-before-interruption')
            self.assertEqual((self.service/'override.conf').read_text(),'fixed')
            self.assert_retained(record)
            self.controller.dispatch(envelope)
            self.assertEqual((self.home/'config.xml').read_text(),'old')
            # The same completed operation is idempotent while still fenced;
            # after writes resume it cannot restore this backup a second time.
            self.controller.dispatch(envelope)
            self.state['quieting_down']=False
            with self.assertRaises(control.Refused):self.controller.dispatch(envelope)
            self.assertFalse(list(self.controller_base.glob('previous-*')))
            self.assertFalse(list(self.controller_base.glob('restore-staging-*')))
    def test_interrupted_restore_before_extraction_recovers_the_original_home(self):
        _,record=self.capture();original=Path.mkdir
        envelope=self.signed('controller-maintenance',mode='restore',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],backup_id=record['backup_id'],backup_sha256=record['backup_sha256'],old_tuple=record['old_tuple'])
        def mkdir(path,*args,**kwargs):
            result=original(path,*args,**kwargs)
            if path.name.startswith('restore-staging-'):raise KeyboardInterrupt('simulated death before extraction')
            return result
        with patch.object(Path,'mkdir',mkdir):
            with self.assertRaises(KeyboardInterrupt):self.controller.dispatch(envelope)
        self.controller.recover_restore()
        self.assertEqual((self.home/'config.xml').read_text(),'old');self.assert_retained(record)
        self.controller.dispatch(envelope)
        self.assertFalse((self.controller_base/'restore-journal.json').exists())

    def test_interrupted_committed_restore_keeps_verified_home_and_reclaims_old_copy(self):
        _,record=self.capture();(self.home/'config.xml').write_text('broken-before-restore')
        envelope=self.signed('controller-maintenance',mode='restore',target='CT107/jenkins',authorization_id=self.policy['authorization_id'],backup_id=record['backup_id'],backup_sha256=record['backup_sha256'],old_tuple=record['old_tuple'])
        original=maintenance.atomic_json
        def persist(path,value):
            original(path,value)
            if Path(path)==self.controller_base/'restore-journal.json' and value.get('committed') is True:raise KeyboardInterrupt('simulated death after durable commit')
        with patch.object(maintenance,'atomic_json',side_effect=persist):
            with self.assertRaises(KeyboardInterrupt):self.controller.dispatch(envelope)
        self.assertEqual((self.home/'config.xml').read_text(),'old')
        self.controller.recover_restore();self.controller.recover_restore()
        self.assertFalse(list(self.controller_base.glob('previous-*')))
        result=self.controller.dispatch(envelope)
        self.assertTrue(control.verify(result,self.policy['keys'],'controller-status')['result']['healthy'])
        self.assertEqual((self.home/'config.xml').read_text(),'old');self.assert_retained(record)


if __name__=='__main__':unittest.main()
