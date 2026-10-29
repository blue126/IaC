#!/usr/bin/python3
"""Independent controller helper and signed recovery gate; no arbitrary shell."""
import argparse
import base64
import fcntl
import hashlib
import json
import http.client
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import urllib.error
import urllib.parse
from control import Refused, atomic_json, canonical, command, digest, private_file, sha_file, sign, token, verify, secret_file

BASE=Path('/var/lib/jenkins-recovery')
HOME=Path('/var/lib/jenkins')
SERVICE_CONFIG=Path('/etc/systemd/system/jenkins.service.d')
CLEANUP_FIELDS={'unit_stopped','cgroup_empty','netns_removed','bindings_removed','workspace_removed'}
FENCE=HOME/'init.groovy.d/00-peer-recovery-fence.groovy'
FENCE_SOURCE='jenkins.model.Jenkins.get().doQuietDown()\n'
EXPECTED_JOBS={'IaC-Homelab-Pipeline','Webhook-Router','n8n-rental','n8n-rental-clasp-validation','IaC-ReadOnly-Plan'}


def tuple_for(home=HOME):
    plugins={p.name:sha_file(p) for p in sorted((home/'plugins').glob('*.jpi'))}
    plugins.update({p.name:sha_file(p) for p in sorted((home/'plugins').glob('*.hpi'))})
    java=subprocess.run(['/usr/lib/jvm/temurin-25-jre-amd64/bin/java','-version'],text=True,capture_output=True,check=True).stderr.splitlines()[0]
    # Configuration closure excludes queues, node monitors and build/runtime XML.
    paths={home/name for name in ['secret.key','secret.key.not-so-secret']}
    paths.update(path for path in home.glob('*.xml') if path.name not in {'queue.xml','nodeMonitors.xml'})
    for branch in ['jobs','nodes','users']:
        paths.update((home/branch).rglob('config.xml'))
    paths.update((home/'init.groovy.d').glob('*.groovy'))
    paths.add(home/'init.groovy')
    paths.update((home/'secrets').glob('*'))
    config={str(p.relative_to(home)):sha_file(p) for p in sorted(paths)
            if p.is_file() and not p.is_symlink() and p!=home/'init.groovy.d/00-peer-recovery-fence.groovy'}
    casc_files={path for pattern in ['*.yaml','*.yml'] for path in (home/'casc').rglob(pattern)}
    config.update({str(p.relative_to(home)):sha_file(p) for p in sorted(casc_files) if p.is_file() and not p.is_symlink()})
    config.update({str(p):sha_file(p) for p in sorted(SERVICE_CONFIG.glob('*.conf')) if p.is_file() and not p.is_symlink()})
    return {'core':command(['dpkg-query','-W','-f=${Version}','jenkins']), 'plugins':digest(canonical(plugins)), 'java':java,'config':digest(canonical(config))}


def inspect_tar(archive):
    for member in archive.getmembers():
        path=Path(member.name)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in {'home','service'}:
            raise Refused('archive crosses the fixed recovery roots')
        if not (member.isfile() or member.isdir()):
            raise Refused('archive contains a link or special file')


