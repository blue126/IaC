#!/usr/bin/env python3
"""Bind synthetic signed Access identities; no real identities or cloud writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import socket
import time
import unittest

spec = importlib.util.spec_from_file_location('fixtures', Path(__file__).with_name('test-auth.py'))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
auth = fixtures.auth


class EnrollmentTest(unittest.TestCase):
    setUpClass = classmethod(fixtures.AuthTest.setUpClass.__func__)
    save = fixtures.AuthTest.save
    token = fixtures.AuthTest.token
    start = fixtures.AuthTest.start

    def request(self, path, token=None, method='GET', extra=None, body=b''):
        if not getattr(self, 'address', None):
            self.address = self.start()
        headers = {'Host': 'hapi.example.com', 'Connection': 'close'}
        if token is not None:
            headers['Cf-Access-Jwt-Assertion'] = token
        headers.update(extra or {})
        if method == 'POST':
            headers.setdefault('Content-Length', str(len(body)))
        raw = (f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in headers.items()) + '\r\n').encode() + body
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(3)
            connection.connect(self.address)
            connection.sendall(raw)
            result = b''
            while chunk := connection.recv(65536):
                result += chunk
        head, payload = result.split(b'\r\n\r\n', 1)
        return int(head.split()[1]), head, payload

    def setUp(self):
        fixtures.AuthTest.setUp(self)
        self.config['shared_hub'] = True
        for route in self.config['routes']:
            route['namespace'] = route['workspace_id']
        self.nonce = '1' * 64
        self.entry = {'workspace_id': 'charlie', 'email': 'charlie@example.com', 'request_id': 'a' * 32,
                      'generation': 1, 'nonce_sha256': hashlib.sha256(self.nonce.encode()).hexdigest(),
                      'expires_at': int(time.time()) + 600}
        self.config['enrollments'] = [self.entry]
        self.path = '/_workspace/enroll/' + self.nonce
        self.save()

    def get(self, token=None):
        return self.request(self.path, token=token or self.token('charlie'))

    def confirm(self, token=None, csrf=None, extra=None):
        token = token or self.token('charlie')
        if csrf is None:
            status, _, body = self.request(self.path, token=token)
            self.assertEqual(status, 200)
            csrf = re.search(rb'name="csrf" value="([a-f0-9]+)"', body).group(1).decode()
        headers = {'Origin': fixtures.ORIGIN, 'Content-Type': 'application/x-www-form-urlencoded'}
        headers.update(extra or {})
        return self.request(self.path, token=token, method='POST', extra=headers, body=('csrf=' + csrf).encode())

    def test_get_is_read_only_and_post_binds_only_verified_claims(self):
        status, headers, body = self.get()
        self.assertEqual(status, 200)
        self.assertIn(b'no-store', headers)
        self.assertNotIn(b'charlie@example.com', body)
        self.assertEqual(self.policy.database.execute('SELECT count(*) FROM verified_enrollments').fetchone()[0], 0)
        self.assertEqual(self.confirm()[0], 303)
        row = self.policy.database.execute('SELECT email,subject,request_id,issuer,audience FROM verified_enrollments').fetchone()
        self.assertEqual(row, ('charlie@example.com', 'subject-charlie', 'a' * 32, fixtures.ISSUER, fixtures.AUD))
        self.assertEqual(self.get()[0], 202)
        self.assertEqual(self.request('/_workspace/identity', token=self.token('charlie'))[0], 403)
        self.assertEqual(self.request('/_workspace/identity', token=self.token('bob'))[0], 200)

    def test_wrong_identity_signature_expiry_and_nonce_are_rejected(self):
        for token in [self.token('bob'), self.token('charlie', exp=time.time() - 10),
                      self.token('charlie', header={'alg': 'none', 'kid': 'test-key'})]:
            self.assertEqual(self.get(token)[0], 403)
        self.assertEqual(self.request('/_workspace/enroll/' + '2' * 64, token=self.token('charlie'))[0], 403)
        self.entry['expires_at'] = int(time.time()) - 1
        self.save()
        self.assertEqual(self.get()[0], 403)

    def test_origin_csrf_and_form_encoding_are_checked_before_binding(self):
        self.assertEqual(self.confirm(csrf='0' * 64)[0], 403)
        self.assertEqual(self.confirm(csrf='%E3%81%82')[0], 403)
        self.assertEqual(self.confirm(extra={'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(self.confirm(extra={'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.policy.database.execute('SELECT count(*) FROM verified_enrollments').fetchone()[0], 0)

    def test_bound_nonce_cannot_be_reassigned_and_promotion_redirects_to_unified_entry(self):
        token = self.token('charlie')
        self.assertEqual(self.confirm(token)[0], 303)
        self.assertEqual(self.get(self.token('charlie', sub='different-subject'))[0], 403)
        route = fixtures.route('charlie', 4)
        route['namespace'] = 'charlie'
        self.config['enrollments'] = []
        self.config['routes'].append(route)
        self.save()
        status, headers, _ = self.get(token)
        self.assertEqual(status, 303)
        self.assertIn(b'Location: /\r\n', headers)
        self.assertEqual(self.request('/_workspace/identity', token=token)[0], 200)
        route['enabled'] = False
        self.save()
        self.assertEqual(self.get(token)[0], 403)

    def test_existing_owner_subject_cannot_claim_a_pending_other_workspace(self):
        self.assertEqual(self.confirm(token=self.token('charlie', sub='subject-alice'), csrf='0' * 64)[0], 403)
        with self.assertRaises(auth.Denied):
            self.policy.enrollment(self.token('charlie', sub='subject-alice'), self.nonce, bind=True)
        self.assertEqual(self.policy.database.execute('SELECT count(*) FROM verified_enrollments').fetchone()[0], 0)

    def test_duplicate_confirmation_is_idempotent_and_shared_subject_cannot_bind_twice(self):
        token = self.token('charlie', sub='shared-subject')
        self.assertEqual(self.confirm(token)[0], 303)
        # A repeated POST uses the already bound proof and creates no second row.
        csrf = self.policy.csrf(token, {'enrollment': self.entry['nonce_sha256']})
        self.assertEqual(self.confirm(token, csrf)[0], 303)
        nonce = '3' * 64
        self.config['enrollments'].append({**self.entry, 'workspace_id': 'dana', 'email': 'dana@example.com',
            'request_id': 'b' * 32, 'nonce_sha256': hashlib.sha256(nonce.encode()).hexdigest()})
        self.save()
        with self.assertRaises(auth.Denied):
            self.policy.enrollment(self.token('dana', sub='shared-subject'), nonce, bind=True)
        self.assertEqual(self.policy.database.execute('SELECT count(*) FROM verified_enrollments').fetchone()[0], 1)

    def test_proof_survives_policy_restart_without_rebinding(self):
        path = self.root / 'bindings.sqlite3'
        policy = auth.Policy(self.config_file, self.verifier, revocations=path)
        policy.enrollment(self.token('charlie'), self.nonce, bind=True)
        policy.database.close()
        restarted = auth.Policy(self.config_file, self.verifier, revocations=path)
        self.addCleanup(restarted.database.close)
        self.assertEqual(restarted.enrollment(self.token('charlie'), self.nonce), 'pending')
        with self.assertRaises(auth.Denied):
            restarted.enrollment(self.token('charlie', sub='another-subject'), self.nonce, bind=True)

    def test_invalid_pending_config_cannot_overlap_active_owner(self):
        self.entry['email'] = 'alice@example.com'
        self.save()
        with self.assertRaises(ValueError):
            auth.load_config(self.config_file)


if __name__ == '__main__':
    unittest.main()
