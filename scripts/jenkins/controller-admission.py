#!/usr/bin/python3
"""CT107 trusted job admission. Jenkins build metadata owns identity and approvals."""
import base64
import fcntl
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import hmac
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import socket
import subprocess
import tarfile
import tempfile
import shutil
import time
import urllib.parse
import urllib.request
from control import Refused,atomic_json,canonical,private_file,sha_file,sign,token,verify,digest,secret_file

GROOVY=r'''
import groovy.json.JsonOutput
import jenkins.model.Jenkins
import jenkins.scm.api.SCMRevisionAction
import org.jenkinsci.plugins.workflow.graph.FlowGraphWalker
import org.jenkinsci.plugins.workflow.actions.ArgumentsAction
import org.jenkinsci.plugins.workflow.actions.WorkspaceAction
import org.jenkinsci.plugins.workflow.support.steps.input.InputSubmittedAction
String jobName = __JOB__
int buildNumber = __BUILD__
String nodeName = __NODE__
def job = Jenkins.get().getItemByFullName(jobName)
def build = job?.getBuildByNumber(buildNumber)
if (!build || (__REQUIRE_RUNNING__ && !build.isBuilding())) { throw new IllegalStateException("Build is not running") }
def revision = build.getAction(SCMRevisionAction)?.revision
String sha = revision?.hasProperty('hash') ? revision.hash : null
def definition = job.definition
def standalone = definition?.class?.name == 'org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition'
def scmEntry = standalone ? [definition:definition.class.name, urls:definition.scm.userRemoteConfigs.collect { it.url }, branches:definition.scm.branches.collect { it.name }, path:definition.scriptPath] : null
String scriptSHA = java.security.MessageDigest.getInstance('SHA-256').digest(build.execution.script.getBytes('UTF-8')).encodeHex().toString()
def computer = nodeName == null ? null : Jenkins.get().getComputer(nodeName)
boolean nodeOnline = nodeName == null || (computer != null && !computer.isOffline() && computer.getChannel() != null)
def approvals = [:]
int workspaces = 0
int shellBindings = 0
for (node in new FlowGraphWalker(build.execution)) {
  if (node.getAction(WorkspaceAction)) { workspaces++ }
  if (node.hasProperty('descriptor') && node.descriptor?.functionName in ['sh','bat','powershell','pwsh','withCredentials']) { shellBindings++ }
  def submitted = node.getAction(InputSubmittedAction)
  if (!submitted) { continue }
  def arguments = ArgumentsAction.getResolvedArguments(node)
  def approver = hudson.model.User.getById(submitted.approver, false)
  if (approver && approver.getAuthorities().contains('iac-approvers')) {
    approvals[arguments.id] = submitted.approver
  }
}
def manual = build.getCause(hudson.model.Cause.UserIdCause)?.userId
println(JsonOutput.toJson([node_online:nodeOnline,manual_user:manual,job:jobName,build:buildNumber,sha:sha,scm_entry:scmEntry,building:build.isBuilding(),approvals:approvals,script_sha256:scriptSHA,no_workspace:workspaces==0,no_shell_or_secret_binding:shellBindings==0,result:build.result?.toString()]))
'''


