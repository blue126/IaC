#!/usr/bin/python3
"""Validate synthetic/provisioning TLS and SSH material before writing bindings."""
import base64
import json
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
from control import Refused


def basename(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',value):
        raise Refused('binding filename must be a basename')


def tls_material(ca,certificate,key,identity=None,server_ip=None):
    if any(not isinstance(item,str) or not item.strip() for item in [ca,certificate,key]):raise Refused('complete TLS material is required')
    with tempfile.TemporaryDirectory(prefix='jenkins-material-') as directory:
        directory=Path(directory)
        for name,value in [('ca',ca),('cert',certificate),('key',key)]:
            path=directory/name;path.write_text(value);path.chmod(0o600)
        context=ssl.create_default_context(cadata=ca)
        context.load_cert_chain(directory/'cert',directory/'key')
        arguments=['openssl','verify','-CAfile',str(directory/'ca'),'-purpose','sslserver' if server_ip else 'sslclient']
        if server_ip:arguments+=['-verify_ip',server_ip]
        subprocess.run([*arguments,str(directory/'cert')],check=True,capture_output=True)
        if identity:
            subject=subprocess.check_output(['openssl','x509','-in',str(directory/'cert'),'-noout','-subject','-nameopt','RFC2253'],text=True).strip().removeprefix('subject=')
            common_name=re.search(r'(?:^|,)CN=([^,]+)(?:,|$)',subject)
            if common_name is None or common_name[1]!=identity:raise Refused('TLS certificate identity differs from its transport role')
        subprocess.run(['openssl','x509','-in',str(directory/'cert'),'-checkend','0','-noout'],check=True,capture_output=True)


def ssh_material(public,private):
    if not isinstance(public,str) or '\n' in public or '\r' in public or not re.fullmatch(r'(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)) [A-Za-z0-9+/]+={0,3}(?: [^\r\n]*)?',public):
        raise Refused('exactly one unrestricted public key line is required')
    if any(word in {'ssh-ed25519','ssh-rsa','ecdsa-sha2-nistp256','ecdsa-sha2-nistp384','ecdsa-sha2-nistp521'} for word in public.split()[2:]):raise Refused('multiple public keys are refused')
    if not isinstance(private,str) or not private.strip():raise Refused('SSH private key is required')
    with tempfile.TemporaryDirectory(prefix='jenkins-ssh-') as directory:
        path=Path(directory)/'key';path.write_text(private);path.chmod(0o600)
        actual=subprocess.check_output(['ssh-keygen','-y','-P','','-f',str(path)],stderr=subprocess.DEVNULL,text=True).split()[:2]
        if actual!=public.split()[:2]:raise Refused('SSH public/private pair does not match')


def validate(data):
    kind=data['kind']
    if kind=='agent':
        clients=data['clients'];roots=data['roots']
        if sorted(item['name'] for item in clients)!=['iac-apps','iac-deploy','iac-plan']:raise Refused('exact three client identities required')
        if len({item['filename'] for item in roots})!=len(roots):raise Refused('duplicate root binding')
        root={}
        for item in roots:basename(item['filename']);root[item['filename']]=item['value']
        for item in clients:tls_material(item['ca'],item['certificate'],item['key'],identity='iac-peer-remoting')
        tls_material(root['controller-ca.pem'],root['admission.crt'],root['admission.key'],identity='iac-peer-root')
        ssl.create_default_context(cadata=root['broker-ca.pem'])
    elif kind=='gateway':
        files={item['path']:item['value'] for item in data['bindings']}
        broker,admission=data['policies']
        for policy in [broker,admission]:
            if any(not isinstance(policy.get(name),str) or not policy[name].startswith('/') for name in ['certificate','private_key','ca']):raise Refused('explicit TLS paths required')
            tls_material(files[policy['ca']],files[policy['certificate']],files[policy['private_key']],server_ip='192.168.1.107')
    elif kind=='watchdog':
        for item in data['peer_bindings']+data['controller_bindings']:basename(item['filename'])
        ssh_material(data['public'],data['private'])
    else:raise Refused('unknown material profile')


if __name__=='__main__':
    try:validate(json.load(sys.stdin))
    except Exception:raise SystemExit('deployment material validation refused')
