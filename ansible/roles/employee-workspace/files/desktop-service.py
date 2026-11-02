#!/usr/bin/python3
"""Own the employee X/XFCE session; never launch the daily browser."""
import configparser
import ctypes
import errno
import contextlib
import fcntl
import importlib.util
import ipaddress
import json
import os
import grp
import pwd
import shlex
from pathlib import Path
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

CONFIG = Path('/etc/employee-workspace-desktop.json')
RUNTIME = Path('/run/employee-desktop')
SESSION = RUNTIME / 'session.json'
LOCK = Path('/run/lock/employee-desktop.lock')
MARKER = Path('/var/lib/employee-workspace/transition.json')
PROFILE = '/home/employee/.local/share/employee-workspace/firefox'
DESKTOP = 'employee-desktop.service'
BROWSER = 'employee-browser.service'
_spec = importlib.util.spec_from_file_location('desktop_contract', Path(__file__).with_name('desktop-contract.py'))
contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contract)


class Refused(Exception):
    def __init__(self, message, code=69):
        super().__init__(message)
        self.code = code


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kwargs)


def secure_file(path, owner, maximum=0o644, group=None):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or stat.S_IMODE(info.st_mode) & ~maximum:
        raise Refused('Unsafe managed file')
    if group is not None and info.st_mode & 0o040 and info.st_gid != group:
        raise Refused('Unsafe material group')
    # Reject symlinked ancestors, including material generation directories.
    if any(p.is_symlink() for p in path.parents):
        raise Refused('Unsafe managed path')
    return path


def load_config():
    secure_file(CONFIG, 0)
    return validate_config_content(json.loads(CONFIG.read_text()))


def validate_config_content(config):
    if set(config) != {'vmid', 'backend', 'generation', 'materials_root', 'viewer_url'} or type(config.get('vmid')) is not int or config['vmid'] not in contract.approved_vmids():
        raise Refused('Desktop target rejected')
    backend = config['backend']
    if backend.get('type') != 'kasmvnc':
        raise Refused('Desktop mode rejected')
    generation = config['generation']
    # Reuse the fixed descriptor contract with the already selected target.
    contract.validate_backends({'networks': {'target': {'vmid': config['vmid'], 'ip': backend['address'], 'disabled': False}},
                                'desktop_backends': {str(config['vmid']): backend},
                                'desktop_generations': {backend['generation_id']: generation}})
    viewer = urlsplit(config['viewer_url'])
    if (viewer.scheme != 'https' or viewer.port != 8443 or viewer.path != '/' or viewer.query or viewer.fragment or viewer.username is not None or viewer.password is not None):
        raise Refused('Desktop viewer URL rejected')
    ipaddress.IPv4Address(viewer.hostname)
    root = Path(config['materials_root'])
    if not root.is_absolute() or '..' in root.parts:
        raise Refused('Material root rejected')
    config['materials'] = {key: root / generation[key] for key in ('trust_ref', 'certificate_ref', 'private_key_ref', 'authentication_ref')}
    return config


@contextlib.contextmanager
def startup_lock():
    transition_guard()
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o660:
            raise Refused('Unsafe startup lock')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        os.close(fd)


def transition_guard():
    # Only absence permits a start; inaccessible state also fails closed.
    try:
        MARKER.lstat()
    except FileNotFoundError:
        return
    except OSError:
        pass
    raise Refused('Desktop maintenance in progress', contract.external_start_exit({}))


