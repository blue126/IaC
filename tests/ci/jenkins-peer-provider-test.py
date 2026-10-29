#!/usr/bin/env python3
"""Run the real pinned provider against a fake HTTPS PVE and the actual broker."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control
gateway=SourceFileLoader('gateway_provider_test',str(ROOT/'scripts/jenkins/plan-gateway.py')).load_module()
runner=SourceFileLoader('runner_provider_test',str(ROOT/'scripts/jenkins/job-runner.py')).load_module()


class FakePVE(BaseHTTPRequestHandler):
    writes=0
    reads=[]
    heads=0
    def log_message(self,*_args):pass
    def do_GET(self):
        self.reads.append(self.path)
        if self.path=='/api2/json/version':data={'version':'8.3.0','release':'8.3','repoid':'fixture'}
        elif self.path=='/api2/json/nodes/pve0/lxc/110/config':
            data={'hostname':'jenkins-agent','cores':2,'memory':2048,'swap':1024,
                  'rootfs':'vmdata:subvol-110-disk-0,size=16G','net0':'name=eth0,bridge=vmbr1,ip=192.168.1.110/24,gw=192.168.1.1,firewall=1,type=veth',
                  'features':'nesting=1','ostype':'debian','unprivileged':1,'onboot':1,'digest':'0'*40,
                  'unreviewed_token':'SECRET_CANARY_IN_FAKE_UPSTREAM'}
        elif self.path=='/api2/json/cluster/resources?type=vm':data=[{'id':'qemu/210','vmid':210,'node':'pve0','type':'qemu','name':'fixture-vm','status':'running'},{'id':'qemu/999','vmid':999,'node':'pve0','type':'qemu','name':'UNOWNED_VM_CANARY'}]
        elif self.path=='/api2/json/nodes/pve0/qemu/210/config':
            data={'name':'fixture-vm','cores':2,'sockets':1,'memory':2048,'balloon':2048,'bios':'seabios',
                  'ostype':'l26','net0':'virtio=02:00:00:00:02:10,bridge=vmbr1','scsihw':'virtio-scsi-pci',
                  'scsi0':'vmdata:vm-210-disk-0,size=16G','onboot':1,'agent':'enabled=0',
                  'description':'SECRET_CANARY_IN_DESCRIPTION','cipassword':'SECRET_CANARY_IN_PASSWORD'}
        elif self.path=='/api2/json/nodes/pve0/qemu/210/status/current':
            data={'status':'running','qmpstatus':'running','vmid':210,'maxmem':2147483648,'maxdisk':17179869184,'name':'fixture-vm','uptime':100}
        elif self.path=='/api2/json/nodes/pve0/qemu/210/agent/network-get-interfaces':data={'result':[]}
        elif self.path=='/api2/json/nodes/pve0/qemu':data=[{'vmid':210,'name':'fixture-vm','template':0,'status':'running'},{'vmid':999,'name':'UNOWNED_VM_CANARY'}]
        elif self.path=='/api2/json/nodes/pve0/lxc/110/status/current':
            data={'status':'running','vmid':110,'maxmem':2147483648,'maxdisk':17179869184,'maxswap':1073741824,'name':'jenkins-agent','uptime':100}
        elif self.path=='/api2/json/nodes/pve0/storage/local/content':data=[{'volid':'local:iso/fixed-image.img','content':'iso','format':'raw','size':1048576}]
        elif self.path.startswith('/api2/json/storage/'):
            data={'type':'zfspool','pool':'vmdata','content':'rootdir,images','username':'CANARY','password':'CANARY'}
        else:
            self.send_error(404);return
        raw=json.dumps({'data':data}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_HEAD(self):
        if self.path!='/fixed-image.img':self.send_error(404);return
        type(self).heads+=1
        self.send_response(200);self.send_header('Content-Length','1048576');self.send_header('Content-Type','application/octet-stream');self.end_headers()
    def deny(self):
        type(self).writes+=1;self.send_error(403)
    do_POST=do_PUT=do_PATCH=do_DELETE=do_CONNECT=deny


def serve(handler,cert,key):
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--terraform',required=True);parser.add_argument('--mirror',required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='peer-provider-fixture-') as temporary:
        directory=Path(temporary);cert=directory/'cert.pem';key=directory/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
        upstream=serve(FakePVE,cert,key)
        policy=json.loads((ROOT/'ci/proxmox-plan-policy.json').read_text())['broker']
        credential=directory/'fake.token';credential.write_text('fixture@pve!read=synthetic-token')
        policy['upstreams']['primary'].update(origin='https://127.0.0.1:'+str(upstream.server_port),token_file=str(credential),ca_file=str(cert))
        policy['vmids']={'primary':{'pve0':[110,210]}}
        policy['file_ids']=['local:iso/fixed-image.img']
        image='https://127.0.0.1:'+str(upstream.server_port)+'/fixed-image.img'
        probe=next(route for route in policy['routes'] if route.get('adaptation'))
        probe['query']['url']=[image]
        probe['metadata_ca_file']=str(cert)
        policy['download_probes']=[{'alias':'primary','node':'pve0','query':{'url':image,'verify-certificates':'1'}}]
        class FixtureBroker(gateway.Handler):
            def deny(self):
                import traceback
                self.server.refusals.append(traceback.format_exc())
                super().deny()
        broker=serve(FixtureBroker,cert,key);broker.policy=policy;broker.refusals=[]
        job=directory/'job';(job/'control').mkdir(parents=True)
        service=runner.Runner(directory/'runner',{'keys':{},'profiles':{}})
        def fixed_ca(path):
            assert str(path)=='/etc/jenkins-agent/control/broker-ca.pem'
            return cert
        with patch.object(runner,'private_file',side_effect=fixed_ca):
            service.prepare_plan_ca(job,{'name':'plan'})
        copied_ca=job/'control/broker-ca.pem'
        assert copied_ca.read_bytes()==cert.read_bytes() and copied_ca.stat().st_mode&0o777==0o444
        copied_ca.unlink()
        with patch.object(runner,'private_file',side_effect=AssertionError('non-plan must not read the CA')):
            service.prepare_plan_ca(job,{'name':'iac'})
        invalid=directory/'invalid-ca';invalid.write_text('not a certificate')
        with patch.object(runner,'private_file',return_value=invalid):
            try:service.prepare_plan_ca(job,{'name':'plan'})
            except ssl.SSLError:pass
            else:raise AssertionError('invalid broker CA accepted')
        assert not copied_ca.exists()
        with patch.object(runner,'private_file',side_effect=fixed_ca):service.prepare_plan_ca(job,{'name':'plan'})
        environment={key:value for key,value in os.environ.items() if not key.startswith(('TF_','ANSIBLE_','AWS_','OCI_'))}
        environment.update(TF_IN_AUTOMATION='1',CHECKPOINT_DISABLE='1',SSL_CERT_FILE=str(copied_ca),TF_CLI_CONFIG_FILE=str(directory/'terraform.rc'))
        (directory/'terraform.rc').write_text('disable_checkpoint = true\nprovider_installation { filesystem_mirror { path = '+json.dumps(args.mirror)+' } }\n')
        (directory/'.terraform.lock.hcl').write_bytes((ROOT/'terraform/proxmox/.terraform.lock.hcl').read_bytes())
        shutil.copytree(ROOT/'terraform/modules/proxmox-lxc',directory/'modules/proxmox-lxc')
        def configuration(cores):
            return '''terraform {
 required_providers {
  proxmox = { source = "bpg/proxmox", version = "0.70.0" }
  ansible = { source = "ansible/ansible", version = "1.3.0" }
 }
}
provider "proxmox" {
 endpoint = "https://127.0.0.1:'''+str(broker.server_port)+'''"
 api_token = "projection@pve!primary=projection"
 insecure = false
}
module "peer" {
 source = "./modules/proxmox-lxc"
 ostemplate = "local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst"
 lxc_name = "jenkins-agent"
 target_node = "pve0"
 vmid = 110
 cores = '''+str(cores)+'''
 memory = 2048
 swap = 1024
 rootfs_storage = "vmdata"
 rootfs_size = "16G"
 ip_address = "192.168.1.110/24"
 gateway = "192.168.1.1"
 unprivileged = true
 features = ["nesting=1"]
 ostype = "debian"
}
resource "proxmox_virtual_environment_vm" "fixture_vm" {
 node_name = "pve0"
 vm_id = 210
 name = "fixture-vm"
 cpu { cores = '''+str(cores)+''' }
 memory { dedicated = 2048 }
}
data "proxmox_virtual_environment_vms" "fixture_templates" { node_name = "pve0" }
resource "proxmox_virtual_environment_download_file" "fixture" {
 node_name = "pve0"
 datastore_id = "local"
 content_type = "iso"
 url = "'''+image+'''"
}
'''
        (directory/'main.tf').write_text(configuration(2))
        def terraform(*argv,allowed=(0,)):
            result=subprocess.run([args.terraform,*argv],cwd=directory,env=environment,capture_output=True,text=True,timeout=120)
            if result.returncode not in allowed:raise AssertionError('terraform '+str(argv)+' failed:\n'+result.stdout+'\n'+result.stderr+'\nBroker refusals:\n'+'\n'.join(broker.refusals))
            return result
        with patch.object(gateway,'private_file',lambda path:control.private_file(path,owner=os.getuid())):
            terraform('init','-backend=false','-lockfile=readonly','-input=false','-no-color')
            terraform('import','-input=false','-no-color','module.peer.proxmox_virtual_environment_container.lxc','pve0/110')
            terraform('import','-input=false','-no-color','proxmox_virtual_environment_vm.fixture_vm','pve0/210')
            state=json.loads((directory/'terraform.tfstate').read_text())
            attributes=next(resource for resource in state['resources'] if resource['type']=='proxmox_virtual_environment_container')['instances'][0]['attributes']
            attributes.update(unprivileged=True,vm_id=110,start_on_boot=True,features=[{'nesting':True,'fuse':False,'keyctl':False}])
            attributes['operating_system'][0]['template_file_id']='local:vztmpl/debian-12-standard_12.12-1_amd64.tar.zst'
            definition=json.loads((ROOT/'ci/agent-provider-schema.json').read_text())['provider_schemas']['registry.terraform.io/bpg/proxmox']['resource_schemas']['proxmox_virtual_environment_download_file']
            attributes={name:None for name in definition['block']['attributes']}
            attributes.update(content_type='iso',datastore_id='local',file_name='fixed-image.img',id='local:iso/fixed-image.img',node_name='pve0',overwrite=True,overwrite_unmanaged=False,size=1048576,upload_timeout=600,url=image,verify=True)
            state['resources'].append({'mode':'managed','type':'proxmox_virtual_environment_download_file','name':'fixture','provider':'provider["registry.terraform.io/bpg/proxmox"]','instances':[{'schema_version':definition['version'],'attributes':attributes}]})
            (directory/'terraform.tfstate').write_text(json.dumps(state))
            (directory/'main.tf').write_text(configuration(3))
            terraform('plan','-input=false','-lock=false','-no-color','-out=fixture.plan','-detailed-exitcode',allowed=(2,))
            plan=json.loads(terraform('show','-json','fixture.plan').stdout)
            terraform('refresh','-input=false','-no-color')
            refreshed=json.loads((directory/'terraform.tfstate').read_text())
            projection=SourceFileLoader('provider_state_projection',str(ROOT/'scripts/jenkins/proxmox-projection.py')).load_module()
            projected,_=projection.project_state(refreshed,json.loads((ROOT/'ci/agent-provider-schema.json').read_text()))
            assert 'SECRET_CANARY' not in json.dumps(projected)
        change=next(change for change in plan['resource_changes'] if change['address']=='module.peer.proxmox_virtual_environment_container.lxc')
        assert change['change']['before']['cpu'][0]['cores']==2,change
        assert change['change']['after']['cpu'][0]['cores']==3,change
        vm=next(change for change in plan['resource_changes'] if change['address']=='proxmox_virtual_environment_vm.fixture_vm')
        assert vm['change']['before']['cpu'][0]['cores']==2 and vm['change']['after']['cpu'][0]['cores']==3,vm
        assert 'UNOWNED_VM_CANARY' not in json.dumps(plan)
        assert 'SECRET_CANARY' not in json.dumps(plan)
        assert FakePVE.writes==0
        assert any('/lxc/110/config' in path for path in FakePVE.reads)
        # The probe is adapted by HEAD; it must never hit the privileged PVE endpoint.
        assert not any('query-url-metadata' in path for path in FakePVE.reads)
        assert FakePVE.heads>0,'fixed-image HEAD adapter was not exercised'
        print('PASS: Terraform1.14.4 / bpg0.70.0 VM/LXC refresh predicts CPU 2→3; data list filtered; fixed-image HEAD; upstream writes=0')
        broker.shutdown();upstream.shutdown()


if __name__=='__main__':main()
