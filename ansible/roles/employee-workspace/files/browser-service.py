#!/usr/bin/python3
"""Supervise the daily Firefox and its fixed, employee-only control socket."""
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

_spec = importlib.util.spec_from_file_location('desktop_service', Path(__file__).with_name('desktop-service.py'))
service = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(service)
RUNTIME = Path('/run/employee-browser')
CONTROL = RUNTIME / 'control.sock'
READY = RUNTIME / 'browser-ready'
MAXIMUM = 8192


def environment():
    # The service supplies identity; only the validated live desktop supplies X/DBus.
    env = {'HOME': '/home/employee', 'USER': 'employee', 'LOGNAME': 'employee',
           'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'GNUPGHOME': '/home/employee/.gnupg', 'MOZ_ENABLE_WAYLAND': '0'}
    env.update(service.live_session())
    return env


def ensure_profile():
    """Create the daily profile directory when absent; never reset its contents or locks."""
    # Firefox refuses a missing --profile path ("Profile Missing"); only the
    # workspace-login supervisor used to create it.
    employee = pwd.getpwnam('employee').pw_uid
    if os.geteuid() != employee:
        raise service.Refused('Browser profile requires the employee identity')
    profile = Path(service.PROFILE)
    # Match secure_file: a symlinked profile or ancestor could redirect writes.
    if any(p.is_symlink() for p in (profile, *profile.parents)):
        raise service.Refused('Unsafe browser profile path')
    try:
        profile.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd = os.open(profile, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise service.Refused('Browser profile unavailable') from None
    try:
        info = os.fstat(fd)
        if info.st_uid != employee:
            raise service.Refused('Browser profile owned by another user')
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def firefox_ready(child, env):
    if child.poll() is not None:
        raise service.Refused('Browser exited before ready')
    result = service.run(['xprop', '-root', '_NET_CLIENT_LIST'], env=env, text=True, timeout=3)
    own = Path('/proc/self/cgroup').read_text()
    for window in re.findall(r'0x[0-9a-fA-F]+', result.stdout):
        try:
            props = service.run(['xprop', '-id', window, '_NET_WM_PID', 'WM_CLASS'], env=env, text=True, timeout=3).stdout
        except subprocess.CalledProcessError:
            continue
        match = re.search(r'_NET_WM_PID\(CARDINAL\) = ([0-9]+)', props)
        if match and 'firefox' in props.lower():
            try:
                if Path('/proc/' + match[1] + '/cgroup').read_text() == own:
                    return True
            except FileNotFoundError:
                continue
    return False


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate field')
        result[key] = value
    return result


def request(peer):
    peer.settimeout(3)
    data = bytearray()
    while b'\n' not in data:
        chunk = peer.recv(MAXIMUM + 1 - len(data))
        if not chunk:
            raise ValueError('Incomplete request')
        data.extend(chunk)
        if len(data) > MAXIMUM:
            raise ValueError('Request too long')
    if not data.endswith(b'\n') or data.count(b'\n') != 1:
        raise ValueError('One request required')
    return service.contract.validate_open(json.loads(data.decode('utf-8'), object_pairs_hook=unique_fields))


def handle(peer):
    code = 64
    try:
        uid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
        if uid not in (0, os.getuid()):
            raise ValueError('Peer rejected')
        url = request(peer)
        with service.startup_lock():
            service.transition_guard()
            env = environment()
            subprocess.run(['firefox', '--profile', service.PROFILE, '--new-tab', url],
                           env=env, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20)
        code = 0
    except (OSError, ValueError, service.Refused, subprocess.SubprocessError):
        pass
    response = {'version': 1, 'status': 'opened' if code == 0 else 'rejected', 'exit_code': code}
    try:
        peer.sendall((json.dumps(response) + '\n').encode())
    except OSError:
        pass


def retire():
    for path in (READY, CONTROL):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def supervise():
    os.umask(0o077)
    child = None
    def stopped(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    try:
        with service.startup_lock():
            service.preflight(service.load_config(), running=True)
            ensure_profile()
            env = environment()
            # RuntimeDirectory is owned by this unit; stale endpoints cannot be used.
            retire()
            child = subprocess.Popen(['firefox', '--new-instance', '--profile', service.PROFILE, 'about:blank'],
                                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(150):
                if firefox_ready(child, env):
                    break
                time.sleep(.1)
            else:
                raise service.Refused('Browser readiness timed out')
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(CONTROL))
            CONTROL.chmod(0o600)
            server.listen(16)
            server.settimeout(.5)
            READY.touch(mode=0o600)
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify:
                target = os.environ['NOTIFY_SOCKET']
                notify.connect('\0' + target[1:] if target.startswith('@') else target)
                notify.sendall(b'READY=1')
        with server:
            while child.poll() is None:
                try:
                    peer, _ = server.accept()
                except socket.timeout:
                    continue
                with peer:
                    handle(peer)
        raise service.Refused('Browser exited')
    finally:
        retire()
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        # systemd terminates this unit's remaining Firefox descendants only.


if __name__ == '__main__':
    try:
        if sys.argv[1:]:
            raise service.Refused('Unsupported browser action', 64)
        supervise()
    except (service.Refused, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print('Browser operation failed', file=sys.stderr)
        sys.exit(exc.code if isinstance(exc, service.Refused) else 69)
