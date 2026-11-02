#!/usr/bin/python3
"""Collect actual root-owned peer receipts; never turn missing jobs into success."""
import argparse
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
from control import Refused,atomic_json,private_file,sha_file,verify

JOBS={'IaC-Homelab-Pipeline','IaC-ReadOnly-Plan','Webhook-Router','n8n-rental','n8n-rental-clasp-validation'}


def collect(mapping,destination,runner):
    if set(mapping)!=JOBS:raise Refused('all five mapped jobs are required')
    destination=Path(destination);destination.mkdir(mode=0o700)
    result={'jobs':{},'evidence_files':{}}
    for index,job in enumerate(sorted(mapping)):
        build=mapping[job]
        if type(build) is not int or build<=0:raise Refused('exact positive build numbers required')
        if job=='Webhook-Router':envelope=runner.controller('route-evidence',{'build':build})
        else:
            matches=[]
            for path in runner.base.glob('result-*.json'):
                receipt=json.loads(private_file(path).read_text())
                if 'evidence' not in receipt:continue
                observed=receipt['evidence']['payload']
                if observed['job']==job and observed['build']==build:matches.append(receipt['evidence'])
            if len(matches)!=1:raise Refused('job has no unique root execution receipt: '+job)
            envelope=matches[0]
        purpose='router-run-evidence' if job=='Webhook-Router' else 'job-run-evidence'
        verify(envelope,runner.config['keys'],purpose,envelope['payload']['issued_at'])
        filename='job-'+str(index)+'.json';atomic_json(destination/filename,envelope)
        result['evidence_files'][filename]=sha_file(destination/filename)
        result['jobs'][job]={field:filename for field in ['scheduling_evidence','cleanup_evidence','credential_scope_evidence']}
    atomic_json(destination/'index.json',result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--builds',required=True);parser.add_argument('--destination',required=True);args=parser.parse_args()
    if os.geteuid()!=0:raise Refused('root receipt collector required')
    module=SourceFileLoader('handoff_runner',str(Path(__file__).with_name('job-runner.py'))).load_module()
    collect(json.loads(private_file(args.builds).read_text()),args.destination,module.Runner())


if __name__=='__main__':main()
