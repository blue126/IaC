#!/usr/bin/python3
"""Create one immutable backend generation on its owning VM; retain frontend identity."""
import base64
import grp
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile

ROOT = Path('/var/lib/employee-workspace/desktop-materials')
FRONTEND = Path('/etc/oci-hub')
OUTPUT = Path('/usr/local/lib/employee-workspace/presentation/update-vars.json')


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def fingerprint(path):
    return run(['openssl', 'x509', '-in', str(path), '-noout', '-fingerprint', '-sha256']).split('=', 1)[1].replace(':', '').lower()


def prepare(vmid, address, generation, frontend_pin):
    os.umask(0o077)
    if type(vmid) is not int or vmid <= 0 or not re.fullmatch(r'g-[a-z0-9][a-z0-9-]{0,47}', generation):
        raise ValueError('Invalid generation identity')
    address = str(ipaddress.IPv4Address(address))
    if not re.fullmatch('[a-f0-9]{64}', frontend_pin) or fingerprint(FRONTEND / 'desktop.crt') != frontend_pin:
        raise ValueError('Existing frontend fingerprint changed')
    target = ROOT / 'generations' / generation / str(vmid)
    for parent in reversed([target.parent, *target.parent.parents]):
        if parent.is_symlink():
            raise ValueError('Symlink material parent')
        existed = parent.exists()
        parent.mkdir(mode=0o755, exist_ok=True)
        if not existed:
            os.chmod(parent, 0o755)
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Unsafe material parent')
    if target.is_symlink():
        raise ValueError('Symlink generation')
    if not target.exists():
        # Interrupted generation remains private and cannot become an active reference.
        temp = Path(tempfile.mkdtemp(prefix='.pending-', dir=target.parent))
        run(['openssl', 'req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '365',
             '-subj', f'/CN=Employee desktop VM{vmid} backend CA', '-addext', 'basicConstraints=critical,CA:TRUE',
             '-keyout', str(temp / 'ca.key'), '-out', str(temp / 'ca.pem')])
        run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost',
             '-keyout', str(temp / 'server.key'), '-out', str(temp / 'server.csr')])
        (temp / 'extensions').write_text('basicConstraints=critical,CA:FALSE\nsubjectAltName=DNS:localhost\nextendedKeyUsage=serverAuth\n')
        run(['openssl', 'x509', '-req', '-in', str(temp / 'server.csr'), '-CA', str(temp / 'ca.pem'),
             '-CAkey', str(temp / 'ca.key'), '-set_serial', str(secrets.randbits(128)), '-days', '90',
             '-extfile', str(temp / 'extensions'), '-out', str(temp / 'server.pem')])
        (temp / 'authentication.json').write_text(json.dumps({'username': 'employee', 'password': secrets.token_urlsafe(32)}))
        for name in ('ca.key', 'server.key', 'authentication.json'):
            os.chmod(temp / name, 0o600 if name == 'ca.key' else 0o640)
            if name != 'ca.key':
                os.chown(temp / name, 0, grp.getgrnam('employee').gr_gid)
        for name in ('ca.pem', 'server.pem'):
            os.chmod(temp / name, 0o644)
        os.chmod(temp, 0o755)
        os.rename(temp, target)
    refs = {key: f'generations/{generation}/{vmid}/{name}' for key, name in (
        ('trust_ref', 'ca.pem'), ('certificate_ref', 'server.pem'), ('private_key_ref', 'server.key'),
        ('authentication_ref', 'authentication.json'))}
    for path in (target, *(target / name for name in ('ca.pem', 'server.pem', 'server.key', 'authentication.json'))):
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise ValueError('Unsafe existing generation')
    authentication = json.loads((target / 'authentication.json').read_text())
    basic = base64.b64encode((authentication['username'] + ':' + authentication['password']).encode()).decode()
    # A frontend issued by a separate CA (the VM502 pilot) keeps that CA beside it;
    # every other VM uses a self-signed frontend that is its own trust anchor.
    frontend_ca = FRONTEND / 'desktop-ca.crt'
    if not frontend_ca.exists():
        frontend_ca = FRONTEND / 'desktop.crt'
    elif frontend_ca.is_symlink() or frontend_ca.stat().st_uid != 0 or frontend_ca.stat().st_mode & 0o022:
        raise ValueError('Unsafe frontend CA')
    variables = {
        'employee_desktop_frontend': {'address': address, 'certificate': str(FRONTEND / 'desktop.crt'),
            'private_key': str(FRONTEND / 'desktop.key'), 'ca': str(frontend_ca), 'pinned_sha256': frontend_pin},
        'employee_desktop_config': {'vmid': vmid, 'backend': {'type': 'kasmvnc', 'address': '127.0.0.1',
            'port': 8444, 'client_path': '/', 'route_enabled': True, 'generation_id': generation,
            'tls_server_name': 'localhost', 'trust_ref': refs['trust_ref']},
            'generation': dict(refs, vmid=vmid), 'materials_root': str(ROOT), 'viewer_url': f'https://{address}:8443/'},
        'oci_hub_desktop_backend_basic': basic,
    }
    if OUTPUT.is_symlink():
        raise ValueError('Symlink output')
    data = json.dumps(variables)
    if OUTPUT.exists() and OUTPUT.read_text() == data and OUTPUT.stat().st_uid == 0 and OUTPUT.stat().st_mode & 0o777 == 0o600:
        return False
    fd, name = tempfile.mkstemp(prefix='.update-', dir=OUTPUT.parent)
    with os.fdopen(fd, 'w') as stream:
        stream.write(data)
    os.replace(name, OUTPUT)
    return True


if __name__ == '__main__':
    print('changed' if prepare(int(sys.argv[1]), *sys.argv[2:]) else 'unchanged')
