#!/usr/bin/env python3
"""Prepare public offline artifacts in an explicitly selected fresh directory."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request
import yaml
from control import atomic_json,sha_file


def fetch(url,destination,expected=None,algorithm='sha256'):
    if urllib.parse.urlsplit(url).scheme!='https':raise ValueError('artifact source must use HTTPS')
    digest=hashlib.new(algorithm)
    with urllib.request.urlopen(url,timeout=60) as response,open(destination,'xb') as output:
        while block:=response.read(1024*1024):output.write(block);digest.update(block)
    if expected and digest.hexdigest()!=expected:raise ValueError('artifact checksum mismatch: '+destination.name)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--destination',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    lock=json.loads((root/'ci/agent-toolchain.lock.json').read_text())
    bom=yaml.safe_load((root/'ci/toolchain-bom.yml').read_text())
    destination=Path(args.destination);destination.mkdir(mode=0o700,parents=False)
    for directory in ['providers','collections','wheels','npm-cache','npm-tarballs']:(destination/directory).mkdir(mode=0o700)
    for artifact in lock['archives']:fetch(artifact['url'],destination/artifact['filename'],artifact['sha256'])
    java=bom['jenkins']['java']['upgrade']
    core=next(entry for entry in bom['jenkins']['core']['upgrade_path'] if entry['version']==bom['jenkins']['core']['version'])
    for artifact in [java,*java['package_dependencies'],core]:
        url=artifact.get('package_url',artifact.get('url'));expected=artifact.get('package_sha256',artifact.get('sha256'))
        fetch(url,destination/Path(urllib.parse.urlsplit(url).path).name,expected)
    requirements=destination/'requirements.lock'
    requirements.write_text('\n'.join(item['name']+'=='+item['version']+' '+' '.join('--hash=sha256:'+digest for digest in item['hashes']) for item in lock['python_packages'])+'\n')
    subprocess.run(['python3','-m','pip','download','--disable-pip-version-check','--only-binary=:all:','--require-hashes','--python-version','311','--platform','manylinux2014_x86_64','--platform','manylinux_2_28_x86_64','--platform','manylinux_2_17_x86_64','--implementation','cp','--abi','cp311','--dest',str(destination/'wheels'),'-r',str(requirements)],check=True)
    for name,package in lock['npm_lock']['packages'].items():
        if not name:continue
        filename=hashlib.sha256(name.encode()).hexdigest()+'.tgz'
        artifact=destination/'npm-tarballs'/filename
        integrity=package['integrity'];algorithm,expected=integrity.split('-',1)
        fetch(package['resolved'],artifact,base64.b64decode(expected).hex(),algorithm)
        subprocess.run(['npm','cache','add',str(artifact),'--ignore-scripts','--cache',str(destination/'npm-cache')],check=True)
    import re
    for address,version,body in re.findall(r'provider "([^"]+)" \{\s+version\s+= "([^"]+)"(.*?)\n}',lock['provider_lock_text'],re.S):
        namespace,name=address.split('/')[1:]
        url='https://registry.terraform.io/v1/providers/'+namespace+'/'+name+'/'+version+'/download/linux/amd64'
        with urllib.request.urlopen(url,timeout=30) as response:metadata=json.load(response)
        if 'zh:'+metadata['shasum'] not in body:raise ValueError('provider archive differs from repository lock')
        fetch(metadata['download_url'],destination/'providers'/metadata['filename'],metadata['shasum'])
    for collection in lock['collections']:
        namespace,name=collection['name'].split('.')
        url='https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/index/'+namespace+'/'+name+'/versions/'+collection['version']+'/'
        with urllib.request.urlopen(url,timeout=30) as response:metadata=json.load(response)
        fetch(metadata['download_url'],destination/'collections'/(namespace+'-'+name+'-'+collection['version']+'.tar.gz'),metadata['artifact']['sha256'])
    atomic_json(destination/'manifest.json',{'schema':1,'lock_sha256':sha_file(root/'ci/agent-toolchain.lock.json'),
        'files':{str(path.relative_to(destination)):sha_file(path) for path in destination.rglob('*') if path.is_file()}})
    print('Prepared offline artifacts; package installation has not been performed')


if __name__=='__main__':main()
