#!/usr/bin/env python3
"""Exercise real SQLite WAL snapshots, guarded import and worker bindings."""
import importlib.util
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


data = module('hub_data', 'scripts/hapi-hub-data.py')
config = module('hub_config', 'ansible/roles/hapi-shared-hub/files/hapi-hub-config.py')


class HubDataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hapi-data-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir(mode=0o700)
        self.backup = self.root / 'snapshot'
        self.target = self.root / 'target'
        self.owner = pwd.getpwuid(os.getuid()).pw_name
        self.writer = sqlite3.connect(self.source / 'hapi.db')
        self.addCleanup(self.writer.close)
        self.writer.execute('PRAGMA journal_mode=WAL')
        self.writer.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, namespace TEXT)')
        self.writer.execute('CREATE TABLE messages (id TEXT PRIMARY KEY, session_id TEXT, content TEXT)')
        self.writer.execute("INSERT INTO sessions VALUES ('first', 'default')")
        self.writer.execute("INSERT INTO messages VALUES ('message-one', 'first', 'synthetic first')")
        self.writer.commit()
        for name in data.FILES[1:]:
            (self.source / name).write_text('{"synthetic": true}')
        self.stopped = patch.object(data, 'stopped')
        self.guard = self.stopped.start()
        self.addCleanup(self.stopped.stop)

    def final(self):
        return data.snapshot(self.source, self.backup, 'employee-hapi-hub', True)

    def install(self):
        return data.install(self.backup, self.target, 'hapi-shared-hub', self.owner)

    def test_live_wal_backup_includes_commits_and_excludes_uncommitted_data(self):
        self.assertGreater((self.source / 'hapi.db-wal').stat().st_size, 0)
        self.writer.execute("INSERT INTO messages VALUES ('uncommitted', 'first', 'pending')")
        result = data.snapshot(self.source, self.backup, 'employee-hapi-hub', False)
        self.assertEqual(result['database']['tables']['messages'], 1)
        self.guard.assert_not_called()
        with sqlite3.connect(self.backup / 'hapi.db') as reader:
            self.assertEqual(reader.execute('SELECT content FROM messages').fetchall(), [('synthetic first',)])
        with self.assertRaises(ValueError):
            self.install()

    def test_final_snapshot_and_import_preserve_data_and_hub_identity_files(self):
        result = self.final()
        self.assertEqual(result['database']['namespaces']['sessions'], {'default': 1})
        restored = self.install()
        self.assertEqual(restored['snapshot_id'], result['snapshot_id'])
        self.assertEqual(restored['database'], result['database'])
        for name in data.FILES:
            self.assertEqual(data.sha(self.backup / name), data.sha(self.target / name))
            self.assertEqual((self.target / name).stat().st_mode & 0o777, 0o600)
        config.migration(self.target)

    def test_active_source_refuses_final_snapshot_before_creating_files(self):
        self.guard.side_effect = ValueError('active')
        with self.assertRaises(ValueError):
            self.final()
        self.assertFalse(self.backup.exists())

    def test_active_destination_refuses_import(self):
        self.final()
        self.guard.side_effect = ValueError('active')
        with self.assertRaises(ValueError):
            self.install()
        self.assertFalse(self.target.exists())

    def test_tampered_snapshot_and_different_target_are_retained_and_rejected(self):
        self.final()
        original = (self.backup / 'settings.json').read_bytes()
        (self.backup / 'settings.json').write_text('changed')
        with self.assertRaises(ValueError):
            self.install()
        (self.backup / 'settings.json').write_bytes(original)
        self.target.mkdir()
        (self.target / 'settings.json').write_text('existing destination')
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual((self.target / 'settings.json').read_text(), 'existing destination')
        self.assertFalse((self.target / 'hapi.db').exists())

    def test_interrupted_copy_does_not_publish_partial_data_and_can_retry(self):
        self.final()
        def interrupted(reader, output):
            output.write(reader.read(11))
            raise OSError('synthetic interrupted copy')
        with patch.object(data.shutil, 'copyfileobj', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse((self.target / 'hapi.db').exists())
        self.assertFalse((self.target / 'migration.json').exists())
        # Simulate the leftover private part file after a process crash.
        manifest = data.checked_snapshot(self.backup)
        part = self.target / f'.hapi-import-{manifest["snapshot_id"]}-hapi.db'
        part.write_bytes(b'partial')
        self.assertEqual(self.install()['status'], 'imported')
        self.assertFalse(part.exists())
        self.assertEqual(data.sha(self.target / 'hapi.db'), data.sha(self.backup / 'hapi.db'))

    def test_repeated_import_does_not_overwrite_new_hub_writes(self):
        self.final()
        self.install()
        with sqlite3.connect(self.target / 'hapi.db') as writer:
            writer.execute("INSERT INTO messages VALUES ('new-on-hub', 'first', 'new write')")
        self.guard.side_effect = ValueError('new Hub is active')
        self.assertEqual(self.install()['status'], 'already_imported')
        self.assertEqual(data.database_summary(self.target / 'hapi.db')['tables']['messages'], 2)
        config.migration(self.target)

    def test_target_symlink_is_rejected_without_modifying_the_referenced_file(self):
        self.final()
        self.target.mkdir()
        protected = self.root / 'unrelated'
        protected.write_text('retain')
        (self.target / 'hapi.db').symlink_to(protected)
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(protected.read_text(), 'retain')


class HubBindingsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hapi-binding-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credentials = {'version': 1, 'credentials': [
            {'id': 'alice', 'namespace': 'default', 'token': 'a' * 48, 'generation': 1, 'enabled': True},
            {'id': 'bob', 'namespace': 'bob', 'token': 'b' * 48, 'generation': 1, 'enabled': True}]}
        self.agents = {'version': 1, 'agents': [
            {'id': 'worker-alice', 'address': '10.77.0.2', 'credential_id': 'alice', 'namespace': 'default'},
            {'id': 'worker-bob', 'address': '10.77.0.3', 'credential_id': 'bob', 'namespace': 'bob'}]}

    def save(self):
        for name, value in [('credentials', self.credentials), ('agents', self.agents)]:
            path = self.root / (name + '.json')
            path.write_text(json.dumps(value))
            path.chmod(0o640)

    def test_distinct_workers_bind_to_distinct_credentials(self):
        self.save()
        config.bindings(self.root)

    def test_old_or_unbound_signer_cannot_pass_the_service_start_guard(self):
        key = self.root / 'jwt.json'
        binding = self.root / 'signer-sha256'
        fresh = base64.b64encode(b'n' * 32).decode()
        old = base64.b64encode(b'o' * 32).decode()
        key.write_text(json.dumps({'secretBase64': fresh}))
        key.chmod(0o600)
        with self.assertRaises(ValueError):
            config.jwt(key, binding)
        binding.write_text(hashlib.sha256(fresh.encode()).hexdigest() + '\n')
        binding.chmod(0o640)
        config.jwt(key, binding)
        key.write_text(json.dumps({'secretBase64': old}))
        with self.assertRaises(ValueError):
            config.jwt(key, binding)

    def test_hub_signer_requires_exactly_one_full_strength_private_key(self):
        path = self.root / 'jwt.json'
        path.write_text(json.dumps({'secretBase64': base64.b64encode(os.urandom(32)).decode()}))
        path.chmod(0o600)
        config.jwt(path)
        for value in [{'secretBase64': base64.b64encode(b'weak').decode()}, {'secretBase64': '*invalid*'},
                      {'secretBase64': base64.b64encode(os.urandom(32)).decode(), 'unexpected': True}]:
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                config.jwt(path)
        path.write_text(json.dumps({'secretBase64': base64.b64encode(os.urandom(32)).decode()}))
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            config.jwt(path)

    def test_worker_cannot_bind_its_credential_to_another_namespace(self):
        self.agents['agents'][0]['namespace'] = 'bob'
        self.save()
        with self.assertRaises(ValueError):
            config.bindings(self.root)

    def test_duplicate_tokens_and_worker_addresses_are_rejected(self):
        self.credentials['credentials'][1]['token'] = 'a' * 48
        self.save()
        with self.assertRaises(ValueError):
            config.bindings(self.root)
        self.credentials['credentials'][1]['token'] = 'b' * 48
        self.agents['agents'][1]['address'] = '10.77.0.2'
        self.save()
        with self.assertRaises(ValueError):
            config.bindings(self.root)

    def test_world_readable_registry_and_injected_certificate_names_are_rejected(self):
        self.save()
        (self.root / 'credentials.json').chmod(0o644)
        with self.assertRaises(ValueError):
            config.bindings(self.root)
        self.agents['agents'][0]['id'] = 'worker-alice"; injected'
        self.save()
        with self.assertRaises(ValueError):
            config.bindings(self.root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
