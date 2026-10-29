#!/usr/bin/python3
"""Verify and predict only the signed paired projection inside the plan job unit."""
import json
import os
from pathlib import Path
import subprocess
import sys
from control import Refused,atomic_json,sha_file,verify


def main():
    sha,build,nonce=sys.argv[1:]
    base=Path('/job/workspace');trust=json.loads(Path('/opt/jenkins-agent/control/trust.json').read_text())
    manifest=verify(json.loads((base/'manifest.json').read_text()),trust['keys'],'plan-snapshot')
    if manifest['source_sha']!=sha or manifest['nonce']!=nonce:raise Refused('snapshot source/nonce mismatch')
    for name,expected in manifest['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or sha_file(base/path)!=expected:raise Refused('snapshot file mismatch')
    root=base/'terraform/proxmox'
    environment={'HOME':'/job/home','TMPDIR':'/job/tmp','PATH':'/opt/jenkins-toolchain/bin:/usr/bin:/bin',
                 'TF_CLI_CONFIG_FILE':'/opt/jenkins-toolchain/terraform.rc','TF_IN_AUTOMATION':'1','CHECKPOINT_DISABLE':'1',
                 'SSL_CERT_FILE':'/job/control/broker-ca.pem'}
    for argv in [['terraform','init','-lockfile=readonly','-input=false'],['terraform','plan','-input=false','-out=/job/tmp/predictive.tfplan','-detailed-exitcode']]:
        result=subprocess.run(argv,cwd=root,env=environment,capture_output=True,text=True)
        if result.returncode not in ({0} if argv[1]=='init' else {0,2}):raise Refused('provider prediction failed; coverage is unpredictable')
    result=subprocess.run(['terraform','show','-json','/job/tmp/predictive.tfplan'],cwd=root,env=environment,capture_output=True,text=True,check=True)
    plan=json.loads(result.stdout)
    changes=[{'address':item['address'],'actions':item['change']['actions']} for item in plan.get('resource_changes',[]) if item['change']['actions']!=['no-op']]
    atomic_json(Path('/job/report/status.json'),{'phase':'prediction-finished','summary':{'status':manifest['coverage']['status'],'coverage':manifest['coverage'],'changes':changes}})
    # Root monitor rechecks finalized current-state-version before returning a result.


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('prediction refused; no full-root no-change assertion is valid')