def check_resources(mem_available_kib,free_bytes,free_inodes,archive_bytes,home_bytes,runtime_bytes,required_inodes=10000):
    required=archive_bytes+home_bytes+runtime_bytes+max(512*1024**2,home_bytes//4)+2*1024**3
    if mem_available_kib<1792*1024 or free_bytes<required or free_inodes<required_inodes:
        raise Refused('restore drill exceeds memory/disk/inode admission budget')
    return required


def validate_evidence(envelope,policy,now=None,zero=False,require_armed=True):
    evidence=verify(envelope,policy['keys'],'controller-recovery-evidence',now)
    if evidence['target']!='CT107/jenkins' or evidence['drill_target']!='CT110':
        raise Refused('recovery evidence target mismatch')
    if evidence['tuple']!=policy['tuple'] or evidence['authorization_id']!=policy['authorization_id']:
        raise Refused('recovery evidence tuple or authorization mismatch')
    if evidence['backup_sha256']!=sha_file(private_file(policy['backup'])):
        raise Refused('backup was modified after restore testing')
    for name,expected in evidence['evidence_files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or sha_file(private_file(Path(policy['evidence_dir'])/path))!=expected:
            raise Refused('restore drill evidence file mismatch')
    required={'stop','archive_verify','namespace_isolation','config_parse','plugin_load','health','gitea_unchanged'}
    observed={record['name'] for record in evidence['commands'] if record['exit_code']==0}
    if not required<=observed or not evidence['evidence_files']:
        raise Refused('restore drill did not supply complete execution records')
    if require_armed:
        armed=verify(json.loads(private_file(policy['watchdog_attestation']).read_text()),policy['keys'],'controller-watchdog-armed',now)
        if armed['nonce']!=evidence['nonce'] or armed['backup_sha256']!=evidence['backup_sha256'] or armed['old_tuple']!=evidence['tuple']:
            raise Refused('watchdog attestation does not match restored backup')
    if zero:
        jobs=evidence.get('jobs',{})
        if set(jobs)!=EXPECTED_JOBS:
            raise Refused('every surviving job and the new plan entry needs migration evidence')
        migration=policy.get('migration_inputs',{})
        if set(migration)!=EXPECTED_JOBS:raise Refused('current approved migration input map is required')
        for job,record in jobs.items():
            for key in ['scheduling_evidence','cleanup_evidence','credential_scope_evidence']:
                filename=record.get(key)
                if filename not in evidence['evidence_files']:raise Refused('job migration requires actual hashed execution evidence: '+job)
                signed=json.loads(private_file(Path(policy['evidence_dir'])/filename).read_text())
                historical=signed['payload']
                if job=='Webhook-Router':
                    router=verify(signed,policy['keys'],'router-run-evidence',historical['issued_at'])
                    expected_input=migration[job]
                    if (router.get('job')!=job or type(router.get('build')) is not int or router['build']!=expected_input['build']
                        or router.get('source_sha')!=expected_input['source_sha'] or router['no_workspace'] is not True
                        or router['no_shell_or_secret_binding'] is not True or router['script_sha256']!=policy['router_script_sha256']
                        or router['script_sha256']!=expected_input['script_sha256'] or router['result']!='SUCCESS'):
                        raise Refused('router execution evidence did not verify')
                    continue
                observed=verify(signed,policy['keys'],'job-run-evidence',historical['issued_at'])
                expected_input=migration[job]
                cleanup=observed.get('cleanup')
                if (observed['job']!=job or type(observed.get('build')) is not int or observed['build']!=expected_input['build']
                    or observed.get('profile_sha256')!=expected_input['profile_sha256'] or observed.get('source_sha')!=expected_input['source_sha'] or observed.get('uid')!=expected_input['uid']
                    or observed.get('scope')!=expected_input['scope'] or observed.get('credential_versions')!=expected_input['credential_versions']
                    or observed['exit_code']!=0 or observed['runner_sha256']!=policy['runner_sha256']
                    or observed['isolation_verified'] is not True or not isinstance(cleanup,dict) or set(cleanup)!=CLEANUP_FIELDS
                    or any(value is not True for value in cleanup.values())):
                    raise Refused('job migration execution evidence did not verify: '+job)
                expected='iac-plan' if job=='IaC-ReadOnly-Plan' else 'iac-deploy' if job=='IaC-Homelab-Pipeline' else 'iac-apps'
                if job!='Webhook-Router' and observed['node']!=expected:raise Refused('job ran on the wrong identity')
        required_extra={'agent_reconnect','second_ansible_run','normal_plan','normal_deploy','oom_budget','failed_maintenance_restore'}
        command_names={item['name'] for item in evidence['commands'] if item['exit_code']==0}
        if not required_extra<=command_names:raise Refused('controller handoff runtime evidence is incomplete')
    return evidence


class Controller:
    def __init__(self,policy):
        self.policy=policy
        for key in ['signing_key','jenkins_api_credentials']:secret_file(policy[key])
        for path in policy['keys'].values():private_file(path)
        command(['openssl','pkey','-in',policy['signing_key'],'-check','-noout'])
        BASE.mkdir(mode=0o700,exist_ok=True)
    def api(self,path,post=False,data=None):
        # The helper owns this fixed local endpoint; it never proxies arbitrary URLs.
        credential=json.loads(private_file(self.policy['jenkins_api_credentials']).read_text())
        auth=base64.b64encode((credential['user']+':'+credential['token']).encode()).decode()
        request=urllib.request.Request('http://127.0.0.1:8080/'+path,
                 headers={'Authorization':'Basic '+auth},data=(urllib.parse.urlencode(data).encode() if data is not None else b'') if post else None)
        with urllib.request.urlopen(request,timeout=10) as response:return response.read()
    def status(self):
        status=command(['systemctl','show','jenkins.service','-p','ActiveState','-p','SubState'])
        result=dict(line.split('=',1) for line in status.splitlines())
        gitea=command(['systemctl','show','gitea.service','-p','MainPID','-p','ExecMainStartTimestampMonotonic','-p','ActiveState'])
        result['gitea']=dict(line.split('=',1) for line in gitea.splitlines())
        result['tuple']=tuple_for()
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/login',timeout=5) as response:result['healthy']=response.status==200
        except Exception:result['healthy']=False
        try:result['quieting_down']=json.loads(self.api('api/json?tree=quietingDown'))['quietingDown']
        except Exception:result['quieting_down']=None
        return result
    def stop(self):
        self.api('quietDown',True)
        try:
            deadline=time.monotonic()+600
            while True:
                computers=json.loads(self.api('computer/api/json?tree=computer[executors[currentExecutable[url]],oneOffExecutors[currentExecutable[url]]]'))['computer']
                if not any(e.get('currentExecutable') for c in computers for e in c.get('executors',[])+c.get('oneOffExecutors',[])):break
                if time.monotonic()>deadline:raise Refused('controller failed to drain within maintenance window')
                time.sleep(2)
            command(['systemctl','stop','jenkins.service'])
            if self.status()['ActiveState']!='inactive':raise Refused('Jenkins is still writing')
            group=command(['systemctl','show','jenkins.service','--value','-p','ControlGroup'])
            if group:
                procs=Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs'
                if procs.exists() and procs.read_text().strip():raise Refused('Jenkins cgroup still has processes')
        except Exception:
            try:self.api('cancelQuietDown',True)
            except Exception:pass
            raise
    def backup(self,nonce):
        if self.status()['ActiveState']!='inactive':raise Refused('backup requires stopped Jenkins')
        registry_path=BASE/'backup-registry.json'
        registry=json.loads(registry_path.read_text()) if registry_path.exists() else {}
        if registry.get('candidate'):raise Refused('an unverified candidate already exists; use signed discard-candidate')
        registry['candidate']=nonce;atomic_json(registry_path,registry)
        directory=BASE/token(nonce)
        directory.mkdir(mode=0o700)
        backup=directory/'backup.tar'
        with tarfile.open(backup,'w') as archive:
            for source,name in [(HOME,'home'),(SERVICE_CONFIG,'service')]:
                if not source.exists():continue
                # Reject even internal links: no archive operation follows a link.
                for root,dirs,files in os.walk(source,followlinks=False):
                    for entry in dirs+files:
                        path=Path(root)/entry
                        if path.is_symlink() or not (path.is_file() or path.is_dir()):
                            raise Refused('backup contains a link or special file')
                archive.add(source,arcname=name,recursive=True)
        backup.chmod(0o600)
        with tarfile.open(backup) as archive:
            inspect_tar(archive)
            expanded=sum(member.size for member in archive.getmembers())
            inodes=len(archive.getmembers())
        now=int(time.time())
        manifest={'purpose':'controller-backup','target':'CT107/jenkins','nonce':nonce,
                  'issued_at':now,'expires_at':now+1800,'tuple':tuple_for(),
                  'backup_sha256':sha_file(backup),'archive_bytes':backup.stat().st_size,'expanded_bytes':expanded,'inodes':inodes,'authorization_id':self.policy['authorization_id']}
        atomic_json(directory/'manifest.json',sign(manifest,self.policy['key_id'],self.policy['signing_key']))
        return manifest
    def managed_backup(self,backup_id,slot,expected_hash=None):
        backup_id=token(backup_id)
        registry=json.loads(private_file(BASE/'backup-registry.json').read_text())
        if registry.get(slot)!=backup_id or (slot=='candidate' and registry.get('verified')==backup_id):
            raise Refused('backup is not the managed '+slot)
        directory=BASE/backup_id
        if directory.is_symlink() or not directory.is_dir():raise Refused('unsafe managed backup directory')
        envelope=json.loads(private_file(directory/'manifest.json').read_text())
        # Retained backups outlive their capture window. A fresh maintenance
        # signature and the registry authorize use; the historical signature
        # still binds the exact archive and tuple to its original capture.
        manifest=verify(envelope,self.policy['keys'],'controller-backup',envelope['payload']['issued_at'])
        backup=private_file(directory/'backup.tar')
        if manifest['target']!='CT107/jenkins' or manifest['nonce']!=backup_id or manifest['authorization_id']!=self.policy['authorization_id']:
            raise Refused('backup manifest identity mismatch')
        self.checked_tuple(manifest['tuple'])
        actual=sha_file(backup)
        if actual!=manifest['backup_sha256'] or (expected_hash is not None and actual!=expected_hash):raise Refused('backup hash mismatch')
        return backup,manifest,registry
    def reclaim_retired(self):
        registry_path=BASE/'backup-registry.json'
        if not registry_path.exists():return
        registry=json.loads(private_file(registry_path).read_text())
        changed=False
        for field in ['retired','discarding']:
            old=registry.get(field)
            if not old:continue
            old=token(old)
            if old in {registry.get('verified'),registry.get('candidate')}:raise Refused('retired backup is still referenced')
            directory=BASE/old
            if directory.exists():
                if directory.is_symlink() or not directory.is_dir():raise Refused('unsafe retired backup')
                shutil.rmtree(directory)
            registry.pop(field,None);changed=True
        if changed:atomic_json(registry_path,registry)

    def export(self,envelope,output):
        payload=verify(envelope,self.policy['keys'],'controller-maintenance')
        if payload.get('mode')!='export' or payload['target']!='CT107/jenkins' or payload['authorization_id']!=self.policy['authorization_id']:
            raise Refused('export authorization mismatch')
        nonce=token(payload['nonce']);backup_id=token(payload['backup_id'])
        registry=json.loads(private_file(BASE/'backup-registry.json').read_text())
        slot='candidate' if registry.get('candidate')==backup_id else 'verified' if payload.get('allow_verified') is True else None
        if slot is None:raise Refused('export requires managed candidate or explicitly allowed verified backup')
        archive,manifest,_=self.managed_backup(backup_id,slot,payload['backup_sha256'])
        status=self.status()
        if status['ActiveState']!='inactive' or status['tuple']!=manifest['tuple']:raise Refused('export requires unchanged stopped backup tuple')
        receipt=BASE/(nonce+'-export.json')
        if receipt.exists():raise Refused('export nonce already consumed')
        atomic_json(receipt,{'backup_id':backup_id,'started_at':int(time.time())})
        now=int(time.time())
        header=sign({'purpose':'controller-status','target':'CT107/jenkins','nonce':nonce,
                     'issued_at':now,'expires_at':now+60,'result':{'backup_sha256':manifest['backup_sha256']}},self.policy['key_id'],self.policy['signing_key'])
        output.write(canonical(header)+b'\n');output.flush()
        with open(archive,'rb') as source:shutil.copyfileobj(source,output)

    @staticmethod
    def checked_tuple(value):
        if not isinstance(value,dict) or set(value)!={'core','java','plugins','config'} or any(not isinstance(item,str) or not item for item in value.values()):
            raise Refused('complete signed controller tuple required')
        return value
    def fence(self,enabled):
        if FENCE.exists() and (FENCE.is_symlink() or FENCE.read_text()!=FENCE_SOURCE):raise Refused('startup fence path conflicts with existing configuration')
        if enabled:
            FENCE.parent.mkdir(mode=0o755,exist_ok=True)
            FENCE.write_text(FENCE_SOURCE);FENCE.chmod(0o444)
        elif FENCE.exists():FENCE.unlink()
    def start(self,resume=True):
        command(['systemctl','daemon-reload'])
        command(['systemctl','start','jenkins.service'])
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            try:
                self.api('api/json')
                if not resume and not json.loads(self.api('api/json?tree=quietingDown'))['quietingDown']:raise Refused('startup maintenance fence did not take effect')
                if resume:
                    self.fence(False);self.api('cancelQuietDown',True)
                return {'healthy':True,'tuple':tuple_for()}
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, json.JSONDecodeError):time.sleep(2)
        raise Refused('Jenkins failed health verification')
    def recover_restore(self):
        path=BASE/'restore-journal.json'
        if not path.exists():return
        record=json.loads(private_file(path).read_text())
        nonce=token(record['nonce'])
        staging=BASE/('restore-staging-'+nonce)
        pairs=[(HOME,BASE/('previous-'+nonce),'home'),
               (SERVICE_CONFIG,BASE/('previous-service-'+nonce),'service')]
        # All mutable paths are derived from the validated nonce and fixed roots.
        for destination,previous,name in pairs:
            if previous.is_symlink() or staging.is_symlink() or destination.is_symlink():raise Refused('unsafe restore journal path')
        if record.get('committed') is not True:
            command(['systemctl','stop','jenkins.service'])
            state=command(['systemctl','show','jenkins.service','--value','-p','ActiveState'])
            if state not in {'inactive','failed'}:raise Refused('restore rollback requires stopped Jenkins')
            group=command(['systemctl','show','jenkins.service','--value','-p','ControlGroup'])
            if group:
                root=Path('/sys/fs/cgroup')/group.lstrip('/')
                if root.exists() and any(item.read_text().strip() for item in root.rglob('cgroup.procs')):
                    raise Refused('restore rollback cgroup is not empty')
            for destination,previous,name in reversed(pairs):
                if previous.exists():
                    if destination.exists():shutil.rmtree(destination)
                    previous.rename(destination)
                elif name=='service' and record['replace_service'] and not record['service_existed'] and not (staging/'service').exists() and destination.exists():
                    shutil.rmtree(destination)
            if not HOME.is_dir():raise Refused('restore journal could not recover original home')
        else:
            # The restored copy passed boot/health/tuple verification before this
            # durable commit. Reclamation never rolls it back after new writes.
            receipt=BASE/(nonce+'-restore.json')
            consumed=json.loads(private_file(receipt).read_text())
            if consumed.get('request_digest')!=record['request_digest']:raise Refused('restore journal authorization mismatch')
            atomic_json(receipt,{**consumed,'completed':True,'result':record['result']})
            for destination,previous,name in pairs:
                if previous.exists():shutil.rmtree(previous)
        if staging.exists():shutil.rmtree(staging)
        path.unlink()

    def restore(self,payload):
        self.recover_restore()
        backup,manifest,_=self.managed_backup(payload['backup_id'],'verified',payload['backup_sha256'])
        if self.checked_tuple(payload['old_tuple'])!=manifest['tuple']:raise Refused('restore tuple differs from signed backup')
        current=tuple_for()
        if payload['old_tuple']['core']!=current['core'] or payload['old_tuple']['java']!=current['java']:
            raise Refused('core/Java restoration is outside this helper')
        if self.status()['ActiveState'] not in {'inactive','failed'}:raise Refused('restoration requires stopped/failed Jenkins')
        nonce=token(payload['nonce'])
        staging=BASE/('restore-staging-'+nonce)
        previous=BASE/('previous-'+nonce)
        previous_service=BASE/('previous-service-'+nonce)
        if staging.exists() or previous.exists() or previous_service.exists() or HOME.is_symlink() or SERVICE_CONFIG.is_symlink():
            raise Refused('restore path collision')
        if not HOME.is_dir():raise Refused('current home is absent')
        journal=BASE/'restore-journal.json'
        record={'nonce':nonce,'replace_service':False,'service_existed':SERVICE_CONFIG.exists(),'committed':False,'request_digest':digest(canonical(payload))}
        atomic_json(journal,record)
        try:
            staging.mkdir(mode=0o700)
            with tarfile.open(backup) as archive:
                inspect_tar(archive);archive.extractall(staging)
            candidate=staging/'home'
            if not candidate.is_dir() or not HOME.is_dir():raise Refused('backup or current home is absent')
            record['replace_service']=(staging/'service').exists()
            atomic_json(journal,record)
            HOME.rename(previous)
            candidate.rename(HOME)
            if record['replace_service']:
                if record['service_existed']:SERVICE_CONFIG.rename(previous_service)
                (staging/'service').rename(SERVICE_CONFIG)
            import pwd
            identity=pwd.getpwnam('jenkins')
            for root,dirs,files in os.walk(HOME):
                os.chown(root,identity.pw_uid,identity.pw_gid)
                for name in files:os.chown(Path(root)/name,identity.pw_uid,identity.pw_gid)
            self.fence(True)
            result=self.start(resume=False)
            if result['tuple']!=payload['old_tuple']:raise Refused('restored tuple differs from verified backup')
            record['committed']=True;record['result']=result;atomic_json(journal,record)
            self.recover_restore()
            return result
        except Exception:
            if journal.exists():
                self.recover_restore()
            elif staging.exists():shutil.rmtree(staging)
            raise

    def dispatch(self,envelope):
        payload=verify(envelope,self.policy['keys'],'controller-maintenance')
        if payload['target']!='CT107/jenkins' or payload['authorization_id']!=self.policy['authorization_id']:
            raise Refused('controller target or authorization mismatch')
        nonce=token(payload['nonce'])
        phase=payload['mode']
        receipt=BASE/(nonce+'-'+phase+'.json')
        request_digest=digest(canonical(payload))
        replay=receipt.exists()
        if replay:
            previous=json.loads(private_file(receipt).read_text())
            if phase not in {'promote','discard-candidate','restore'} or previous.get('request_digest')!=request_digest:
                raise Refused('maintenance authorization already consumed')
        if replay and phase=='restore' and previous.get('completed') is True:
            status=self.status()
            if status['ActiveState']!='active' or status.get('healthy') is not True or status.get('quieting_down') is not True or status['tuple']!=payload['old_tuple']:
                raise Refused('completed restore cannot be replayed after production resumes')
            now=int(time.time())
            return sign({'purpose':'controller-status','target':'CT107/jenkins','nonce':nonce,'issued_at':now,'expires_at':now+60,'result':previous['result']},self.policy['key_id'],self.policy['signing_key'])
        if phase not in {'status','stop','backup','start','restore','agent-status','promote','discard-candidate','fail-stop','prepare','resume'}:raise Refused('unknown fixed helper mode')
        if not replay:atomic_json(receipt,{'started_at':int(time.time()),'mode':phase,'request_digest':request_digest})
        if phase in {'promote','discard-candidate'}:
            if phase=='promote':
                registry=json.loads(private_file(BASE/'backup-registry.json').read_text())
                if replay and registry.get('verified')==payload['backup_id'] and not registry.get('candidate'):
                    self.reclaim_retired()
                else:
                    backup,manifest,registry=self.managed_backup(payload['backup_id'],'candidate')
                    candidate=manifest['nonce']
                    proof=verify(payload['evidence'],self.policy['keys'],'controller-recovery-evidence')
                    status=self.status()
                    if (proof['target']!='CT107/jenkins' or proof['drill_target']!='CT110' or proof['authorization_id']!=self.policy['authorization_id']
                        or proof['nonce']!=candidate or proof['backup_id']!=candidate or proof['backup_sha256']!=manifest['backup_sha256']
                        or proof['tuple']!=manifest['tuple'] or status['ActiveState']!='inactive' or status['tuple']!=manifest['tuple']):
                        raise Refused('only an unchanged stopped-controller restore-tested candidate can be promoted')
                    old=registry.get('verified')
                    old_valid=True
                    if old:
                        try:self.managed_backup(old,'verified')
                        except (Refused,OSError,ValueError):old_valid=False
                    registry['verified']=candidate
                    registry.pop('candidate',None)
                    if old and old!=candidate:
                        if old_valid:registry['retired']=old
                        else:registry.setdefault('quarantined',[]).append(old)
                    atomic_json(BASE/'backup-registry.json',registry)
                    self.reclaim_retired()
            else:
                registry=json.loads(private_file(BASE/'backup-registry.json').read_text())
                candidate=token(payload['backup_id'])
                if registry.get('candidate')!=candidate or registry.get('verified')==candidate:
                    if replay and previous.get('validated_backup_id')==candidate and registry.get('verified')!=candidate and not (BASE/candidate).exists():
                        return sign({'purpose':'controller-status','target':'CT107/jenkins','nonce':nonce,'issued_at':int(time.time()),'expires_at':int(time.time())+60,'result':{'retention_updated':True}},self.policy['key_id'],self.policy['signing_key'])
                    raise Refused('only the unverified managed candidate can be discarded')
                directory=BASE/candidate
                if directory.is_symlink() or not directory.is_dir():raise Refused('unsafe candidate directory')
                atomic_json(receipt,{'started_at':int(time.time()),'mode':phase,'request_digest':request_digest,'validated_backup_id':candidate})
                registry.pop('candidate',None);registry['discarding']=candidate
                atomic_json(BASE/'backup-registry.json',registry)
                self.reclaim_retired()
            result={'retention_updated':True}
        elif phase in {'prepare','resume','fail-stop'}:
            _,manifest,_=self.managed_backup(payload['backup_id'],'verified',payload['backup_sha256'])
            status=self.status()
            if phase=='prepare':
                if self.checked_tuple(payload['old_tuple'])!=manifest['tuple'] or status['ActiveState']!='inactive' or status['tuple']!=manifest['tuple']:
                    raise Refused('prepare requires the stopped signed backup tuple')
                self.fence(True)
            elif phase=='resume':
                expected=self.checked_tuple(payload['expected_tuple'])
                if any(expected[key]!=manifest['tuple'][key] for key in ['core','java']) or status['ActiveState']!='active' or status.get('healthy') is not True or status['tuple']!=expected or status.get('quieting_down') is not True:
                    raise Refused('resume requires the healthy fenced authorized tuple')
                self.fence(False);self.api('cancelQuietDown',True)
            else:
                if self.checked_tuple(payload['old_tuple'])!=manifest['tuple'] or any(status['tuple'][key]!=manifest['tuple'][key] for key in ['core','java']):
                    raise Refused('failure stop differs from signed backup runtime')
                if status['ActiveState']=='active' and status.get('quieting_down') is not True:raise Refused('failure stop requires the maintenance write fence')
                command(['systemctl','stop','jenkins.service'])
                if self.status()['ActiveState'] not in {'inactive','failed'}:raise Refused('failure stop did not stop Jenkins')
            result=self.status()
        elif phase=='agent-status':
            script="import groovy.json.JsonOutput; import jenkins.model.Jenkins; println(JsonOutput.toJson(['iac-plan','iac-deploy','iac-apps'].collectEntries { name -> def c=Jenkins.get().getComputer(name); [name,[offline:c==null || c.isOffline(),connect_time:c==null ? 0 : c.getConnectTime()]] }))"
            result=json.loads(self.api('scriptText',True,{'script':script}))
        elif phase=='status':result=self.status()
        elif phase=='stop':self.stop();result=self.status()
        elif phase=='backup':result=self.backup(nonce)
        elif phase=='start':result=self.start()
        else:result=self.restore(payload)
        if phase=='restore':atomic_json(receipt,{'mode':phase,'request_digest':request_digest,'completed':True,'result':result})
        now=int(time.time())
        return sign({'purpose':'controller-status','target':'CT107/jenkins','nonce':nonce,
                     'issued_at':now,'expires_at':now+60,'result':result},self.policy['key_id'],self.policy['signing_key'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['helper','gate','gate-zero','check-policy'])
    parser.add_argument('--policy',default='/etc/jenkins-recovery/policy.json')
    parser.add_argument('--evidence')
    parser.add_argument('--authorization-id')
    parser.add_argument('--evidence-id')
    parser.add_argument('--bundle-sha256')
    args=parser.parse_args()
    policy=json.loads(private_file(args.policy).read_text())
    if args.mode=='check-policy':Controller(policy);return
    if args.mode=='helper':
        if os.geteuid()!=0 or os.environ.get('SSH_ORIGINAL_COMMAND','') not in {'','jenkins-recovery'}:
            raise Refused('fixed root helper required')
        controller=Controller(policy)
        with open(BASE/'control-plane.lock','a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            controller.recover_restore()
            controller.reclaim_retired()
            envelope=json.loads(__import__('sys').stdin.buffer.readline(1024*1024))
            if envelope.get('payload',{}).get('mode')=='export':
                controller.export(envelope,__import__('sys').stdout.buffer)
            else:
                print(json.dumps(controller.dispatch(envelope)))
    else:
        envelope=json.loads(private_file(args.evidence).read_text())
        evidence=validate_evidence(envelope,policy,zero=args.mode=='gate-zero')
        if args.authorization_id!=evidence['authorization_id'] or args.evidence_id!=evidence['nonce'] or args.bundle_sha256!=sha_file(private_file(policy['watchdog_attestation'])):
            raise Refused('Ansible lifecycle IDs/hash do not match the actual signed evidence')
        BASE.mkdir(mode=0o700,exist_ok=True)
        receipt=BASE/('gate-'+token(evidence['nonce'])+'.json')
        with open(BASE/'gate.lock','a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if receipt.exists():raise Refused('recovery evidence has already authorized a controller write')
            atomic_json(receipt,{'nonce':evidence['nonce'],'authorization_id':evidence['authorization_id'],'mode':args.mode})
        print('verified recovery evidence')


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('controller maintenance or recovery gate refused')
