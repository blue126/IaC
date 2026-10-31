#!/usr/bin/python3
"""Report HAPI public PKI expiry and external network-policy drift."""
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

UTC = datetime.timezone.utc


def require(condition):
    if not condition:
        raise ValueError('Invalid HAPI health configuration')


def validate(value):
    require(isinstance(value, dict) and set(value) == {'version', 'minimum_valid_days', 'network', 'tls'})
    require(type(value['version']) is int and value['version'] == 1)
    require(type(value['minimum_valid_days']) is int and 1 <= value['minimum_valid_days'] <= 90)
    require(type(value['network']) is bool and isinstance(value['tls'], list) and len(value['tls']) <= 16)
    require(value['network'] or value['tls'])
    labels, paths = set(), set()
    for row in value['tls']:
        require(isinstance(row, dict) and set(row) == {'label', 'kind', 'path'})
        require(isinstance(row['kind'], str) and row['kind'] in {'certificate', 'crl'})
        require(isinstance(row['label'], str) and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', row['label']))
        require(isinstance(row['path'], str) and re.fullmatch(r'/[A-Za-z0-9_./-]+', row['path']))
        require('..' not in Path(row['path']).parts and row['label'] not in labels and row['path'] not in paths)
        labels.add(row['label']); paths.add(row['path'])
    return value


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    return validate(json.loads(Path(path).read_bytes(), object_pairs_hook=unique))


def execute(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=20)


def tls_check(row, days, now):
    result = {'label': row['label'], 'ok': False}
    try:
        kind = row['kind']
        argv = ['/usr/bin/openssl', 'x509' if kind == 'certificate' else 'crl', '-in', row['path'], '-noout']
        argv += ['-dates'] if kind == 'certificate' else ['-lastupdate', '-nextupdate']
        read = execute(argv)
        if read.returncode:
            raise ValueError('Unreadable public PKI material')
        dates = dict(line.split('=', 1) for line in read.stdout.splitlines())
        start, end = ('notBefore', 'notAfter') if kind == 'certificate' else ('lastUpdate', 'nextUpdate')
        def date(key):
            return datetime.datetime.strptime(dates[key], '%b %d %H:%M:%S %Y %Z').replace(tzinfo=UTC)
        begins, expires = date(start), date(end)
        result['expires_at'] = expires.isoformat()
        if begins > now or expires <= now:
            result['reason'] = 'outside-validity-period'
        elif expires <= now + datetime.timedelta(days=days):
            result['reason'] = 'expires-soon'
        else:
            result.update(ok=True, reason='valid')
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        result['reason'] = 'pki-read-or-parse-failed'
    return result


def check(value, now=None):
    validate(value)
    now = now or datetime.datetime.now(UTC)
    checks = [tls_check(row, value['minimum_valid_days'], now) for row in value['tls']]
    if value['network']:
        try:
            result = execute(['/usr/bin/python3', '/usr/local/lib/hapi-network.py', 'verify'])
            ok = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        checks.append({'label': 'network-policy', 'ok': ok, 'reason': 'verified' if ok else 'drift-or-unavailable'})
    return {'ok': all(row['ok'] for row in checks), 'checks': checks}


if __name__ == '__main__':
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--validate':
            load(sys.argv[2])
            sys.exit(0)
        require(len(sys.argv) == 2)
        result = check(load(sys.argv[1]))
        print(json.dumps(result, sort_keys=True))
        sys.exit(0 if result['ok'] else 1)
    except (ValueError, KeyError, TypeError, OSError):
        print('{"ok":false,"reason":"health-configuration-unavailable"}')
        sys.exit(1)
