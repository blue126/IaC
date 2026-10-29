#!/usr/bin/python3
"""In-unit capability probe. It runs before any stage credential is bound."""
import errno
import sys
import json
import os
from pathlib import Path
import socket
from control import Refused, token


def rejected(host,port,family=socket.AF_INET):
    try:
        connection=socket.socket(family,socket.SOCK_STREAM)
    except OSError as error:
        if family==socket.AF_INET6 and error.errno==errno.EAFNOSUPPORT:return
        raise Refused('cannot establish forbidden-endpoint probe') from error
    with connection:
        connection.settimeout(1)
        try:connection.connect((host,port))
        except OSError as error:
            if family==socket.AF_INET6 and error.errno==errno.EAFNOSUPPORT:return
            if error.errno in {errno.ECONNREFUSED,errno.EACCES,errno.EPERM,errno.ENETUNREACH,errno.EHOSTUNREACH,errno.ETIMEDOUT} or isinstance(error,TimeoutError):return
            raise Refused('unrecognized forbidden-endpoint probe error') from error
    raise Refused('a forbidden network endpoint was reachable')


def proc_access_denied(path):
    # Root confirms both processes and both synthetic canaries are alive before
    # and after the probe. hidepid may deliberately render the PID as ENOENT.
    for access in [os.O_RDONLY,os.O_WRONLY]:
        try:descriptor=os.open(path,access|os.O_NONBLOCK|os.O_NOFOLLOW)
        except OSError as error:
            if error.errno in {errno.EACCES,errno.EPERM,errno.ENOENT}:continue
            raise Refused('unexpected process-root probe failure') from error
        else:
            os.close(descriptor)
            raise Refused('same-identity process root is accessible')


def peer_check(pid,nonce):
    if type(pid) is not int or pid<=0:raise Refused('invalid job process identity')
    nonce=token(nonce)
    proc_access_denied('/proc/'+str(pid)+'/root/job/report/proc-boundary-'+nonce)


def check():
    proof=json.loads(Path('/job/control/isolation.json').read_text())
    for kind in ['net','ipc','mnt','user']:
        if os.readlink('/proc/self/ns/'+kind)==proof['host_namespaces'][kind]:
            raise Refused('job did not enter its isolated namespace')
    status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if status['NoNewPrivs'].strip()!='1' or int(status['CapEff'].strip(),16)!=0:
        raise Refused('job retained privilege escalation or effective capabilities')
    for pid in proof['other_identity_pids']:
        try:
            descriptor=os.open('/proc/'+str(pid)+'/environ',os.O_RDONLY)
        except OSError:continue
        os.close(descriptor);raise Refused('cross-identity process environment is readable')
    for user in proof['other_identities']:
        if (os.access('/var/lib/jenkins-agent/'+user,os.R_OK) or os.access('/var/lib/jenkins-agent/'+user,os.X_OK)):raise Refused('other identity home is accessible')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        try:connection.connect(proof['unix_canary'])
        except OSError:pass
        else:raise Refused('host Unix socket was visible in job mount namespace')
    rejected('127.0.0.1',proof['loopback_port'])
    rejected('::1',proof['loopback_port'],socket.AF_INET6)
    if proof['profile']=='plan':
        for host,port in [('192.168.1.50',8006),('192.168.1.52',8006),('192.168.1.107',22),('192.168.1.107',8080),('1.1.1.1',443)]:rejected(host,port)
        rejected('::ffff:192.168.1.50',8006,socket.AF_INET6)
        # Namespace resolver is deliberately empty. Numeric broker IP is the only peer.
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as dns:
            dns.settimeout(1)
            try:
                dns.sendto(b'\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01',('192.168.1.1',53))
                dns.recvfrom(1024)
            except OSError:pass
            else:raise Refused('plan job can reach DNS')
    nonce=token(proof['nonce'])
    if type(proof['remoting_pid']) is not int or proof['remoting_pid']<=0:raise Refused('invalid remoting process identity')
    expected='/var/lib/jenkins-agent/'+proof['unix_user']+'/.proc-boundary-'+nonce
    if proof['unix_user'] not in {'iac-plan','iac-deploy','iac-apps'} or proof['remoting_canary']!=expected:raise Refused('unexpected remoting canary path')
    proc_access_denied('/proc/'+str(proof['remoting_pid'])+'/root'+expected)
    path=Path('/job/report')/('proc-boundary-'+nonce)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as output:output.write('synthetic-job-boundary:'+nonce)
    return {'namespaces':['net','ipc','mnt','user'],'same_uid_proc_root':'job-to-remoting-denied','no_new_privileges':True,'effective_capabilities':0,
            'cross_uid_proc':'denied','host_unix_socket':'denied','loopback':'isolated'}


if __name__=='__main__':
    try:
        if len(sys.argv)==1:check()
        elif len(sys.argv)==4 and sys.argv[1]=='peer':peer_check(int(sys.argv[2]),sys.argv[3])
        else:raise Refused('unknown fixed isolation probe mode')
    except Exception:raise SystemExit(77)
