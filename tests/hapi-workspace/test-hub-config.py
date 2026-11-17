#!/usr/bin/env python3
"""Exercise the shared Hub credential, worker binding and signer guards."""
import importlib.util
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


config = module('hub_config', 'ansible/roles/hapi-shared-hub/files/hapi-hub-config.py')


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
