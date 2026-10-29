#!/usr/bin/python3
"""Paired config/state projection. Unsupported source/schema yields no bundle."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import time
import urllib.parse
import urllib.request
from control import NoRedirect, Refused, atomic_json, canonical, digest, private_file, sha_file, sign, token, verify, secret_file
from importlib.machinery import SourceFileLoader


class HCP:
    def __init__(self,policy):
        self.policy=policy
        self.token=secret_file(policy['state_token_file']).read_text().strip()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def get(self,path):
        if not path.startswith('/api/v2/') or '?' in path:raise Refused('invalid fixed HCP route')
        request=urllib.request.Request('https://app.terraform.io'+path,headers={'Authorization':'Bearer '+self.token})
        with self.opener.open(request,timeout=30) as response:
            raw=response.read(64*1024*1024+1)
            if len(raw)>64*1024*1024:raise Refused('HCP response exceeds resource budget')
            return json.loads(raw)
    def current(self):
        workspace=self.policy['workspace_id']
        if not re.fullmatch(r'ws-[A-Za-z0-9]+',workspace):raise Refused('invalid fixed workspace')
        workspace_data=self.get('/api/v2/workspaces/'+workspace)['data']
        information=workspace_data['attributes']
        if information['name']!='iac-proxmox-lab' or workspace_data['relationships']['organization']['data']['id']!='homelab-roseville' or information['terraform-version']!='1.14.4':
            raise Refused('workspace owner/name/locked runtime mismatch')
        permissions=information['permissions']
        if information['execution-mode']!='local' or not permissions.get('can-read-state-versions'):
            raise Refused('workspace is not local/readable with the dedicated state identity')
        readonly={'can-read-state-versions','can-read-variable','can-read-run','can-read-run-variables','can-read-settings','can-read-assessment-results'}
        if any(value is True and name not in readonly for name,value in permissions.items()):
            raise Refused('producer HCP identity has capabilities beyond the audited read policy')
        data=self.get('/api/v2/workspaces/'+workspace+'/current-state-version')['data']
        if data['attributes'].get('status')!='finalized':raise Refused('state is not finalized')
        return data
    def state(self,version):
        url=version['attributes']['hosted-state-download-url']
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname not in self.policy['download_hosts'] or parsed.port not in {None,443} or parsed.username or parsed.fragment:
            raise Refused('unapproved state download host')
        # Never attach the HCP Authorization header to the pre-signed download URL.
        with self.opener.open(url,timeout=30) as response:
            content=response.read(64*1024*1024+1)
            if len(content)>64*1024*1024:raise Refused('raw state exceeds resource budget')
            return json.loads(content)


def produce(policy,source,nonce,destination):
    token(nonce)
    source=Path(source)
    if policy.get('enabled') is not True:raise Refused('projection policy is not activated')
    adapter=SourceFileLoader('proxmox_projection',str(Path(__file__).with_name('proxmox-projection.py'))).load_module()
    schema_path=private_file(policy['provider_schema'])
    if sha_file(schema_path)!=policy['schema_sha256']:raise Refused('provider schema digest mismatch')
    hcp=HCP(policy)
    before=hcp.current()
    raw=hcp.state(before)
    schema=json.loads(schema_path.read_text())
    state,state_rewrites=adapter.project_state(raw,schema)
    destination=Path(destination)
    destination.mkdir(mode=0o700)
    rewrites=adapter.project_source(source/'terraform',destination/'terraform',policy)
    coverage=copy.deepcopy(policy['coverage'])
    coverage['rewrites']=rewrites+[{'state_field':field,'dependency':'secret equality or redacted field unverified'} for field in state_rewrites]
    atomic_json(destination/'terraform/proxmox/projection.tfstate',state)
    lock=private_file(policy['provider_lock'])
    shutil.copyfile(lock,destination/'terraform/proxmox/.terraform.lock.hcl')
    if hcp.current()['id']!=before['id']:raise Refused('state became stale before signing')
    files={str(p.relative_to(destination)):sha_file(p) for p in destination.rglob('*') if p.is_file()}
    now=int(time.time())
    manifest={'purpose':'plan-snapshot','root':'proxmox','source_sha':policy['source_sha'],
              'state_version':before['id'],'lineage':raw['lineage'],'serial':raw['serial'],
              'terraform':'1.14.4','provider_lock_sha256':sha_file(lock),
              'schema_sha256':policy['schema_sha256'],'policy_sha256':digest(canonical(policy)),
              'files':files,'bundle_sha256':digest(canonical(files)),'coverage':coverage,
              'nonce':nonce,'issued_at':now,'expires_at':now+900}
    atomic_json(destination/'manifest.json',sign(manifest,policy['key_id'],private_file(policy['signing_key'])))
    return manifest


def finalize(policy,envelope):
    manifest=verify(envelope,policy['keys'],'plan-snapshot')
    current=HCP(policy).current()
    status='stale' if current['id']!=manifest['state_version'] else manifest['coverage']['status']
    now=int(time.time())
    return sign({'purpose':'plan-result','root':'proxmox','source_sha':manifest['source_sha'],
                 'nonce':manifest['nonce'],'issued_at':now,'expires_at':min(now+900,manifest['expires_at']),
                 'snapshot_sha256':digest(canonical(envelope)),'state_version':current['id'],
                 'status':status,'coverage':manifest['coverage']},policy['key_id'],policy['signing_key'])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--policy',required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--destination',required=True)
    parser.add_argument('--nonce',required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:raise Refused('root producer required')
    produce(json.loads(private_file(args.policy).read_text()),args.source,args.nonce,args.destination)


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('snapshot refused; no predictive result issued')
