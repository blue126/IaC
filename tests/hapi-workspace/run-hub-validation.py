#!/usr/bin/env python3
"""Run the prepared Hub against quarantined data before the production cut."""
import http.client
import os
from pathlib import Path
import signal
import subprocess
import threading
import time


def main():
    root = Path('/var/lib/hapi-shared-hub-validation')
    if not root.is_dir() or os.environ.get('HAPI_HOME') != '/var/lib/hapi-shared-hub':
        raise RuntimeError('Use the explicitly staged validation service')
    environment = {**os.environ, 'HAPI_HOME': str(root), 'DB_PATH': str(root / 'hapi.db')}
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    processes = []
    try:
        hub = subprocess.Popen([os.environ['HAPI_VALIDATION_BINARY'], '--no-relay'],
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(hub)
        for _ in range(100):
            if hub.poll() is not None:
                raise RuntimeError('Validation Hub exited')
            connection = http.client.HTTPConnection('127.0.0.1', 3006, timeout=1)
            try:
                connection.request('GET', '/health')
                response = connection.getresponse()
                if response.status == 200:
                    response.read()
                    break
            except OSError:
                pass
            finally:
                connection.close()
            time.sleep(.1)
        else:
            raise RuntimeError('Validation Hub did not start')
        transport = subprocess.Popen(['/usr/sbin/nginx', '-c', '/etc/hapi-shared-hub/nginx.conf',
                                      '-p', '/run/hapi-hub-transport/', '-g', 'daemon off;'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(transport)
        while not stopped.wait(.2):
            if any(process.poll() is not None for process in processes):
                raise RuntimeError('Validation transport exited')
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    main()
