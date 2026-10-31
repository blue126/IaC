#!/usr/bin/env python3
"""Render the worker transport with real Ansible and verify loopback mTLS."""
import datetime
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import copy
import os
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

spec = importlib.util.spec_from_file_location('proxy_helpers', Path(__file__).with_name('test-proxy.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
ROOT = helpers.ROOT


class Backend(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        data = json.dumps({'path': self.path, 'headers': dict(self.headers)}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)


@unittest.skipUnless(shutil.which('nginx') and shutil.which('ansible'), 'requires approved Sandbox proxy tools')
class WorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='hapi-worker-test-')
        cls.root = Path(cls.temp.name)
        cls.addClassCleanup(cls.temp.cleanup)
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'synthetic-worker-ca')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cls.ca = (x509.CertificateBuilder().subject_name(cls.name).issuer_name(cls.name).public_key(cls.key.public_key())
                  .serial_number(1).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=1))
                  .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                  .add_extension(x509.SubjectKeyIdentifier.from_public_key(cls.key.public_key()), critical=False)
                  .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                      data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                      encipher_only=False, decipher_only=False), critical=True).sign(cls.key, hashes.SHA256()))
        (cls.root / 'ca.pem').write_bytes(cls.ca.public_bytes(serialization.Encoding.PEM))
        crl = (x509.CertificateRevocationListBuilder().issuer_name(cls.name).last_update(now - datetime.timedelta(minutes=1))
               .next_update(now + datetime.timedelta(days=1)).sign(cls.key, hashes.SHA256()))
        (cls.root / 'crl.pem').write_bytes(crl.public_bytes(serialization.Encoding.PEM))
        for label, name, client in [('server', 'alice.hapi.internal', False),
                                    ('gateway', 'hapi-control-plane', True), ('other', 'hapi-bob', True)]:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            builder = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
                       .issuer_name(cls.name).public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(hours=1))
                       .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                       .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(cls.key.public_key()), critical=False)
                       .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH]), critical=False))
            if not client:
                builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            cert = builder.sign(cls.key, hashes.SHA256())
            (cls.root / (label + '.pem')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            (cls.root / (label + '.key')).write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        cls.backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
        cls.addClassCleanup(cls.backend.server_close);cls.addClassCleanup(cls.backend.shutdown)
        threading.Thread(target=cls.backend.serve_forever, daemon=True).start()
        cls.port = helpers.available_port()
        for name in ['', 'body', 'proxy', 'fastcgi', 'uwsgi', 'scgi']:
            (cls.root / 'run' / name).mkdir(parents=True, exist_ok=True)
        text = helpers.render(ROOT / 'ansible/roles/hapi-worker/templates/nginx.conf.j2', {
            'hapi_worker_id': 'alice', 'hapi_worker_address': '127.0.0.1',
            'hapi_worker_control_address': '127.0.0.1', 'hapi_worker_origin': helpers.helpers.ORIGIN})
        text = text.replace('/run/hapi-worker-proxy', str(cls.root / 'run')).replace('/etc/hapi-worker', str(cls.root))
        text = text.replace(':9443', ':' + str(cls.port)).replace(':6082', ':' + str(cls.backend.server_address[1]))
        cls.config = cls.root / 'nginx.conf';cls.config.write_text(text)
        subprocess.run(['nginx', '-t', '-c', str(cls.config)], capture_output=True, check=True)
        cls.nginx = subprocess.Popen(['nginx', '-c', str(cls.config), '-g', 'daemon off;'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.addClassCleanup(cls.nginx.wait, 5);cls.addClassCleanup(cls.nginx.terminate)
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=.1):
                    break
            except OSError:
                time.sleep(.02)
        else:
            raise AssertionError('Worker proxy did not start')

    def request(self, path, identity='gateway', source='127.0.0.1', name='alice.hapi.internal', headers=None):
        context = ssl.create_default_context(cafile=str(self.root / 'ca.pem'))
        if identity:
            context.load_cert_chain(str(self.root / (identity + '.pem')), str(self.root / (identity + '.key')))
        raw = socket.create_connection(('127.0.0.1', self.port), timeout=3, source_address=(source, 0))
        try:
            wrapped = context.wrap_socket(raw, server_hostname=name)
            connection = http.client.HTTPConnection(name, self.port, timeout=3)
            connection.sock = wrapped
            try:
                connection.request('GET', path, headers={'Host': name, **(headers or {})})
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()
        finally:
            raw.close()

    def test_login_request_reaches_only_fixed_api_with_overwritten_identity_headers(self):
        status, body = self.request('/api/login/status', headers={'Cookie': 'secret-cookie',
            'Authorization': 'Bearer secret-token', 'X-Hapi-CSRF': 'secret-csrf',
            'Cf-Access-Jwt-Assertion': 'secret-assertion', 'X-Hapi-Login-Service': 'forged',
            'X-Hapi-Expected-Namespace': 'foreign'})
        self.assertEqual(status, 200)
        data = json.loads(body);headers = {k.lower(): v for k, v in data['headers'].items()}
        self.assertEqual(headers['host'], 'hapi.example.com')
        self.assertEqual(headers['x-hapi-login-service'], 'verified-proxy')
        for name in ['cookie', 'authorization', 'x-hapi-csrf', 'cf-access-jwt-assertion', 'x-hapi-expected-namespace']:
            self.assertNotIn(name, headers)

    def test_other_employee_certificate_or_source_is_denied(self):
        self.assertEqual(self.request('/api/login/status', identity='other')[0], 403)
        self.assertEqual(self.request('/api/login/status', source='127.0.0.2')[0], 403)
        try:
            status, _ = self.request('/api/login/status', identity=None)
            self.assertGreaterEqual(status, 400)
        except (ssl.SSLError, http.client.HTTPException, OSError):
            pass

    def test_app_management_and_unknown_login_paths_are_not_exposed(self):
        for path in ['/', '/api/auth', '/api/sessions', '/api/login/unknown', '/_workspace/session']:
            self.assertEqual(self.request(path)[0], 403)

    def test_server_identity_is_verified(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request('/api/login/status', name='another.hapi.internal')


class IdentityTest(unittest.TestCase):
    def test_real_ansible_identity_preflight_rejects_wrong_vm_before_installation(self):
        if not os.environ.get('SANDBOX_ID') or not shutil.which('ansible-playbook'):
            self.skipTest('requires approved repository Sandbox')
        values = {'hapi_worker_activate': True, 'hapi_worker_vmid': 550, 'hapi_worker_id': 'alice',
                  'hapi_worker_request_id': 'a' * 32, 'hapi_worker_product_uuid': '11111111-2222-3333-4444-555555555555',
                  'hapi_worker_address': '10.77.0.20', 'hapi_worker_mac': '02:00:00:00:00:20',
                  'hapi_worker_control_address': '10.90.0.10',
                  'ansible_facts': {'system': 'Linux', 'architecture': 'x86_64', 'virtualization_role': 'guest',
                      'product_uuid': '11111111-2222-3333-4444-555555555555',
                      'default_ipv4': {'address': '10.77.0.20', 'macaddress': '02:00:00:00:00:20'}}}
        cases = [(True, {}), (False, {'hapi_worker_vmid': 500}),
                 (False, {'hapi_worker_id': 'control-plane'}), (False, {'hapi_worker_id': 'hub'}),
                 (False, {'hapi_worker_product_uuid': 'ffffffff-2222-3333-4444-555555555555'}),
                 (False, {'hapi_worker_address': '10.77.0.99'}), (False, {'hapi_worker_mac': '02:00:00:00:00:99'})]
        with tempfile.TemporaryDirectory(prefix='hapi-worker-identity-') as folder:
            for expected, changed in cases:
                play = [{'hosts': 'localhost', 'gather_facts': False, 'vars': copy.deepcopy(values) | changed,
                         'tasks': [{'name': 'Check only worker identity', 'ansible.builtin.include_role':
                                    {'name': 'hapi-worker', 'tasks_from': 'identity'}}]}]
                path = Path(folder) / 'identity.json';path.write_text(json.dumps(play))
                env = os.environ | {'ANSIBLE_CONFIG': str(ROOT / 'tests/ci/fixtures/ansible.cfg'),
                                    'ANSIBLE_ROLES_PATH': str(ROOT / 'ansible/roles')}
                run = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)],
                                     env=env, capture_output=True)
                self.assertEqual(run.returncode == 0, expected, run.stdout.decode() + run.stderr.decode())


if __name__ == '__main__':
    unittest.main()
