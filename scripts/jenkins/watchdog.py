#!/usr/bin/python3
"""Root CT110 recovery monitor, independent of all remoting JVMs."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import xml.etree.ElementTree as ET
import zipfile
from control import Refused, atomic_json, canonical, command, digest, private_file, sha_file, sign, token, verify, secret_file
from importlib.machinery import SourceFileLoader
maintenance=SourceFileLoader('maintenance',str(Path(__file__).with_name('controller-maintenance.py'))).load_module()
BASE=Path('/var/lib/jenkins-agent-control')
REMOTING_READY=Path('/run/jenkins-agent-remoting-ready')


def start_remoting():
    if (BASE/'quarantine.json').exists() or (BASE/'agent-update-incomplete').exists():
        raise Refused('persistent runtime fence blocks remoting')
    REMOTING_READY.write_text('authorized-maintenance-reconnect\n');REMOTING_READY.chmod(0o600)
    for identity in ['iac-plan','iac-deploy','iac-apps']:
        command(['systemctl','start','jenkins-agent@'+identity+'.service'])


def request(policy,payload,stream=None):
    now=int(time.time())
    payload.update({'purpose':'controller-maintenance','target':'CT107/jenkins',
                    'authorization_id':policy['authorization_id'],'issued_at':now,'expires_at':now+60})
    envelope=sign(payload,policy['key_id'],policy['signing_key'])
    argv=['ssh','-T','-oBatchMode=yes','-oStrictHostKeyChecking=yes','-oClearAllForwardings=yes',
          '-oConnectTimeout=10','-oUserKnownHostsFile='+policy['known_hosts'],'-i',policy['ssh_key'],
          'jenkins-recovery@192.168.1.107','jenkins-recovery']
    process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    process.stdin.write(canonical(envelope)+b'\n');process.stdin.close()
    try:
        header=process.stdout.readline(1024*1024)
        status=verify(json.loads(header),policy['keys'],'controller-status')
        if status['nonce']!=payload['nonce']:raise Refused('recovery response nonce mismatch')
        if stream is not None:
            with open(stream,'xb') as output:
                os.chmod(stream,0o600)
                shutil.copyfileobj(process.stdout,output,length=1024*1024)
        if process.wait(timeout=600):raise Refused('remote helper failed')
        return status['result']
    except Exception:
        process.kill();process.wait()
        raise


def drill(policy,backup,manifest,nonce):
    if sha_file(backup)!=manifest['backup_sha256']:raise Refused('drill archive hash mismatch')
    war=private_file(policy['war'])
    with zipfile.ZipFile(war) as archive:
        metadata=archive.read('META-INF/MANIFEST.MF').decode()
    expected_core=manifest['tuple']['core']
    if 'Jenkins-Version: '+expected_core not in metadata:raise Refused('drill core does not match backup')
    java=subprocess.run([policy['java'],'-version'],capture_output=True,text=True,check=True).stderr.splitlines()[0]
    if java!=manifest['tuple']['java']:raise Refused('drill Java does not match backup')
    available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))
    stat=os.statvfs(BASE)
    with tarfile.open(backup) as archive:
        maintenance.inspect_tar(archive)
        members=archive.getmembers()
        expanded=sum(member.size for member in members)
    maintenance.check_resources(available,stat.f_bavail*stat.f_frsize,stat.f_favail,0,expanded,policy['missing_runtime_bytes'],max(10000,len(members)+1024))
    directory=BASE/('drill-'+nonce)
    directory.mkdir(mode=0o700)
    with tarfile.open(backup) as archive:
        archive.extractall(directory)
    home=directory/'home'
    plugins={path.name:sha_file(path) for pattern in ['*.jpi','*.hpi'] for path in sorted((home/'plugins').glob(pattern))}
    if digest(canonical(plugins))!=manifest['tuple']['plugins']:raise Refused('drill plugins do not match backup')
    overlay=[]
    for path in home.rglob('*.xml'):
        if not path.is_file():continue
        tree=ET.parse(path)  # Validate original configuration before suppression.
        if path.name=='config.xml' and 'jobs' in path.relative_to(home).parts:
            root=tree.getroot()
            for triggers in root.findall('triggers'):root.remove(triggers)
            disabled=root.find('disabled')
            if disabled is None:disabled=ET.SubElement(root,'disabled')
            disabled.text='true'
            tree.write(path)
            overlay.append(str(path.relative_to(home)))
    config=ET.parse(home/'config.xml')
    for name,text in [('numExecutors','0'),('slaveAgentPort','-1')]:
        element=config.getroot().find(name)
        if element is None:element=ET.SubElement(config.getroot(),name)
        element.text=text
    config.write(home/'config.xml')
    if (home/'init.groovy').exists():
        (home/'init.groovy').unlink();overlay.append('init.groovy')
    for name in ['nodes','init.groovy.d']:
        if (home/name).exists():shutil.rmtree(home/name)
        (home/name).mkdir(mode=0o700)
        overlay.append(name)
    # A fixed startup hook supplies an offline completion marker and quiets the copy.
    (home/'init.groovy.d/00-restore-drill.groovy').write_text('jenkins.model.Jenkins.get().setNumExecutors(0)\njenkins.model.Jenkins.get().doQuietDown()\nprintln("RESTORE_DRILL_CONFIGURATION_LOADED")\n')
    uid=int(command(['id','-u','jenkins-drill']));gid=int(command(['id','-g','jenkins-drill']))
    for root,dirs,files in os.walk(directory):
        os.chown(root,uid,gid)
        for name in files:os.chown(Path(root)/name,uid,gid)
    unit='jenkins-restore-drill-'+nonce+'.service'
    properties={'User':'jenkins-drill','Group':'jenkins-drill','PrivateNetwork':'yes','PrivateIPC':'yes',
                'PrivateTmp':'yes','PrivateDevices':'yes','ProtectSystem':'strict','ProtectHome':'yes',
                'ProtectControlGroups':'yes','ProtectProc':'invisible','NoNewPrivileges':'yes','Delegate':'no',
                'KillMode':'control-group','MemoryHigh':'1280M','MemoryMax':'1536M','MemorySwapMax':'0',
                'RuntimeMaxSec':'600','UMask':'0077','BindPaths':str(directory)+':/drill',
                'ReadWritePaths':'/drill','InaccessiblePaths':'-/etc/jenkins-agent -/var/lib/jenkins-agent -/var/lib/jenkins-agent-control -/run/docker.sock -/var/run/docker.sock -/run/dbus',
                'Environment':'JENKINS_HOME=/drill/home'}
    argv=['systemd-run','--unit',unit,'--no-block']
    for key,value in properties.items():argv+=['-p',key+'='+value]
    argv += [policy['java'],'-Xmx768m','-Djenkins.install.runSetupWizard=false',
             '-Dhudson.model.UpdateCenter.never=true','-jar',str(private_file(policy['war'])),
             '--httpListenAddress=127.0.0.1','--httpPort=18080','--webroot=/drill/war']
    records=[{'name':name,'exit_code':0} for name in ['archive_verify','config_parse']]
    try:
        command(argv)
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            pid=int(command(['systemctl','show',unit,'--value','-p','MainPID']))
            if pid<=0:raise Refused('restore drill JVM exited')
            interfaces=json.loads(command(['nsenter','-t',str(pid),'-n','ip','-j','link']))
            routes=json.loads(command(['nsenter','-t',str(pid),'-n','ip','-j','route','show','table','all']))
            if any(link['ifname']!='lo' for link in interfaces) or any(route.get('dev')!='lo' for route in routes):
                raise Refused('restore drill namespace has an external interface/route')
            logs=command(['journalctl','-u',unit,'--no-pager','-o','cat'])
            if 'Jenkins is fully up and running' in logs and 'RESTORE_DRILL_CONFIGURATION_LOADED' in logs:
                command(['nsenter','-t',str(pid),'-n','curl','--fail','--silent','--output','/dev/null','http://127.0.0.1:18080/login'])
                records += [{'name':name,'exit_code':0} for name in ['namespace_isolation','plugin_load','health']]
                return records,{'suppression_overlay':overlay,'archive_sha256':manifest['backup_sha256'],'isolated_interfaces':['lo']}
            time.sleep(2)
        raise Refused('restore drill exceeded ten minutes')
    finally:
        command(['systemctl','stop',unit])
        group=command(['systemctl','show',unit,'--value','-p','ControlGroup'])
        if group and (Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs').exists() and (Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs').read_text().strip():
            atomic_json(BASE/'quarantine.json',{'reason':'restore drill cgroup remained populated'})
            raise Refused('restore drill cleanup failed')
        # Retain candidate and execution evidence. No other task data is removed.


class Watchdog:
    def __init__(self,policy):self.policy=policy
    def arm(self,envelope):
        payload=verify(envelope,self.policy['keys'],'watchdog-maintenance')
        if payload['target']!='CT107/jenkins' or payload['authorization_id']!=self.policy['authorization_id']:
            raise Refused('maintenance authorization mismatch')
        evidence=maintenance.validate_evidence(json.loads(private_file(payload['evidence']).read_text()),self.policy,require_armed=False)
        if payload['backup_sha256']!=evidence['backup_sha256'] or payload['old_tuple']!=evidence['tuple']:
            raise Refused('armed tuple/backup differs from restored evidence')
        if (BASE/'maintenance.json').exists():raise Refused('maintenance is already armed')
        payload['phase']='armed'
        atomic_json(BASE/'maintenance.json',payload)
        attestation={**payload,'purpose':'controller-watchdog-armed'}
        atomic_json(BASE/'watchdog-armed.json',sign(attestation,self.policy['key_id'],self.policy['signing_key']))
    def tick(self):
        path=BASE/'maintenance.json'
        if not path.exists():return
        record=json.loads(path.read_text())
        now=int(time.time())
        if record['phase'] in {'committing','recovered'}:
            expected=record['old_tuple'] if record['phase']=='recovered' else record['new_tuple']
            start_remoting()
            nodes=request(self.policy,{'mode':'agent-status','nonce':record['nonce']+'_nodes_'+str(now)})
            if set(nodes)!={'iac-plan','iac-deploy','iac-apps'} or any(node['offline'] for node in nodes.values()):
                atomic_json(BASE/'maintenance-diagnostic.json',{'status':'waiting-for-agent-reconnection','nonce':record['nonce'],'time':now})
                return
            result=request(self.policy,{'mode':'resume','nonce':record['nonce']+'_resume_'+str(now),'backup_id':record['backup_id'],'backup_sha256':record['backup_sha256'],'expected_tuple':expected})
            atomic_json(BASE/'maintenance-result.json',{'status':'restored' if record['phase']=='recovered' else 'completed','result':result,'time':now,'nonce':record['nonce']})
            path.unlink();return
        if record['phase']=='baseline':
            if now>=record['expires_at']:
                status=request(self.policy,{'mode':'status','nonce':record['nonce']+'_baseline_status'})
                if status['ActiveState']=='inactive':request(self.policy,{'mode':'start','nonce':record['nonce']+'_baseline_start'})
                atomic_json(BASE/'maintenance-result.json',{'status':'baseline-timeout','nonce':record['nonce']})
                path.unlink()
            return
        if record['phase']=='agent-update':return
        if record['phase']=='armed':
            if now>=record['expires_at']:
                status=request(self.policy,{'mode':'status','nonce':record['nonce']+'_expired_status'})
                if status['ActiveState']=='inactive':request(self.policy,{'mode':'start','nonce':record['nonce']+'_expired_start'})
                atomic_json(BASE/'maintenance-result.json',{'status':'expired-before-start','nonce':record['nonce']})
                path.unlink()
            return
        if record['phase']=='write-resumed-unexpectedly':return
        if record['phase']!='started':raise Refused('unknown maintenance phase')
        # Only a signed SSH status confirming service failure permits rollback.
        try:status=request(self.policy,{'mode':'status','nonce':token(record['nonce']+'_'+str(now))})
        except Exception:
            atomic_json(BASE/'maintenance-diagnostic.json',{'status':'ssh-unreachable','time':now,'nonce':record['nonce']})
            return
        if status.get('ActiveState')=='active' and status.get('quieting_down') is not True:
            record['phase']='write-resumed-unexpectedly';atomic_json(path,record)
            atomic_json(BASE/'maintenance-diagnostic.json',{'status':'production-write-fence-unconfirmed; capture a fresh backup before any further change','nonce':record['nonce']})
            return
        failed=status.get('ActiveState')=='failed' or (status.get('ActiveState')=='active' and status.get('healthy') is False)
        timeout=now>=record['expires_at']
        if failed or timeout:
            if status.get('ActiveState') not in {'failed','inactive'} and status.get('healthy') is not False and not (timeout and status.get('quieting_down') is True):
                atomic_json(BASE/'maintenance-diagnostic.json',{'status':'timeout-service-not-failed','time':now})
                return
            if status.get('ActiveState')=='active':request(self.policy,{'mode':'fail-stop','nonce':record['nonce']+'_failure_stop','backup_id':record['backup_id'],'backup_sha256':record['backup_sha256'],'old_tuple':record['old_tuple']})
            result=request(self.policy,{'mode':'restore','nonce':record['nonce'],'backup_id':record['backup_id'],
                           'backup_sha256':record['backup_sha256'],'old_tuple':record['old_tuple']})
            record['phase']='recovered';atomic_json(path,record)
            self.tick()


def capture_and_drill(policy,envelope):
    authorization=verify(envelope,policy['keys'],'maintenance-bootstrap')
    if authorization['target']!='CT107/jenkins' or authorization['authorization_id']!=policy['authorization_id']:
        raise Refused('baseline bootstrap authorization mismatch')
    nonce=token(authorization['nonce'])
    with open(BASE/'global.lock','a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (BASE/'quarantine.json').exists():raise Refused('peer quarantine blocks restore drill')
        if (BASE/'maintenance.json').exists():raise Refused('another maintenance authorization is active')
        previous=json.loads((BASE/'baseline-ready.json').read_text()) if (BASE/'baseline-ready.json').exists() else None
        verified_backup=Path(previous['backup']) if previous else None
        if any(path!=verified_backup for path in BASE.glob('candidate-*.tar')):raise Refused('unverified local candidate requires signed discard')
        atomic_json(BASE/'maintenance.json',{'phase':'baseline','nonce':nonce,'expires_at':int(time.time())+600})
        REMOTING_READY.unlink(missing_ok=True)
        for identity in ['iac-plan','iac-deploy','iac-apps']:command(['systemctl','stop','jenkins-agent@'+identity+'.service'])
        before=request(policy,{'mode':'status','nonce':nonce+'_before'})
        stopped=False
        armed=False
        recovery_pending=False
        try:
            request(policy,{'mode':'stop','nonce':nonce+'_stop'});stopped=True
            manifest=request(policy,{'mode':'backup','nonce':nonce})
            available=int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))
            stat=os.statvfs(BASE)
            maintenance.check_resources(available,stat.f_bavail*stat.f_frsize,stat.f_favail,manifest['archive_bytes'],manifest['expanded_bytes'],policy['missing_runtime_bytes'],max(10000,manifest['inodes']+1024))
            backup=BASE/('candidate-'+nonce+'.tar')
            request(policy,{'mode':'export','nonce':nonce+'_export','backup_id':nonce,'backup_sha256':manifest['backup_sha256']},stream=backup)
            records,overlay=drill(policy,backup,manifest,nonce)
            after=request(policy,{'mode':'status','nonce':nonce+'_after'})
            if after['ActiveState']!='inactive' or after['tuple']!=manifest['tuple']:raise Refused('production wrote after backup or baseline timeout restarted it')
            if after['gitea']!=before['gitea']:raise Refused('Gitea service identity changed during Jenkins drill')
            evidence_dir=BASE/('evidence-'+nonce);evidence_dir.mkdir(mode=0o700)
            atomic_json(evidence_dir/'overlay.json',overlay)
            atomic_json(evidence_dir/'commands.json',records)
            records += [{'name':'stop','exit_code':0},{'name':'gitea_unchanged','exit_code':0}]
            now=int(time.time())
            evidence={'purpose':'controller-recovery-evidence','target':'CT107/jenkins','drill_target':'CT110',
                      'authorization_id':policy['authorization_id'],'nonce':nonce,'issued_at':now,'expires_at':now+1800,
                      'backup_sha256':manifest['backup_sha256'],'backup_id':nonce,'tuple':manifest['tuple'],
                      'commands':records,'evidence_files':{name:sha_file(evidence_dir/name) for name in ['overlay.json','commands.json']},
                      'gitea':after['gitea'],'ad9':authorization.get('ad9')}
            signed=sign(evidence,policy['key_id'],policy['signing_key'])
            atomic_json(evidence_dir/'evidence.json',signed)
            request(policy,{'mode':'promote','nonce':nonce+'_promote','backup_id':nonce,'evidence':signed})
            request(policy,{'mode':'prepare','nonce':nonce+'_prepare','backup_id':nonce,'backup_sha256':manifest['backup_sha256'],'old_tuple':manifest['tuple']})
            # The controller stays stopped after successful capture/drill. A subsequent
            # change must arm the watchdog using this exact tuple before any new write.
            atomic_json(BASE/'baseline-ready.json',{'nonce':nonce,'evidence':str(evidence_dir/'evidence.json'),'backup':str(backup)})
            if previous:
                old_nonce=token(previous['nonce'])
                expected=BASE/('candidate-'+old_nonce+'.tar')
                if Path(previous['backup'])!=expected or expected.is_symlink():raise Refused('previous backup path is outside the managed retention set')
                old_evidence=json.loads(private_file(previous['evidence']).read_text())['payload']
                if sha_file(expected)!=old_evidence['backup_sha256']:raise Refused('previous managed backup was modified')
                expected.unlink()
                old_drill=BASE/('drill-'+old_nonce)
                if old_drill.exists():shutil.rmtree(old_drill)
            record={'purpose':'controller-watchdog-armed','phase':'armed','target':'CT107/jenkins',
                    'nonce':nonce,'issued_at':now,'expires_at':now+1800,
                    'authorization_id':policy['authorization_id'],'backup_id':nonce,
                    'backup_sha256':manifest['backup_sha256'],'old_tuple':manifest['tuple'],
                    'new_tuple':authorization['new_tuple'],'evidence':str(evidence_dir/'evidence.json')}
            atomic_json(BASE/'maintenance.json',record)
            atomic_json(BASE/'watchdog-armed.json',sign(record,policy['key_id'],policy['signing_key']))
            armed=True
            return signed
        except Exception:
            try:
                status=request(policy,{'mode':'status','nonce':nonce+'_failed_capture_status'})
                if status['ActiveState'] in {'inactive','failed'}:request(policy,{'mode':'start','nonce':nonce+'_recover'})
            except Exception:
                recovery_pending=True
                atomic_json(BASE/'maintenance-diagnostic.json',{'status':'capture-recovery-unconfirmed','nonce':nonce})
            raise
        finally:
            if not armed and not recovery_pending:(BASE/'maintenance.json').unlink(missing_ok=True)


def update_agents(policy):
    pending=BASE/'agent-update-pending'
    if not pending.exists() or (BASE/'maintenance.json').exists() or (BASE/'quarantine.json').exists() or (BASE/'agent-update-incomplete').exists():return
    with open(BASE/'global.lock','a+b') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        nonce='agent_update_'+str(int(time.time()))
        atomic_json(BASE/'maintenance.json',{'phase':'agent-update','nonce':nonce})
        try:
            previous_connections=request(policy,{'mode':'agent-status','nonce':nonce+'_before'})
            if set(previous_connections)!={'iac-plan','iac-deploy','iac-apps'}:raise Refused('incomplete prior connection map')
            REMOTING_READY.unlink(missing_ok=True)
            for identity in ['iac-plan','iac-deploy','iac-apps']:
                command(['systemctl','stop','jenkins-agent@'+identity+'.service'])
            fcntl.flock(lock,fcntl.LOCK_UN)
            command(['systemctl','daemon-reload'])
            command(['systemctl','restart','jenkins-job-runner.service'])
            fcntl.flock(lock,fcntl.LOCK_EX)
            if (BASE/'quarantine.json').exists() or (BASE/'agent-update-incomplete').exists():raise Refused('restarted runner found incomplete cleanup')
            start_remoting()
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                status=request(policy,{'mode':'agent-status','nonce':nonce+'_'+str(int(time.time()))})
                if set(status)=={'iac-plan','iac-deploy','iac-apps'} and all(value['offline'] is False and type(value['connect_time']) is int and value['connect_time']>previous_connections[name]['connect_time'] for name,value in status.items()):
                    pending.unlink();return
                time.sleep(5)
            raise Refused('agents failed to reconnect after asynchronous update')
        except Exception:
            REMOTING_READY.unlink(missing_ok=True)
            atomic_json(BASE/'quarantine.json',{'reason':'agent maintenance failed','nonce':nonce})
            for identity in ['iac-plan','iac-deploy','iac-apps']:
                subprocess.run(['systemctl','stop','jenkins-agent@'+identity+'.service'],capture_output=True,check=False)
            raise
        finally:(BASE/'maintenance.json').unlink(missing_ok=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['watch','arm','begin','complete','capture-and-drill','discard-candidate','check-policy'])
    parser.add_argument('--policy',default='/etc/jenkins-watchdog/policy.json')
    parser.add_argument('--bundle')
    args=parser.parse_args()
    if os.geteuid()!=0:raise Refused('root-only maintenance entry')
    policy=json.loads(private_file(args.policy).read_text())
    for name in ['signing_key','ssh_key']:secret_file(policy[name])
    for path in policy['keys'].values():private_file(path)
    private_file(policy['known_hosts'])
    command(['openssl','pkey','-in',policy['signing_key'],'-check','-noout'])
    if args.mode=='check-policy':return
    watchdog=Watchdog(policy)
    if args.mode=='watch':
        while True:
            watchdog.tick();update_agents(policy);time.sleep(5)
    else:
        with open(BASE/'control-plane.lock','a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            envelope=json.loads(private_file(args.bundle).read_text())
            if args.mode=='discard-candidate':
                payload=verify(envelope,policy['keys'],'maintenance-discard-candidate')
                candidate=token(payload['backup_id'])
                if (BASE/'maintenance.json').exists():raise Refused('active maintenance prevents candidate retirement')
                previous=json.loads((BASE/'baseline-ready.json').read_text()) if (BASE/'baseline-ready.json').exists() else {}
                if previous.get('nonce')==candidate:raise Refused('the verified backup is retained until a replacement passes')
                unit='jenkins-restore-drill-'+candidate+'.service'
                command(['systemctl','stop',unit])
                group=command(['systemctl','show',unit,'--value','-p','ControlGroup'])
                if group and (Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs').exists() and (Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs').read_text().strip():raise Refused('drill cgroup remains active')
                request(policy,{'mode':'discard-candidate','nonce':payload['nonce'],'backup_id':candidate})
                backup=BASE/('candidate-'+candidate+'.tar')
                if backup.exists():
                    if backup.is_symlink() or sha_file(backup)!=payload['backup_sha256']:raise Refused('candidate cleanup target hash mismatch')
                    backup.unlink()
                directory=BASE/('drill-'+candidate)
                if directory.exists():shutil.rmtree(directory)
            elif args.mode=='capture-and-drill':capture_and_drill(policy,envelope)
            elif args.mode=='arm':watchdog.arm(envelope)
            else:
                payload=verify(envelope,policy['keys'],'watchdog-'+args.mode)
                record=json.loads((BASE/'maintenance.json').read_text())
                if payload['nonce']!=record['nonce'] or payload['backup_sha256']!=record['backup_sha256']:
                    raise Refused('maintenance phase tuple mismatch')
                if args.mode=='begin':
                    if record['phase']!='armed':raise Refused('maintenance already started')
                    record['phase']='started';atomic_json(BASE/'maintenance.json',record)
                else:
                    status=request(policy,{'mode':'status','nonce':record['nonce']+'_complete'})
                    if status.get('ActiveState')!='active' or not status.get('healthy') or status.get('tuple')!=record['new_tuple']:raise Refused('controller is not healthy at the approved new tuple')
                    record['phase']='committing';atomic_json(BASE/'maintenance.json',record)
                    watchdog.tick()


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('independent maintenance refused; inspect root evidence')
