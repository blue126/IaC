#!/usr/bin/python3
"""Peer root admission daemon. The signed profile, never the caller, chooses exec."""
import argparse
import base64
import ssl
import tarfile
import urllib.request
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import pwd
import shutil
import signal
import stat
import selectors
from concurrent.futures import ThreadPoolExecutor
import socket
import struct
import subprocess
import sys
import threading
import time

from control import NoRedirect, Refused, atomic_json, command, private_file, token, verify, sha_file, sign, report_status, read_job_report, read_job_bytes

BASE = Path('/var/lib/jenkins-agent-control')
CONFIG = Path('/etc/jenkins-agent/runner.json')
REMOTING_READY = Path('/run/jenkins-agent-remoting-ready')
IDENTITIES = {'iac-plan', 'iac-deploy', 'iac-apps'}


def validate_admission(envelope, config, uid, now=None):
    payload = verify(envelope, config['keys'], 'job-admission', now)
    profile = config['profiles'][payload['job']]
    if profile['user'] not in IDENTITIES or pwd.getpwnam(profile['user']).pw_uid != uid or payload.get('uid')!=uid or payload.get('unix_user')!=profile['user']:
        raise Refused('peer UID does not match signed job identity')
    if payload['profile'] != profile['name'] or sorted(payload['scope']) != sorted(profile['scope']):
        raise Refused('job profile or scope differs from authorization')
    if not __import__('re').fullmatch('[0-9a-f]{40}', payload['sha']):
        raise Refused('immutable source SHA required')
    if profile['user'] == 'iac-plan' and (profile.get('secrets') or profile.get('dns')):
        raise Refused('plan profile cannot receive secrets or DNS')
    if profile.get('enabled') is not True:
        raise Refused('profile is not activated')
    timeout=profile.get('timeout',3600)
    if type(timeout) is not int or not 1<=timeout<=3600:raise Refused('execution timeout must be between 1 and 3600 seconds')
    profile={**profile,'timeout':timeout}
    return payload, profile


def network_rules(peers):
    rules = []
    for peer in peers:
        address = ipaddress.ip_address(peer['ip'])
        port = peer['port']
        if not isinstance(port, int) or not 1 <= port <= 65535 or address.is_loopback:
            raise Refused('invalid fixed network peer')
        family = 'ip' if address.version == 4 else 'ip6'
        rules.append(f'{family} daddr {address} tcp dport {port} accept')
    # inet policy covers both families, loopback, UDP/DNS and local services.
    return ('table inet job { chain output { type filter hook output priority 0; policy drop; '
            'ct state established,related accept; ' + '; '.join(rules) + '; } '
            'chain input { type filter hook input priority 0; policy drop; '
            'ct state established,related accept; } }\n')


