#!/usr/bin/env python3
"""Exercise real CSR signing, two-way TLS and recoverable certificate publication."""
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('pki', ROOT / 'ansible/roles/hapi-pki-agent/files/hapi-pki.py')
pki = importlib.util.module_from_spec(spec);spec.loader.exec_module(pki)


def key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def make_authority(label):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'synthetic-' + label)])
    at = pki.now()
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(at - dt.timedelta(days=1)).not_valid_after(at + dt.timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True).sign(key, hashes.SHA256()))
    revoked = x509.RevokedCertificateBuilder().serial_number(42).revocation_date(at - dt.timedelta(days=2)).build()
    crl = (x509.CertificateRevocationListBuilder().issuer_name(subject).last_update(at - dt.timedelta(days=31))
        .next_update(at + dt.timedelta(days=59)).add_revoked_certificate(revoked)
        .add_extension(x509.CRLNumber(1), critical=False).sign(key, hashes.SHA256()))
    return key, {'certificate': pki.pem(certificate), 'crl': pki.pem(crl)}


class PeerHandler(pki.Handler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Length', '2');self.end_headers();self.wfile.write(b'{}')

    def do_POST(self):
        if self.path == '/_hapi_pki/op':
            self.path = '/op'
        super().do_POST()


class TLSHost(ThreadingHTTPServer):
    daemon_threads = True
    def get_request(self):
        connection, address = super().get_request()
        files = self.agent.files(self.ident)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(files['certificate']), str(files['key']))
        context.load_verify_locations(cafile=str(files['ca']));context.load_verify_locations(cafile=str(files['crl']))
        context.verify_mode = ssl.CERT_REQUIRED;context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
        connection.settimeout(10)
        try:
            return context.wrap_socket(connection, server_side=True), address
        except Exception:
            connection.close();raise


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hapi-pki-test-');self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.keys, self.authorities = {}, {}
        for ident in ['hub', 'login']:
            self.keys[ident], self.authorities[ident] = make_authority(ident)
        self.profiles = {}
        definitions = [('gateway-client', 'hapi-control-plane', [], []), ('hub-server', 'hapi-hub.internal', ['hapi-hub.internal'], ['10.77.0.1']),
                       ('hub-client', 'hapi-vm502', [], []), ('login-server', 'vm502.hapi.internal', ['vm502.hapi.internal'], ['10.77.0.2'])]
        self.leaf_keys = {}
        for ident, cn, dns, ips in definitions:
            issuer = 'hub' if ident.startswith('hub-') else 'login'
            self.profiles[ident] = {'id': ident, 'authority': issuer, 'cn': cn, 'dns': dns, 'ips': ips,
                                   'ca_spki': pki.spki(self.keys[issuer].public_key())}
            self.leaf_keys[ident] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.agents = {};self.reloads = []
        for role in ['control', 'worker']:
            profiles = [p for p in self.profiles.values() if pki.SLOTS[p['id']][0] == role]
            config = {'version': 1, 'role': role, 'profiles': profiles, 'probe': {
                'address': '10.77.0.2' if role == 'control' else '10.77.0.1',
                'name': 'vm502.hapi.internal' if role == 'control' else 'hapi-hub.internal'}}
            agent = pki.Agent(config, self.root / role, runner=self.reloads.append);self.agents[role] = agent
            for p in profiles:
                runtime = agent.path(pki.SLOTS[p['id']][5]);runtime.mkdir(parents=True, exist_ok=True)
                (runtime / 'nginx.pid').write_text(str(os.getpid()))
                key = self.leaf_keys[p['id']];csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, p['cn'])]))
                names = [x509.DNSName(n) for n in p['dns']] + [x509.IPAddress(pki.ipaddress.ip_address(ip)) for ip in p['ips']]
                if names:
                    csr = csr.add_extension(x509.SubjectAlternativeName(names), critical=False)
                certificate = pki.issue(self.authorities[p['authority']], self.keys[p['authority']], pki.pem(csr.sign(key, hashes.SHA256())), p, pki.now())
                files = agent.files(p['id']);files['key'].parent.mkdir(parents=True, mode=0o750, exist_ok=True)
                for name, data in {'key': key_pem(key), 'certificate': certificate.encode(),
                                   'ca': self.authorities[p['authority']]['certificate'].encode(), 'crl': self.authorities[p['authority']]['crl'].encode()}.items():
                    files[name].write_bytes(data);files[name].chmod(0o640)
        self.unix = self.root / 'agent.sock'
        server = pki.Server(str(self.unix), pki.Handler);server.agent = self.agents['control']
        self.start(server)
        self.aliases = {}
        for role, ident, address in [('control', 'hub-server', '10.77.0.1'), ('worker', 'login-server', '10.77.0.2')]:
            server = TLSHost(('127.0.0.1', 0), PeerHandler);server.agent = self.agents[role];server.ident = ident
            self.start(server);self.aliases[address] = ('127.0.0.1', server.server_address[1])
        real_connect = socket.create_connection
        self.addCleanup(patch.stopall)
        patch.object(pki.socket, 'create_connection', side_effect=lambda address, *a, **k: real_connect(self.aliases.get(address[0], address), *a, **k)).start()
        unix_type = pki.UnixConnection
        patch.object(pki, 'UnixConnection', side_effect=lambda ignored: unix_type(self.unix)).start()
        credentials = self.root / 'credentials';credentials.mkdir()
        for name, source in [('control-client.pem', 'certificate'), ('control-client.key', 'key')]:
            (credentials / name).write_bytes(self.agents['control'].files('gateway-client')[source].read_bytes())
            (credentials / name).chmod(0o600)
        patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': str(credentials)}).start()
        self.config = {'version': 1, 'authorities': self.authorities, 'targets': [
            {'id': 'control', 'profiles': self.agents['control'].config['profiles']},
            {'id': 'worker', 'profiles': self.agents['worker'].config['profiles'], 'address': '10.77.0.2', 'name': 'vm502.hapi.internal'}]}
        self.controller = pki.Controller(self.config, self.root / 'controller', self.keys)

    def start(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)

    def snapshot(self):
        return {ident: {name: path.read_bytes() for name, path in agent.files(ident).items()}
                for agent in self.agents.values() for ident in agent.profiles}

    def test_one_year_leaves_five_year_ca_and_six_month_crl_over_real_mutual_tls(self):
        before = self.snapshot();result = self.controller.run();self.assertTrue(result['changed'])
        after = self.snapshot()
        for ident, values in after.items():
            self.assertEqual(values['key'], before[ident]['key'])
            leaf = x509.load_pem_x509_certificate(values['certificate'])
            ca = x509.load_pem_x509_certificate(values['ca']);crl = x509.load_pem_x509_crl(values['crl'])
            self.assertGreater(pki.date(leaf, 'not_valid_after'), pki.now() + dt.timedelta(days=364))
            self.assertGreater(pki.date(ca, 'not_valid_after'), pki.now() + dt.timedelta(days=1824))
            self.assertGreater(pki.date(crl, 'next_update'), pki.now() + dt.timedelta(days=179))
            self.assertIn(42, [r.serial_number for r in crl])
        self.assertNotIn('PRIVATE KEY', (self.controller.root / 'transaction.json').read_text())
        self.assertNotIn('PRIVATE KEY', (self.controller.root / 'authorities.json').read_text())
        self.assertTrue(pki.read(self.controller.root / 'health.json')['ok'])
        self.assertEqual(len(self.reloads), 8)

    def test_second_hour_checks_are_idempotent(self):
        self.controller.run();before = self.snapshot();count = len(self.reloads)
        self.assertFalse(self.controller.run()['changed'])
        self.assertEqual(before, self.snapshot());self.assertEqual(len(self.reloads), count)

    def test_lost_activation_receipt_rolls_back_then_retries_the_same_generation(self):
        before = self.snapshot();original = pki.Transport.call;lost = []
        def reply(transport, target, request):
            result = original(transport, target, request)
            if target['id'] == 'worker' and request['action'] == 'activate' and not lost:
                lost.append(True);raise OSError('synthetic lost response')
            return result
        with patch.object(pki.Transport, 'call', reply):
            with self.assertRaisesRegex(ValueError, 'rollout-not-verified'):
                self.controller.run()
        self.assertEqual(before, self.snapshot())
        transaction = pki.read(self.controller.root / 'transaction.json')
        self.assertEqual(transaction['status'], 'retryable')
        self.assertEqual(self.controller.run()['generation'], transaction['id'])

    def test_wrong_csr_name_is_refused_without_publishing(self):
        p = self.profiles['hub-client'];key = self.leaf_keys['hub-client']
        csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'hapi-control-plane')])).sign(key, hashes.SHA256())
        with self.assertRaises(ValueError):
            pki.issue(self.authorities['hub'], self.keys['hub'], pki.pem(csr), p, pki.now())

    def test_unapproved_authority_pin_and_file_paths_are_not_accepted(self):
        bad = self.profiles['hub-client'] | {'ca_spki': '0' * 64}
        with self.assertRaises(ValueError):
            pki.issue(self.authorities['hub'], self.keys['hub'], self.agents['worker'].inspect()['materials']['hub-client']['csr'], bad, pki.now())
        with self.assertRaises(ValueError):
            self.agents['worker'].operation({'action': 'inspect', 'path': '/etc/shadow'})

    def test_unknown_certificate_changes_are_not_overwritten(self):
        self.controller.run()
        transaction = pki.read(self.controller.root / 'transaction.json')
        agent = self.agents['worker'];files = agent.files('hub-client')
        files['certificate'].write_bytes(self.snapshot()['login-server']['certificate'])
        with self.assertRaises(ValueError):
            agent.operation({'action': 'rollback', 'generation': transaction['id']})

    def test_corrupt_or_mismatched_signing_key_cannot_publish(self):
        self.controller.keys['hub'] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.controller.run()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(pki.read(self.controller.root / 'health.json')['ok'])

    def test_temporary_old_nginx_worker_is_rechecked_before_rollback(self):
        original = pki.Agent.probe;attempts = []
        def probe(agent, expected):
            if agent.config['role'] == 'control' and len(attempts) < 2:
                attempts.append(True);raise ValueError('synthetic old worker certificate')
            return original(agent, expected)
        with patch.object(pki.Agent, 'probe', probe):
            self.assertTrue(self.controller.run()['ok'])
        self.assertEqual(len(attempts), 2)

    def test_ca_private_material_is_not_accepted_as_public_configuration(self):
        config = copy.deepcopy(self.config)
        config['authorities']['hub']['certificate'] = key_pem(self.keys['hub']).decode()
        with self.assertRaises(ValueError):
            pki.controller_config(config)

    def test_unreviewed_revocation_change_is_not_undone_by_the_renewal_loop(self):
        self.controller.run();before = self.snapshot()
        state = pki.read(self.controller.root / 'authorities.json')
        ca = x509.load_pem_x509_certificate(state['hub']['certificate'].encode())
        old = x509.load_pem_x509_crl(state['hub']['crl'].encode())
        entry = x509.RevokedCertificateBuilder().serial_number(43).revocation_date(pki.now() - dt.timedelta(minutes=1)).build()
        builder = x509.CertificateRevocationListBuilder().issuer_name(ca.subject).last_update(pki.now() - dt.timedelta(minutes=1)).next_update(pki.now() + dt.timedelta(days=180))
        for row in [*old, entry]:builder = builder.add_revoked_certificate(row)
        state['hub']['crl'] = pki.pem(builder.sign(self.keys['hub'], hashes.SHA256()))
        pki.save(self.controller.root / 'authorities.json', state)
        with self.assertRaisesRegex(ValueError, 'revocation-change-needs'):
            self.controller.run()
        self.assertEqual(self.snapshot(), before)
        self.assertIn(43, [row.serial_number for row in x509.load_pem_x509_crl(pki.read(self.controller.root / 'authorities.json')['hub']['crl'].encode())])

    def test_forged_existing_leaf_is_not_used_to_obtain_a_valid_renewal(self):
        ident = 'hub-client';agent = self.agents['worker'];p = self.profiles[ident]
        forged_ca = x509.load_pem_x509_certificate(self.authorities['hub']['certificate'].encode())
        fake_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = agent.inspect()['materials'][ident]['csr']
        bad_profile = p | {'ca_spki': pki.spki(fake_key.public_key())}
        # Preserve subject and original leaf key, but sign with an untrusted CA key.
        fake_root = (x509.CertificateBuilder().subject_name(forged_ca.subject).issuer_name(forged_ca.subject)
            .public_key(fake_key.public_key()).serial_number(100).not_valid_before(pki.now() - dt.timedelta(days=1))
            .not_valid_after(pki.now() + dt.timedelta(days=730)).add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .sign(fake_key, hashes.SHA256()))
        forged = pki.issue({'certificate': pki.pem(fake_root)}, fake_key, csr, bad_profile, pki.now())
        agent.files(ident)['certificate'].write_text(forged)
        with self.assertRaises(Exception):
            self.controller.run()
        self.assertFalse((self.controller.root / 'transaction.json').exists())

    def test_failed_reload_rollback_is_reconciled_only_through_the_guarded_generation(self):
        before = self.snapshot()
        with patch.object(self.agents['control'], 'runner', side_effect=OSError('synthetic unavailable reload')):
            with self.assertRaisesRegex(ValueError, 'rollout-not-verified'):
                self.controller.run()
        plan = pki.read(self.controller.root / 'transaction.json')
        self.assertEqual(plan['status'], 'reconciliation-required')
        self.assertEqual(self.snapshot(), before)
        result = self.controller.run()
        self.assertEqual(result['generation'], plan['id'])
        self.assertTrue(result['ok'])

    def test_expired_bootstrap_crl_does_not_override_a_valid_renewed_runtime(self):
        self.controller.run()
        config = copy.deepcopy(self.config)
        for ident, authority in config['authorities'].items():
            ca = x509.load_pem_x509_certificate(authority['certificate'].encode())
            old = x509.load_pem_x509_crl(authority['crl'].encode())
            builder = (x509.CertificateRevocationListBuilder().issuer_name(ca.subject)
                .last_update(pki.now() - dt.timedelta(days=2)).next_update(pki.now() - dt.timedelta(days=1)))
            for entry in old:builder = builder.add_revoked_certificate(entry)
            authority['crl'] = pki.pem(builder.sign(self.keys[ident], hashes.SHA256()))
        controller = pki.Controller(config, self.controller.root, self.keys)
        self.assertFalse(controller.run()['changed'])

    def test_invalid_configuration_and_duplicate_slot_are_rejected(self):
        config = copy.deepcopy(self.agents['worker'].config)
        config['profiles'].append(config['profiles'][0])
        with self.assertRaises(ValueError):
            pki.Agent(config)
        config = copy.deepcopy(self.config);config['targets'][1]['address'] = '8.8.8.8'
        with self.assertRaises(ValueError):
            pki.controller_config(config)


if __name__ == '__main__':
    unittest.main()
