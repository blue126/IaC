#!/usr/bin/env python3
"""Refresh only the reviewed local source/schema fingerprint, never runtime scope."""
import argparse
import hashlib
import json
from pathlib import Path
from importlib.machinery import SourceFileLoader
from control import Refused


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    path=root/'ci/proxmox-plan-policy.json';policy=json.loads(path.read_text())
    adapter=SourceFileLoader('update_projection',str(Path(__file__).with_name('proxmox-projection.py'))).load_module()
    files={}
    for directory in [root/'terraform/proxmox',*[root/'terraform/modules'/name for name in sorted(adapter.MODULES)]]:
        for source in sorted(directory.glob('*.tf')):
            if source.is_symlink():raise Refused('source closure may not include links')
            relative=str(source.relative_to(root/'terraform'))
            adapter.project_file(source.read_text(),relative,policy)
            files[relative]=hashlib.sha256(source.read_bytes()).hexdigest()
    schema=hashlib.sha256((root/'ci/agent-provider-schema.json').read_bytes()).hexdigest()
    if args.check:
        if files!=policy['source_files'] or schema!=policy['schema_sha256']:raise Refused('reviewed projection fingerprint is stale')
    else:
        policy['source_files']=files;policy['schema_sha256']=schema
        path.write_text(json.dumps(policy,indent=2)+'\n')


if __name__=='__main__':main()
