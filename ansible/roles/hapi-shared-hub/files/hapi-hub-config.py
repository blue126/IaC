#!/usr/bin/env python3
"""Validate shared Hub configuration without exposing service credentials."""
import ipaddress
import base64
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate configuration field')
        value[key] = item
    return value


def load(path):
    path = Path(path)
    info = path.lstat()
    if not path.is_file() or path.is_symlink() or info.st_mode & 0o007 or info.st_size > 131072:
        raise ValueError('Unsafe configuration file')
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def credentials(path):
    value = load(path)
    if set(value) != {'version', 'credentials'} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Invalid credential format')
    rows = value['credentials']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
        raise ValueError('Invalid credential count')
    ids, tokens = set(), set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'token', 'namespace', 'generation', 'enabled'} or
                not matches(r'[a-z][a-z0-9_-]{0,63}', row['id']) or
                not matches(r'[A-Za-z0-9_-]{32,256}', row['token']) or
                not matches(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', row['namespace']) or
                type(row['generation']) is not int or row['generation'] < 1 or
                type(row['enabled']) is not bool or row['id'] in ids or row['token'] in tokens):
            raise ValueError('Invalid credential binding')
        ids.add(row['id'])
        tokens.add(row['token'])
    return rows


def agents(path):
    value = load(path)
    if set(value) != {'version', 'agents'} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Invalid transport format')
    rows = value['agents']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
        raise ValueError('Invalid transport count')
    ids, addresses = set(), set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'address', 'namespace', 'credential_id'} or
                not matches(r'[a-z][a-z0-9_-]{0,63}', row['id']) or
                not matches(r'[a-z][a-z0-9_-]{0,63}', row['credential_id']) or
                not matches(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', row['namespace'])):
            raise ValueError('Invalid worker binding')
        address = ipaddress.IPv4Address(row['address'])
        if not any(address in ipaddress.ip_network(cidr) for cidr in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']):
            raise ValueError('Invalid worker address')
        if row['id'] in ids or row['address'] in addresses:
            raise ValueError('Duplicate worker allocation')
        ids.add(row['id'])
        addresses.add(row['address'])
    return rows


def bindings(path):
    root = Path(path)
    rows = {row['id']: row for row in credentials(root / 'credentials.json')}
    for row in agents(root / 'agents.json'):
        credential = rows.get(row['credential_id'])
        if not credential or credential['namespace'] != row['namespace']:
            raise ValueError('Worker and credential namespace differ')


def migration(path):
    root = Path(path)
    marker = load(root / 'migration.json')
    if marker.get('version') != 1 or marker.get('final') is not True:
        raise ValueError('Final database import required')
    database = root / 'hapi.db'
    if database.is_symlink() or not database.is_file():
        raise ValueError('Imported database missing')
    # Subsequent Hub writes legitimately change the database checksum.
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('Imported database integrity failed')


def jwt(path, expected_file=None):
    value = load(path)
    if set(value) != {'secretBase64'} or not isinstance(value['secretBase64'], str):
        raise ValueError('Invalid Hub signing secret')
    if len(base64.b64decode(value['secretBase64'], validate=True)) != 32:
        raise ValueError('Invalid Hub signing secret size')
    if expected_file is not None:
        expected = Path(expected_file)
        if expected.is_symlink() or not expected.is_file() or expected.stat().st_mode & 0o007:
            raise ValueError('Missing approved signer binding')
        fingerprint = expected.read_text().strip()
        if not matches(r'[a-f0-9]{64}', fingerprint) or hashlib.sha256(value['secretBase64'].encode()).hexdigest() != fingerprint:
            raise ValueError('Hub signer differs from the approved control-plane signer')


if __name__ == '__main__':
    try:
        if len(sys.argv) == 4 and sys.argv[1] == 'jwt':
            jwt(sys.argv[2], sys.argv[3])
        elif len(sys.argv) == 3 and sys.argv[1] in {'credentials', 'agents', 'bindings', 'migration', 'jwt'}:
            globals()[sys.argv[1]](sys.argv[2])
        else:
            raise ValueError('Invalid validator command')
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error):
        raise SystemExit('Shared Hub configuration rejected') from None
