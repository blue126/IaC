#!/usr/bin/python3 -I
"""Dispatch authenticated device accounts without interpreting client commands."""
import ipaddress
import json
import os
import pwd
import re
import shlex
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


def mosh_command(mapping, original, policy, account=None):
    """Start Mosh with a fixed VM command; never execute the client request."""
    inner_ssh = command(mapping, '', True)
    if set(policy) not in ({'address', 'port_start', 'port_end'}, {'address', 'port_start', 'port_end', 'network_timeout'}):
        raise ValueError('invalid Mosh policy')
    ipaddress.IPv4Address(policy['address'])
    timeout = policy.get('network_timeout', 604800)
    if type(timeout) is not int or not 60 <= timeout <= 2592000:
        raise ValueError('invalid Mosh network timeout')
    start, end = policy['port_start'], policy['port_end']
    if type(start) is not int or type(end) is not int or not 60000 <= start <= end <= 61000:
        raise ValueError('invalid Mosh ports')
    try:
        requested = shlex.split(original)
    except ValueError as exc:
        raise ValueError('invalid Mosh request') from exc
    if requested[:1] == ['exec']:
        requested.pop(0)
    if requested[:1] != ['employee-mosh']:
        raise ValueError('unsupported Mosh request')
    if requested == ['employee-mosh', '--version']:
        return ['/usr/bin/mosh-server', '--version']
    if requested[1:2] == ['new']:
        options = requested[2:]
        while options:
            option = options.pop(0)
            if option == '-s':
                continue
            if option == '-c' and options and re.fullmatch(r'\d{1,3}', options[0]):
                options.pop(0)
                continue
            if option == '-l' and options and re.fullmatch(r'(?:LANG|LANGUAGE|LC_[A-Z_]+)=[A-Za-z0-9_.@+-]+', options[0]):
                options.pop(0)
                continue
            if option == '-p' and options and options[0] == f'{start}:{end}':
                options.pop(0)
                continue
            raise ValueError('unsupported Mosh option')
    elif requested[1:2] == ['-H']:
        if (len(requested) != 9 or
                not re.fullmatch(r'[A-Za-z0-9_+/=-]{1,128}', requested[2]) or
                requested[3:5] != ['-t', '-u'] or
                requested[5] not in {mapping['user'], mapping['employee'], account} or
                requested[6:] != ['--', str(start), str(end)]):
            raise ValueError('unsupported Mosh startup')
    else:
        raise ValueError('unsupported Mosh request')
    return ['/usr/bin/mosh-server', 'new', '-i', policy['address'], '-p', f'{start}:{end}',
            '-c', '256', '--', *inner_ssh]


def main():
    try:
        account = pwd.getpwuid(os.getuid()).pw_name
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,27}', account):
            raise ValueError('unknown device')
        mapping = json.loads((ROOT / 'devices' / (account + '.json')).read_text())
        original = os.environ.get('SSH_ORIGINAL_COMMAND', '')
        if original.startswith(('employee-mosh ', 'exec employee-mosh ')):
            policy = json.loads((ROOT / 'mosh-devices' / (account + '.json')).read_text())
            args = mosh_command(mapping, original, policy, account)
        else:
            args = command(mapping, original, bool(os.environ.get('SSH_TTY')))
        term = os.environ.get('TERM', 'xterm')
        if not re.fullmatch(r'[a-zA-Z0-9+_.-]{1,64}', term):
            term = 'xterm'
        env = {'PATH': '/usr/bin:/bin', 'HOME': '/var/empty/employee-access', 'TERM': term, 'LANG': 'C.UTF-8'}
        if original.startswith(('employee-mosh ', 'exec employee-mosh ')):
            env['MOSH_SERVER_NETWORK_TMOUT'] = str(policy.get('network_timeout', 604800))
        os.execve(args[0], args, env)
    except (ValueError, KeyError, OSError, TypeError):
        print('Access denied.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
