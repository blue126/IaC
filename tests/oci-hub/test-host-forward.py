#!/usr/bin/env python3
"""Verify exact legacy-forward compatibility without changing foreign rules."""
import copy,importlib.util,json,os,unittest,subprocess,sys,tempfile,uuid,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(os.environ.get('IAC_TEST_ROOT',Path(__file__).resolve().parents[2]))
SOURCE=Path(os.environ.get('OCI_HUB_BOUNDARY_PATH',str(ROOT/'scripts/oci-hub/boundary.py')))
s=importlib.util.spec_from_file_location('b',SOURCE);b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
C=dict(profile='oci-hub',kind='hub',generation=1,uplink='eth0',interfaces={'wg-users':'10.235.0.1/24','wg-workspaces':'10.234.0.1/24'},device_sources=['192.0.2.2/32'],workspace_sources=['198.51.100.2/32'],pairs=[dict(device='10.235.0.3',workspace='10.234.0.3',mosh_ports=[60040,60049])])
class Rules(unittest.TestCase):
 def test_exact_mapping_and_only_authorized_ports(self):
  rules=b.host_forward_rules(C);self.assertEqual(len(rules),4)
  for r in rules:self.assertIn('-s',r);self.assertIn('-d',r);self.assertIn('--ctdir',r);self.assertTrue(b.owned_forward(r));self.assertIn('ACCEPT',r)
  self.assertEqual(sum('60040:60049' in r for r in rules),2);self.assertEqual(sum('22,8443' in r for r in rules),2)
  self.assertEqual(b.host_forward_rules({**C,'kind':'pve'}),[])
 def test_preserves_foreign_order_and_revokes_stale_grants(self):
  foreign=[['-j','DOCKER-USER'],['-j','REJECT','--reject-with','icmp-host-prohibited']];expected=b.host_forward_rules(C);actual=copy.deepcopy(foreign+expected)
  def system(*args):
   if args[:3]==('iptables','-w','5'):args=('iptables',)+args[3:]
   if args[:3]==('iptables','-S','FORWARD'):return '\n'.join(' '.join(['-A','FORWARD',*r]) for r in actual)
   if args[:3]==('iptables','-D','FORWARD'):actual.remove(list(args[3:]));return ''
   if args[:3]==('iptables','-I','FORWARD'):actual.insert(int(args[3])-1,list(args[4:]));return ''
   raise AssertionError(args)
  with patch.object(b,'run',side_effect=system):
   with self.assertRaisesRegex(ValueError,'behind'):b.verify_host_forward(C)
   b.sync_host_forward(C);self.assertEqual([r for r in actual if not b.owned_forward(r)],foreign);b.verify_host_forward(C)
   before=copy.deepcopy(actual);b.sync_host_forward(C);self.assertEqual(actual,before)
   b.sync_host_forward({**C,'pairs':[]});self.assertEqual(actual,foreign)

