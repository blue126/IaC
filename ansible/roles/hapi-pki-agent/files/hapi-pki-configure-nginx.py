#!/usr/bin/python3
"""Publish one reviewed PKI endpoint without replacing an existing ingress config."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

PATH = Path('/etc/hapi-ingress/nginx.conf')
SNIPPET = Path('/etc/hapi-ingress/pki/agent.conf')
CANDIDATE = Path('/etc/hapi-pki/agent-location.candidate.conf')
LINE = '        include /etc/hapi-ingress/pki/*.conf;\n'


def publish(path, data):
    if path.is_symlink():
        raise ValueError('Unexpected proxy symlink')
    info = path.stat() if path.exists() else None
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pki-nginx-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chown(name, info.st_uid if info else os.geteuid(), info.st_gid if info else path.parent.stat().st_gid)
        os.chmod(name, info.st_mode & 0o777 if info else 0o640)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def configure(name, expected):
    if not re.fullmatch(r'[a-z0-9.-]+', name) or not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ValueError('Invalid private proxy binding')
    if not PATH.is_file() or PATH.is_symlink() or SNIPPET.is_symlink() or not CANDIDATE.is_file() or CANDIDATE.is_symlink():
        raise ValueError('Private proxy material missing or symlinked')
    before = PATH.read_bytes();text = before.decode()
    if text.count(LINE) > 1 or expected not in [hashlib.sha256(before).hexdigest(), hashlib.sha256(text.replace(LINE, '', 1).encode()).hexdigest()]:
        raise ValueError('Private proxy changed; prepare a new deployment plan')
    pattern = r'(^\s*server_name ' + re.escape(name) + r';\n)'
    if len(re.findall(pattern, text, flags=re.M)) != 1:
        raise ValueError('Expected one private login server')
    after = text if LINE in text else re.sub(pattern, lambda match: match[1] + LINE, text, flags=re.M)
    old_snippet = SNIPPET.read_bytes() if SNIPPET.exists() else None
    new_snippet = CANDIDATE.read_bytes()
    command = ['/usr/sbin/runuser', '-u', 'hapi-ingress', '--', '/usr/sbin/nginx',
               '-c', str(PATH), '-p', '/run/hapi-ingress/']
    publish(SNIPPET, new_snippet);publish(PATH, after.encode())
    try:
        subprocess.run([*command, '-t'], check=True, capture_output=True, timeout=20)
        subprocess.run([*command, '-s', 'reload'], check=True, capture_output=True, timeout=20)
    except Exception:
        publish(PATH, before)
        if old_snippet is None:
            SNIPPET.unlink()
        else:
            publish(SNIPPET, old_snippet)
        try:
            subprocess.run([*command, '-s', 'reload'], check=True, capture_output=True, timeout=20)
        except Exception:
            pass
        raise
    return before != after.encode() or old_snippet != new_snippet


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True);parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    try:
        print('changed' if configure(args.name, args.expected_sha256) else 'unchanged')
    except Exception:
        raise SystemExit('Private PKI endpoint not published') from None