class Runner:
    def __init__(self, base=BASE, config=None):
        self.base = Path(base)
        self.base.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.config = config or json.loads(private_file(CONFIG).read_text())
        self.active = None
        self.guard = threading.RLock()
        self.approval_guard = threading.Lock()
        self.code_sha256=sha_file(__file__)
        self.cancelled = threading.Event()
        self.stopping=threading.Event()

    def quarantine(self, reason):
        atomic_json(self.base/'quarantine.json', {'reason': reason, 'time': int(time.time())})
        for user in sorted(IDENTITIES):
            subprocess.run(['systemctl', 'stop', f'jenkins-agent@{user}.service'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    def reconcile(self):
        # A persistent unfinished registry always needs administrator inspection.
        pending = list(self.base.glob('run-*.json'))
        if pending:
            self.quarantine('daemon restarted with unfinished run registry')
            for registry in pending:
                try:
                    record = json.loads(registry.read_text())
                    self.cleanup(record)
                except Exception:
                    pass
            self.quarantine('daemon restarted with unfinished run registry')
        units = command(['systemctl', 'list-units', '--all', '--plain', '--no-legend', 'iac-job-*.service'])
        if units.strip() or list(Path('/run/netns').glob('iac-job-*')):
            self.quarantine('orphan job unit or network namespace')

    def fenced(self):
        return any((self.base/name).exists() for name in
                   ['quarantine.json', 'maintenance.json', 'agent-update-incomplete', 'agent-update-pending'])

    def resume_agents(self):
        if self.fenced() or list(self.base.glob('run-*.json')) or list(self.base.glob('job-*')):
            REMOTING_READY.unlink(missing_ok=True)
            return
        # Reconcile has proved there are no units/namespaces before this path.
        REMOTING_READY.write_text('reconciled\n');REMOTING_READY.chmod(0o600)
        for user in sorted(IDENTITIES):
            command(['systemctl', 'start', '--no-block', f'jenkins-agent@{user}.service'])

    def reserve(self, envelope, uid):
        payload, profile = validate_admission(envelope, self.config, uid)
        nonce = token(payload['nonce'])
        with self.guard:
            if self.active is not None or self.fenced():
                raise Refused('peer is busy or fenced')
            if (self.base/f'used-{nonce}.json').exists():
                raise Refused('admission nonce has already been consumed')
            record = {'nonce': nonce, 'unit': f'iac-job-{nonce}.service',
                      'directory': str(self.base/f'job-{nonce}'), 'uid': uid,
                      'profile': profile['name'], 'scope': sorted(payload['scope']),
                      'sha': payload['sha'], 'credential_versions': payload['credential_versions']}
            atomic_json(self.base/f'used-{nonce}.json',
                        {'nonce': nonce, 'build': payload['build'], 'sha': payload['sha'], 'uid': uid})
            self.persist(record)
            self.active = record
            self.cancelled.clear()
        return record

    def refresh_lease(self, payload, directory):
        envelope = self.controller('lease', {'nonce': payload['nonce']})
        current = verify(envelope, self.config['keys'], 'job-lease')
        if any(current[key] != payload[key] for key in
               ['nonce', 'sha', 'scope', 'credential_versions', 'job', 'build', 'uid', 'profile', 'bundle_sha256']):
            raise Refused('run lease source/scope/credentials changed')
        self.publish_control(directory, 'lease.json', envelope)

    def start_network(self, record, profile):
        namespace = record['unit'].removesuffix('.service')
        record['netns'] = namespace
        self.persist(record)
        command(['ip', 'netns', 'add', namespace])
        # Fixed root-managed uplink helper owns routing/NAT. The job cannot supply it.
        # The helper accepts only namespace and fixed profile ID, never arbitrary rules.
        helper = private_file(self.config['network_helper'])
        command([str(helper), 'create', namespace, profile['name']])
        rules = network_rules(profile['peers'])
        subprocess.run(['ip', 'netns', 'exec', namespace, 'nft', '-f', '-'],
                       input=rules, text=True, check=True, capture_output=True, timeout=30)
        return f'/run/netns/{namespace}'

    def persist(self, record):
        atomic_json(self.base/f"run-{record['nonce']}.json", record)

    def controller(self,operation,data,stream=None):
        endpoint=self.config['controller']
        if endpoint['url']!='https://192.168.1.107:9444':raise Refused('unexpected controller service')
        context=ssl.create_default_context(cafile=endpoint['ca'])
        context.load_cert_chain(endpoint['certificate'],endpoint['private_key'])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=context))
        request=urllib.request.Request(endpoint['url']+'/'+operation,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with opener.open(request,timeout=30) as response:
            if stream is not None:
                with open(stream,'xb') as output:shutil.copyfileobj(response,output,length=1024*1024)
                return None
            return json.load(response)

    def publish_control(self,directory,name,value):
        path=directory/'control'/name
        atomic_json(path,value)
        path.chmod(0o444)

    def prepare_plan_ca(self,directory,profile):
        if profile['name']!='plan':return
        content=private_file('/etc/jenkins-agent/control/broker-ca.pem').read_text()
        ssl.create_default_context(cadata=content)
        target=directory/'control/broker-ca.pem'
        target.write_text(content);target.chmod(0o444)

    def bind_secrets(self,record,stage):
        import hashlib
        secrets=self.controller('secrets',{'nonce':record['nonce'],'stage':stage})
        target=Path(record['directory'])/'secrets'
        target.mkdir(mode=0o755,exist_ok=True)
        for name,secret in secrets.items():
            if not __import__('re').fullmatch('[A-Za-z0-9_.-]{1,100}',name):raise Refused('invalid fixed binding name')
            if record['credential_versions'].get(name)!=secret['version']:raise Refused('credential binding version changed')
            content=base64.b64decode(secret['value'],validate=True)
            path=target/name
            if path.exists():raise Refused('secret binding would overwrite an existing file')
            path.write_bytes(content);path.chmod(0o400);os.chown(path,record['uid'],-1)
            record.setdefault('bindings',{})[name]=hashlib.sha256(content).hexdigest()
        self.persist(record)

    def prepare_proc_probe(self,record,profile):
        user=profile['user']
        home=Path('/var/lib/jenkins-agent')/user
        information=home.lstat()
        if not stat.S_ISDIR(information.st_mode) or information.st_uid!=record['uid'] or stat.S_IMODE(information.st_mode)!=0o700:
            raise Refused('remoting home is not private')
        pid=int(command(['systemctl','show','jenkins-agent@'+user+'.service','--value','-p','MainPID']))
        if pid<=0:raise Refused('remoting process is absent')
        record.update(unix_user=user,remoting_pid=pid,remoting_canary=str(home/('.proc-boundary-'+record['nonce'])))
        self.persist(record)
        descriptor=os.open(record['remoting_canary'],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'w') as output:
            os.fchown(output.fileno(),record['uid'],-1)
            output.write('synthetic-remoting-boundary:'+record['nonce'])

    def verify_proc_probe(self,record,profile):
        nonce=token(record['nonce'])
        pid=int(command(['systemctl','show',record['unit'],'--value','-p','MainPID']))
        if pid<=0:raise Refused('job process is absent')
        if os.readlink('/proc/'+str(pid)+'/ns/user')==os.readlink('/proc/self/ns/user'):
            raise Refused('job user namespace is not isolated')
        def live_canaries():
            expected_pids=[(record['unit'],pid),('jenkins-agent@'+profile['user']+'.service',record['remoting_pid'])]
            for unit,expected in expected_pids:
                if int(command(['systemctl','show',unit,'--value','-p','MainPID']))!=expected:raise Refused('process changed during isolation probe')
                os.kill(expected,0)
            for path,content in [(Path(record['remoting_canary']),'synthetic-remoting-boundary:'+nonce),
                                 (Path(record['directory'])/'report'/('proc-boundary-'+nonce),'synthetic-job-boundary:'+nonce)]:
                if read_job_bytes(path,record['uid'],len(content))!=content.encode():
                    raise Refused('process-root canary identity changed')
        live_canaries()
        probe=private_file(Path(__file__).with_name('isolation-probe.py'))
        command(['runuser','-u',profile['user'],'--','setpriv','--no-new-privs','/usr/bin/python3',str(probe),'peer',str(pid),nonce])
        live_canaries()

    def release_initial_secrets(self,record,profile):
        try:self.verify_proc_probe(record,profile)
        except Exception as error:
            self.quarantine('same-identity process-root isolation could not be proved')
            raise Refused('process-root isolation failed before secret binding') from error
        if profile.get('initial_secret_stage'):self.bind_secrets(record,profile['initial_secret_stage'])
        self.publish_control(Path(record['directory']),'secrets-ready.json',{'ready':True})

    def approval(self,nonce,uid,stage,manifest_digest):
        with self.approval_guard:
            return self.approval_locked(nonce,uid,stage,manifest_digest)

    def approval_locked(self,nonce,uid,stage,manifest_digest):
        if stage not in {'terraform','ansible','apps-publish','apps-google'} or not isinstance(manifest_digest,str) or __import__('re').fullmatch('[0-9a-f]{64}',manifest_digest) is None:raise Refused('invalid approval stage or digest')
        if not self.active or self.active['nonce']!=nonce or self.active['uid']!=uid:raise Refused('not the active run owner')
        existing=Path(self.active['directory'])/'control'/(stage+'-approval.json')
        if existing.exists():
            approved=verify(json.loads(existing.read_text()),self.config['keys'],'job-approval')
            if approved['digest']!=manifest_digest:raise Refused('approval digest changed')
            return {'status':'approved'}
        envelope=self.controller('approval',{'nonce':nonce,'stage':stage,'digest':manifest_digest})
        payload=verify(envelope,self.config['keys'],'job-approval')
        if payload['nonce']!=nonce or payload['stage']!=stage or payload['digest']!=manifest_digest or payload['sha']!=self.active['sha']:
            raise Refused('approval is not bound to this run manifest')
        if stage in {'ansible','apps-publish','apps-google'}:self.bind_secrets(self.active,stage)
        self.publish_control(Path(self.active['directory']),stage+'-approval.json',envelope)
        return {'status':'approved'}

    def status(self,nonce,uid):
        nonce=token(nonce)
        receipt=json.loads((self.base/f'used-{nonce}.json').read_text())
        if receipt['uid']!=uid:raise Refused('run belongs to another identity')
        complete=self.base/f'result-{nonce}.json'
        if complete.exists():return json.loads(complete.read_text())
        if self.active and self.active['nonce']==nonce:
            report=Path(self.active['directory'])/'report/status.json'
            event=read_job_report(report,uid)
            if event is not None:
                phase=event['phase']
                if phase.endswith('-approval') and (Path(self.active['directory'])/'control'/(phase+'.json')).exists():return {'phase':'executing-approved-stage'}
                return event
        return {'phase':'starting'}

    def execute(self, envelope, uid, reserved=False):
        payload, profile = validate_admission(envelope, self.config, uid)
        with open(self.base/'global.lock', 'a+b') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise Refused('another identity holds the global execution lock') from error
            if self.fenced():
                raise Refused('peer is quarantined or under maintenance')
            if shutil.disk_usage(self.base).free < 2 * 1024**3:
                raise Refused('less than 2 GiB free disk space')
            record = self.active if reserved else self.reserve(envelope, uid)
            if not record or record['nonce'] != payload['nonce'] or record['uid'] != uid:
                raise Refused('startup reservation differs from admission')
            nonce = record['nonce']
            directory = Path(record['directory'])
            result = {'status': 'failed'}
            try:
                directory.mkdir(mode=0o711)
                (directory/'control').mkdir(mode=0o755)
                self.publish_control(directory,'admission.json',envelope)
                self.prepare_plan_ca(directory,profile)
                for child in ['home', 'tmp', 'workspace','report']:
                    (directory/child).mkdir(mode=0o700)
                    os.chown(directory/child, uid, pwd.getpwnam(profile['user']).pw_gid)
                archive=directory/'source.tar'
                self.controller('bundle',{'nonce':nonce},stream=archive)
                if sha_file(archive)!=payload['bundle_sha256']:raise Refused('signed source bundle digest mismatch')
                from importlib.machinery import SourceFileLoader
                toolchain=SourceFileLoader('runner_toolchain',str(Path(__file__).with_name('toolchain.py'))).load_module()
                with tarfile.open(archive) as source:
                    toolchain.check_archive(source)
                    source.extractall(directory/'workspace')
                for root,dirs,files in os.walk(directory/'workspace'):
                    os.chown(root,uid,pwd.getpwnam(profile['user']).pw_gid)
                    for name in files:os.chown(Path(root)/name,uid,pwd.getpwnam(profile['user']).pw_gid)
                archive.unlink()
                self.prepare_proc_probe(record,profile)
                namespace = self.start_network(record, profile)
                unix_path='/run/jenkins-control-canary-'+nonce+'.sock'
                unix_canary=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
                unix_canary.bind(unix_path);os.chmod(unix_path,0o666);unix_canary.listen(1)
                loopback_canary=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                loopback_canary.bind(('127.0.0.1',0));loopback_canary.listen(1)
                others=sorted(IDENTITIES-{profile['user']})
                pids=[int(command(['systemctl','show','jenkins-agent@'+name+'.service','--value','-p','MainPID'])) for name in others]
                self.publish_control(directory,'isolation.json',{'host_namespaces':{kind:os.readlink('/proc/self/ns/'+kind) for kind in ['net','ipc','mnt','user']},
                    'nonce':nonce,'unix_user':profile['user'],'remoting_pid':record['remoting_pid'],'remoting_canary':record['remoting_canary'],
                    'other_identities':others,'other_identity_pids':[pid for pid in pids if pid>0],
                    'unix_canary':unix_path,'loopback_port':loopback_canary.getsockname()[1],'profile':profile['name']})
                (directory/'hosts').write_text('127.0.0.1 localhost\n'+''.join(peer['ip']+' '+name+'\n' for name,peer in profile.get('hosts',{}).items()))
                (directory/'resolv.conf').write_text('nameserver 127.0.0.53\noptions timeout:1 attempts:1\n')
                if profile['executable']!='/opt/jenkins-agent/control/job-entry.py':raise Refused('profile must use mandatory fixed job entry')
                executable = private_file(profile['executable'])
                properties = {
                    'User': profile['user'], 'Group': profile['user'], 'Type': 'exec',
                    'RemainAfterExit': 'yes', 'Delegate': 'no', 'KillMode': 'control-group',
                    'TimeoutStopSec': '20', 'SendSIGKILL': 'yes', 'PrivateTmp': 'yes',
                    'PrivateIPC': 'yes', 'PrivateDevices': 'yes', 'ProtectProc': 'invisible', 'PrivateUsers':'yes',
                    'ProtectSystem': 'strict', 'ProtectHome': 'yes', 'NoNewPrivileges': 'yes',
                    'ProtectControlGroups': 'yes', 'CapabilityBoundingSet':'', 'AmbientCapabilities':'',
                    'RestrictNamespaces':'yes', 'RestrictRealtime':'yes', 'LockPersonality':'yes', 'ProtectKernelTunables': 'yes',
                    'ProtectKernelModules': 'yes', 'RestrictSUIDSGID': 'yes', 'MemoryMax': '640M',
                    'MemorySwapMax': '0', 'TasksMax': '128', 'UMask': '0077',
                    'NetworkNamespacePath': namespace, 'RuntimeMaxSec': str(profile['timeout']),
                    'BindPaths': f'{directory}:/job',
                    'BindReadOnlyPaths':f'{directory}/hosts:/etc/hosts {directory}/resolv.conf:/etc/resolv.conf', 'WorkingDirectory': '/job/workspace',
                    'ReadWritePaths': '/job', 'InaccessiblePaths':
                    '-/run/docker.sock -/var/run/docker.sock -/run/dbus -/run/jenkins-job-runner.sock '
                    '-/etc/jenkins-agent -/var/lib/jenkins-agent -/var/lib/jenkins-agent-control '+unix_path,
                    'Environment': 'HOME=/job/home TMPDIR=/job/tmp PATH=/opt/jenkins-toolchain/bin:/usr/bin:/bin',
                }
                argv = ['systemd-run', '--unit', record['unit'], '--no-block']
                for key, value in properties.items():
                    argv.extend(['--property', f'{key}={value}'])
                # No checkout-controlled command is ever passed to root systemd-run.
                argv.extend([str(executable), payload['sha'], str(payload['build']), nonce])
                self.refresh_lease(payload, directory)
                command(argv)
                started = time.monotonic()
                last_lease=0
                initial_bound=False
                notion_bound=False
                while True:
                    if self.cancelled.wait(1) or time.monotonic()-started > profile['timeout']:
                        raise Refused('job cancelled, disconnected or timed out')
                    if time.monotonic()-last_lease>15:
                        self.refresh_lease(payload, directory)
                        last_lease=time.monotonic()
                    event=read_job_report(directory/'report/status.json', uid)
                    if not initial_bound and event is not None and event['phase']=='isolation-verified':
                        self.release_initial_secrets(record,profile)
                        initial_bound=True
                    if event is not None and event['phase']=='notion-sync' and not notion_bound:
                        try:
                            self.bind_secrets(record,'notion')
                            self.publish_control(directory,'notion-ready.json',{'ready':True})
                        except (OSError,TimeoutError):
                            self.publish_control(directory,'notion-ready.json',{'ready':False})
                        notion_bound=True
                    for name,expected in record.get('bindings',{}).items():
                        if sha_file(directory/'secrets'/name)!=expected:raise Refused('bound secret file was modified')
                    status = command(['systemctl', 'show', record['unit'],
                                      '-p', 'SubState', '-p', 'ExecMainStatus', '-p', 'Result'])
                    fields = dict(line.split('=', 1) for line in status.splitlines())
                    if fields.get('SubState') in {'exited', 'failed', 'dead'}:
                        result = {'status': 'completed', 'exit_code': int(fields['ExecMainStatus'])}
                        report=directory/'report/status.json'
                        event=read_job_report(report,uid)
                        if event is not None:result['summary']=event.get('summary',{})
                        if profile['name']=='plan' and result['exit_code']==0:
                            finalized=self.controller('finalize',{'nonce':nonce})
                            final=verify(finalized,self.config['keys'],'plan-result')
                            result['prediction']=finalized
                            if final['status']=='stale':result['status']='failed'
                        if result['exit_code']==77:self.quarantine('job isolation probe failed before secret binding')
                        if fields.get('Result') in {'oom-kill','resources'}:self.quarantine('job exceeded its memory/resource budget')
                        if fields.get('Result') != 'success':
                            result['status'] = 'failed'
                        break
                    if shutil.disk_usage(self.base).free < 2*1024**3:
                        raise Refused('job crossed the disk reserve')
            finally:
                try:
                    self.cleanup(record)
                    if 'unix_canary' in locals():unix_canary.close()
                    if 'loopback_canary' in locals():loopback_canary.close()
                    (self.base/f'run-{nonce}.json').unlink()
                except Exception as error:
                    self.quarantine('cleanup could not prove absence of processes and secrets')
                    raise Refused('cleanup failed; executor quarantined') from error
                finally:
                    self.active = None
            now=int(time.time())
            evidence={'purpose':'job-run-evidence','nonce':nonce,'issued_at':now,'expires_at':now+1800,
                      'job':payload['job'],'build':payload['build'],'source_sha':payload['sha'],
                      'node':profile['user'],'uid':uid,'scope':sorted(payload['scope']),
                      'runner_sha256':self.code_sha256,'profile_sha256':payload['profile_sha256'],'credential_versions':payload['credential_versions'],
                      'isolation_verified':initial_bound,'exit_code':result.get('exit_code'),
                      'cleanup':{'unit_stopped':True,'cgroup_empty':True,'netns_removed':True,'bindings_removed':True,'workspace_removed':True}}
            result['evidence']=sign(evidence,self.config['evidence_key_id'],self.config['evidence_signing_key'])
            atomic_json(self.base/f'result-{nonce}.json',result)
            try:self.controller('complete', {'nonce': nonce})
            except Exception:pass  # Retention expiry reclaims a lost notification.
            return result

    def cleanup(self, record):
        if not isinstance(record,dict) or not {'unit','nonce','directory','profile'}<=set(record):raise Refused('invalid persistent run registry')
        nonce=token(record['nonce'])
        if record['unit']!='iac-job-'+nonce+'.service' or record['directory']!=str(self.base/('job-'+nonce)) or record.get('netns','iac-job-'+nonce)!='iac-job-'+nonce:
            raise Refused('persistent registry escaped its fixed run paths')
        unit = record['unit']
        # Query cgroup before stopping; do not collect the transient unit early.
        load = command(['systemctl', 'show', unit, '--value', '-p', 'LoadState'])
        if load == 'not-found':
            group = ''
        elif load == 'loaded':
            group = command(['systemctl', 'show', unit, '--value', '-p', 'ControlGroup'])
            command(['systemctl', 'stop', unit])
        else:
            raise Refused('cannot prove job unit state')
        if group:
            root = Path('/sys/fs/cgroup')/group.lstrip('/')
            if root.exists() and any(path.read_text().strip() for path in root.rglob('cgroup.procs')):
                raise Refused('cgroup still contains processes')
        namespace = record.get('netns')
        if namespace and Path('/run/netns', namespace).exists():
            if command(['ip', 'netns', 'pids', namespace]).strip():
                raise Refused('network namespace still contains processes')
            command([self.config['network_helper'], 'remove', namespace, record['profile']])
            command(['ip', 'netns', 'delete', namespace])
        directory = Path(record['directory'])
        if directory.parent != self.base or directory.name != 'job-'+record['nonce'] or directory.is_symlink():
            raise Refused('invalid cleanup path')
        if directory.exists():
            # Never traverse an unexpected bind mount or another task's data.
            mounts = Path('/proc/self/mountinfo').read_text().splitlines()
            if any(line.split()[4] == str(directory) or line.split()[4].startswith(str(directory)+'/')
                   for line in mounts):
                raise Refused('run directory still has mounts')
            shutil.rmtree(directory)
        if directory.exists():
            raise Refused('run directory survived cleanup')
        if record.get('remoting_canary'):
            user=record.get('unix_user')
            expected=Path('/var/lib/jenkins-agent')/str(user)/('.proc-boundary-'+nonce)
            if user not in IDENTITIES or record['remoting_canary']!=str(expected):raise Refused('unexpected remoting canary cleanup path')
            content='synthetic-remoting-boundary:'+nonce
            data=read_job_bytes(expected,record['uid'],len(content))
            if data is not None:
                if data!=content.encode():raise Refused('remoting canary cleanup identity is uncertain')
                expected.unlink(missing_ok=True)
        canary=Path('/run/jenkins-control-canary-'+record['nonce']+'.sock')
        if canary.exists():
            if canary.lstat().st_uid!=0 or not stat.S_ISSOCK(canary.lstat().st_mode):raise Refused('unexpected canary path ownership/type')
            canary.unlink()
        subprocess.run(['systemctl', 'reset-failed', unit], check=False, capture_output=True)

    def release(self):
        if self.active:raise Refused('active run prevents quarantine release')
        if (self.base/'agent-update-incomplete').exists():raise Refused('agent configuration is incomplete')
        for registry in self.base.glob('run-*.json'):
            self.cleanup(json.loads(registry.read_text()));registry.unlink()
        if self.active or list(self.base.glob('run-*.json')) or list(self.base.glob('job-*')):
            raise Refused('unresolved run registry or workspace')
        units = command(['systemctl', 'list-units', '--all', '--plain', '--no-legend', 'iac-job-*.service'])
        if units.strip() or list(Path('/run/netns').glob('iac-job-*')):
            raise Refused('job units or network namespaces remain')
        (self.base/'quarantine.json').unlink(missing_ok=True)


def serve(runner):
    with open(runner.base/'global.lock','a+b') as startup_lock:
        fcntl.flock(startup_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        REMOTING_READY.unlink(missing_ok=True)
        runner.reconcile()
        runner.resume_agents()
    if int(os.environ.get('LISTEN_FDS', '0')) != 1 or int(os.environ.get('LISTEN_PID', '0')) != os.getpid():
        raise Refused('socket activation required')
    listener=socket.socket(fileno=3)
    listener.settimeout(1)
    if os.environ.get('NOTIFY_SOCKET'):
        address=os.environ['NOTIFY_SOCKET']
        if address.startswith('@'):address='\x00'+address[1:]
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as ready:
            ready.connect(address);ready.sendall(b'READY=1')
    def execute(envelope,uid):
        nonce=envelope['payload']['nonce']
        try:runner.execute(envelope,uid,reserved=True)
        except Exception:
            # Even a failure between reservation and unit creation must reconcile.
            if runner.active and runner.active['nonce']==nonce:
                try:
                    runner.cleanup(runner.active)
                    (runner.base/f'run-{nonce}.json').unlink(missing_ok=True)
                except Exception:runner.quarantine('startup cleanup could not be proved')
                finally:runner.active=None
            try:runner.controller('complete',{'nonce':nonce})
            except Exception:pass  # Controller retention deadline also reclaims lost runs.
            atomic_json(runner.base/f'result-{nonce}.json',{'status':'failed','phase':'failed'})

    def dispatch(request,uid):
        operation=request['operation']
        if runner.stopping.is_set() and operation not in {'status','abort'}:raise Refused('runner is stopping')
        if operation=='start':
            record=runner.reserve(request['admission'],uid)
            threading.Thread(target=execute,args=(request['admission'],uid),daemon=True).start()
            return {'nonce':record['nonce'],'status':'starting'}
        if operation=='status':return runner.status(request['nonce'],uid)
        if operation=='approval':return runner.approval(request['nonce'],uid,request['stage'],request['digest'])
        if operation=='abort':
            if not runner.active or runner.active['uid']!=uid or runner.active['nonce']!=request['nonce']:raise Refused('not the active run owner')
            runner.cancelled.set();return {'status':'aborting'}
        raise Refused('unknown fixed operation')

    allowed_uids={pwd.getpwnam(user).pw_uid for user in IDENTITIES}
    selector=selectors.DefaultSelector()
    listener.setblocking(False);selector.register(listener,selectors.EVENT_READ)
    pending={}
    def close(connection):
        selector.unregister(connection);pending.pop(connection,None);connection.close()
    # A fixed worker pool serves controller RPCs. Status/abort remain on the
    # nonblocking selector and cannot wait behind slow local senders or RPCs.
    with ThreadPoolExecutor(max_workers=4) as workers:
        rpcs={}
        while not runner.stopping.is_set() or runner.active is not None:
            for connection,future in list(rpcs.items()):
                if future.done():
                    try:answer=future.result()
                    except Exception:answer={'status':'refused'}
                    try:connection.sendall(json.dumps(answer).encode()+b'\n')
                    except OSError:pass
                    connection.close();del rpcs[connection]
            now=time.monotonic()
            for connection,item in list(pending.items()):
                if now>item['deadline']:close(connection)
            for key,_events in selector.select(.1):
                if key.fileobj is listener:
                    try:connection,_=listener.accept()
                    except (BlockingIOError,ConnectionAbortedError):continue
                    _,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    if uid not in allowed_uids:
                        connection.close();continue
                    same=[sock for sock,item in pending.items() if item['uid']==uid]
                    if len(same)>=4:close(min(same,key=lambda sock:pending[sock]['deadline']))
                    connection.setblocking(False)
                    pending[connection]={'uid':uid,'data':b'','deadline':now+1}
                    selector.register(connection,selectors.EVENT_READ)
                    continue
                connection=key.fileobj;item=pending.get(connection)
                if item is None:continue
                try:
                    chunk=connection.recv(65537-len(item['data']))
                    if not chunk:close(connection);continue
                    item['data']+=chunk
                    if len(item['data'])>65536:raise Refused('request too large')
                    if b'\n' not in item['data']:continue
                    if not item['data'].endswith(b'\n'):raise Refused('request framing refused')
                    request=json.loads(item['data'])
                    if request['operation']=='approval':
                        if not runner.active or runner.active['uid']!=item['uid'] or runner.active['nonce']!=request.get('nonce'):
                            raise Refused('not the active run owner')
                        if len(rpcs)>=4:raise Refused('controller RPC capacity reached')
                        selector.unregister(connection);pending.pop(connection)
                        rpcs[connection]=workers.submit(dispatch,request,item['uid'])
                        continue
                    answer=dispatch(request,item['uid'])
                except Exception:answer={'status':'refused'}
                try:connection.sendall(json.dumps(answer).encode()+b'\n')
                except OSError:pass
                close(connection)
        for connection in list(pending):close(connection)
        for connection in rpcs:connection.close()
    selector.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['serve', 'verify-and-release'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise Refused('root service or administrator required')
    runner = Runner()
    def terminate(*_args):
        runner.stopping.set();runner.cancelled.set()
    signal.signal(signal.SIGTERM,terminate)
    if args.mode == 'serve':
        serve(runner)
    else:
        with open(BASE/'global.lock', 'a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            runner.release()


if __name__ == '__main__':
    try:
        main()
    except (Refused, KeyError, OSError, subprocess.SubprocessError):
        sys.exit('peer operation refused; inspect root-owned diagnostics')
