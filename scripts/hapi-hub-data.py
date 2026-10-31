#!/usr/bin/env python3
"""Create and import consistent Hub-only SQLite snapshots without stopping services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import sqlite3
import subprocess
import time

FILES = ('hapi.db', 'settings.json', 'owner-id.json', 'jwt-secret.json')
SERVICES = ('employee-hapi-hub', 'hapi-shared-hub')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('Expected a regular Hub data file')


def stopped(service):
    result = subprocess.run(['systemctl', 'show', service, '--property=LoadState,ActiveState,MainPID'],
                            capture_output=True, text=True, check=True)
    state = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if state.get('LoadState') != 'loaded' or state.get('ActiveState') not in {'inactive', 'failed'} or state.get('MainPID') != '0':
        raise ValueError('Hub service must be stopped before final migration')


def database_summary(path):
    regular(path)
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        summary = {'tables': {}, 'namespaces': {}}
        for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', table):
                raise ValueError('Unexpected SQLite table identifier')
            summary['tables'][table] = connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            if 'namespace' in columns:
                summary['namespaces'][table] = dict(connection.execute(
                    f'SELECT namespace, count(*) FROM "{table}" GROUP BY namespace ORDER BY namespace'))
        summary['user_version'] = connection.execute('PRAGMA user_version').fetchone()[0]
        return summary


def snapshot(source, destination, service, final):
    source, destination = Path(source).resolve(), Path(destination)
    if destination.exists():
        raise ValueError('Refuse to overwrite an existing snapshot')
    if final:
        stopped(service)
    for name in FILES:
        regular(source / name)
    destination.mkdir(mode=0o700, parents=False)
    os.chmod(destination, 0o700)
    database = destination / 'hapi.db'
    with sqlite3.connect((source / 'hapi.db').as_uri() + '?mode=ro', uri=True) as reader:
        with sqlite3.connect(database) as writer:
            reader.backup(writer, pages=256, sleep=0.05)
            writer.execute('PRAGMA journal_mode=DELETE')
    os.chmod(database, 0o600)
    for name in FILES[1:]:
        shutil.copyfile(source / name, destination / name)
        os.chmod(destination / name, 0o600)
    if final:
        stopped(service)
    manifest = {'version': 1, 'final': final, 'source_service': service, 'created_at': int(time.time()),
                'files': {name: {'sha256': sha(destination / name), 'size': (destination / name).stat().st_size} for name in FILES},
                'database': database_summary(database)}
    manifest['snapshot_id'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    marker = destination / 'migration.json'
    marker.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    os.chmod(marker, 0o600)
    return {'snapshot_id': manifest['snapshot_id'], 'final': final, 'database': manifest['database']}


def checked_snapshot(source):
    source = Path(source)
    regular(source / 'migration.json')
    manifest = json.loads((source / 'migration.json').read_bytes())
    expected_id = manifest.pop('snapshot_id')
    actual_id = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    manifest['snapshot_id'] = expected_id
    if (actual_id != expected_id or manifest.get('version') != 1 or manifest.get('final') is not True or
            set(manifest['files']) != set(FILES) or set(path.name for path in source.iterdir()) != set(FILES) | {'migration.json'}):
        raise ValueError('Final snapshot manifest mismatch')
    for name in FILES:
        regular(source / name)
        if sha(source / name) != manifest['files'][name]['sha256']:
            raise ValueError('Snapshot file checksum mismatch')
    if database_summary(source / 'hapi.db') != manifest['database']:
        raise ValueError('Snapshot database summary mismatch')
    return manifest


def install(source, destination, service, owner):
    source, destination = Path(source).resolve(), Path(destination)
    if destination.is_symlink():
        raise ValueError('Refuse a symlink data directory')
    manifest = checked_snapshot(source)
    marker = destination / 'migration.json'
    if marker.exists():
        regular(marker)
        if json.loads(marker.read_bytes()) != manifest:
            raise ValueError('Different snapshot already imported')
        # Never overwrite a database that the new Hub may have changed.
        database_summary(destination / 'hapi.db')
        return {'snapshot_id': manifest['snapshot_id'], 'status': 'already_imported'}
    stopped(service)
    account = pwd.getpwnam(owner)
    destination.mkdir(mode=0o700, parents=False, exist_ok=True)
    if set(path.name for path in destination.iterdir()) - set(FILES):
        temporary = {f'.hapi-import-{manifest["snapshot_id"]}-{name}' for name in FILES}
        if set(path.name for path in destination.iterdir()) - set(FILES) - temporary:
            raise ValueError('Unexpected files in target data directory')
    # Reject all conflicts before creating any target files.
    for name in FILES:
        target = destination / name
        if target.exists() or target.is_symlink():
            regular(target)
            if sha(target) != manifest['files'][name]['sha256']:
                raise ValueError('Refuse to overwrite different target data')
    for name in FILES:
        target = destination / name
        if target.exists() or target.is_symlink():
            regular(target)
            if sha(target) != manifest['files'][name]['sha256']:
                raise ValueError('Refuse to overwrite different target data')
        else:
            # Publish complete files exclusively. A crash leaves only a private,
            # snapshot-bound temporary file that the next attempt can resume.
            partial = destination / f'.hapi-import-{manifest["snapshot_id"]}-{name}'
            fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, 'wb') as output, (source / name).open('rb') as reader:
                    shutil.copyfileobj(reader, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.link(partial, target)
            finally:
                partial.unlink(missing_ok=True)
        os.chmod(target, 0o600)
        os.chown(target, account.pw_uid, account.pw_gid)
    if database_summary(destination / 'hapi.db') != manifest['database']:
        raise ValueError('Imported database differs from source snapshot')
    stopped(service)
    with marker.open('x') as output:
        output.write(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        output.flush()
        os.fsync(output.fileno())
    os.chmod(marker, 0o600)
    os.chown(marker, account.pw_uid, account.pw_gid)
    os.chmod(destination, 0o700)
    os.chown(destination, account.pw_uid, account.pw_gid)
    return {'snapshot_id': manifest['snapshot_id'], 'status': 'imported', 'database': manifest['database']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    backup = actions.add_parser('snapshot')
    backup.add_argument('--source', required=True)
    backup.add_argument('--destination', required=True)
    backup.add_argument('--service', choices=SERVICES, required=True)
    backup.add_argument('--final', action='store_true')
    restore = actions.add_parser('install')
    restore.add_argument('--source', required=True)
    restore.add_argument('--destination', required=True)
    restore.add_argument('--service', choices=SERVICES, required=True)
    restore.add_argument('--owner', required=True)
    args = parser.parse_args()
    if args.action == 'snapshot':
        result = snapshot(args.source, args.destination, args.service, args.final)
    else:
        result = install(args.source, args.destination, args.service, args.owner)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        os.umask(0o077)
        main()
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, subprocess.CalledProcessError):
        raise SystemExit('Hub data migration rejected; existing data retained') from None
