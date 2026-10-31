#!/usr/bin/env python3
"""Check ownership-preserving VM500 HAPI registration transformations offline."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('registration', ROOT / 'ansible/roles/hapi-registration/files/hapi-registration.py')
registration = importlib.util.module_from_spec(spec);spec.loader.exec_module(registration)


class RegistrationTest(unittest.TestCase):
    def setUp(self):
        self.bob = {'id': 'hapi-bob', 'namespace': 'workspace_bob', 'token': 'b' * 64, 'generation': 2, 'enabled': True}
        self.peer = {'id': 'hapi-bob', 'address': '10.77.0.3', 'namespace': 'workspace_bob', 'credential_id': 'hapi-bob'}
        self.alice = {'id': 'hapi-alice', 'namespace': 'workspace_alice', 'token': 'a' * 64, 'generation': 1, 'enabled': True}
        self.agent = {'id': 'hapi-alice', 'address': '10.77.0.4', 'namespace': 'workspace_alice', 'credential_id': 'hapi-alice'}

    def test_registration_preserves_other_credentials_and_is_exactly_idempotent(self):
        credentials = {'version': 1, 'credentials': [copy.deepcopy(self.bob)]}
        peers = {'version': 1, 'agents': [copy.deepcopy(self.peer)]}
        new, agents = registration.append_worker(credentials, peers, self.alice, self.agent)
        self.assertEqual(credentials['credentials'], [self.bob])
        self.assertEqual(new['credentials'][0], self.bob)
        self.assertEqual(agents['agents'][0], self.peer)
        self.assertEqual(registration.append_worker(new, agents, self.alice, self.agent), (new, agents))

    def test_unknown_credential_binding_is_not_replaced(self):
        with self.assertRaises(ValueError):
            registration.append_worker({'version': 1, 'credentials': [self.alice | {'token': 'wrong'}]},
                {'version': 1, 'agents': []}, self.alice, self.agent)
        with self.assertRaises(ValueError):
            registration.append_worker({'version': 1, 'credentials': []},
                {'version': 1, 'agents': [self.agent | {'address': '10.77.0.99'}]}, self.alice, self.agent)

    def test_transport_rewrite_is_limited_to_the_two_registered_identity_maps(self):
        text = (ROOT / 'ansible/roles/hapi-shared-hub/templates/nginx.conf.j2').read_text()
        # Remove only the rendering loops to obtain the empty-map input.
        import re
        empty = re.sub(r'{% for agent.*?{% endfor %}\n', '', text, flags=re.S)
        rendered = registration.transport_config(empty, [self.peer, self.agent])
        self.assertEqual(rendered.count('10.77.0.3|CN=hapi-bob'), 2)
        self.assertEqual(rendered.count('10.77.0.4|CN=hapi-alice'), 2)
        self.assertEqual(registration.transport_config(rendered, [self.peer, self.agent]), rendered)
        self.assertEqual(rendered[rendered.index('    server {'):], empty[empty.index('    server {'):])

    def test_pending_identity_cannot_take_an_existing_employee(self):
        config = {'routes': [{'workspace_id': 'bob', 'email': 'bob@example.invalid'}]}
        with self.assertRaises(ValueError):
            registration.pending_config(config, {'workspace_id': 'alice', 'email': 'bob@example.invalid'})

    def test_expired_ticket_can_only_be_replaced_for_the_same_request_and_identity(self):
        old = {'workspace_id': 'alice', 'email': 'alice@example.invalid', 'request_id': 'a' * 32,
               'generation': 1, 'expires_at': 1, 'nonce_sha256': 'b' * 64}
        new = old | {'expires_at': 4102444800, 'nonce_sha256': 'c' * 64}
        config = {'routes': [], 'enrollments': [old]}
        self.assertEqual(registration.pending_config(config, new)['enrollments'], [new])
        for changed in [{'request_id': 'd' * 32}, {'email': 'other@example.invalid'}, {'generation': 2}]:
            with self.assertRaises(ValueError):
                registration.pending_config(config, new | changed)
        with self.assertRaises(ValueError):
            registration.pending_config({'routes': [], 'enrollments': [old | {'expires_at': 4102444800}]}, new)

    def test_activation_uses_verified_subject_and_preserves_other_route(self):
        bob = {'workspace_id': 'bob', 'email': 'bob@example.invalid', 'subject': 'signed-bob', 'generation': 2, 'enabled': True}
        alice = {'workspace_id': 'alice', 'email': 'alice@example.invalid', 'subject': 'signed-alice', 'generation': 1, 'enabled': True}
        config = {'routes': [bob], 'enrollments': [{'workspace_id': 'alice'}, {'workspace_id': 'dana'}]}
        proof = {k: alice[k] for k in ['workspace_id', 'email', 'subject', 'generation']}
        out = registration.active_config(config, alice, proof)
        self.assertEqual(out['routes'], [bob, alice])
        self.assertEqual(out['enrollments'], [{'workspace_id': 'dana'}])
        self.assertEqual(registration.active_config(out, alice, proof), out)
        with self.assertRaises(ValueError):
            registration.active_config(config, alice | {'subject': 'guessed'}, proof)


if __name__ == '__main__':
    unittest.main()
