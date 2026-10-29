#!/usr/bin/python3
"""Mandatory fixed boundary probe before any checkout code or credential stage."""
import json
import os
from pathlib import Path
import sys
import time
from importlib.machinery import SourceFileLoader
from control import Refused,atomic_json,private_file,sha_file,verify


def main():
    sha,build,nonce=sys.argv[1:]
    trust=json.loads(Path('/opt/jenkins-agent/control/trust.json').read_text())
    admission=verify(json.loads(Path('/job/control/lease.json').read_text()),trust['keys'],'job-lease')
    original=json.loads(Path('/job/control/admission.json').read_text())['payload']
    if any(admission.get(key)!=value for key,value in original.items() if key not in {'purpose','issued_at','expires_at'}):
        raise Refused('entry lease differs from original run')
    if [sha,build,nonce]!=[admission['sha'],str(admission['build']),admission['nonce']]:raise Refused('entry differs from signed build')
    probe=SourceFileLoader('entry_isolation',str(Path(__file__).with_name('isolation-probe.py'))).load_module()
    try:proof=probe.check()
    except Exception:raise SystemExit(77)
    atomic_json(Path('/job/report/status.json'),{'phase':'isolation-verified','summary':proof})
    deadline=time.monotonic()+60
    while not Path('/job/control/secrets-ready.json').exists():
        if time.monotonic()>deadline:raise Refused('root pre-secret admission timed out')
        time.sleep(0.25)
    fixed={'deploy':'/opt/jenkins-agent/control/transaction.py','plan':'/opt/jenkins-agent/control/plan-task.py',
           'apps-publish':'/opt/jenkins-agent/apps/publish.py','apps-validation':'/opt/jenkins-agent/apps/validation.py'}
    target=private_file(fixed[admission['profile']])
    if admission['profile'].startswith('apps-') and (sha_file(target)!=trust['application_wrappers'][admission['profile']] or sha_file(target)!=admission['application_inputs']['wrapper_sha256']):
        raise Refused('application wrapper was not the reviewed fixed artifact')
    os.execv('/usr/bin/python3',['/usr/bin/python3',str(target),sha,build,nonce])


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('fixed job entry refused')
