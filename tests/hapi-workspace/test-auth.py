#!/usr/bin/env python3
"""Synthetic JWT, routing and real Unix HTTP boundary regressions; no cloud access."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('hapi_auth', ROOT / 'ansible/roles/hapi-control-plane/files/hapi-auth.py')
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)
ISSUER = 'https://example.cloudflareaccess.com'
AUD = 'a' * 64
ORIGIN = 'https://hapi.example.com'


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def integer(value):
    return b64(value.to_bytes((value.bit_length() + 7) // 8, 'big'))


def route(wid, number):
    return {'workspace_id': wid, 'email': wid + '@example.com', 'subject': 'subject-' + wid,
            'enabled': True, 'generation': 1, 'backend_address': f'10.77.0.{number}',
            'backend_name': wid + '.hapi.internal'}


class AuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub = cls.key.public_key().public_numbers()
        cls.jwks = {'keys': [{'kty': 'RSA', 'alg': 'RS256', 'kid': 'test-key',
                              'n': integer(pub.n), 'e': integer(pub.e)}]}

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='hapi-auth-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = {'origin': ORIGIN, 'issuer': ISSUER, 'audience': AUD,
                       'routes': [route('alice', 2), route('bob', 3)]}
        self.config_file = self.root / 'config.json'
        self.save()
        self.loads = 0
        def load():
            self.loads += 1
            return self.jwks
        self.verifier = auth.AccessVerifier(ISSUER, AUD, load)
        self.policy = auth.Policy(self.config_file, self.verifier)
        self.addCleanup(self.policy.database.close)

    def save(self):
        self.config_file.write_text(json.dumps(self.config))

    def token(self, wid='alice', header=None, **overrides):
        claims = {'iss': ISSUER, 'aud': [AUD], 'sub': 'subject-' + wid,
                  'email': wid + '@example.com', 'iat': time.time() - 1, 'exp': time.time() + 300}
        claims.update(overrides)
        first = b64(json.dumps(header or {'alg': 'RS256', 'kid': 'test-key'}).encode())
        second = b64(json.dumps(claims).encode())
        message = (first + '.' + second).encode()
        return first + '.' + second + '.' + b64(self.key.sign(message, padding.PKCS1v15(), hashes.SHA256()))

    def start(self):
        server = auth.Server(str(self.root / 'auth.sock'), auth.Handler)
        server.policy = self.policy
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return str(self.root / 'auth.sock')

    def request(self, path, token=None, method='GET', extra=None, body=b''):
        address = getattr(self, 'address', None)
        if address is None:
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
        return int(head.split()[1]), json.loads(payload), head

    def test_signed_identity_always_selects_registered_vm(self):
        for wid in ['alice', 'bob']:
            selected, identity = self.policy.identity(self.token(wid))
            self.assertEqual(selected['backend_name'], wid + '.hapi.internal')
            self.assertEqual(identity['workspace_id'], wid)
        self.assertEqual(self.loads, 1)

    def test_forged_signature_and_algorithm_confusion_are_denied(self):
        good = self.token()
        first, payload, signature = good.split('.')
        modified = json.loads(auth.unbase64(payload)); modified['sub'] = 'subject-bob'
        for token in [first + '.' + b64(json.dumps(modified).encode()) + '.' + signature,
                      self.token(header={'alg': 'HS256', 'kid': 'test-key'}),
                      self.token(header={'alg': 'none', 'kid': 'test-key'}),
                      self.token(header={'alg': 'RS256', 'kid': 'test-key', 'crit': ['x']})]:
            with self.subTest(token_digest=hashlib.sha256(token.encode()).hexdigest()[:8]):
                with self.assertRaises(auth.Denied):
                    self.verifier.verify(token)

    def test_claim_validation_rejects_real_signed_invalid_claims(self):
        for change in [{'aud': ['wrong']}, {'iss': 'https://other.cloudflareaccess.com'},
                       {'exp': time.time() - 1}, {'iat': time.time() + 60},
                       {'nbf': time.time() + 60}, {'exp': float('inf')}, {'iat': True}]:
            with self.subTest(change=list(change)):
                with self.assertRaises(auth.Denied):
                    self.verifier.verify(self.token(**change))

    def test_unknown_keys_are_rate_limited_and_expired_key_cache_fails_closed(self):
        self.verifier.verify(self.token())
        for _ in range(3):
            with self.assertRaises(auth.Denied):
                self.verifier.verify(self.token(header={'alg': 'RS256', 'kid': 'unknown'}))
        self.assertEqual(self.loads, 1)
        self.verifier.expires = 0
        with self.assertRaises(auth.Denied):
            self.verifier.verify(self.token())

    def test_disabled_or_different_subject_cannot_claim_workspace(self):
        with self.assertRaises(auth.Denied):
            self.policy.identity(self.token(sub='subject-bob'))
        self.config['routes'][0]['enabled'] = False
        self.save()
        with self.assertRaises(auth.Denied):
            self.policy.identity(self.token())
        self.policy.identity(self.token('bob'))

    def test_conflicting_or_unsafe_allocations_fail_before_use(self):
        for key, value in [('backend_address', '127.0.0.1'), ('backend_address', '169.254.169.254'),
                           ('backend_name', 'attacker.example.com'), ('workspace_id', '../bob'),
                           ('generation', True), ('subject', ''), ('namespace', '../bob'),
                           ('namespace', 'bob\r\nX-Injected: yes')]:
            candidate = copy.deepcopy(self.config)
            candidate['routes'][0][key] = value
            self.config_file.write_text(json.dumps(candidate))
            with self.subTest(key=key, value=value):
                with self.assertRaises((ValueError, auth.Denied)):
                    auth.load_config(self.config_file)
        self.config['routes'].append(copy.deepcopy(self.config['routes'][0]))
        self.save()
        with self.assertRaises(ValueError):
            auth.load_config(self.config_file)

    def test_shared_hub_ticket_exchange_uses_fixed_loopback_and_registered_namespace(self):
        self.config['shared_hub'] = True
        self.config['routes'][0]['namespace'] = 'alice'
        self.save()
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({'token': 'aaa.bbb.ccc', 'user': {'id': 1}}).encode()
        with patch.object(auth.Path, 'read_text', return_value='a' * 48), \
                patch.object(auth.http.client, 'HTTPConnection', return_value=connection) as factory, \
                patch.object(auth, 'HubConnection') as remote:
            result = self.policy.exchange(self.config['routes'][0])
        factory.assert_called_once_with('127.0.0.1', port=3006, timeout=8)
        remote.assert_not_called()
        headers = connection.request.call_args.kwargs['headers']
        self.assertEqual(headers['X-Hapi-Expected-Namespace'], 'alice')
        self.assertEqual(result['token'], 'aaa.bbb.ccc')
        connection.close.assert_called_once()

    def test_shared_hub_identities_cannot_share_a_namespace_by_omission(self):
        self.config['shared_hub'] = True
        self.save()
        with self.assertRaises(ValueError):
            auth.load_config(self.config_file)
        self.config['routes'][1]['namespace'] = 'bob'
        self.save()
        auth.load_config(self.config_file)

    def test_csrf_binds_identity_route_generation_and_process(self):
        alice, bob = self.token(), self.token('bob')
        _, context = self.policy.identity(alice)
        csrf = self.policy.csrf(alice, context)
        self.assertNotEqual(csrf, self.policy.csrf(bob, context))
        self.assertNotEqual(csrf, self.policy.csrf(alice, {**context, 'generation': 2}))
        other = auth.Policy(self.config_file, self.verifier)
        self.addCleanup(other.database.close)
        self.assertNotEqual(csrf, other.csrf(alice, context))

    def test_http_anonymous_and_forged_routing_headers_are_rejected_or_ignored(self):
        self.assertEqual(self.request('/authorize', extra={'X-Hapi-Method': 'GET'})[0], 403)
        status, _, headers = self.request('/authorize', self.token(), extra={
            'X-Hapi-Method': 'GET', 'X-Hapi-Upstream': 'hapi_bob',
            'Cf-Access-Authenticated-User-Email': 'bob@example.com'})
        self.assertEqual(status, 200)
        self.assertIn(b'X-Hapi-Upstream: hapi_alice', headers)
        self.assertNotIn(b'X-Hapi-Upstream: hapi_bob', headers)

    def test_http_wrong_origin_mutations_and_websocket_are_denied(self):
        for method, origin, upgrade in [('POST', None, ''), ('GET', 'https://evil.example', ''),
                                         ('GET', None, 'websocket'), ('TRACE', ORIGIN, '')]:
            extra = {'X-Hapi-Method': method, 'Upgrade': upgrade}
            if origin:
                extra['Origin'] = origin
            self.assertEqual(self.request('/authorize', self.token(), extra=extra)[0], 403)
        self.assertEqual(self.request('/authorize', self.token(), extra={
            'X-Hapi-Method': 'POST', 'Origin': ORIGIN})[0], 200)

    def test_ticket_exchange_uses_owner_and_rechecks_disable_before_reply(self):
        token = self.token()
        status, identity, headers = self.request('/_workspace/identity', token)
        self.assertEqual(status, 200)
        self.assertIn(b'Cache-Control: no-store', headers)
        calls = []
        def exchange(route):
            calls.append(route['workspace_id'])
            return {'token': 'test.ticket.signature', 'user': {'id': 1}}
        self.policy.exchange = exchange
        extra = {'Origin': ORIGIN, 'Content-Type': 'application/json', 'X-Hapi-CSRF': identity['csrf']}
        status, result, _ = self.request('/_workspace/session', token, 'POST', extra, b'{}')
        self.assertEqual((status, calls), (200, ['alice']))
        self.assertEqual(result['workspace']['workspace_id'], 'alice')
        self.assertEqual(self.request('/_workspace/session', self.token('bob'), 'POST', extra, b'{}')[0], 403)
        def disable(_route):
            self.config['routes'][0]['enabled'] = False; self.save()
            return {'token': 'test.ticket.signature', 'user': {'id': 1}}
        self.policy.exchange = disable
        self.assertEqual(self.request('/_workspace/session', token, 'POST', extra, b'{}')[0], 403)

    def test_session_cannot_choose_target_or_echo_upstream_secrets(self):
        token = self.token()
        _, identity, _ = self.request('/_workspace/identity', token)
        extra = {'Origin': ORIGIN, 'Content-Type': 'application/json', 'X-Hapi-CSRF': identity['csrf']}
        self.assertEqual(self.request('/_workspace/session', token, 'POST', extra, b'{"vmid": 502}')[0], 403)
        def failure(_route):
            raise OSError('SYNTHETIC_SECRET_SENTINEL')
        self.policy.exchange = failure
        status, result, _ = self.request('/_workspace/session', token, 'POST', extra, b'{}')
        self.assertEqual(status, 503)
        self.assertNotIn('SYNTHETIC_SECRET_SENTINEL', json.dumps(result))

    def test_signed_stream_leases_are_bound_to_owner_allocation_and_expiry(self):
        token = self.token()
        route, _ = self.policy.identity(token)
        value = self.policy.lease(route, token)
        record = self.policy.read_lease(value, 'alice')
        with self.assertRaises(auth.Denied): self.policy.read_lease(value, 'bob')
        with self.assertRaises(auth.Denied): self.policy.read_lease(value[:-1]+'x', 'alice')
        self.config['routes'][0]['generation'] = 2; self.save()
        with self.assertRaises(auth.Denied): self.policy.check_lease(record)
        self.config['routes'][0]['generation'] = 1; self.save()
        record['exp'] = time.time()-1
        with self.assertRaises(auth.Denied): self.policy.check_lease(record)

    def test_current_assertion_logout_persists_and_does_not_disable_another_device(self):
        path = self.root/'revoked.sqlite3'
        first = auth.Policy(self.config_file, self.verifier, revocations=path)
        token = self.token()
        first.logout(token); first.database.close()
        second = auth.Policy(self.config_file, self.verifier, revocations=path)
        self.addCleanup(second.database.close)
        with self.assertRaises(auth.Denied): second.identity(token)
        second.identity(self.token(iat=time.time()-2))
        second.identity(self.token('bob'))

    def test_private_stream_sockets_remain_group_reachable_under_daemon_umask(self):
        spec = importlib.util.spec_from_file_location('stream_guard_modes', ROOT/'ansible/roles/hapi-control-plane/files/hapi-stream-guard.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        manager = module.StreamManager(self.policy, self.root/'routes', self.root/'bridges')
        mask = os.umask(0o077)
        try:
            manager.start()
            self.assertEqual((self.root/'routes').stat().st_mode & 0o777, 0o750)
            self.assertEqual((self.root/'routes/alice.sock').stat().st_mode & 0o777, 0o660)
        finally:
            os.umask(mask); manager.close()

    def test_prototype_health_does_not_claim_public_readiness(self):
        status, result, _ = self.request('/health')
        self.assertEqual(status, 200)
        self.assertFalse(result['public_ready'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