def validate_materials(config):
    employee = pwd.getpwnam('employee')
    employee_group = grp.getgrnam('employee').gr_gid
    for key, path in config['materials'].items():
        secret = key in ('private_key_ref', 'authentication_ref')
        secure_file(path, 0, 0o640 if secret else 0o644, group=employee_group if secret else None)
        # Root's candidate check and employee's runtime check must agree about
        # readability; root must not pin materials only root can consume.
        for target, owner_bit, group_bit, other_bit in [(path, 0o400, 0o040, 0o004)] + [(parent, 0o100, 0o010, 0o001) for parent in path.parents]:
            info = target.stat()
            allowed = owner_bit if info.st_uid == employee.pw_uid else group_bit if info.st_gid == employee_group else other_bit
            if not info.st_mode & allowed:
                raise Refused('Material not readable by employee')
    files = config['materials']
    ca = run(['openssl', 'x509', '-text', '-noout', '-in', str(files['trust_ref'])], text=True).stdout
    san = run(['openssl', 'x509', '-ext', 'subjectAltName', '-noout', '-in', str(files['certificate_ref'])], text=True).stdout
    if 'CA:TRUE' not in ca or 'DNS:localhost' not in [item.strip() for item in san.splitlines()[-1].split(',')]:
        raise Refused('Backend CA or SAN rejected')
    run(['openssl', 'verify', '-CAfile', str(files['trust_ref']), '-verify_hostname', config['backend']['tls_server_name'], str(files['certificate_ref'])])
    run(['openssl', 'x509', '-checkend', '0', '-noout', '-in', str(files['certificate_ref'])])
    certificate = run(['openssl', 'x509', '-pubkey', '-noout', '-in', str(files['certificate_ref'])]).stdout
    private = run(['openssl', 'pkey', '-pubout', '-in', str(files['private_key_ref'])]).stdout
    if certificate != private:
        raise Refused('Material identity mismatch')
    authentication = json.loads(files['authentication_ref'].read_text())
    if set(authentication) != {'username', 'password'} or not all(isinstance(v, str) and v and '\n' not in v and '\r' not in v for v in authentication.values()):
        raise Refused('Authentication material rejected')
    if ':' in authentication['username']:
        raise Refused('Authentication username rejected')
    return authentication


def check_platform():
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '26.04':
        raise Refused('Unapproved operating system')
    if run(['dpkg', '--print-architecture'], text=True).stdout.strip() != 'amd64':
        raise Refused('Unapproved architecture')
    if run(['dpkg-query', '-W', '-f=${Version}', 'kasmvncserver'], text=True).stdout.strip() != '1.5.0-1':
        raise Refused('Unapproved KasmVNC version')


