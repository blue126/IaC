#!/usr/bin/python3
"""Start, inspect, or stop the one managed employee desktop."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

spec = importlib.util.spec_from_file_location('desktop_service', '/usr/local/lib/employee-workspace/desktop-service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def control(action, unit):
    return subprocess.run(['sudo', '-n', '/usr/bin/systemctl', action, unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode


def state():
    result = subprocess.run(['/usr/bin/systemctl', 'show', '--property=ActiveState', '--value', service.DESKTOP], capture_output=True, text=True)
    if result.returncode:
        raise service.Refused('Desktop state unavailable')
    return result.stdout.strip()


def status(config):
    current = state()
    if current == 'inactive':
        if os.path.lexists(service.SESSION):
            raise service.Refused('Desktop stale session', 1)
        print('stopped')
        return 3
    if current == 'failed':
        raise service.Refused('Desktop failed', 1)
    if current != 'active':
        raise service.Refused('Desktop not ready')
    service.live_session()
    print('ready ' + config['viewer_url'])
    return 0


def main(argv):
    if len(argv) != 1 or argv[0] not in ('start', 'status', 'stop'):
        raise service.Refused('Usage: workspace-desktop start|status|stop', 64)
    if os.geteuid() == 0:
        raise service.Refused('Run workspace-desktop as employee', 64)
    config = service.load_config()
    action = argv[0]
    if action == 'status':
        return status(config)
    if action == 'stop':
        # Stop only these system units, in this order; SSH is outside both groups.
        browser = subprocess.run(['/usr/bin/systemctl', 'show', '--property=LoadState', '--value', service.BROWSER], capture_output=True, text=True)
        if browser.returncode or browser.stdout.strip() not in ('loaded', 'not-found'):
            raise service.Refused('Browser state unavailable', 1)
        if browser.stdout.strip() == 'loaded' and control('stop', service.BROWSER):
            raise service.Refused('Browser stop failed', 1)
        if control('stop', service.DESKTOP):
            raise service.Refused('Desktop stop failed', 1)
        print('stopped')
        return 0
    with service.startup_lock():
        running = state() == 'active'
        service.preflight(config, running=running)
        if running:
            return status(config)
    # Never wait for a unit while owning its startup lock. systemd coalesces
    # concurrent start jobs; the service checks all guards again under the lock.
    if control('start', service.DESKTOP):
        service.transition_guard()
        raise service.Refused('Desktop start failed', 1)
    return status(config)


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (service.Refused, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, service.Refused) else 'Desktop operation failed', file=sys.stderr)
        sys.exit(exc.code if isinstance(exc, service.Refused) else 69)