def source_revision(metadata,profile):
    if metadata.get('sha') is not None:return metadata['sha']
    entry=metadata.get('scm_entry')
    pinned=profile.get('standalone_entry')
    if (not isinstance(entry,dict) or entry.get('definition')!='org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition'
        or entry.get('urls')!=[profile['scm_url']] or entry.get('branches') not in [['main'],['*/main'],['refs/heads/main']]
        or entry.get('path')!=profile['pipeline_path'] or not isinstance(pinned,dict) or set(pinned)!={'sha','script_sha256'}
        or not isinstance(pinned['sha'],str) or not re.fullmatch('[0-9a-f]{40}',pinned['sha'])
        or not isinstance(pinned['script_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',pinned['script_sha256'])
        or metadata.get('script_sha256')!=pinned['script_sha256']):
        raise Refused('standalone SCM build requires its reviewed root-owned entry version and actual script bytes')
    # The reviewed entry commit identifies script authorization, not the
    # repository revision to execute. The original Jenkins fetch is unknown.
    return None


class Admission:
    def __init__(self,policy):
        self.policy=policy
        for field in ['signing_key','input_digest_key','jenkins_api_credentials']:secret_file(policy[field])
        for path in policy['keys'].values():private_file(path)
        for profile in policy['profiles'].values():
            if profile.get('enabled') and profile['name']!='router':
                timeout=profile.get('timeout',3600)
                if type(timeout) is not int or not 1<=timeout<=3600:raise Refused('execution timeout must be between 1 and 3600 seconds')
                if profile['user'] not in {'iac-plan','iac-deploy','iac-apps'} or profile['uid']<=0:raise Refused('invalid provisioned execution identity')
                self.versions(profile)
        self.base=Path(policy['registry']);self.base.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.collect_expired()
    def metadata(self,job,build,require_running=True):
        if job not in self.policy['profiles'] or type(build) is not int or build<=0:
            raise Refused('job/build outside the fixed map')
        script=GROOVY.replace('__NODE__',json.dumps(self.policy['profiles'][job].get('user'))).replace('__JOB__',json.dumps(job)).replace('__BUILD__',str(build)).replace('__REQUIRE_RUNNING__','true' if require_running else 'false')
        credential=json.loads(private_file(self.policy['jenkins_api_credentials']).read_text())
        auth=base64.b64encode((credential['user']+':'+credential['token']).encode()).decode()
        request=urllib.request.Request('http://127.0.0.1:8080/scriptText',data=urllib.parse.urlencode({'script':script}).encode(),headers={'Authorization':'Basic '+auth})
        with urllib.request.urlopen(request,timeout=15) as response:metadata=json.loads(response.read(1024*1024))
        profile=self.policy['profiles'][job]
        if profile['name']=='plan' and metadata.get('manual_user') not in self.policy['plan_operators']:raise Refused('read-only plan requires an authorized manual operator')
        if profile['name']=='apps-validation':
            if metadata['script_sha256']!=profile['inline_script_sha256']:raise Refused('validation inline script differs from reviewed bundle entry')
            metadata['sha']=profile['validation_sha']
            metadata['source_binding']={'kind':'reviewed-inline-bundle','jenkins_fetch_sha':None,'script_sha256':metadata['script_sha256']}
        else:
            metadata['sha']=source_revision(metadata,profile)
            metadata['source_binding']={'kind':'jenkins-scm-revision' if metadata['sha'] is not None else 'standalone-controller-main',
                                        'jenkins_fetch_sha':metadata['sha'],'script_sha256':metadata['script_sha256']}
            if metadata['sha'] is None:metadata['source_binding']['reviewed_entry_sha']=profile['standalone_entry']['sha']
        if metadata['job']!=job or metadata['build']!=build or (require_running and (not metadata['building'] or not metadata['node_online'])) or (metadata['sha'] is not None and (not isinstance(metadata['sha'],str) or not re.fullmatch('[0-9a-f]{40}',metadata['sha']))):
            raise Refused('Jenkins metadata mismatch')
        return metadata
    def versions(self,profile):
        key=private_file(self.policy['input_digest_key']).read_bytes()
        if any(set(secret)!={'version','path'} for stage in profile.get('secrets',{}).values() for secret in stage.values()):raise Refused('profile must reference Vault-backed versioned root files')
        stages=list(profile.get('secrets',{}).values())+[{'root-only:'+name:secret for name,secret in profile.get('root_only_credentials',{}).items()}]
        return {name:{'version':secret['version'],'key_id':self.policy['input_digest_key_id'],'digest':hmac.new(key,private_file(secret['path']).read_bytes(),hashlib.sha256).hexdigest()} for stage in stages for name,secret in stage.items()}
    def resolve_source(self,metadata,profile,historical=False):
        sha=metadata['sha']
        repository=private_file(Path(profile['git_dir'])/'config').parent
        remote=subprocess.check_output(['git','--git-dir',str(repository),'config','--get','remote.origin.url'],text=True).strip()
        if remote!=profile['scm_url']:raise Refused('SCM origin differs from the fixed repository mapping')
        subprocess.run(['git','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','--git-dir',str(repository),'fetch','--no-tags','--no-recurse-submodules','origin','refs/heads/main:refs/remotes/origin/main'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60,env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_NOSYSTEM':'1'})
        head=subprocess.check_output(['git','--git-dir',str(repository),'rev-parse','refs/remotes/origin/main'],text=True).strip()
        if not re.fullmatch('[0-9a-f]{40}',head):raise Refused('invalid protected main revision')
        if metadata['source_binding']['kind']=='standalone-controller-main':
            reviewed=subprocess.check_output(['git','--git-dir',str(repository),'show',profile['standalone_entry']['sha']+':'+profile['pipeline_path']])
            if hashlib.sha256(reviewed).hexdigest()!=profile['standalone_entry']['script_sha256']:raise Refused('reviewed entry version differs from its immutable Git script')
            sha=profile['standalone_entry']['sha'] if historical else head
        elif not historical and profile['name']!='apps-validation' and head!=sha:raise Refused('build is not the current protected main SHA')
        if profile['name']!='apps-validation':
            script=subprocess.check_output(['git','--git-dir',str(repository),'show',sha+':'+profile['pipeline_path']])
            if hashlib.sha256(script).hexdigest()!=metadata['script_sha256']:raise Refused('build definition differs from its protected source SHA')
        # A private repair object is deliberately prepared by its owner. Never
        # fall back to main when it is missing from the trusted bare repository.
        subprocess.run(['git','--git-dir',str(repository),'cat-file','-e',sha+'^{commit}'],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if profile['name']=='apps-validation':
            inputs=profile.get('application_inputs',{})
            if inputs.get('repair_sha')!=sha or not re.fullmatch('[0-9a-f]{64}',inputs.get('repair_tree_sha256','')):
                raise Refused('private owner repair object digest is required')
            tree=subprocess.check_output(['git','--git-dir',str(repository),'ls-tree','-r','--full-tree',sha])
            if hashlib.sha256(tree).hexdigest()!=inputs['repair_tree_sha256']:
                raise Refused('prepared private repair object differs from reviewed tree')
        return repository,sha
    def admit(self,job,build):
        metadata=self.metadata(job,build);profile=self.policy['profiles'][job]
        if profile.get('enabled') is not True:raise Refused('job migration is not activated')
        if profile['name'] in {'plan','apps-validation'} and profile.get('secrets'):raise Refused('read-only/validation profiles cannot bind mutation secrets')
        nonce=__import__('secrets').token_hex(24)
        archive=self.base/(nonce+'.tar')
        source_archive=self.base/(nonce+'-source.tar')
        now=int(time.time())
        # Reserve quota atomically, then prepare the fixed source without
        # retaining the global registry lock or blocking another run's lease.
        with self.registry_lock():
            if sum(1 for path in self.base.glob('*.json') if re.fullmatch('[0-9a-f]{48}',path.stem) and not json.loads(private_file(path).read_text()).get('terminal'))>=8 or shutil.disk_usage(self.base).free<2*1024**3:
                raise Refused('admission retention or disk budget reached')
            if (self.base/(nonce+'.json')).exists():raise Refused('admission nonce collision')
            atomic_json(self.base/(nonce+'.json'),{'terminal':False,'deadline':now+900,'preparing':True})
        try:
            repository,sha=self.resolve_source(metadata,profile)
            subprocess.run(['git','--git-dir',str(repository),'archive','--format=tar','--output',str(source_archive),sha],check=True)
            source_archive.chmod(0o600)
            if source_archive.stat().st_size>256*1024**2:raise Refused('source bundle exceeds bounded retention size')
            if profile['name']=='plan':
                from importlib.machinery import SourceFileLoader
                projector=SourceFileLoader('snapshot_admission',str(Path(__file__).with_name('plan-snapshot.py'))).load_module()
                recovery=SourceFileLoader('archive_admission',str(Path(__file__).with_name('toolchain.py'))).load_module()
                with self.projection_directory(nonce) as temporary:
                    temporary=Path(temporary);source=temporary/'source';source.mkdir(mode=0o700)
                    with tarfile.open(source_archive) as incoming:
                        recovery.check_archive(incoming);incoming.extractall(source)
                    policy=json.loads(private_file(self.policy['projection_policy']).read_text());policy['source_sha']=sha
                    projector.produce(policy,source,nonce,temporary/'projection')
                    atomic_json(self.base/(nonce+'-snapshot.json'),json.loads((temporary/'projection/manifest.json').read_text()))
                    with tarfile.open(archive,'w') as output:output.add(temporary/'projection',arcname='.',recursive=True)
            else:source_archive.rename(archive)
            source_archive.unlink(missing_ok=True)
            archive.chmod(0o600)
            if archive.stat().st_size>256*1024**2:raise Refused('execution bundle exceeds bounded retention size')
            now=int(time.time())
            payload={'purpose':'job-admission','job':job,'build':build,'sha':sha,'nonce':nonce,
                     'profile':profile['name'],'unix_user':profile['user'],'uid':profile['uid'],'scope':sorted(profile['scope']),'issued_at':now,'expires_at':now+60,
                     'bundle_sha256':sha_file(archive),'profile_sha256':digest(canonical(profile)),
                     'application_inputs':profile.get('application_inputs',{}),'credential_versions':self.versions(profile),
                     'source_binding':metadata['source_binding'],'source_resolution':'admission',
                     'changes':self.changed_paths(repository,sha) if profile['name']=='deploy' else None,
                     'notion':profile.get('notion',{'enabled':False})}
            envelope=sign(payload,self.policy['key_id'],self.policy['signing_key'])
            with self.registry_lock():
                pending=json.loads(private_file(self.base/(nonce+'.json')).read_text())
                if pending.get('preparing') is not True or pending.get('terminal') or int(time.time())>=pending['deadline']:
                    raise Refused('source preparation reservation expired')
                atomic_json(self.base/(nonce+'.json'),{'admission':envelope,'approvals':{},'deadline':now+profile.get('timeout',3600)+900,'terminal':False})
            return envelope
        except Exception:
            with self.registry_lock():
                self.remove_run_files(nonce)
                path=self.base/(nonce+'.json')
                if path.exists() and not json.loads(private_file(path).read_text()).get('terminal'):path.unlink()
            raise
        finally:
            source_archive.unlink(missing_ok=True)

    @staticmethod
    def changed_paths(repository,sha):
        git=['git','--git-dir',str(repository)]
        parents=subprocess.check_output(git+['rev-list','--parents','-n','1',sha],text=True).split()
        # Compare merges with their first parent, matching the legacy pipeline.
        # A root commit has no parent and must still expose its added files.
        arguments=(['diff','--name-status','-z','--no-renames',parents[1],sha] if len(parents)>1
                   else ['diff-tree','--root','--no-commit-id','--name-status','-z','-r','--no-renames',sha])
        data=subprocess.check_output(git+arguments)
        result=[]
        fields=data.decode().split('\0')
        if fields.pop()!='' or len(fields)%2:raise Refused('invalid Git path framing')
        for status,path in zip(fields[::2],fields[1::2]):
            if path.startswith(('terraform/','ansible/','scripts/','ci/','Jenkinsfile')) and not re.fullmatch('[A-Za-z0-9_./-]+',path):raise Refused('change path cannot be classified safely')
            result.append({'path':path,'deleted':status=='D'})
        return result

    @contextmanager
    def registry_lock(self,blocking=True):
        # Global quota and record commits are short; no source/network work here.
        with open(self.base/'registry.lock','a+b') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                yield False;return
            yield True

    @contextmanager
    def nonce_lock(self,nonce):
        nonce=token(nonce)
        if not re.fullmatch('[0-9a-f]{48}',nonce):raise Refused('unmanaged run nonce')
        with self.registry_lock():
            private_file(self.base/(nonce+'.json'))
            lock=open(self.base/(nonce+'.lock'),'a+b')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX)
            yield
        finally:lock.close()

    def live_record(self,nonce):
        record=json.loads(private_file(self.base/(token(nonce)+'.json')).read_text())
        if record.get('terminal') or record.get('preparing') or int(time.time())>=record['deadline']:
            raise Refused('run is not ready, terminal or expired')
        return record

    @contextmanager
    def projection_directory(self,nonce):
        directory=self.base/(token(nonce)+'-projection')
        directory.mkdir(mode=0o700)
        try:yield directory
        finally:
            if directory.exists():shutil.rmtree(directory)

    def remove_run_files(self,nonce):
        nonce=token(nonce)
        for suffix in ['.tar','-source.tar','-snapshot.json']:
            (self.base/(nonce+suffix)).unlink(missing_ok=True)
        directory=self.base/(nonce+'-projection')
        if directory.exists():
            if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid!=os.geteuid():raise Refused('unsafe run projection directory')
            shutil.rmtree(directory)

    def collect_expired(self,blocking=True):
        now=int(time.time())
        with self.registry_lock(blocking) as acquired:
            if not acquired:return
            records=[]
            for path in self.base.glob('*.json'):
                if not re.fullmatch('[0-9a-f]{48}',path.stem):continue
                record=json.loads(private_file(path).read_text())
                if not record.get('terminal') and now>=record['deadline']:
                    self.remove_run_files(path.stem)
                    record={'terminal':True,'deadline':now,'nonce':path.stem}
                    atomic_json(path,record)
                if record.get('terminal'):records.append((record['deadline'],path))
            # Small audit records survive seven days, with a hard count bound.
            records.sort(reverse=True,key=lambda pair:pair[0])
            for index,(finished,path) in enumerate(records):
                if index>=1000 or now-finished>7*86400:
                    path.unlink(missing_ok=True);path.with_suffix('.lock').unlink(missing_ok=True)

    def existing(self,nonce):
        nonce=token(nonce)
        with self.registry_lock():record=self.live_record(nonce)
        original=record['admission']['payload']
        metadata=self.metadata(original['job'],original['build'])
        if metadata['source_binding']!=original['source_binding'] or (metadata['sha'] is not None and metadata['sha']!=original['sha']):raise Refused('build source or reviewed entry changed')
        profile=self.policy['profiles'][original['job']]
        if digest(canonical(profile))!=original['profile_sha256']:raise Refused('execution policy changed; replan required')
        if self.versions(profile)!=original['credential_versions']:raise Refused('credential version changed; replan required')
        with self.registry_lock():
            current=self.live_record(nonce)
            if current['admission']!=record['admission']:raise Refused('run admission changed during metadata verification')
        return current,original,metadata,profile
    def request(self,operation,data,root=False):
        if operation=='admit':return self.admit(data['job'],data['build'])
        if not root:raise Refused('this control operation requires peer root certificate')
        if operation=='route-evidence':return self.request_locked(operation,data,root)
        with self.nonce_lock(data['nonce']):
            return self.request_locked(operation,data,root)

    def request_locked(self,operation,data,root=False):
        if operation=='admit':return self.admit(data['job'],data['build'])
        if not root:raise Refused('this control operation requires peer root certificate')
        if operation=='route-evidence':
            metadata=self.metadata('Webhook-Router',data['build'],require_running=False)
            profile=self.policy['profiles']['Webhook-Router']
            repository,sha=self.resolve_source(metadata,profile,historical=True)
            script=subprocess.check_output(['git','--git-dir',str(repository),'show',sha+':'+profile['pipeline_path']])
            if hashlib.sha256(script).hexdigest()!=metadata['script_sha256'] or not metadata['no_workspace'] or not metadata['no_shell_or_secret_binding']:
                raise Refused('router allocated execution or did not use its protected pipeline')
            if metadata['result']!='SUCCESS':raise Refused('successful router migration requires SUCCESS')
            now=int(time.time())
            return sign({'purpose':'router-run-evidence','nonce':__import__('secrets').token_hex(24),
                         'issued_at':now,'expires_at':now+1800,'job':'Webhook-Router','build':data['build'],
                         'source_sha':sha,'source_binding':metadata['source_binding'],'source_resolution':'evidence-only','script_sha256':metadata['script_sha256'],
                         'no_workspace':True,'no_shell_or_secret_binding':True,'result':metadata['result']},self.policy['key_id'],self.policy['signing_key'])
        if operation=='complete':
            nonce=token(data['nonce'])
            path=self.base/(nonce+'.json')
            with self.registry_lock():
                record=json.loads(private_file(path).read_text())
                self.remove_run_files(nonce)
                atomic_json(path,{'terminal':True,'deadline':int(time.time()),'nonce':nonce})
            return {'status':'completed'}
        record,original,metadata,profile=self.existing(data['nonce'])
        now=int(time.time())
        if operation=='finalize':
            from importlib.machinery import SourceFileLoader
            projector=SourceFileLoader('snapshot_finalize',str(Path(__file__).with_name('plan-snapshot.py'))).load_module()
            policy=json.loads(private_file(self.policy['projection_policy']).read_text())
            return projector.finalize(policy,json.loads(private_file(self.base/(original['nonce']+'-snapshot.json')).read_text()))
        if operation=='lease':
            return sign({**original,'purpose':'job-lease','issued_at':now,'expires_at':now+60},self.policy['key_id'],self.policy['signing_key'])
        if operation=='approval':
            stage=data['stage'];digest=data['digest']
            allowed={'plan':set(),'deploy':{'terraform','ansible'},'apps-publish':{'apps-publish','apps-google'},'apps-validation':set()}[profile['name']]
            if stage not in allowed or not re.fullmatch('[0-9a-f]{64}',digest):raise Refused('invalid approval request')
            prefix={'terraform':'TF-','ansible':'ANSIBLE-','apps-publish':'APPS-PUBLISH-','apps-google':'APPS-GOOGLE-'}[stage]
            approver=metadata['approvals'].get(prefix+digest)
            if not approver:raise Refused('authorized Jenkins input has not approved this exact digest')
            payload={**original,'purpose':'job-approval','stage':stage,'digest':digest,'approver':approver,'issued_at':now,'expires_at':now+900}
            old=record['approvals'].get(stage)
            if old is not None:
                if old['digest']!=digest or old['approver']!=approver:raise Refused('stage was already approved for another manifest')
                if now<old['expires_at']:return sign(old,self.policy['key_id'],self.policy['signing_key'])
                raise Refused('original approval expired; recreate run')
            with self.registry_lock():
                record=self.live_record(original['nonce'])
                record['approvals'][stage]=payload;atomic_json(self.base/(original['nonce']+'.json'),record)
            return sign(payload,self.policy['key_id'],self.policy['signing_key'])
        if operation=='secrets':
            stage=data['stage']
            if stage in {'ansible','notion'} and 'ansible' not in record['approvals']:raise Refused('Ansible credentials require scope approval')
            if stage not in {'terraform','ansible','apps-publish','apps-google','notion'}:raise Refused('unknown credential stage')
            if stage.startswith('apps-') and stage not in record['approvals']:raise Refused('application stage requires its approved integration contract')
            authorization_stage='ansible' if stage=='notion' else stage
            if stage!='terraform' and record['approvals'].get(authorization_stage,{}).get('expires_at',0)<=now:raise Refused('stage credential approval expired')
            if stage=='notion' and ('integration:notion' not in original['scope'] or profile.get('notion',{}).get('enabled') is not True):raise Refused('Notion integration is not authorized')
            bindings={}
            secrets=profile.get('secrets',{}).get(stage,{})
            key=private_file(self.policy['input_digest_key']).read_bytes() if secrets else b''
            for name,secret in secrets.items():
                content=private_file(secret['path']).read_bytes()
                actual={'version':secret['version'],'key_id':self.policy['input_digest_key_id'],
                        'digest':hmac.new(key,content,hashlib.sha256).hexdigest()}
                expected=original['credential_versions'][name]
                if not hmac.compare_digest(canonical(actual),canonical(expected)):
                    raise Refused('credential bytes changed before binding; recreate run')
                bindings[name]={'version':expected,'value':base64.b64encode(content).decode()}
            return bindings
        raise Refused('unknown control operation')


class AdmissionServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,handler,tls):
        self.tls=tls
        self.slots=threading.BoundedSemaphore(16)
        self.last_gc=0
        self.gc_worker=ThreadPoolExecutor(max_workers=1)
        self.gc_future=None
        super().__init__(address,handler)
    def service_actions(self):
        if time.monotonic()-self.last_gc>60 and (self.gc_future is None or self.gc_future.done()):
            self.gc_future=self.gc_worker.submit(self.control.collect_expired,blocking=False)
            self.last_gc=time.monotonic()

    def server_close(self):
        super().server_close()
        self.gc_worker.shutdown(wait=False,cancel_futures=True)

    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):request.close();return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        wrapped=None
        def expire():
            connection=wrapped if wrapped is not None else request
            try:connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            connection.close()
        timer=threading.Timer(3,expire);timer.daemon=True;timer.start()
        try:
            request.settimeout(3)
            wrapped=self.tls.wrap_socket(request,server_side=True,do_handshake_on_connect=False)
            wrapped.request_read_timer=timer
            wrapped.settimeout(3);wrapped.do_handshake()
            super().process_request_thread(wrapped,address)
        except (OSError,ssl.SSLError):
            self.audit('tls-rejected',None,None)
        finally:
            timer.cancel()
            if wrapped is not None:wrapped.close()
            request.close();self.slots.release()
    def audit(self,reason,identity,nonce):
        # Never log exception strings, HTTP payloads, certificates or API tokens.
        print(json.dumps({'event':'admission','reason':reason,
                          'identity':identity if identity in {'iac-peer-root','iac-peer-remoting'} else None,
                          'nonce':nonce if isinstance(nonce,str) and re.fullmatch('[0-9a-f]{48}',nonce) else None}),flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_args):pass
    def do_POST(self):
        started=False;identity=None;nonce=None
        try:
            self.connection.settimeout(3)
            names=dict(item for group in self.connection.getpeercert()['subject'] for item in group)
            identity=names.get('commonName')
            if identity not in {'iac-peer-remoting','iac-peer-root'} or self.client_address[0]!='192.168.1.110':raise Refused('unapproved peer')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:raise Refused('invalid request size')
            raw=self.rfile.read(length)
            if len(raw)!=length:raise Refused('incomplete request')
            self.connection.request_read_timer.cancel()
            data=json.loads(raw);operation=self.path.removeprefix('/');nonce=data.get('nonce')
            if operation=='bundle':
                if identity!='iac-peer-root':raise Refused('root transport required')
                with self.server.control.nonce_lock(nonce):
                    self.server.control.existing(nonce)
                    archive=self.server.control.base/(token(nonce)+'.tar')
                    # Hold the descriptor through streaming, even if completion
                    # on another connection subsequently unlinks this run.
                    source=open(archive,'rb')
                with source:
                    self.send_response(200);started=True
                    self.send_header('Content-Type','application/x-tar');self.send_header('Content-Length',str(os.fstat(source.fileno()).st_size));self.end_headers()
                    __import__('shutil').copyfileobj(source,self.wfile)
                return
            result=self.server.control.request(operation,data,identity=='iac-peer-root')
            body=canonical(result);self.send_response(200);started=True;self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        except Exception:
            self.server.audit('request-refused',identity,nonce)
            if started:self.close_connection=True
            else:
                try:self.send_error(403,'control policy refused request')
                except OSError:pass
    def deny(self):self.send_error(403)
    do_GET=do_CONNECT=do_PUT=do_PATCH=do_DELETE=deny


def main():
    policy=json.loads(private_file('/etc/jenkins-control/admission.json').read_text())
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.minimum_version=ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(policy['certificate'],policy['private_key']);tls.load_verify_locations(policy['peer_ca']);tls.verify_mode=ssl.CERT_REQUIRED
    server=AdmissionServer(('192.168.1.107',9444),Handler,tls);server.control=Admission(policy)
    server.serve_forever()


if __name__=='__main__':main()
