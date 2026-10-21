#!/usr/bin/python3 -I
"""Dispatch authenticated device accounts without interpreting client commands."""
import ipaddress
import json
import os
import pwd
import re
import sys
from pathlib import Path

ROOT = Path('/etc/employee-access')


def command(mapping, original, tty=False):
    if set(mapping) != {'employee', 'host', 'user', 'enabled'} or mapping['enabled'] is not True:
        raise ValueError('inactive mapping')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,19}', mapping['employee']):
        raise ValueError('invalid employee')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', mapping['user']):
        raise ValueError('invalid user')
    ipaddress.IPv4Address(mapping['host'])
    if original not in ('', 'employee-sftp'):
        raise ValueError('unsupported request')
    args = ['/usr/bin/ssh', '-F', '/dev/null', '-o', 'BatchMode=yes',
            '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none',
            '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
            '-o', 'ForwardX11=no', '-o', 'EscapeChar=none',
            '-o', 'EnableEscapeCommandline=no', '-o', 'PermitLocalCommand=no',
            '-o', 'ProxyCommand=none', '-o', 'ProxyJump=none',
            '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
            '-o', 'ControlPersist=no', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'UpdateHostKeys=no',
            '-o', 'KnownHostsCommand=none', '-o', 'ConnectTimeout=15',
            '-o', 'UserKnownHostsFile=' + str(ROOT / 'known-hosts'),
            '-o', 'HostKeyAlias=employee-' + mapping['employee'],
            '-i', str(ROOT / 'keys' / pwd.getpwuid(os.getuid()).pw_name),
            '-p', '22']
    target = mapping['user'] + '@' + mapping['host']
    if original == 'employee-sftp':
        return args + ['-T', '-s', target, 'sftp']
    return args + (['-tt'] if tty else ['-T']) + [target]


def main():
    try:
        account = pwd.getpwuid(os.getuid()).pw_name
        if not re.fullmatch(r'ed-[a-z0-9-]{1,25}', account):
            raise ValueError('unknown device')
        mapping = json.loads((ROOT / 'devices' / (account + '.json')).read_text())
        args = command(mapping, os.environ.get('SSH_ORIGINAL_COMMAND', ''), bool(os.environ.get('SSH_TTY')))
        term = os.environ.get('TERM', 'xterm')
        if not re.fullmatch(r'[a-zA-Z0-9+_.-]{1,64}', term):
            term = 'xterm'
        os.execve(args[0], args, {'PATH': '/usr/bin:/bin', 'HOME': '/var/empty/employee-access', 'TERM': term, 'LANG': 'C.UTF-8'})
    except (ValueError, KeyError, OSError, TypeError):
        print('Access denied.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
