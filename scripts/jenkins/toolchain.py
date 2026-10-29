#!/usr/bin/python3
"""Install only an administrator-staged, complete offline execution kit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from control import Refused, atomic_json, private_file, sha_file

PREFIX = Path('/opt/jenkins-toolchain')


def check_archive(archive):
    """Reject path traversal, links, devices and sockets before extraction."""
    members = archive.infolist() if isinstance(archive, zipfile.ZipFile) else archive.getmembers()
    for member in members:
        name = member.filename if isinstance(member, zipfile.ZipInfo) else member.name
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise Refused('unsafe archive path')
        if isinstance(member, zipfile.ZipInfo):
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise Refused('archive symlink refused')
        elif not (member.isfile() or member.isdir()):
            raise Refused('archive special file refused')


def validate_lock(lock):
    if lock['schema'] != 1 or lock['platform'] != 'linux_amd64' or lock['python'] != '3.11':
        raise Refused('unsupported toolchain platform')
    if hashlib.sha256(lock['provider_lock_text'].encode()).hexdigest() != lock['provider_lock_sha256']:
        raise Refused('provider lock digest mismatch')
    for package in lock['python_packages']:
        if not package['hashes'] or not all(re.fullmatch('[0-9a-f]{64}', h) for h in package['hashes']):
            raise Refused('unhashed Python dependency')
    for name, package in lock['npm_lock']['packages'].items():
        if name and not package.get('integrity', '').startswith('sha512-'):
            raise Refused('unhashed npm dependency')


def unpack_node(source,destination,root):
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            if member.name==root and member.isdir():continue
            relative=member.name.removeprefix(root+'/')
            if relative==member.name or Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise Refused('invalid Node archive')
            # Only these official command links are recreated by the installer.
            if member.issym() and (relative,member.linkname) in {
                ('bin/npm','../lib/node_modules/npm/bin/npm-cli.js'),
                ('bin/npx','../lib/node_modules/npm/bin/npx-cli.js'),
                ('bin/corepack','../lib/node_modules/corepack/dist/corepack.js')}:
                continue
            if not (member.isfile() or member.isdir()):raise Refused('unexpected Node link or special file')
            if member.isfile():
                target=destination/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as data:target.write_bytes(data.read())
                target.chmod(0o555 if member.mode & 0o111 else 0o444)


def unpack_provider(source,target,name,version):
    with zipfile.ZipFile(source) as archive:
        check_archive(archive)
        binaries=[]
        for member in archive.infolist():
            if member.is_dir():continue
            if re.fullmatch('terraform-provider-'+re.escape(name)+'_v'+re.escape(version)+r'(?:_x[0-9]+)?',member.filename):
                binaries.append(member.filename)
            elif member.filename!='LICENSE.txt':raise Refused('unexpected provider archive member')
        if len(binaries)!=1:raise Refused('provider archive must contain its fixed binary')
        archive.extractall(target)
        for member in archive.infolist():
            if not member.is_dir():(target/member.filename).chmod(0o555 if member.filename in binaries else 0o444)


def install(lock_path, kit, bom_path):
    if os.geteuid() != 0:
        raise Refused('root and explicit Ansible installation authorization required')
    lock = json.loads(private_file(lock_path).read_text())
    validate_lock(lock)
    kit = Path(kit)
    private_file(kit/'manifest.json')
    manifest = json.loads((kit/'manifest.json').read_text())
    # Every staged file is checked before executing any installer.
    for name, expected in manifest['files'].items():
        candidate = Path(name)
        if candidate.is_absolute() or '..' in candidate.parts or sha_file(private_file(kit/candidate)) != expected:
            raise Refused('offline kit checksum mismatch')
    for artifact in lock['archives']:
        if sha_file(kit/artifact['filename']) != artifact['sha256']:
            raise Refused('BOM archive mismatch')
    bom = json.loads(private_file(bom_path).read_text())
    if bom['terraform']['version'] != next(a['version'] for a in lock['archives'] if a['name']=='terraform'):
        raise Refused('BOM Terraform differs from dependency lock')
    if bom['ansible']['core']['version'] != next(p['version'] for p in lock['python_packages'] if p['name']=='ansible-core'):
        raise Refused('BOM Ansible differs from dependency lock')
    java = bom['jenkins']['java']['upgrade']
    debs = [java] + java['package_dependencies']
    core=next(item for item in bom['jenkins']['core']['upgrade_path'] if item['version']==bom['jenkins']['core']['version'])
    if sha_file(kit/Path(core['url']).name)!=core['sha256']:raise Refused('BOM controller runtime package mismatch')
    for deb in debs:
        filename = Path(deb.get('package_url', deb.get('url', ''))).name
        if sha_file(kit/filename) != deb.get('package_sha256', deb.get('sha256')):
            raise Refused('BOM Java package mismatch')
    providers = re.findall(r'provider "([^"]+)" \{\s+version\s+= "([^"]+)"(.*?)\n}',
                           lock['provider_lock_text'], re.S)
    for address, version, body in providers:
        filename = f'terraform-provider-{address.split("/")[-1]}_{version}_linux_amd64.zip'
        source = kit/'providers'/filename
        if 'zh:'+sha_file(source) not in body:
            raise Refused('provider archive is absent from authoritative lock')
    marker = PREFIX/'installed.json'
    expected = {'lock': sha_file(lock_path), 'kit': sha_file(kit/'manifest.json'),'bom':sha_file(bom_path),'installer':sha_file(__file__)}
    if marker.exists() and json.loads(marker.read_text()) == expected:
        verify_install(lock, bom)
        return False
    PREFIX.mkdir(mode=0o755, exist_ok=True)
    (PREFIX/'bin').mkdir(exist_ok=True)
    subprocess.run(['dpkg-deb','-x',str(kit/Path(core['url']).name),str(PREFIX/'controller')],check=True)
    subprocess.run(['dpkg', '-i', *[str(kit/Path(d.get('package_url', d.get('url', ''))).name) for d in reversed(debs)]], check=True)
    for artifact in lock['archives']:
        source = kit/artifact['filename']
        if artifact['name'] == 'terraform':
            with zipfile.ZipFile(source) as archive:
                check_archive(archive)
                (PREFIX/'bin'/'terraform').write_bytes(archive.read('terraform'))
                (PREFIX/'bin'/'terraform').chmod(0o555)
        else:
            # Node's official tar contains symlinks; extract only the known binaries
            # and npm's regular files, recreating the two fixed links ourselves.
            unpack_node(source,PREFIX/'node',artifact['filename'].removesuffix('.tar.xz'))
            for name,target in [('node', PREFIX/'node/bin/node'), ('npm', PREFIX/'node/lib/node_modules/npm/bin/npm-cli.js')]:
                (PREFIX/'bin'/name).unlink(missing_ok=True)
                (PREFIX/'bin'/name).symlink_to(target)
    requirements = PREFIX/'requirements.lock'
    requirements.write_text('\n'.join(p['name']+'=='+p['version']+' '+ ' '.join('--hash=sha256:'+h for h in p['hashes']) for p in lock['python_packages'])+'\n')
    subprocess.run(['/usr/bin/python3', '-m', 'venv', str(PREFIX/'python')], check=True)
    subprocess.run([str(PREFIX/'python/bin/python'), '-m', 'pip', 'install', '--no-index', '--only-binary=:all:', '--require-hashes', '--find-links', str(kit/'wheels'), '-r', str(requirements)], check=True)
    for executable in (PREFIX/'python/bin').iterdir():
        if executable.name.startswith(('ansible', 'python')):
            target = PREFIX/'bin'/executable.name
            target.unlink(missing_ok=True)
            target.symlink_to(executable)
    npm = PREFIX/'apps'
    npm.mkdir(exist_ok=True)
    (npm/'package-lock.json').write_text(json.dumps(lock['npm_lock']))
    (npm/'package.json').write_text(json.dumps({'name':lock['npm_lock']['name'], 'version':'1.0.0', 'private':True, 'dependencies':{'@google/clasp':'2.4.2'}}))
    subprocess.run([str(PREFIX/'bin/npm'), 'ci', '--offline', '--ignore-scripts', '--no-audit', '--no-fund', '--cache', str(kit/'npm-cache'), '--prefix', str(npm)], check=True, env={'PATH':str(PREFIX/'bin')+':/usr/bin:/bin','HOME':str(PREFIX)})
    (PREFIX/'bin/clasp').unlink(missing_ok=True)
    (PREFIX/'bin/clasp').symlink_to(npm/'node_modules/.bin/clasp')
    mirror=PREFIX/'providers'
    for address, version, _ in providers:
        filename=f'terraform-provider-{address.split("/")[-1]}_{version}_linux_amd64.zip'
        target=mirror/address/version/'linux_amd64'
        target.mkdir(parents=True,exist_ok=True)
        unpack_provider(kit/'providers'/filename,target,address.split('/')[-1],version)
        # Terraform links unpacked mirrors into each job. The executed provider
        # stays root-owned/read-only rather than becoming a writable job copy.
    (PREFIX/'terraform.rc').write_text('disable_checkpoint = true\nprovider_installation {\n filesystem_mirror {\n path = "/opt/jenkins-toolchain/providers"\n }\n}\n')
    for collection in lock['collections']:
        source=kit/'collections'/(collection['name'].replace('.','-')+'-'+collection['version']+'.tar.gz')
        with tarfile.open(source) as archive:
            check_archive(archive)
            metadata=json.load(archive.extractfile('MANIFEST.json'))['collection_info']
            if metadata['namespace']+'.'+metadata['name'] != collection['name'] or metadata['version'] != collection['version']:
                raise Refused('collection identity differs from fixed manifest')
        subprocess.run([str(PREFIX/'bin/ansible-galaxy'),'collection','install','--offline','--no-deps','-p',str(PREFIX/'collections'),str(source)],check=True)
    verify_install(lock,bom)
    atomic_json(marker,expected)
    for directory, dirs, files in os.walk(PREFIX):
        Path(directory).chmod(0o555)
        for filename in files:
            path=Path(directory)/filename
            if not path.is_symlink():path.chmod(0o555 if path.stat().st_mode & 0o111 else 0o444)

    return True


def verify_install(lock,bom):
    result=subprocess.check_output([str(PREFIX/'bin/terraform'),'version','-json'],text=True)
    if json.loads(result)['terraform_version'] != bom['terraform']['version']:
        raise Refused('installed Terraform version mismatch')
    output=subprocess.check_output([str(PREFIX/'bin/ansible-playbook'),'--version'],text=True)
    if '[core '+bom['ansible']['core']['version']+']' not in output:
        raise Refused('installed Ansible version mismatch')
    java=subprocess.run(['/usr/lib/jvm/temurin-25-jre-amd64/bin/java','-version'],capture_output=True,text=True,check=True)
    if '"'+bom['jenkins']['java']['runtime_version']+'"' not in java.stderr:
        raise Refused('installed Java version mismatch')
    node=subprocess.check_output([str(PREFIX/'bin/node'),'--version'],text=True).strip()
    if node!='v'+next(a['version'] for a in lock['archives'] if a['name']=='node'):
        raise Refused('installed Node version mismatch')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['install','check-lock'])
    parser.add_argument('--lock',required=True)
    parser.add_argument('--kit')
    parser.add_argument('--bom')
    args=parser.parse_args()
    if args.mode=='install':print('installed' if install(args.lock,args.kit,args.bom) else 'unchanged')
    else:validate_lock(json.loads(Path(args.lock).read_text()))


if __name__=='__main__':
    main()