def profile_guard():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if PROFILE.encode() in args or any(a.startswith((PROFILE + '/').encode()) for a in args):
                if not any(line.split(':', 2)[-1] == '/system.slice/' + BROWSER for line in (proc / 'cgroup').read_text().splitlines()):
                    raise Refused('Unmanaged profile writer')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            # The employee can inspect its own profile writers. Other users must
            # not own this employee-only profile; root performs deployment checks.
            continue
    # Hold the real POSIX lock while checking compatibility artifacts. Firefox
    # uses IPv4:+PID symlinks when .parentlock provides its authoritative lock.
    # A free .parentlock makes that compatibility link stale; Firefox reclaims
    # it itself. Never delete a lock here or accept an unverified symlink.
    employee_uid = pwd.getpwnam('employee').pw_uid
    with contextlib.ExitStack() as locks:
        posix_locked = False
        active = None
        for name in ('.parentlock', 'lock', 'parent.lock'):
            path = Path(PROFILE) / name
            if not os.path.lexists(path):
                continue
            if active is None:
                active = subprocess.run(['systemctl', 'is-active', '--quiet', BROWSER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            if active:
                continue
            if path.is_symlink():
                host, separator, owner = os.readlink(path).partition(':')
                try:
                    ipaddress.IPv4Address(host)
                except ValueError:
                    raise Refused('Unmanaged profile lock') from None
                if name != 'lock' or not posix_locked or not separator or not owner.startswith('+') or not owner[1:].isdecimal() or int(owner[1:]) < 1 or path.lstat().st_uid != employee_uid:
                    raise Refused('Unmanaged profile lock')
                continue
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            locks.callback(os.close, fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != employee_uid:
                raise Refused('Unsafe profile lock')
            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused('Unmanaged profile lock') from None
            if name == '.parentlock':
                posix_locked = True


def port_guard(config):
    endpoints = [('127.0.0.1', 6081), ('127.0.0.1', 5901), ('127.0.0.1', 8444),
                 (urlsplit(config['viewer_url']).hostname, 6081)]
    for address, port in endpoints:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((address, port))
            except OSError:
                raise Refused('Desktop port unavailable: ' + str(port)) from None
    if Path('/tmp/.X98-lock').exists() or os.path.lexists('/tmp/.X11-unix/X98'):
        raise Refused('Desktop display unavailable')


def preflight(config, running=False):
    transition_guard()
    check_platform()
    validate_materials(config)
    profile_guard()
    if not running:
        port_guard(config)


def live_session():
    secure_file(SESSION, os.getuid(), 0o600)
    env = contract.validate_session(json.loads(SESSION.read_text()))
    if env['DISPLAY'] != ':98' or env['XAUTHORITY'] != str(RUNTIME / 'Xauthority') or env['XDG_RUNTIME_DIR'] != str(RUNTIME / 'xdg'):
        raise Refused('Unexpected desktop environment')
    if env['DBUS_SESSION_BUS_ADDRESS'].split(',')[0] != 'unix:path=' + str(RUNTIME / 'bus'):
        raise Refused('Unexpected session bus')
    result = run(['xprop', '-root', '_NET_SUPPORTING_WM_CHECK'], env=dict(os.environ, **env), text=True, timeout=3)
    if 'window id' not in result.stdout:
        raise Refused('Desktop not ready')
    return env


def record_x_resources(pid):
    lock = Path('/tmp/.X98-lock')
    try:
        if int(lock.read_text().strip()) != pid:
            return
        records = []
        for path in (lock, Path('/tmp/.X11-unix/X98')):
            info = path.lstat()
            if info.st_uid != os.getuid() or path.is_symlink():
                return
            records.append([str(path), info.st_dev, info.st_ino])
        target = RUNTIME / 'x-resources.json'
        if not target.exists():
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump({'pid': pid, 'resources': records}, stream)
    except (FileNotFoundError, ValueError):
        return


def cleanup_x_resources():
    record = RUNTIME / 'x-resources.json'
    if not record.exists():
        return
    data = json.loads(secure_file(record, os.getuid(), 0o600).read_text())
    # systemd invokes ExecStopPost after terminating this unit's cgroup. Never
    # remove an X endpoint if its recorded process is still alive.
    if Path('/proc/' + str(data['pid'])).exists():
        return
    for filename, device, inode in data['resources']:
        if filename not in ('/tmp/.X98-lock', '/tmp/.X11-unix/X98'):
            raise Refused('Unexpected managed X resource')
        path = Path(filename)
        try:
            info = path.lstat()
            if (info.st_dev, info.st_ino, info.st_uid) != (device, inode, os.getuid()) or path.is_symlink():
                raise Refused('Managed X resource ownership changed')
            if filename.endswith('-lock') and int(path.read_text().strip()) != data['pid']:
                raise Refused('Managed X lock changed')
            path.unlink()
        except FileNotFoundError:
            pass
    record.unlink()


def retire():
    try:
        SESSION.unlink()
    except FileNotFoundError:
        pass


def xfce_policy(env):
    # Change only the required keys through xfconf, preserving other user settings.
    policies = {
        'xfce4-session': {'/general/SaveOnExit': ('bool', 'false'), '/general/AutoSave': ('bool', 'false'), '/general/LockCommand': ('string', '/usr/bin/true'), '/general/SessionName': ('string', 'employee-' + secrets.token_hex(16)), '/chooser/AlwaysDisplay': ('bool', 'false'), '/sessions/Failsafe/Count': ('int', '5')},
        'xfce4-power-manager': {'/xfce4-power-manager/blank-on-ac': ('int', '0'), '/xfce4-power-manager/inactivity-on-ac': ('int', '14'), '/xfce4-power-manager/lock-screen-suspend-hibernate': ('bool', 'false')},
        'xfce4-screensaver': {'/saver/enabled': ('bool', 'false'), '/lock/enabled': ('bool', 'false')},
    }
    for index, (command, priority, per_screen) in enumerate(((['xfwm4'], 15, False), (['xfsettingsd'], 20, False), (['xfce4-panel'], 25, False), (['Thunar', '--daemon'], 30, False), (['xfdesktop'], 35, False))):
        prefix = f'/sessions/Failsafe/Client{index}'
        policies['xfce4-session'][prefix + '_Command'] = ('string', command)
        policies['xfce4-session'][prefix + '_Priority'] = ('int', str(priority))
        policies['xfce4-session'][prefix + '_PerScreen'] = ('bool', str(per_screen).lower())
    for channel, keys in policies.items():
        for key, (kind, value) in keys.items():
            base = ['xfconf-query', '-c', channel, '-p', key]
            exists = subprocess.run(base, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            array = key.endswith('_Command')
            values = value if array else [value]
            options = [item for entry in values for item in (['-t', kind, '-s', entry] if not exists or array else ['-s', entry])]
            run(base + ([] if exists else ['--create']) + (['--force-array'] if array else []) + options, env=env)


def deny_kasm_udp():
    """Limit only the imminent Kasm exec; other supervisor children stay normal."""
    class Filter(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte), ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ushort), ('filters', ctypes.POINTER(Filter))]
    # Pinned Ubuntu amd64: socket=41; seccomp_data arch/nr/args offsets=4/0/16.
    rules = [(0x20,0,0,4), (0x15,1,0,0xc000003e), (0x06,0,0,0x80000000),
             (0x20,0,0,0), (0x15,0,6,41), (0x20,0,0,16),
             (0x15,1,0,2), (0x15,0,3,10), (0x20,0,0,24),
             (0x54,0,0,15), (0x15,1,0,2), (0x06,0,0,0x7fff0000),
             (0x06,0,0,0x50000 | errno.EPERM)]
    filters = (Filter * len(rules))(*(Filter(*row) for row in rules))
    program = Program(len(rules), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38,1,0,0,0) or libc.prctl(22,2,ctypes.byref(program),0,0):
        raise OSError(ctypes.get_errno(), 'Kasm UDP filter unavailable')


def autostart_policy(env):
    # Preserve normal XDG discovery and change only prohibited autostart entries.
    user = Path(env['HOME']) / '.config/autostart'
    if any(path.is_symlink() for path in (user, *user.parents)):
        raise Refused('Unsafe autostart directory')
    user.mkdir(parents=True, exist_ok=True)
    programs = {'firefox', 'firefox-esr', 'xfce4-screensaver', 'xscreensaver',
                'light-locker', 'gnome-screensaver', 'xss-lock', 'ibus',
                'ibus-daemon', 'ibus-setup', 'ibus-x11', 'ibus-autostart', 'im-launch', 'fcitx', 'fcitx5',
                'fcitx-autostart', 'fcitx5-autostart', 'start-fcitx', 'start-fcitx5', 'fcitx5-wayland-launcher'}
    filenames = programs | {'org.mozilla.firefox', 'org.mozilla.firefox-esr', 'org.freedesktop.ibus.panel.wayland', 'org.freedesktop.ibus.panel.extension.gtk3', 'org.fcitx.fcitx5'}
    # The employee entry takes precedence over a same-name system entry.
    entries = {}
    for directory in (Path('/etc/xdg/autostart'), user):
        for path in directory.glob('*.desktop'):
            entries[path.name] = path
    for name, source in entries.items():
        prohibited_name = name[:-8].lower() in filenames
        try:
            text = source.read_text(encoding='utf-8')
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read_string(text)
            entry = parser['Desktop Entry'] if parser.has_section('Desktop Entry') else {}
            args = shlex.split(entry.get('Exec', ''))
            if args and Path(args[0]).name == 'env':
                args = args[1:]
                while args and ('=' in args[0] or args[0].startswith('-')):
                    args.pop(0)
            program = Path(args[0]).name if args else ''
            if not prohibited_name and program not in programs:
                continue
            if not parser.has_section('Desktop Entry'):
                text = '[Desktop Entry]\n'
        except (OSError, UnicodeError, configparser.Error, ValueError):
            if not prohibited_name:
                continue
            text = '[Desktop Entry]\n'
        target = user / name
        # Keep comments, keys, localized labels and all other groups unchanged.
        lines = text.splitlines(keepends=True)
        inside = False
        found = False
        output = []
        for line in lines:
            if line.strip().startswith('['):
                if inside and not found:
                    output.append('Hidden=true\n')
                    found = True
                inside = line.strip() == '[Desktop Entry]'
            if inside and line.partition('=')[0].strip() == 'Hidden':
                output.append('Hidden=true\n')
                found = True
            else:
                output.append(line if line.endswith('\n') else line + '\n')
        if inside and not found:
            output.append('Hidden=true\n')
        value = ''.join(output)
        if source != target or target.is_symlink() or value != text:
            temporary = user / ('.employee-autostart-' + secrets.token_hex(16))
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    stream.write(value)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if temporary.exists():
                    temporary.unlink()


def supervise():
    children = []
    os.umask(0o077)
    def stopped(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    try:
        with startup_lock():
            config = load_config()
            preflight(config)
            retire()
            runtime = RUNTIME
            (runtime / 'xdg').mkdir(mode=0o700, exist_ok=True)
            # Keep normal persistent application configuration and system XDG menus.
            env = dict(os.environ, HOME='/home/employee', DISPLAY=':98', XAUTHORITY=str(runtime / 'Xauthority'), XDG_RUNTIME_DIR=str(runtime / 'xdg'), XDG_CURRENT_DESKTOP='XFCE', GTK_IM_MODULE='simple', QT_IM_MODULE='compose', XMODIFIERS='@im=none')
            env.pop('XDG_CONFIG_HOME', None)
            env.pop('XDG_CACHE_HOME', None)
            env.pop('XDG_CONFIG_DIRS', None)
            run(['xauth', '-f', env['XAUTHORITY'], 'source', '-'], input='add :98 . ' + secrets.token_hex(16) + '\n', text=True)
            authentication = validate_materials(config)
            run(['kasmvncpasswd', '-u', authentication['username'], '-w', str(runtime / 'password')], input=authentication['password'] + '\n' + authentication['password'] + '\n', text=True)
            files = config['materials']
            argv = ['Xkasmvnc', ':98', '-geometry', '1024x768', '-AcceptSetDesktopSize', '0', '-AlwaysShared', '1', '-DisconnectClients', '0', '-depth', '24', '-interface', config['backend']['address'], '-websocketPort', '8444', '-rfbport', '-1', '-SecurityTypes', 'None', '-publicIP', config['backend']['address'], '-httpd', '/usr/share/kasmvnc/www', '-KasmPasswordFile', str(runtime / 'password'), '-cert', str(files['certificate_ref']), '-key', str(files['private_key_ref']), '-sslOnly', '1', '-nolisten', 'tcp', '-auth', env['XAUTHORITY']]
            children.append(subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=deny_kasm_udp))
            wait_x(env, children)
            bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--address=unix:path=' + str(runtime / 'bus'), '--print-address=1'], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            children.append(bus)
            env['DBUS_SESSION_BUS_ADDRESS'] = bus.stdout.readline().strip()
            autostart_policy(env)
            xfce_policy(env)
            children.append(subprocess.Popen(['xfce4-session', '--disable-tcp'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            wait_x(env, children, wm=True)
            run(['xset', 's', 'off'], env=env)
            run(['xset', '-dpms'], env=env)
            session = {'version': 1, 'ready': True, 'display': ':98', 'xauthority': env['XAUTHORITY'], 'dbus_session_bus_address': env['DBUS_SESSION_BUS_ADDRESS'], 'xdg_runtime_dir': env['XDG_RUNTIME_DIR']}
            contract.publish_session(SESSION, session)
            notify = os.environ.get('NOTIFY_SOCKET')
            if not notify:
                raise Refused('Missing system supervisor')
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as peer:
                peer.connect('\0' + notify[1:] if notify.startswith('@') else notify)
                peer.sendall(b'READY=1')
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise Refused('Desktop component exited')
    finally:
        retire()
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        # systemd owns final cgroup termination, including orphaned XFCE children.


def wait_x(env, children, wm=False):
    for _ in range(150):
        if children:
            record_x_resources(children[0].pid)
        if any(child.poll() is not None for child in children):
            raise Refused('Desktop component exited before ready')
        result = subprocess.run(['xprop', '-root'] + (['_NET_SUPPORTING_WM_CHECK'] if wm else []), env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if result.returncode == 0 and (not wm or 'window id' in result.stdout):
            return
        time.sleep(0.1)
    raise Refused('Desktop readiness timed out')


def main():
    if sys.argv[1:] == ['cleanup']:
        retire()
        cleanup_x_resources()
    elif len(sys.argv) == 3 and sys.argv[1] == 'validate-config':
        if os.geteuid() != 0:
            raise Refused('Configuration validation requires root', 64)
        candidate = secure_file(sys.argv[2], 0)
        validate_materials(validate_config_content(json.loads(candidate.read_text())))
    elif sys.argv[1:] == ['check']:
        config = load_config()
        check_platform()
        validate_materials(config)
    elif sys.argv[1:] == ['browser-check']:
        # Until Story4 replaces the browser supervisor, dependency installation
        # must not allow the inherited legacy X/browser command to run.
        command = run(['systemctl', 'show', BROWSER, '--property=ExecStart', '--value'], text=True).stdout
        if 'auth-browser.py' in command:
            raise Refused('Legacy browser is incompatible with desktop mode')
        with startup_lock():
            preflight(load_config(), running=True)
            live_session()
    elif not sys.argv[1:]:
        supervise()
    else:
        raise Refused('Unsupported service action', 64)


if __name__ == '__main__':
    try:
        main()
    except (Refused, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, Refused) else 'Desktop operation failed', file=sys.stderr)
        sys.exit(exc.code if isinstance(exc, Refused) else 69)
