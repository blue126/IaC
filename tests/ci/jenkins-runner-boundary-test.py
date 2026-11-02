#!/usr/bin/env python3
"""Exercise cleanup, signed approvals and job-report trust boundaries offline."""
import copy
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control
runner=SourceFileLoader('boundary_runner',str(ROOT/'scripts/jenkins/job-runner.py')).load_module()
transaction=SourceFileLoader('boundary_transaction',str(ROOT/'scripts/jenkins/transaction.py')).load_module()
client=SourceFileLoader('boundary_client',str(ROOT/'scripts/jenkins/runner-client.py')).load_module()

class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.nonce='boundary_fixture_nonce_1234';self.uid=os.getuid()
        self.payload={'nonce':self.nonce,'sha':'a'*40,'scope':['root:proxmox'],'credential_versions':{'vault':'v1'},'build':1}
        self.profile={'name':'deploy','user':'iac-deploy'}
        self.service=runner.Runner(self.base,{'profiles':{},'keys':{}})
        self.record={'nonce':self.nonce,'unit':'iac-job-'+self.nonce+'.service','directory':str(self.base/('job-'+self.nonce)),'profile':'deploy','uid':self.uid,'sha':'a'*40}
        self.key=self.base/'key';self.public=self.base/'public'
        subprocess.run(['openssl','genpkey','-algorithm','ed25519','-out',str(self.key)],check=True,capture_output=True)
        subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.public)],check=True,capture_output=True)
        original=control.private_file
        item=patch.object(control,'private_file',lambda path,owner=0:original(path,owner=os.getuid()));item.start();self.addCleanup(item.stop)
    def sign(self,purpose,**values):
        now=int(time.time());return control.sign({'purpose':purpose,'issued_at':now,'expires_at':now+120,**self.payload,**values},'current',self.key)
    def test_normal_cleanup_removes_only_the_private_run(self):
        directory=Path(self.record['directory']);directory.mkdir(mode=0o700);(directory/'secret').write_text('synthetic')
        sibling=self.base/'other-task';sibling.mkdir();(sibling/'keep').write_text('preserve')
        with patch.object(runner,'command',side_effect=lambda argv:'not-found' if 'LoadState' in argv else ''),patch.object(runner.subprocess,'run'):
            self.service.cleanup(self.record)
        self.assertFalse(directory.exists());self.assertEqual((sibling/'keep').read_text(),'preserve')
    def test_execute_finally_quarantines_on_delete_failure_before_any_next_transport(self):
        calls=[]
        def systemctl(argv,**kwargs):calls.append(argv)
        def transport(operation,data,stream=None):raise control.Refused('synthetic interrupted bundle before secret binding')
        with patch.object(runner,'validate_admission',return_value=(self.payload,self.profile)),patch.object(runner.os,'chown'),patch.object(runner.pwd,'getpwnam',return_value=type('Identity',(),{'pw_gid':os.getgid()})()),patch.object(runner.shutil,'disk_usage',return_value=type('Disk',(),{'free':10*1024**3})()),patch.object(self.service,'controller',side_effect=transport) as connection,patch.object(runner,'command',side_effect=lambda argv:'not-found' if 'LoadState' in argv else ''),patch.object(runner.subprocess,'run',side_effect=systemctl),patch.object(runner.shutil,'rmtree',side_effect=OSError('synthetic deletion failure')):
            with self.assertRaisesRegex(control.Refused,'cleanup failed'):self.service.execute({},self.uid)
            self.assertTrue((self.base/'quarantine.json').exists());self.assertTrue((self.base/('run-'+self.nonce+'.json')).exists())
            self.assertIsNone(self.service.active)
            before=connection.call_count
            with self.assertRaisesRegex(control.Refused,'quarantined'):self.service.execute({},self.uid)
            self.assertEqual(connection.call_count,before)
        self.assertEqual({argv[-1] for argv in calls if argv[:2]==['systemctl','stop']},{'jenkins-agent@'+name+'.service' for name in runner.IDENTITIES})
    def test_execute_finally_quarantines_when_cgroup_retains_processes(self):
        cgroup=self.base/'fake-cgroup';cgroup.mkdir();(cgroup/'cgroup.procs').write_text('1234\n')
        real_path=Path
        def paths(*parts):
            value=real_path(*parts)
            return cgroup if value==real_path('/sys/fs/cgroup') else value
        with patch.object(runner,'validate_admission',return_value=(self.payload,self.profile)),patch.object(runner.os,'chown'),patch.object(runner.pwd,'getpwnam',return_value=type('Identity',(),{'pw_gid':os.getgid()})()),patch.object(self.service,'controller',side_effect=control.Refused('interrupted')),patch.object(runner,'Path',side_effect=paths),patch.object(runner,'command',side_effect=lambda argv:'loaded' if 'LoadState' in argv else '.' if 'ControlGroup' in argv else ''),patch.object(runner.subprocess,'run') as services:
            with self.assertRaisesRegex(control.Refused,'cleanup failed'):self.service.execute({},self.uid)
            self.assertTrue((self.base/'quarantine.json').exists());self.assertTrue(Path(self.record['directory']).exists())
            self.assertEqual(services.call_count,3)
    def test_real_status_rejects_job_owned_phase_and_digest_injection(self):
        directory=Path(self.record['directory']);(directory/'report').mkdir(parents=True);(directory/'control').mkdir()
        self.service.active=self.record;control.atomic_json(self.base/('used-'+self.nonce+'.json'),{'uid':self.uid})
        for phase,digest in [('terraform-approval','a'*64+';touch /tmp/escape'),('terraform-approval','$(id)'),('terraform-approval',''),('terraform-approval/../../evil','a'*64),('evil;sh','a'*64)]:
            control.atomic_json(directory/'report/status.json',{'phase':phase,'manifest_digest':digest})
            with self.subTest(phase=phase,digest=digest),self.assertRaises(control.Refused):self.service.status(self.nonce,self.uid)
        control.atomic_json(directory/'report/status.json',{'phase':'terraform-approval','manifest_digest':'a'*64,'summary':[]})
        self.assertEqual(self.service.status(self.nonce,self.uid)['manifest_digest'],'a'*64)
        with patch.object(client,'socket_request') as transport,patch.object(sys,'argv',['runner-client','approval','--nonce',self.nonce,'--stage','terraform','--digest','a'*64+';id']):
            with self.assertRaises(control.Refused):client.main()
            transport.assert_not_called()
        with patch.object(self.service,'controller') as transport:
            with self.assertRaises(control.Refused):self.service.approval(self.nonce,self.uid,'terraform','a'*64+';id')
            transport.assert_not_called()
    def test_transaction_approval_binds_manifest_sha_credentials_nonce_and_lease(self):
        (self.base/'control').mkdir();(self.base/'report').mkdir();keys={'current':self.public}
        now=int(time.time());manifest={'expires_at':now+100,'summary':[],'plan_sha256':'b'*64}
        digest=control.digest(control.canonical(manifest))
        lease=self.sign('job-lease');control.atomic_json(self.base/'control/lease.json',lease)
        approval=self.sign('job-approval',stage='terraform',digest=digest)
        with patch.object(transaction,'JOB',self.base):
            control.atomic_json(self.base/'control/terraform-approval.json',approval)
            self.assertEqual(transaction.approve('terraform',manifest,self.payload,keys)['digest'],digest)
            for modify in [{'digest':'c'*64},{'sha':'d'*40},{'credential_versions':{'vault':'v2'}},{'nonce':'different_nonce_123456'},{'stage':'ansible'}]:
                control.atomic_json(self.base/'control/terraform-approval.json',self.sign('job-approval',**{'stage':'terraform','digest':digest,**modify}))
                with self.subTest(modify=modify),self.assertRaises(control.Refused):transaction.approve('terraform',manifest,self.payload,keys)
            control.atomic_json(self.base/'control/terraform-approval.json',approval)
            with self.assertRaises(control.Refused):transaction.approve('terraform',dict(manifest,plan_sha256='c'*64),self.payload,keys)
            expired=self.sign('job-lease',issued_at=now-120,expires_at=now-1);control.atomic_json(self.base/'control/lease.json',expired)
            with self.assertRaises(control.Refused):transaction.approve('terraform',manifest,self.payload,keys)
            control.atomic_json(self.base/'control/lease.json',lease)
            with self.assertRaises(control.Refused):transaction.approve('terraform',dict(manifest,expires_at=now-1),self.payload,keys)

if __name__=='__main__':unittest.main()
