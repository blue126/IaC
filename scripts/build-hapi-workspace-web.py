#!/usr/bin/env python3
"""Build the pinned HAPI automatic-login frontend inside the approved Sandbox."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / 'scripts/hapi-workspace-web'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--bun', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if not os.environ.get('SANDBOX_ID'):
        raise SystemExit('Run inside the approved task Sandbox; no host dependency installation')
    pin = json.loads((INPUTS/'upstream.json').read_text())
    if sha(args.archive) != pin['archive_sha256']:
        raise SystemExit('Upstream archive checksum mismatch')
    if subprocess.check_output([str(args.bun), '--version'], text=True).strip() != pin['bun']:
        raise SystemExit('Unexpected Bun version')
    if args.output.exists():
        raise SystemExit('Output directory already exists; refuse to replace existing artifacts')
    workspace = Path(tempfile.mkdtemp(prefix='hapi-workspace-web-'))
    print(f'Build workspace: {workspace}', flush=True)
    with tarfile.open(args.archive) as archive:
        archive.extractall(workspace, filter='data')
    sources = list(workspace.iterdir())
    if len(sources) != 1 or not sources[0].is_dir():
        raise SystemExit('Unexpected archive layout')
    source = sources[0]
    for name, checksum in pin['files'].items():
        if sha(source/name) != checksum:
            raise SystemExit('Pinned upstream source mismatch: ' + name)
    patch = INPUTS/'workspace-auth.patch'
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True)
    for path in sorted((INPUTS/'overlay').rglob('*')):
        if path.is_file():
            target = source/'web/src'/path.relative_to(INPUTS/'overlay')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    if args.prepare_only:
        print(f'Prepared source: {source}', flush=True)
        return
    env = {**os.environ, 'VITE_HAPI_WORKSPACE_AUTH': '1', 'CI': '1'}
    # Install only in this task; dependency lifecycle and release scripts never run.
    install_log = workspace/'dependencies.log'
    with install_log.open('w') as log:
        installed = subprocess.run([str(args.bun), 'install', '--frozen-lockfile', '--ignore-scripts'],
                                   cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
    if installed.returncode:
        print('\n'.join(install_log.read_text().splitlines()[-18:]), flush=True)
        raise SystemExit(f'Dependency installation failed; log: {install_log}')
    print('Pinned dependencies installed; lifecycle scripts disabled', flush=True)
    web = source/'web'
    subprocess.run([str(args.bun), 'run', 'test', 'src/lib/workspace-auth.test.ts',
                    'src/components/WorkspaceGate.test.tsx', 'src/hooks/useWorkspaceAuth.test.tsx',
                    'src/hooks/useAuth.test.tsx'], cwd=web, env=env, check=True)
    subprocess.run([str(args.bun), 'run', 'typecheck'], cwd=web, env=env, check=True)
    subprocess.run([str(args.bun), 'run', 'build'], cwd=web, env=env, check=True)
    dist = web/'dist'
    if not (dist/'index.html').is_file() or (dist/'sw.js').exists():
        raise SystemExit('Missing frontend entry or unexpected service worker')
    args.output.mkdir(parents=True)
    output = args.output/'hapi-workspace-web.tar.gz'
    overlay = {str(p.relative_to(INPUTS)): sha(p) for p in sorted((INPUTS/'overlay').rglob('*')) if p.is_file()}
    manifest = {'upstream_commit': pin['commit'], 'upstream_archive_sha256': sha(args.archive),
                'patch_sha256': sha(patch), 'overlay_sha256': overlay,
                'workspace_auth': True, 'service_worker': False}
    (dist/'workspace-build.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')
    with output.open('wb') as stream, gzip.GzipFile(fileobj=stream, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for path in sorted(dist.rglob('*')):
                if path.is_symlink():
                    raise SystemExit('Unexpected output symlink')
                info = archive.gettarinfo(str(path), arcname=str(path.relative_to(dist)))
                info.uid, info.gid, info.uname, info.gname, info.mtime = 0, 0, '', '', 0
                if path.is_file():
                    with path.open('rb') as content:
                        archive.addfile(info, content)
                else:
                    archive.addfile(info)
    manifest['artifact_sha256'] = sha(output)
    (args.output/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n')
    print(json.dumps({'artifact': str(output), 'sha256': manifest['artifact_sha256']}))


if __name__ == '__main__':
    main()
