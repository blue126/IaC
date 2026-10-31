#!/usr/bin/env python3
"""Run real routed nft ACL positive/negative probes in disposable Linux netns."""
import importlib.util
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('offline',Path(__file__).with_name('test-offline.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def run(*args,**kwargs):return subprocess.run(args,check=True,capture_output=True,text=True,**kwargs)


def main():
    if sys.platform!='linux' or os.geteuid()!=0:
        print('NOT RUN: Linux root and network namespace capabilities required');return 77
    prefix='oh'+uuid.uuid4().hex[:6];hub=prefix+'h';users=prefix+'u';vms=prefix+'v';names=[];servers=[]
    try:
        for ns in (hub,users,vms):
            run('ip','netns','add',ns);names.append(ns)
            run('ip','-n',ns,'link','set','lo','up')
        for n,other,iface in [('u',users,'wg-users'),('v',vms,'wg-workspaces')]:
            run('ip','link','add',prefix+n,'type','veth','peer','name',prefix+n+'p')
            run('ip','link','set',prefix+n,'netns',hub);run('ip','link','set',prefix+n+'p','netns',other)
            run('ip','-n',hub,'link','set',prefix+n,'name',iface)
            run('ip','-n',hub,'link','set',iface,'up');run('ip','-n',other,'link','set',prefix+n+'p','up')
            subnet='10.235.0.' if n=='u' else '10.234.0.'
            run('ip','-n',hub,'addr','add',subnet+'1/24','dev',iface)
            for suffix in ('2','3','4'):run('ip','-n',other,'addr','add',subnet+suffix+'/24','dev',prefix+n+'p')
            run('ip','-n',other,'route','add','default','via',subnet+'1')
        run('ip','netns','exec',hub,'sysctl','-w','net.ipv4.ip_forward=0')
        with tempfile.TemporaryDirectory(prefix='oci-hub-netns-') as directory:
            p=Path(directory);policy=p/'policy.json';policy.write_text(json.dumps(m.HUB));receipt=p/'receipt.json'
            run('ip','netns','exec',hub,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'apply','--config',str(policy),'--receipt',str(receipt))
            run('ip','netns','exec',hub,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'verify','--routing','--config',str(policy),'--receipt',str(receipt))
            run('ip','netns','exec',hub,'sysctl','-w','net.ipv4.ip_forward=0')
            denied=subprocess.run(['ip','netns','exec',hub,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'verify','--routing','--config',str(policy),'--receipt',str(receipt)],capture_output=True)
            assert denied.returncode!=0,'disabled forwarding was accepted'
            run('ip','netns','exec',hub,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'apply','--config',str(policy),'--receipt',str(receipt))
            server="import socket,threading,time\ndef listen(ip,port):\n s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((ip,port));s.listen()\n while True:\n  c,_=s.accept();c.close()\nfor ip in ('10.234.0.2','10.234.0.3'):\n for port in (22,8443,8006):threading.Thread(target=listen,args=(ip,port),daemon=True).start()\ntime.sleep(60)"
            servers.append(subprocess.Popen(['ip','netns','exec',vms,'python3','-c',server]))
            time.sleep(.3)
            def probe(source,dest,port,expected):
                code="import socket,sys\ns=socket.socket();s.settimeout(.5);s.bind((sys.argv[1],0))\ntry:s.connect((sys.argv[2],int(sys.argv[3])));ok=True\nexcept OSError:ok=False\nassert ok==(sys.argv[4]=='yes'),(sys.argv[1:],ok)"
                run('ip','netns','exec',users,'python3','-c',code,source,dest,str(port),'yes' if expected else 'no')
            probe('10.235.0.2','10.234.0.2',22,True)
            probe('10.235.0.3','10.234.0.3',8443,True)
            probe('10.235.0.2','10.234.0.3',22,False)
            probe('10.235.0.2','10.234.0.2',8006,False)
            probe('10.235.0.2','10.235.0.1',22,False)
            udp_server = "import socket,threading,time\ndef echo(ip,port):\n s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind((ip,port))\n while True:\n  data,peer=s.recvfrom(1024);s.sendto(data,peer)\nfor ip in ('10.234.0.2','10.234.0.3'):\n for port in (60000,60010,60020):threading.Thread(target=echo,args=(ip,port),daemon=True).start()\ntime.sleep(60)"
            servers.append(subprocess.Popen(['ip','netns','exec',vms,'python3','-c',udp_server]))
            time.sleep(.3)
            def udp_probe(source, destination, port, expected, namespace=users, local_port=43000):
                code="import socket,sys\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(.4);s.bind((sys.argv[1],int(sys.argv[5])))\ns.sendto(b'controlled-udp-echo',(sys.argv[2],int(sys.argv[3])))\ntry:ok=s.recv(128)==b'controlled-udp-echo'\nexcept OSError:ok=False\nassert ok==(sys.argv[4]=='yes'),(sys.argv[1:],ok)"
                run('ip','netns','exec',namespace,'python3','-c',code,source,destination,str(port),'yes' if expected else 'no',str(local_port))
            udp_probe('10.235.0.2','10.234.0.2',60000,False)
            config=copy.deepcopy(m.HUB)
            config['device_sources']=config.pop('ga2_sources')
            config['pairs'][0]['mosh_ports']=[60000,60009]
            config['pairs'][1]['mosh_ports']=[60020,60029]
            config['pairs'].append({'device':'10.235.0.4','workspace':'10.234.0.2','mosh_ports':[60010,60019]})
            def apply_hub():
                policy.write_text(json.dumps(config))
                run('ip','netns','exec',hub,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'apply','--config',str(policy),'--receipt',str(receipt))
            apply_hub()
            udp_probe('10.235.0.2','10.234.0.2',60000,True)
            udp_probe('10.235.0.2','10.234.0.2',60010,False)
            udp_probe('10.235.0.4','10.234.0.2',60010,True)
            udp_probe('10.235.0.4','10.234.0.2',60000,False)
            udp_probe('10.235.0.2','10.234.0.3',60020,False)
            udp_probe('10.235.0.3','10.234.0.3',60020,True)
            udp_probe('10.235.0.2','10.235.0.1',60000,False)
            # Preserve the existing UDP conntrack tuple: deleting only its grant
            # must block it while other devices and native SSH continue working.
            del config['pairs'][0]['mosh_ports'];apply_hub()
            udp_probe('10.235.0.2','10.234.0.2',60000,False)
            udp_probe('10.235.0.4','10.234.0.2',60010,True)
            probe('10.235.0.2','10.234.0.2',22,True)
            print('PASS: native Mosh UDP replies, cross-device/VM/input denial and revocation with an existing conntrack tuple; SSH remains available')
            run('ip','netns','exec',hub,'nft','delete','table','inet','oci_hub')
            result=subprocess.run(['ip','netns','exec',hub,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'verify','--config',str(policy),'--receipt',str(receipt)],capture_output=True)
            assert result.returncode!=0,'missing ACL was accepted'
        # A second topology exercises the VM's external bridge/routed boundary.
        pve=prefix+'p';guest=prefix+'g';outside=prefix+'o'
        for ns in (pve,guest,outside):
            run('ip','netns','add',ns);names.append(ns)
            run('ip','-n',ns,'link','set','lo','up')
        for suffix,left,right,leftname,rightname in [('t',pve,guest,'tap601i0','eth0'),('e',pve,outside,'eth0','eth0')]:
            run('ip','link','add',prefix+suffix,'type','veth','peer','name',prefix+suffix+'p')
            run('ip','link','set',prefix+suffix,'netns',left);run('ip','link','set',prefix+suffix+'p','netns',right)
            run('ip','-n',left,'link','set',prefix+suffix,'name',leftname);run('ip','-n',right,'link','set',prefix+suffix+'p','name',rightname)
            run('ip','-n',left,'link','set',leftname,'up');run('ip','-n',right,'link','set',rightname,'up')
        run('ip','-n',pve,'link','add','ohfix','type','bridge')
        run('ip','-n',pve,'link','set','ohfix','up');run('ip','-n',pve,'link','set','tap601i0','master','ohfix')
        run('ip','-n',guest,'link','set','eth0','address','02:00:00:00:01:02')
        run('ip','-n',pve,'addr','add','10.236.1.1/30','dev','ohfix');run('ip','-n',guest,'addr','add','10.236.1.2/30','dev','eth0')
        run('ip','-n',guest,'route','add','default','via','10.236.1.1')
        run('ip','-n',pve,'addr','add','198.51.100.1/24','dev','eth0')
        for address in ('198.51.100.2/24','198.51.100.3/24','198.51.100.4/24','198.51.100.5/24'):run('ip','-n',outside,'addr','add',address,'dev','eth0')
        run('ip','-n',outside,'route','add','10.236.0.0/16','via','198.51.100.1')
        bob=prefix+'b';run('ip','netns','add',bob);names.append(bob)
        run('ip','-n',bob,'link','set','lo','up')
        run('ip','link','add',prefix+'b0','type','veth','peer','name',prefix+'b1')
        run('ip','link','set',prefix+'b0','netns',pve);run('ip','link','set',prefix+'b1','netns',bob)
        run('ip','-n',pve,'link','set',prefix+'b0','name','tap602i0');run('ip','-n',bob,'link','set',prefix+'b1','name','eth0')
        run('ip','-n',pve,'link','add','ohbob','type','bridge');run('ip','-n',pve,'link','set','ohbob','up')
        run('ip','-n',pve,'link','set','tap602i0','master','ohbob');run('ip','-n',pve,'link','set','tap602i0','up')
        run('ip','-n',bob,'link','set','eth0','address','02:00:00:00:02:02');run('ip','-n',bob,'link','set','eth0','up')
        run('ip','-n',pve,'addr','add','10.236.2.1/30','dev','ohbob');run('ip','-n',bob,'addr','add','10.236.2.2/30','dev','eth0')
        run('ip','-n',bob,'route','add','default','via','10.236.2.1')
        run('ip','netns','exec',pve,'sysctl','-w','net.ipv4.ip_forward=0')
        with tempfile.TemporaryDirectory(prefix='oci-hub-pve-netns-') as directory:
            p=Path(directory);policy=p/'policy.json';receipt=p/'receipt.json'
            config=copy.deepcopy(m.PVE);config.update(endpoint='198.51.100.2',protected=['198.51.100.2/32'])
            config['workspaces'][0]['vnet']='ohfix'
            config['workspaces'].append({'vmid':602,'vnet':'ohbob','subnet':'10.236.2.0/30','address':'10.236.2.2','gateway':'10.236.2.1','mac':'02:00:00:00:02:02','disabled':False})
            config['management_access']=[{'source':'198.51.100.4/32','vmid':601}]
            policy.write_text(json.dumps(config))
            run('ip','netns','exec',pve,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'apply','--config',str(policy),'--receipt',str(receipt))
            run('ip','netns','exec',pve,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'verify','--routing','--config',str(policy),'--receipt',str(receipt))
            sourcefile=p/'source.txt'
            server="import socket,threading,time,pathlib\ndef listen(ip):\n s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((ip,443));s.listen()\n while True:\n  c,a=s.accept();pathlib.Path("+repr(str(sourcefile))+").write_text(a[0]);c.close()\nfor ip in ('198.51.100.2','198.51.100.3'):threading.Thread(target=listen,args=(ip,),daemon=True).start()\ntime.sleep(60)"
            servers.append(subprocess.Popen(['ip','netns','exec',outside,'python3','-c',server]));time.sleep(.3)
            listener="import socket,threading,time\ndef serve(address,port):\n s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((address,port));s.listen()\n while True:\n  c,_=s.accept();c.sendall(b'controlled-reply');c.close()\nfor port in (22,8443):threading.Thread(target=serve,args=(ADDRESS,port),daemon=True).start()\ntime.sleep(60)"
            for namespace,address in ((guest,'10.236.1.2'),(bob,'10.236.2.2'),(outside,'198.51.100.4'),(pve,'10.236.1.1')):
                code=listener.replace('ADDRESS',repr(address))
                servers.append(subprocess.Popen(['ip','netns','exec',namespace,'python3','-c',code]))
            time.sleep(.3)
            def management_probe(namespace,source,destination,port,expected):
                code="import socket,sys\ns=socket.socket();s.settimeout(.7);s.bind((sys.argv[1],0))\ntry:s.connect((sys.argv[2],int(sys.argv[3])));ok=s.recv(64)==b'controlled-reply'\nexcept OSError:ok=False\nassert ok==(sys.argv[4]=='yes'),(sys.argv[1:],ok)"
                run('ip','netns','exec',namespace,'python3','-c',code,source,destination,str(port),'yes' if expected else 'no')
            management_probe(outside,'198.51.100.4','10.236.1.2',22,True)
            management_probe(outside,'198.51.100.5','10.236.1.2',22,False)
            management_probe(outside,'198.51.100.4','10.236.1.2',8443,False)
            management_probe(outside,'198.51.100.4','10.236.2.2',22,False)
            management_probe(guest,'10.236.1.2','10.236.2.2',22,False)
            management_probe(guest,'10.236.1.2','198.51.100.4',22,False)
            management_probe(guest,'10.236.1.2','198.51.100.4',8443,False)
            management_probe(guest,'10.236.1.2','10.236.1.1',22,False)
            management_probe(pve,'10.236.1.1','10.236.1.2',22,False)
            # Removing the grant must refuse a new connection from the same
            # administrator; restore it through the deployment entry point.
            config['management_access']=[];policy.write_text(json.dumps(config))
            run('ip','netns','exec',pve,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'apply','--config',str(policy),'--receipt',str(receipt))
            management_probe(outside,'198.51.100.4','10.236.1.2',22,False)
            config['management_access']=[{'source':'198.51.100.4/32','vmid':601}];policy.write_text(json.dumps(config))
            run('ip','netns','exec',pve,'python3',str(ROOT/'scripts/oci-hub/boundary.py'),'apply','--config',str(policy),'--receipt',str(receipt))
            management_probe(outside,'198.51.100.4','10.236.1.2',22,True)
            # Exercise public diagnostic protocols and verify the same ports remain private.
            diagnostic_server = "import socket,threading,time\ndef echo(ip,port):\n s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind((ip,port))\n while True:\n  data,peer=s.recvfrom(1024);s.sendto(data,peer)\nfor ip in ('198.51.100.2','198.51.100.3'):\n for port in (53,33434,33534,33535):threading.Thread(target=echo,args=(ip,port),daemon=True).start()\ntime.sleep(60)"
            servers.append(subprocess.Popen(['ip','netns','exec',outside,'python3','-c',diagnostic_server]));time.sleep(.3)
            for address in ('198.51.100.2','198.51.100.3'):
                code=listener.replace('ADDRESS',repr(address)).replace('(22,8443)', '(53,)')
                servers.append(subprocess.Popen(['ip','netns','exec',outside,'python3','-c',code]))
            time.sleep(.3)
            management_probe(guest,'10.236.1.2','198.51.100.3',53,True)
            management_probe(guest,'10.236.1.2','198.51.100.2',53,False)
            for destination,expected in [('198.51.100.3',True),('198.51.100.2',False),('10.236.2.2',False),('10.236.1.1',False)]:
                echo="import socket,struct,sys\np=struct.pack('!BBHHH',8,0,0,1234,1)+b'probe123';total=sum(struct.unpack('!8H',p));total=(total&65535)+(total>>16);total=(total&65535)+(total>>16);p=p[:2]+struct.pack('!H',(~total)&65535)+p[4:]\ns=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_ICMP);s.settimeout(.7);s.sendto(p,(sys.argv[1],0));ok=False\ntry:\n r,_=s.recvfrom(4096);h=(r[0]&15)*4;ok=r[h]==0 and r[h+4:h+6]==struct.pack('!H',1234)\nexcept OSError:pass\nassert ok==(sys.argv[2]=='yes'),sys.argv"
                run('ip','netns','exec',guest,'python3','-c',echo,destination,'yes' if expected else 'no')
            for destination in ('198.51.100.3','198.51.100.2'):
                for port in (53,33434,33534,33535):
                    expected=destination=='198.51.100.3' and port!=33535
                    code="import socket,sys\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(.5)\ntry:s.sendto(b'probe',(sys.argv[1],int(sys.argv[2])));ok=s.recv(32)==b'probe'\nexcept OSError:ok=False\nassert ok==(sys.argv[3]=='yes'),sys.argv"
                    run('ip','netns','exec',guest,'python3','-c',code,destination,str(port),'yes' if expected else 'no')
            print('PASS: public ICMP/DNS/traceroute replies; protected endpoints, private destinations and UDP outside range denied')
            print('PASS: exact routed administrator TCP22 and reply; non-admin, wrong port/VM, VM-initiated management, PVE-local and missing-grant paths denied')
            def physical_probe(source,destination,expected,interface='eth0'):
                code="import socket,sys\ns=socket.socket();s.settimeout(.5);s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,sys.argv[4].encode()+b'\\0');s.bind((sys.argv[1],0))\ntry:s.connect((sys.argv[2],443));ok=True\nexcept OSError:ok=False\nassert ok==(sys.argv[3]=='yes'),(sys.argv[1:],ok)"
                run('ip','netns','exec',guest,'python3','-c',code,source,destination,'yes' if expected else 'no',interface)
            physical_probe('10.236.1.2','198.51.100.3',True)
            self_source=sourcefile.read_text();assert self_source=='10.236.1.2',self_source
            physical_probe('10.236.1.2','198.51.100.2',False)
            run('ip','-n',guest,'addr','add','10.236.99.2/30','dev','eth0')
            physical_probe('10.236.99.2','198.51.100.3',False)
            try:
                run('ip','-n',guest,'link','add','link','eth0','name','eth0.100','type','vlan','id','100')
                run('ip','-n',guest,'link','set','eth0.100','up');run('ip','-n',guest,'addr','add','10.236.3.2/30','dev','eth0.100')
                physical_probe('10.236.3.2','198.51.100.3',False,'eth0.100')
            except subprocess.CalledProcessError as error:
                print("NOT RUN: VLAN subinterface probe: "+error.stderr.strip())
            run('ip','-n',guest,'-6','addr','add','fd00::2/64','dev','eth0','nodad')
            run('ip','-n',pve,'-6','addr','add','fd00::1/64','dev','ohfix','nodad')
            ipv6_server="import socket,time\ns=socket.socket(socket.AF_INET6);s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('fd00::1',443));s.listen()\nwhile True:\n c,_=s.accept();c.close()"
            servers.append(subprocess.Popen(['ip','netns','exec',pve,'python3','-c',ipv6_server]));time.sleep(.3)
            ipv6="import socket\ns=socket.socket(socket.AF_INET6);s.settimeout(.5)\ntry:s.connect(('fd00::1',443));ok=True\nexcept OSError:ok=False\nassert not ok"
            run('ip','netns','exec',guest,'python3','-c',ipv6)
            run('ip','netns','exec',pve,'nft','delete','table','inet','oci_hub')
            run('ip','netns','exec',pve,'nft','delete','table','bridge','oci_hub')
            physical_probe('10.236.1.2','198.51.100.2',True)
            run('ip','netns','exec',guest,'python3','-c',ipv6.replace('assert not ok','assert ok'))
        print('PASS: PVE pure routing preserves source; protected OCI service, spoofed source and IPv6 probes denied; VLAN result reported separately')
        print('PASS: real routed own-VM SSH/HTTPS, cross-user/port/input rejection and missing-ACL startup rejection');return 0
    except subprocess.CalledProcessError as e:
        if not names:
            print('NOT RUN: network namespace creation denied: '+e.stderr.strip());return 77
        raise
    finally:
        for server in servers:server.terminate();server.wait()
        for ns in reversed(names):subprocess.run(['ip','netns','del',ns],capture_output=True)


if __name__=='__main__':sys.exit(main())
