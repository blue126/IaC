#!/usr/bin/python3
"""The only remoting shell wrapper: admission, status and approval transport."""
import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import ssl
import urllib.request
from control import Refused,canonical,token,report_status


def socket_request(request):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(45);connection.connect('/run/jenkins-job-runner.sock')
        connection.sendall(canonical(request)+b'\n')
        with connection.makefile('rb') as source:result=json.loads(source.readline(65537))
    if result.get('status')=='refused':raise Refused('peer admission or cleanup gate refused the operation')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['start','status','approval','abort'])
    parser.add_argument('--nonce');parser.add_argument('--stage',choices=['terraform','ansible','apps-publish','apps-google']);parser.add_argument('--digest')
    args=parser.parse_args()
    if args.operation=='start':
        identity=pwd.getpwuid(os.getuid()).pw_name
        if identity not in {'iac-plan','iac-deploy','iac-apps'}:raise Refused('unknown remoting identity')
        directory=Path('/etc/jenkins-agent')/identity
        context=ssl.create_default_context(cafile=directory/'controller-ca.pem')
        context.load_cert_chain(directory/'admission.crt',directory/'admission.key')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        data={'job':os.environ['JOB_NAME'],'build':int(os.environ['BUILD_NUMBER'])}
        request=urllib.request.Request('https://192.168.1.107:9444/admit',data=canonical(data),headers={'Content-Type':'application/json'})
        with opener.open(request,timeout=30) as response:envelope=json.load(response)
        result=socket_request({'operation':'start','admission':envelope})
    else:
        request={'operation':args.operation,'nonce':token(args.nonce)}
        if args.operation=='approval':
            if not args.stage or not isinstance(args.digest,str) or __import__('re').fullmatch('[0-9a-f]{64}',args.digest) is None:raise Refused('invalid approval digest')
            request.update(stage=args.stage,digest=args.digest)
        result=socket_request(request)
    if 'phase' in result:report_status(result)
    if 'nonce' in result:token(result['nonce'])
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('trusted remoting wrapper refused; inspect peer control status')
