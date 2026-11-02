#!/usr/bin/env python3
"""Explicit Linux Sandbox fixture; uses existing sudo/unshare and synthetic canaries only."""
import tempfile,pathlib,os,json,subprocess,shlex,sys,errno
from importlib.machinery import SourceFileLoader
ROOT=pathlib.Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/'scripts/jenkins'
sys.path.insert(0,str(SCRIPTS))
import control
probe=SourceFileLoader('kernel_proc_probe',str(SCRIPTS/'isolation-probe.py')).load_module()
if sys.platform!='linux':raise SystemExit('Run this explicit fixture in the assigned Linux Sandbox.')

def access(path,flags):
 try:
  descriptor=os.open(path,flags|os.O_NONBLOCK|os.O_NOFOLLOW)
 except OSError as error:
  if error.errno in {errno.EPERM,errno.EACCES,errno.ENOENT}:return False
  raise
 else:os.close(descriptor);return True

uid=os.getuid();gid=os.getgid();assert uid>0
results=[]
for private in [False,True]:
 with tempfile.TemporaryDirectory(prefix='jenkins-peer-privateusers-') as tmp:
  base=pathlib.Path(tmp);home=base/'remoting-home';home.mkdir(mode=0o700)
  (home/'canary').write_text('synthetic-remoting-only')
  mask=base/'mask';mask.mkdir(mode=0);view=base/'job-view';view.mkdir(mode=0)
  parent=os.getpid()
  child=r"""import os,pathlib,json,errno,sys
from importlib.machinery import SourceFileLoader
sys.path.insert(0,SCRIPTS)
import control
probe=SourceFileLoader('kernel_child_proc_probe',SCRIPTS+'/isolation-probe.py').load_module()
home=pathlib.Path(HOME);foreign=pathlib.Path('/proc/PARENT/root'+HOME)
def access(path,flags):
 try:fd=os.open(path,flags|os.O_NONBLOCK|os.O_NOFOLLOW)
 except OSError as error:
  if error.errno in {errno.EPERM,errno.EACCES,errno.ENOENT}:return False
  raise
 else:os.close(fd);return True
try:home.joinpath('canary').read_text();direct=True
except PermissionError:direct=False
read=access(foreign/'canary',os.O_RDONLY);write=access(foreign/'canary',os.O_WRONLY)
if write:(foreign/'leftover').write_text('synthetic-residue')
try:probe.proc_access_denied(str(foreign/'canary'));runtime_denied=True
except control.Refused:runtime_denied=False
status=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
canary=pathlib.Path(VIEW)/'canary';canary.write_text('synthetic-job-only');canary.chmod(0o600)
print(json.dumps({'pid':os.getpid(),'uid':os.getuid(),'userns':os.readlink('/proc/self/ns/user'),'uid_map':pathlib.Path('/proc/self/uid_map').read_text(),'job_to_remoting_read':read,'job_to_remoting_write':write,'direct_remoting_visible':direct,'runtime_job_probe_denied':runtime_denied,'no_new_privs':status['NoNewPrivs'].strip(),'effective_caps':int(status['CapEff'].strip(),16)}),flush=True)
sys.stdin.readline()
""".replace('SCRIPTS',repr(str(SCRIPTS))).replace('HOME',repr(str(home))).replace('VIEW',repr(str(view))).replace('PARENT',str(parent))
  commands=['chown 0:0 '+shlex.quote(str(mask))+' '+shlex.quote(str(view)),
   'mount --bind '+shlex.quote(str(mask))+' '+shlex.quote(str(home)),
   'mount -o remount,bind,ro '+shlex.quote(str(home)),
   'mount -t proc -o hidepid=2 proc /proc',
   'mount -t tmpfs -o mode=0700 tmpfs '+shlex.quote(str(view)),
   'chown '+str(uid)+':'+str(gid)+' '+shlex.quote(str(view))]
  enter=['unshare','--user','--map-users','0:0:1','--map-users',f'{uid}:{uid}:1','--map-groups','0:0:1','--map-groups',f'{gid}:{gid}:1'] if private else []
  argv=enter+['setpriv','--reuid='+str(uid),'--regid='+str(gid),'--clear-groups','--no-new-privs','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','python3','-c',child]
  commands.append('exec '+shlex.join(argv))
  process=subprocess.Popen(['sudo','-n','unshare','--mount','--propagation','private','bash','-c',' && '.join(commands)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   first=process.stdout.readline()
   if not first:raise RuntimeError(process.stderr.read())
   observed=json.loads(first)
   target=pathlib.Path('/proc')/str(observed['pid'])/'root'/str(view).lstrip('/')/'canary'
   observed.update(private_users=private,remoting_to_job_read=access(target,os.O_RDONLY),remoting_to_job_write=access(target,os.O_WRONLY),synthetic_file_persisted=(home/'leftover').exists())
   try:probe.proc_access_denied(str(target));observed['runtime_peer_probe_denied']=True
   except control.Refused:observed['runtime_peer_probe_denied']=False
   print(json.dumps(observed),flush=True);results.append(observed)
   process.stdin.write('\n');process.stdin.flush();process.communicate(timeout=10)
   if process.returncode:raise RuntimeError('child process failed')
  finally:
   if process.poll() is None:process.kill();process.communicate()
   subprocess.run(['sudo','-n','chown',str(uid)+':'+str(gid),str(mask),str(view)],check=True)
   mask.chmod(0o700);view.chmod(0o700)
assert all(results[0][name] for name in ['job_to_remoting_read','job_to_remoting_write','remoting_to_job_read','remoting_to_job_write','synthetic_file_persisted'])
assert not results[0]['direct_remoting_visible']
assert all(not results[1][name] for name in ['job_to_remoting_read','job_to_remoting_write','remoting_to_job_read','remoting_to_job_write','synthetic_file_persisted','direct_remoting_visible'])
assert results[0]['uid']==results[1]['uid']==uid
assert results[0]['userns']!=results[1]['userns']

assert not results[0]['runtime_job_probe_denied'] and not results[0]['runtime_peer_probe_denied']
assert results[1]['runtime_job_probe_denied'] and results[1]['runtime_peer_probe_denied']
assert all(item['no_new_privs']=='1' and item['effective_caps']==0 for item in results)
assert {(int(line.split()[0]),int(line.split()[1]),int(line.split()[2])) for line in results[1]['uid_map'].splitlines()}=={(0,0,1),(uid,uid,1)}
print('PASS: root-owned PrivateUsers mapping denies actual same-UID proc-root probes in both directions; unsafe control reproduces residue')
