#!/usr/bin/env python3
"""Standalone SCM metadata and host-only IPAM matching with synthetic fixtures."""
import copy
import hashlib
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control
admission=SourceFileLoader('source_admission',str(ROOT/'scripts/jenkins/controller-admission.py')).load_module()
preflight=SourceFileLoader('source_preflight',str(ROOT/'scripts/jenkins/peer-preflight.py')).load_module()

class SourcePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        original=control.private_file
        for module in [control,admission,preflight]:
            item=patch.object(module,'private_file',lambda path,owner=0:original(path,owner=os.getuid()));item.start();self.addCleanup(item.stop)
        self.key=self.base/'key';self.public=self.base/'public'
        subprocess.run(['openssl','genpkey','-algorithm','ed25519','-out',str(self.key)],check=True,capture_output=True)
        subprocess.run(['openssl','pkey','-in',str(self.key),'-pubout','-out',str(self.public)],check=True,capture_output=True)
    def test_standalone_entry_authorization_allows_new_main_and_freezes_each_run(self):
        repository=self.base/'source.git';subprocess.run(['git','init','--bare',str(repository)],check=True,capture_output=True)
        def git(*args,input=None,env=None):return subprocess.check_output(['git','--git-dir',str(repository),*args],input=input,env=env).decode().strip()
        script=b'pipeline { agent none }\n';blob=git('hash-object','-w','--stdin',input=script)
        tree=git('mktree',input=('100644 blob '+blob+'\tJenkinsfile\n').encode())
        sha=git('commit-tree',tree,input=b'synthetic fixture\n',env={**os.environ,'GIT_AUTHOR_NAME':'Fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'Fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'})
        git('update-ref','refs/remotes/origin/main',sha);git('config','remote.origin.url','https://example.invalid/fixed.git')
        api=self.base/'api';control.atomic_json(api,{'user':'synthetic','token':'fixture'})
        profile={'name':'deploy','user':'iac-deploy','uid':1001,'scope':['root:proxmox'],'enabled':True,'git_dir':str(repository),'scm_url':'https://example.invalid/fixed.git','pipeline_path':'Jenkinsfile','standalone_entry':{'sha':sha,'script_sha256':hashlib.sha256(script).hexdigest()}}
        service=admission.Admission.__new__(admission.Admission);service.base=self.base/'registry';service.base.mkdir()
        service.policy={'jenkins_api_credentials':str(api),'profiles':{'Fixture':profile},'keys':{'current':self.public},'key_id':'current','signing_key':str(self.key)}
        metadata={'job':'Fixture','build':1,'sha':None,'scm_entry':{'definition':'org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition','urls':[profile['scm_url']],'branches':['*/main'],'path':'Jenkinsfile'},'script_sha256':hashlib.sha256(script).hexdigest(),'node_online':True,'building':True}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,_):return json.dumps(metadata).encode()
        original_run=subprocess.run;fetches=[]
        def commands(argv,**kwargs):
            if 'fetch' in argv:
                fetches.append(argv)
                return subprocess.CompletedProcess(argv,0)
            return original_run(argv,**kwargs)
        with patch.object(admission.urllib.request,'urlopen',return_value=Response()),patch.object(service,'versions',return_value={}),patch.object(admission.subprocess,'run',side_effect=commands):
            result=service.admit('Fixture',1)
            payload=control.verify(result,service.policy['keys'],'job-admission');self.assertEqual(payload['sha'],sha)
            self.assertTrue((service.base/(payload['nonce']+'.tar')).exists())
            self.assertIsNone(payload['source_binding']['jenkins_fetch_sha'])
            self.assertEqual(payload['source_binding']['reviewed_entry_sha'],sha)
            self.assertEqual(payload['source_resolution'],'admission')
            # Ordinary repository changes leave the reviewed entry authorized.
            ordinary=git('hash-object','-w','--stdin',input=b'ordinary application change\n')
            newer_tree=git('mktree',input=('100644 blob '+blob+'\tJenkinsfile\n100644 blob '+ordinary+'\tapplication.txt\n').encode())
            newer=git('commit-tree',newer_tree,'-p',sha,input=b'ordinary change\n',env={**os.environ,'GIT_AUTHOR_NAME':'Fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'Fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'})
            git('update-ref','refs/remotes/origin/main',newer)
            newer_payload=control.verify(service.admit('Fixture',1),service.policy['keys'],'job-admission')
            self.assertEqual(newer_payload['sha'],newer);self.assertNotEqual(newer_payload['sha'],sha)
            self.assertEqual(newer_payload['source_binding']['reviewed_entry_sha'],sha)
            with tarfile.open(service.base/(newer_payload['nonce']+'.tar')) as archive:
                self.assertEqual(archive.extractfile('application.txt').read(),b'ordinary application change\n')
            # Lease renewal never re-resolves main, and preserves each signed SHA.
            fetched=len(fetches)
            for admitted in [payload,newer_payload]:
                renewed=control.verify(service.request('lease',{'nonce':admitted['nonce']},root=True),service.policy['keys'],'job-lease')
                self.assertEqual(renewed['sha'],admitted['sha'])
                self.assertEqual(renewed['bundle_sha256'],admitted['bundle_sha256'])
                self.assertEqual(renewed['source_binding'],admitted['source_binding'])
            self.assertEqual(len(fetches),fetched)
            # A main entry change requires a new reviewed entry, even when the
            # running Jenkins build still uses the older approved script bytes.
            changed_blob=git('hash-object','-w','--stdin',input=b'pipeline { agent any }\n')
            changed_tree=git('mktree',input=('100644 blob '+changed_blob+'\tJenkinsfile\n').encode())
            changed=git('commit-tree',changed_tree,'-p',newer,input=b'entry change\n',env={**os.environ,'GIT_AUTHOR_NAME':'Fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'Fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'})
            git('update-ref','refs/remotes/origin/main',changed)
            with self.assertRaises(control.Refused):service.admit('Fixture',1)
            frozen=control.verify(service.request('lease',{'nonce':newer_payload['nonce']},root=True),service.policy['keys'],'job-lease')
            self.assertEqual(frozen['sha'],newer)

            for key,value in [('branches',['feature']),('urls',['https://example.invalid/other.git']),('path','other.groovy')]:
                original=metadata['scm_entry'][key];metadata['scm_entry'][key]=value
                with self.subTest(key=key),self.assertRaises(control.Refused):service.metadata('Fixture',1)
                metadata['scm_entry'][key]=original
            metadata['script_sha256']='f'*64
            with self.assertRaises(control.Refused):service.metadata('Fixture',1)
            metadata['script_sha256']=hashlib.sha256(script).hexdigest();entry=profile.pop('standalone_entry')
            with self.assertRaises(control.Refused):service.metadata('Fixture',1)
            profile['standalone_entry']=dict(entry,sha='invalid-sha')
            with self.assertRaises(control.Refused):service.admit('Fixture',1)
            # Historical evidence binds the actual old script object even after
            # current main has advanced to an unreviewed entry.
            profile['standalone_entry']=entry
            metadata['job']='Webhook-Router';metadata.update(building=False,result='SUCCESS',no_workspace=True,no_shell_or_secret_binding=True)
            router_profile={**profile,'name':'router'}
            service.policy['profiles']['Webhook-Router']=router_profile
            receipt=control.verify(service.request('route-evidence',{'build':1},root=True),service.policy['keys'],'router-run-evidence')
            self.assertEqual(receipt['source_sha'],sha)
            self.assertIsNone(receipt['source_binding']['jenkins_fetch_sha'])
            metadata['job']='Fixture';metadata['building']=True
            # Matching a pinned hash is insufficient if Git's immutable script differs.
            profile['standalone_entry']=dict(entry,script_sha256='f'*64);metadata['script_sha256']='f'*64
            with self.assertRaises(control.Refused):service.admit('Fixture',1)
    def test_apps_validation_checks_real_repair_object_sha_and_tree_digest(self):
        remote=self.base/'remote.git';cache=self.base/'cache.git'
        subprocess.run(['git','init','--bare','--template=',str(remote)],check=True,capture_output=True)
        def git(*args,input=None):
            return subprocess.check_output(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','--git-dir',str(remote),*args],input=input).decode().strip()
        blob=git('hash-object','-w','--stdin',input=b'synthetic repair fixture\n')
        tree=git('mktree',input=('100644 blob '+blob+'\tfixture.txt\n').encode())
        sha=git('commit-tree',tree,input=b'fixture: private repair contract\n');git('update-ref','refs/heads/main',sha)
        subprocess.run(['git','clone','--bare',str(remote),str(cache)],check=True,capture_output=True)
        digest=hashlib.sha256(subprocess.check_output(['git','--git-dir',str(cache),'ls-tree','-r','--full-tree',sha])).hexdigest()
        service=admission.Admission.__new__(admission.Admission)
        profile={'name':'apps-validation','git_dir':str(cache),'scm_url':str(remote),'application_inputs':{'repair_sha':sha,'repair_tree_sha256':digest}}
        metadata={'sha':sha,'source_binding':{'kind':'reviewed-inline-bundle'}}
        self.assertEqual(service.resolve_source(metadata,profile),(cache,sha))
        for field,value in [('repair_sha','f'*40),('repair_tree_sha256','f'*64),('repair_tree_sha256','invalid')]:
            invalid=copy.deepcopy(profile);invalid['application_inputs'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(control.Refused):service.resolve_source(metadata,invalid)
        missing=copy.deepcopy(profile);missing['application_inputs']['repair_sha']='0'*40
        with self.assertRaises(subprocess.CalledProcessError):service.resolve_source({**metadata,'sha':'0'*40},missing)

    def test_merge_changes_include_first_parent_additions_and_deletions(self):
        repository=self.base/'merge-fixture';repository.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid',*args],
                                           cwd=repository,stderr=subprocess.DEVNULL,text=True).strip()
        git('init','-b','fixture-base')
        (repository/'README.md').write_text('synthetic base')
        (repository/'说明 + @.md').write_text('synthetic documentation')
        playbooks=repository/'ansible/playbooks';playbooks.mkdir(parents=True)
        (playbooks/'deploy-obsolete.yml').write_text('---\n')
        git('add','.');git('commit','-m','fixture: base')
        first=git('rev-parse','HEAD')
        initial=admission.Admission.changed_paths(repository/'.git',first)
        self.assertEqual({row['path'] for row in initial},{'README.md','说明 + @.md','ansible/playbooks/deploy-obsolete.yml'})
        self.assertTrue(all(row['deleted'] is False for row in initial))
        git('checkout','-b','fixture-feature')
        terraform=repository/'terraform/proxmox';terraform.mkdir(parents=True)
        (terraform/'fixture.tf').write_text('# synthetic infrastructure\n')
        (playbooks/'deploy-obsolete.yml').unlink()
        git('add','-A');git('commit','-m','fixture: infrastructure and deletion')
        git('checkout','fixture-base')
        (repository/'README.md').write_text('parallel synthetic documentation')
        git('add','.');git('commit','-m','fixture: parallel docs')
        git('merge','--no-ff','fixture-feature','-m','fixture: merge')
        merged=git('rev-parse','HEAD')
        self.assertEqual(len(git('rev-list','--parents','-n','1',merged).split()),3)
        self.assertEqual(admission.Admission.changed_paths(repository/'.git',merged),[
            {'path':'ansible/playbooks/deploy-obsolete.yml','deleted':True},
            {'path':'terraform/proxmox/fixture.tf','deleted':False}])

    def test_preflight_queries_bare_host_and_refuses_other_prefixes_and_partial_ipam(self):
        policy_path=self.base/'policy.json';token=self.base/'token';token.write_text('synthetic-read-only-token')
        policy={'pve_origin':'https://pve.invalid','pve_read_token':str(token),'pve_ca':None,'netbox_origin':'https://netbox.invalid','netbox_read_token':str(token),'nonce':'preflight_fixture_nonce_1234','operator':'fixture','authorization_id':'fixture','key_id':'current','signing_key':str(self.key)}
        control.atomic_json(policy_path,policy);output=self.base/'report.json';calls=[]
        empty={'count':0,'results':[],'next':None,'previous':None}
        ipam=copy.deepcopy(empty)
        def get(url,*args):
            calls.append(url)
            if '/ipam/' in url:
                self.assertTrue(url.endswith('?address=192.168.1.110'));self.assertNotIn('%2F',url)
                return ipam
            if '/cluster/resources' in url:return {'data':[]}
            if '/content?' in url:return {'data':[{'volid':'local:vztmpl/'+preflight.TARGET['template']}]}
            return {'data':{'active':1,'avail':32*1024**3,'content':'rootdir,images'}}
        with patch.object(preflight,'get',side_effect=get),patch.object(sys,'argv',['preflight','--policy',str(policy_path),'--output',str(output)]):
            preflight.main();self.assertEqual(control.verify(json.loads(output.read_text()),{'current':self.public},'peer-allocation-preflight')['target']['ip'],'192.168.1.110/24')
            for prefix in [24,32]:
                ipam=dict(empty,count=1,results=[{'address':'192.168.1.110/'+str(prefix)}])
                with self.subTest(prefix=prefix),self.assertRaises(control.Refused):preflight.main()
            for malformed in [{},{'count':0},dict(empty,count='0'),dict(empty,count=False),dict(empty,results=None),dict(empty,next='https://netbox.invalid/page2'),dict(empty,previous='https://netbox.invalid/page1')]:
                ipam=malformed
                with self.subTest(ipam=ipam),self.assertRaises(control.Refused):preflight.main()
        self.assertTrue(calls)

if __name__=='__main__':unittest.main()