def network():
 token=uuid.uuid4().hex[:6];hub,user,vm=['hf'+token+x for x in ('h','u','v')];created=[];server=None
 def run(*a,stdin=None):return subprocess.run(a,input=stdin,text=True,capture_output=True,check=True).stdout
 try:
  for ns in (hub,user,vm):run('ip','netns','add',ns);created.append(ns);run('ip','-n',ns,'link','set','lo','up')
  for other,hname in [(user,'wg-users'),(vm,'wg-workspaces')]:
   a='ha'+uuid.uuid4().hex[:6];z='za'+uuid.uuid4().hex[:6];run('ip','link','add',a,'type','veth','peer','name',z);run('ip','link','set',a,'netns',hub);run('ip','link','set',z,'netns',other);run('ip','-n',hub,'link','set',a,'name',hname);run('ip','-n',other,'link','set',z,'name','eth0');run('ip','-n',hub,'link','set',hname,'up');run('ip','-n',other,'link','set','eth0','up')
  run('ip','-n',hub,'link','add','eth0','type','veth','peer','name','eth1');run('ip','-n',hub,'link','set','eth0','up')
  for ns,address,dev in [(hub,'10.235.0.1/24','wg-users'),(hub,'10.234.0.1/24','wg-workspaces'),(user,'10.235.0.3/24','eth0'),(user,'10.235.0.4/24','eth0'),(vm,'10.234.0.3/24','eth0'),(vm,'10.234.0.4/24','eth0')]:run('ip','-n',ns,'address','add',address,'dev',dev)
  for ns,gateway in [(user,'10.235.0.1'),(vm,'10.234.0.1')]:run('ip','-n',ns,'route','add','default','via',gateway)
  run('ip','netns','exec',hub,'sysctl','-w','net.ipv4.ip_forward=1')
  run('ip','netns','exec',hub,'iptables','-N','FOREIGN-HUB-TEST');run('ip','netns','exec',hub,'iptables','-A','FORWARD','-j','FOREIGN-HUB-TEST');run('ip','netns','exec',hub,'iptables','-A','FORWARD','-j','REJECT')
  foreign=run('ip','netns','exec',hub,'iptables','-S','FORWARD').splitlines()
  code="import socket,threading,time\ndef tcp(ip):\n s=socket.socket();s.bind((ip,22));s.listen()\n while True:c,a=s.accept();c.close()\ndef udp(p):\n s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('10.234.0.3',p))\n while True:d,a=s.recvfrom(100);s.sendto(d,a)\nfor ip in ['10.234.0.3','10.234.0.4']:threading.Thread(target=tcp,args=(ip,),daemon=True).start()\nfor p in [60049,60050]:threading.Thread(target=udp,args=(p,),daemon=True).start()\ntime.sleep(90)"
  server=subprocess.Popen(['ip','netns','exec',vm,sys.executable,'-c',code]);time.sleep(.2)
  def probe(target,port,udp=False,source='10.235.0.3'):
   code="import socket,sys\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM if sys.argv[3]=='yes' else socket.SOCK_STREAM);s.settimeout(.3);s.bind((sys.argv[4],0))\ntry:\n s.connect((sys.argv[1],int(sys.argv[2])))\n if sys.argv[3]=='yes':s.send(b'x');assert s.recv(10)==b'x'\nexcept OSError:sys.exit(2)"
   return subprocess.run(['ip','netns','exec',user,sys.executable,'-c',code,target,str(port),'yes' if udp else 'no',source],capture_output=True).returncode==0
  run('ip','netns','exec',hub,'nft','-f','-',stdin=b.render(C));assert not probe('10.234.0.3',22)
  with tempfile.TemporaryDirectory(prefix='hub-forward-') as temp:
   path=Path(temp)/'policy.json';path.write_text(json.dumps(C));receipt=Path(temp)/'receipt.json'
   def apply():run('ip','netns','exec',hub,sys.executable,str(SOURCE),'apply','--config',str(path),'--receipt',str(receipt))
   apply();assert probe('10.234.0.3',22);assert probe('10.234.0.3',60049,True);assert not probe('10.234.0.3',60050,True);assert not probe('10.234.0.4',22);assert not probe('10.234.0.3',22,source='10.235.0.4')
   current=run('ip','netns','exec',hub,'iptables','-S','FORWARD').splitlines();assert [r for r in current if 'oci-hub-forward-' not in r]==foreign
   path.write_text(json.dumps({**C,'pairs':[]}));apply();assert not probe('10.234.0.3',22);assert not probe('10.234.0.3',60049,True);assert run('ip','netns','exec',hub,'iptables','-S','FORWARD').splitlines()==foreign
  print('PASS: legacy rejection reproduced; exact TCP/UDP mappings work; wrong source/target/port and revoked mappings deny; foreign rules unchanged')
 finally:
  if server:server.terminate();server.wait()
  for ns in reversed(created):subprocess.run(['ip','netns','del',ns],capture_output=True)
if __name__=='__main__':
 if '--network' in sys.argv:network()
 else:unittest.main()
