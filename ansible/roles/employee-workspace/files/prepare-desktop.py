#!/usr/bin/python3
"""Apply only the staged employee presentation surface, under its existing lock."""
import base64
import fcntl
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import grp
import subprocess
import sys
import tempfile

STAGE = Path('/usr/local/lib/employee-workspace/presentation')
LIB = Path('/usr/local/lib/employee-workspace')
ETC = Path('/etc')
LOCK = Path('/run/lock/employee-desktop.lock')
MARKER = Path('/var/lib/employee-workspace/transition.json')
NGINX = ETC / 'nginx/conf.d/oci-hub-desktop.conf'
BIN = Path('/usr/local/bin')
GUIDE = Path('/usr/local/lib/employee-login-guide.py')
EMPLOYEE_HOME = Path('/home/employee')


def run(argv):
    return subprocess.run(argv, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True).stdout.strip()


def install(source, target, mode=0o644):
    target = Path(target)
    if target.is_symlink() or any(p.is_symlink() for p in target.parents):
        raise ValueError('Unsafe installation path')
    data = Path(source).read_bytes()
    if target.exists() and target.read_bytes() == data and target.stat().st_uid == 0 and target.stat().st_mode & 0o777 == mode:
        return False
    fd, temporary = tempfile.mkstemp(prefix='.presentation-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def service():
    spec = importlib.util.spec_from_file_location('desktop_service', STAGE / 'desktop-service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_frontend(config):
    address = str(ipaddress.IPv4Address(config['address']))
    for key in ('certificate', 'private_key', 'ca'):
        path = Path(config[key])
        if not path.is_absolute() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError('Unsafe frontend material path')
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & (0o037 if key == 'private_key' else 0o022):
            raise ValueError('Unsafe frontend material permissions')
    run(['openssl', 'verify', '-CAfile', config['ca'], '-verify_ip', address, config['certificate']])
    run(['openssl', 'x509', '-checkend', '0', '-noout', '-in', config['certificate']])
    ca = run(['openssl', 'x509', '-text', '-noout', '-in', config['ca']])
    pinned = config.get('pinned_sha256')
    if pinned is not None:
        if not isinstance(pinned, str) or len(pinned) != 64 or any(c not in '0123456789abcdef' for c in pinned):
            raise ValueError('Invalid frontend fingerprint')
        actual = run(['openssl', 'x509', '-in', config['certificate'], '-noout', '-fingerprint', '-sha256']).split('=', 1)[1].replace(':', '').lower()
        if actual != pinned or config['ca'] != config['certificate']:
            raise ValueError('Pinned frontend identity mismatch')

    san = run(['openssl', 'x509', '-ext', 'subjectAltName', '-noout', '-in', config['certificate']])
    if ('IP Address:' + address) not in [value.strip() for value in san.splitlines()[-1].split(',')]:
        raise ValueError('Frontend SAN mismatch')
    if pinned is None and 'CA:TRUE' not in ca:
        raise ValueError('Frontend trust anchor must be a CA')
    if run(['openssl', 'x509', '-pubkey', '-noout', '-in', config['certificate']]) != run(['openssl', 'pkey', '-pubout', '-in', config['private_key']]):
        raise ValueError('Frontend material identity mismatch')


def trust(config):
    validate_frontend(config)
    changed = install(config['certificate'], ETC / 'oci-hub/desktop.crt')
    changed = install(config['private_key'], ETC / 'oci-hub/desktop.key', 0o600) or changed
    run(['nginx', '-t'])
    if changed:
        run(['systemctl', 'reload', 'nginx'])
    return changed


def validate_stage():
    module = service()
    candidate = module.validate_config_content(json.loads((STAGE / 'desktop.json').read_text()))
    authentication = module.validate_materials(candidate)
    frontend = json.loads((STAGE / 'frontend.json').read_text())
    validate_frontend(frontend)
    if candidate['viewer_url'] != 'https://' + frontend['address'] + ':8443/':
        raise ValueError('Frontend target mismatch')
    basic = base64.b64encode((authentication['username'] + ':' + authentication['password']).encode()).decode()
    nginx = (STAGE / 'desktop.conf').read_text()
    if 'proxy_set_header Authorization "Basic ' + basic + '";' not in nginx:
        raise ValueError('Backend authentication mismatch')
    return module, candidate, frontend


def activate():
    module, candidate, frontend = validate_stage()
    # The lock inode is shared with all managed start paths; never replace it.
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if info.st_uid != 0 or info.st_gid != grp.getgrnam('employee').gr_gid or info.st_mode & 0o777 != 0o660:
            raise ValueError('Unsafe startup lock')
        fcntl.flock(fd, fcntl.LOCK_EX)
        if MARKER.exists() or MARKER.is_symlink():
            if MARKER.is_symlink() or json.loads(MARKER.read_text()) != {'purpose': 'vm502-presentation' if candidate['vmid'] == 502 else 'employee-presentation', 'vmid': candidate['vmid']}:
                raise ValueError('Another maintenance operation owns the desktop')
        for unit in ('employee-browser.service', 'employee-desktop.service'):
            result = subprocess.run(['systemctl', 'show', '--property=LoadState,ActiveState', unit], capture_output=True, text=True)
            metadata = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            missing = metadata.get('LoadState') == 'not-found' and result.returncode in (0, 1)
            if not missing and (result.returncode or metadata.get('LoadState') != 'loaded' or metadata.get('ActiveState') not in ('inactive', 'failed')):
                raise ValueError('Stop the existing desktop/browser before activation')
        module.check_platform()
        module.profile_guard()
        module.port_guard(candidate)
        MARKER.parent.mkdir(exist_ok=True)
        if not MARKER.exists():
            with MARKER.open('x') as stream:
                json.dump({'purpose': 'vm502-presentation' if candidate['vmid'] == 502 else 'employee-presentation', 'vmid': candidate['vmid']}, stream)
        # Close only this presentation route before changing runtime definitions.
        disabled = NGINX.with_suffix('.conf.presentation-disabled')
        if NGINX.exists():
            os.replace(NGINX, disabled)
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
        try:
            for name in ('desktop-targets.json', 'desktop-contract.py', 'desktop-service.py', 'browser-service.py'):
                install(STAGE / name, LIB / name, 0o755 if name.endswith('service.py') else 0o644)
            for name in ('workspace-desktop.py', 'workspace-browser.py'):
                install(STAGE / name, BIN / name[:-3], 0o755)
            install(STAGE / 'login-guide.py', GUIDE, 0o755)
            for name in ('employee-desktop.service', 'employee-browser.service'):
                install(STAGE / name, ETC / 'systemd/system' / name)
            dropin = ETC / 'systemd/system/employee-browser.service.d'
            dropin.mkdir(exist_ok=True)
            install(STAGE / 'employee-browser-desktop.conf', dropin / 'desktop.conf')
            install(STAGE / 'desktop.json', ETC / 'employee-workspace-desktop.json')
            browser = ETC / 'employee-workspace-browser.json'
            config = json.loads(browser.read_text())
            config['mode'] = 'kasmvnc'
            merged = STAGE / 'browser-merged.json'
            merged.write_text(json.dumps(config, indent=2) + '\n')
            install(merged, browser)
            install(STAGE / 'backend-ca.crt', ETC / 'oci-hub/backend-ca.crt')
            trust(frontend)
            configure_browser_entries()
            run(['systemctl', 'daemon-reload'])
            for unit in ('employee-desktop.service', 'employee-browser.service'):
                state = run(['systemctl', 'show', '--property=UnitFileState', '--value', unit])
                if state in ('enabled', 'enabled-runtime'):
                    run(['systemctl', 'disable', unit])
                metadata = run(['systemctl', 'show', '--property=User,Restart', unit])
                if set(metadata.splitlines()) != {'User=employee', 'Restart=no'}:
                    raise ValueError('Unexpected service metadata')
            # Never start a browser or access the user's profile during deployment.
            install(STAGE / 'desktop.conf', NGINX, 0o600)
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
            run(['systemctl', 'restart', 'employee-login-guide.service'])
            MARKER.unlink()
        except BaseException:
            if NGINX.exists():
                os.replace(NGINX, disabled)
            run(['nginx', '-t'])
            run(['systemctl', 'reload', 'nginx'])
            raise
    finally:
        os.close(fd)



def configure_browser_entries():
    """Configure web launchers without inspecting or replacing a Firefox profile."""
    import pwd
    employee = pwd.getpwnam('employee')
    entries = {
        '.local/share/applications/employee-browser.desktop':
            '[Desktop Entry]\nType=Application\nName=Workspace Browser\nExec=/usr/local/bin/workspace-browser open %u\nTerminal=false\nMimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;\nCategories=Network;WebBrowser;\n',
        'Desktop/employee-browser.desktop':
            '[Desktop Entry]\nType=Application\nName=Workspace Browser\nExec=/usr/local/bin/workspace-browser start\nTerminal=false\nIcon=firefox\n',
        '.local/share/xfce4/helpers/employee-browser.desktop':
            '[Desktop Entry]\nVersion=1.0\nType=X-XFCE-Helper\nName=Workspace Browser\nX-XFCE-Category=WebBrowser\nX-XFCE-Commands=/usr/local/bin/workspace-browser start;\nX-XFCE-CommandsWithParameter=/usr/local/bin/workspace-browser open "%s";\n',
    }
    def write(path, value, mode):
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError('Unsafe desktop entry path')
        # Create only missing configuration directories; never touch the profile.
        missing = [p for p in path.parents if not p.exists()]
        for parent in reversed(missing):
            parent.mkdir(mode=0o700)
            os.chown(parent, employee.pw_uid, employee.pw_gid)
        if path.exists() and path.read_text() == value:
            return
        fd, temporary = tempfile.mkstemp(prefix='.workspace-browser-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(value)
            os.chmod(temporary, mode)
            os.chown(temporary, employee.pw_uid, employee.pw_gid)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    for name, value in entries.items():
        write(EMPLOYEE_HOME / name, value, 0o755 if name.startswith('Desktop/') else 0o644)
    preferences = EMPLOYEE_HOME / '.config/xfce4/helpers.rc'
    original = preferences.read_text() if preferences.exists() and not preferences.is_symlink() else ''
    lines = [line for line in original.splitlines() if not line.startswith('WebBrowser=')]
    write(preferences, '\n'.join(lines + ['WebBrowser=employee-browser']) + '\n', 0o600)
    for kind in ('text/html', 'x-scheme-handler/http', 'x-scheme-handler/https'):
        command = ['runuser', '-u', 'employee', '--', 'env', 'HOME=' + str(EMPLOYEE_HOME), 'XDG_CURRENT_DESKTOP=XFCE', 'LANG=C.UTF-8', 'gio', 'mime', kind]
        current = run(command)
        if not current.splitlines()[0].endswith(': employee-browser.desktop'):
            run(command + ['employee-browser.desktop'])

def main():
    if os.geteuid() != 0:
        raise ValueError('Root required')
    if sys.argv[1:] == ['activate']:
        activate()
        print('activated; desktop stopped, on-demand verification still required')
    elif sys.argv[1:] == ['check']:
        module, _, _ = validate_stage()
        module.check_platform()
        print('prepared; active desktop definitions unchanged')
    elif len(sys.argv) == 3 and sys.argv[1] == 'trust':
        print('changed' if trust(json.loads(Path(sys.argv[2]).read_text())) else 'unchanged')
    else:
        raise ValueError('Unsupported presentation phase')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Presentation operation failed; sensitive details withheld.', file=sys.stderr)
        sys.exit(69)
