#!/usr/bin/env python3
"""Exercise fixed upstream Portal, the real API and kernel in a disposable netns."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import urllib.error
import urllib.parse
import secrets
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[2]
DIGESTS={'aarch64':'73b524f7427c1975d1b0744a4c1ad82418ad07589df48f850d7a66935d9952e7',
         'x86_64':'f7399f7d7bd84169509c0fa5b3826687a01c284f0d3a5ad0877bdd6f43f14e51'}


def run(*args,**kwargs):
    return subprocess.run(args,check=True,capture_output=True,text=True,**kwargs)


def keypair():
    private=run('wg','genkey').stdout.strip()
    public=run('wg','pubkey',input=private+'\n').stdout.strip()
    return private,public


def inside(binary,source):
    sys.path.insert(0,str(source))
    from executor import Executor,kernel
    from ledger import Ledger
    from portal import Portal
    env={key:os.environ[key] for key in ('PATH','LANG','LC_ALL') if key in os.environ};env['NO_PROXY']='127.0.0.1,localhost';os.environ['NO_PROXY']=env['NO_PROXY']
    process=None;ledger=None
    with tempfile.TemporaryDirectory(prefix='portal-v231-synthetic-') as temporary:
        base=Path(temporary)
        for name,port in (('wg-hk-oci',51822),('wg-oci-home',51823)):
            private,public=keypair();path=base/(name+'.key');path.write_text(private+'\n');path.chmod(0o600)
            run('ip','link','add',name,'type','wireguard')
            run('wg','set',name,'private-key',str(path),'listen-port',str(port))
        foreign={name:run('wg','show',name,'public-key').stdout.strip() for name in ('wg-hk-oci','wg-oci-home')}
        run('ip','link','add','eth0','type','veth','peer','name','eth1')
        run('ip','link','set','eth0','up');run('ip','link','set','eth1','up')
        run('iptables','-A','INPUT','-i','lo','-j','ACCEPT')
        run('iptables','-A','INPUT','-p','tcp','--dport','22','-j','ACCEPT')
        run('iptables','-A','INPUT','-j','REJECT')
        legacy_input=run('iptables','-S','INPUT').stdout.splitlines()
        username='admin@wgportal.local';token=secrets.token_hex(32)
        config={'core':{'admin_user':username,'admin_password':secrets.token_hex(32),'admin_api_token':token,'import_existing':False,'restore_state':True,
                        'create_default_peer':False,'create_default_peer_on_creation':False,'create_default_peer_on_login':False,
                        'create_default_peer_on_user_creation':False,'create_default_peer_on_interface_creation':False,'self_provisioning_allowed':False},
                'backend':{'ignored_local_interfaces':list(foreign)},
                'advanced':{'use_ip_v6':False,'config_storage_path':'','api_admin_only':True,'log_level':'error'},
                'web':{'listening_address':'127.0.0.1:8888','external_url':'http://127.0.0.1:8888','request_logging':False,'session_secret':secrets.token_hex(32),'csrf_secret':secrets.token_hex(32)},
                'database':{'type':'sqlite','dsn':str(base/'portal.sqlite'),'debug':False},
                'statistics':{'collect_audit_data':False,'listening_address':'127.0.0.1:8787'}}
        config_path=base/'portal.json';config_path.write_text(json.dumps(config));config_path.chmod(0o600)
        env['WG_PORTAL_CONFIG']=str(config_path);env['HOME']=str(base)
        log=(base/'portal.log').open('w')
        try:
            process=subprocess.Popen([str(binary)],cwd=base,env=env,stdout=log,stderr=log)
            portal=Portal('http://127.0.0.1:8888',username,token)
            original_open=portal.opener.open
            def diagnostic_open(request,*args,**kwargs):
                try:return original_open(request,*args,**kwargs)
                except urllib.error.HTTPError as error:
                    if error.code!=404:
                        raw=error.read(4096).decode('utf-8',errors='replace')
                        labels=sorted(set(re.findall(r"(?:User|Peer|Interface)\.[A-Za-z]+",raw)))
                        tags=sorted(set(re.findall(r"'(required_if|oneof|len|cidr|email|min|max)'",raw)))
                        path=urllib.parse.urlsplit(request.full_url).path
                        if '/by-id/' in path:path=path.split('/by-id/')[0]+'/by-id/<id>'
                        print(json.dumps({'synthetic_api_failure':{'http_status':error.code,'method':request.method,'path':path,'validation_fields':labels,'validation_tags':tags}}),flush=True)
                    raise
            portal.opener.open=diagnostic_open
            for _ in range(100):
                if process.poll() is not None:raise RuntimeError('Synthetic Portal process exited: '+(base/'portal.log').read_text()[-1600:])
                try:portal.request('GET','/interface/all');break
                except Exception:time.sleep(.1)
            else:raise RuntimeError('Synthetic Portal API readiness timed out')
            policy={'profile':'oci-hub','kind':'hub','generation':1,'uplink':'eth0','interfaces':{'wg-users':'10.235.0.1/24','wg-workspaces':'10.234.0.1/24'},
                    'device_sources':['192.0.2.2/32'],'workspace_sources':['198.51.100.2/32'],'pairs':[]}
            policy_path=base/'boundary.json';policy_path.write_text(json.dumps(policy));receipt=base/'boundary-receipt.json'
            boundary=str(ROOT/'scripts/oci-hub/boundary.py')
            run(sys.executable,boundary,'apply','--config',str(policy_path),'--receipt',str(receipt))
            def ready():run(sys.executable,boundary,'verify','--routing','--config',str(policy_path),'--receipt',str(receipt))
            ledger=Ledger(base/'ledger.sqlite',initialize=True)
            ex=Executor(ledger,portal,kernel=kernel,readiness=ready,interface_policy=policy['interfaces'])
            objects=[]
            for name,port in (('wg-users',51824),('wg-workspaces',51825)):
                private,public=keypair()
                objects.append({'kind':'interface','object':dict(Identifier=name,Mode='server',PrivateKey=private,PublicKey=public,Addresses=[policy['interfaces'][name]],ListenPort=port,Mtu=1280,RoutingTable='off',SaveConfig=False,Disabled=False)})
            request=dict(profile='oci-hub',action='bootstrap_interfaces',action_id='synthetic-bootstrap-v1',generation=1,portal_objects=objects)
            ex.execute(request);assert ex.execute(request)['replayed']
            current_input=run('iptables','-S','INPUT').stdout.splitlines()
            assert [line for line in current_input if 'oci-hub-ingress-' not in line]==legacy_input
            assert sum('oci-hub-ingress-' in line for line in current_input)==2
            for name,public in foreign.items():assert run('wg','show',name,'public-key').stdout.strip()==public
            assert set(run('wg','show','interfaces').stdout.split())==set(foreign)|{'wg-users','wg-workspaces'}
            print('PASS: official Portal v2.3.1 real API/bootstrap, exact kernel interfaces/routes and foreign-interface preservation')
            user='oci-hub:user:synthetic';workspace='oci-hub:vm:synthetic';device='oci-hub:device:synthetic'
            rows=[dict(id=user,kind='user',user_id=user,workspace=workspace,details={})]
            portal_objects=[dict(kind='user',object=dict(Identifier=user,IsAdmin=False,Disabled=False,Locked=True,Password='aA1!'+secrets.token_urlsafe(32)))]
            peers={}
            for kind,identity,interface,address in (('workspace',workspace,'wg-workspaces','10.234.0.2/32'),('device',device,'wg-users','10.235.0.2/32')):
                private,public=keypair();peers[kind]=public
                rows.append(dict(id=identity,kind=kind,user_id=user,workspace=workspace,details=dict(user=user,interface=interface,address=address,public_key=public)))
                portal_objects.append(dict(kind='peer',object=dict(Identifier=public,PublicKey=public,PrivateKey=private,InterfaceIdentifier=interface,UserIdentifier=user,Addresses=[address],Mode='client',Disabled=True,DisabledReason='admin_disabled')))
            registration=dict(profile='oci-hub',action='register',action_id='synthetic-registration-v1',generation=2,identities=rows,portal_objects=portal_objects)
            result=ex.execute(registration);assert set(result['created_identities'])=={user,workspace,device}
            assert not kernel('wg-users') and not kernel('wg-workspaces')
            for index,identity in enumerate((user,workspace,device)):
                ex.execute(dict(profile='oci-hub',action='reason',action_id='synthetic-enable-'+str(index),generation=2,identity=identity,reason='admin_disabled',blocked=False))
            assert peers['device'] in kernel('wg-users') and peers['workspace'] in kernel('wg-workspaces')
            ex.execute(dict(profile='oci-hub',action='reason',action_id='synthetic-revoke-device',generation=2,identity=device,reason='revoked',blocked=True))
            assert peers['device'] not in kernel('wg-users') and peers['workspace'] in kernel('wg-workspaces')
            print('PASS: real Portal user/peer registration, disabled-first state, kernel enable and per-device revocation')
        finally:
            if ledger:ledger.db.close()
            if process:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            log.close()
            if sys.exc_info()[0] is None:
                for name,public in foreign.items():assert run('wg','show',name,'public-key').stdout.strip()==public
                print('PASS: foreign WireGuard interfaces remain intact after Portal shutdown')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--portal-binary',type=Path,required=True);parser.add_argument('--source-dir',type=Path,required=True);parser.add_argument('--inside',action='store_true');args=parser.parse_args()
    if sys.platform!='linux' or os.geteuid()!=0:
        print('NOT RUN: approved Linux root test environment required');return 77
    binary=args.portal_binary.resolve();source=args.source_dir.resolve()
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=DIGESTS.get(platform.machine()):raise ValueError('Unapproved Portal artifact')
    if args.inside:inside(binary,source);return 0
    namespace='olp'+uuid.uuid4().hex[:8]
    run('ip','netns','add',namespace)
    try:
        run('ip','-n',namespace,'link','set','lo','up')
        probe=subprocess.run(['ip','-n',namespace,'link','add','wg-probe','type','wireguard'],capture_output=True,text=True)
        if probe.returncode:
            print('NOT RUN: test kernel has no WireGuard link support: '+probe.stderr.strip());return 77
        run('ip','-n',namespace,'link','delete','wg-probe')
        return subprocess.call(['ip','netns','exec',namespace,sys.executable,str(Path(__file__).resolve()),'--inside','--portal-binary',str(binary),'--source-dir',str(source)])
    finally:subprocess.run(['ip','netns','delete',namespace],capture_output=True)


if __name__=='__main__':sys.exit(main())
