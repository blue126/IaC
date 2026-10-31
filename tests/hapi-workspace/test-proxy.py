#!/usr/bin/env python3
"""Exercise rendered Nginx routing with real TLS, SSE and WebSocket loopback peers."""
import datetime
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import ssl
import sys
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import importlib.util
import os
import copy
import re
import yaml

TESTS = Path(__file__).parent
spec = importlib.util.spec_from_file_location('auth_tests', TESTS / 'test-auth.py')
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
auth, ROOT = helpers.auth, helpers.ROOT
spec = importlib.util.spec_from_file_location('stream_guard', ROOT/'ansible/roles/hapi-control-plane/files/hapi-stream-guard.py')
stream_guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(stream_guard)
spec = importlib.util.spec_from_file_location('login_agent', ROOT/'ansible/roles/claude-login-agent/files/claude-login-agent.py')
agent = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent)


class LoginFlow:
    def __init__(self):
        self.state = 'idle'
        self.codes = []
        self.authenticated = False
    def status(self):
        return {'state': self.state, 'authenticated': self.authenticated, 'viewer_ready': self.state == 'running'}
    def start(self):
        self.state = 'running'; return self.status()
    def code(self, value):
        self.codes.append(value); self.authenticated = True; self.state = 'success'
    def cancel(self):
        self.state = 'cancelled'



def available_port():
    import socket
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def ansible_template(parameters, values):
    if not os.environ.get('SANDBOX_ID'):
        raise RuntimeError('Run repository Ansible only inside the approved Sandbox')
    with tempfile.TemporaryDirectory(prefix='hapi-ansible-') as folder:
        variables = Path(folder)/'vars.json'; variables.write_text(json.dumps(values))
        env = {**os.environ, 'ANSIBLE_CONFIG': str(ROOT/'tests/ci/fixtures/ansible.cfg')}
        return subprocess.run(['ansible', 'localhost', '-i', 'localhost,', '-c', 'local',
            '-m', 'ansible.builtin.template', '-a', json.dumps(parameters), '-e', '@'+str(variables)],
            cwd=ROOT, env=env, capture_output=True, text=True)


def render(path, values):
    with tempfile.TemporaryDirectory(prefix='hapi-render-') as folder:
        output = Path(folder)/'rendered'
        result = ansible_template({'src': str(path), 'dest': str(output)}, values)
        if result.returncode:
            raise AssertionError(result.stdout+result.stderr)
        return output.read_text()


class Hub(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *_args):
        pass
    def do_GET(self):
        if self.path.startswith('/socket.io/') or self.path == '/websockify':
            import base64
            accept = base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key'] +
                '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            self.send_response(101)
            self.send_header('Upgrade', 'websocket'); self.send_header('Connection', 'Upgrade')
            self.send_header('Sec-WebSocket-Accept', accept); self.end_headers()
            payload = self.server.workspace.encode()
            self.wfile.write(bytes([0x81, len(payload)]) + payload); self.wfile.flush()
            if 'live=1' in self.path:
                self.connection.settimeout(30)
                while not self.server.release.is_set():
                    try:
                        frame = self.rfile.read(2)
                    except TimeoutError:
                        break
                    if not frame: break
                    length = frame[1] & 127
                    mask = self.rfile.read(4)
                    raw = self.rfile.read(length)
                    payload = bytes(value ^ mask[i % 4] for i, value in enumerate(raw))
                    self.wfile.write(bytes([0x81, len(payload)]) + payload); self.wfile.flush()
            self.close_connection = True
        elif self.path == '/api/large':
            payload = b'x' * (2 * 1024 * 1024)
            self.send_response(200); self.send_header('Content-Length', str(len(payload))); self.end_headers()
            self.wfile.write(payload)
        elif self.path == '/api/events':
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Transfer-Encoding', 'chunked'); self.end_headers()
            payload = ('data: ' + self.server.workspace + '\n\n').encode()
            self.wfile.write(f'{len(payload):x}\r\n'.encode() + payload + b'\r\n'); self.wfile.flush()
            self.server.release.wait(30)
            self.wfile.write(b'0\r\n\r\n'); self.wfile.flush()
        else:
            payload = json.dumps({'workspace': self.server.workspace, 'path': self.path,
                                  'access_header': self.headers.get('Cf-Access-Jwt-Assertion'),
                                  'namespace': self.headers.get('X-Hapi-Expected-Namespace'),
                                  'credential_id': self.headers.get('X-Hapi-Expected-Credential'),
                                  'cookie': self.headers.get('Cookie')}).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path == '/api/auth':
            if json.loads(body) != {'accessToken': 'synthetic-service-token-' + 'x'*32}:
                self.send_error(403); return
            payload = json.dumps({'token': 'test.' + self.server.workspace + '.signature', 'user': {'id': 1}}).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
        else:
            self.do_GET()


class RfbPeer(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.sendall(b'RFB 003.008\n')
        while self.request.recv(4096):
            pass


class RfbServer(socketserver.ThreadingTCPServer):
    daemon_threads = True

@unittest.skipUnless(shutil.which('nginx') and shutil.which('ansible') and os.environ.get('SANDBOX_ID'),
                     'requires Nginx and real repository Ansible inside the approved Sandbox')
class ProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.AuthTest.setUpClass()
        cls.temp = tempfile.TemporaryDirectory(prefix='hapi-proxy-')
        cls.root = Path(cls.temp.name)
        cls.processes, cls.servers = [], []
        cls.ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'HAPI synthetic CA')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cls.ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                  .public_key(cls.ca_key.public_key()).serial_number(x509.random_serial_number())
                  .not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(days=1))
                  .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                  .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                     data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                     encipher_only=False, decipher_only=False), critical=True)
                  .add_extension(x509.SubjectKeyIdentifier.from_public_key(cls.ca_key.public_key()), critical=False)
                  .sign(cls.ca_key, hashes.SHA256()))
        (cls.root/'ca.pem').write_bytes(cls.ca.public_bytes(serialization.Encoding.PEM))
        cls.issue('client', 'hapi-control-plane', client=True)
        cls.issue('other', 'other-client', client=True)
        revoked = cls.issue('revoked', 'hapi-control-plane', client=True)
        crl = (x509.CertificateRevocationListBuilder().issuer_name(cls.ca.subject)
               .last_update(now-datetime.timedelta(minutes=1)).next_update(now+datetime.timedelta(hours=1))
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(cls.ca_key.public_key()), critical=False)
               .add_revoked_certificate(x509.RevokedCertificateBuilder().serial_number(revoked.serial_number)
                                        .revocation_date(now-datetime.timedelta(seconds=1)).build())
               .sign(cls.ca_key, hashes.SHA256()))
        (cls.root/'crl.pem').write_bytes(crl.public_bytes(serialization.Encoding.PEM))
        cls.routes = [helpers.route('alice', 2), helpers.route('bob', 3)]
        for route in cls.routes:
            route['namespace'] = route['workspace_id']
        cls.config_file = cls.root/'registry.json'
        cls.config = {'origin': helpers.ORIGIN, 'issuer': helpers.ISSUER, 'audience': helpers.AUD, 'routes': cls.routes,
                      'ca_file': str(cls.root/'ca.pem'), 'crl_file': str(cls.root/'crl.pem'),
                      'client_certificate': str(cls.root/'client.pem'), 'client_key': str(cls.root/'client.key')}
        cls.save()
        cls.verifier = auth.AccessVerifier(helpers.ISSUER, helpers.AUD, lambda: helpers.AuthTest.jwks)
        cls.policy = auth.Policy(cls.config_file, cls.verifier)
        cls.auth_server = auth.Server(str(cls.root/'auth.sock'), auth.Handler)
        cls.auth_server.policy = cls.policy
        cls.addClassCleanup(cls.cleanup)
        threading.Thread(target=cls.auth_server.serve_forever, daemon=True).start()
        cls.backends = {}
        cls.agents = {}
        for route in cls.routes:
            wid = route['workspace_id']
            cls.issue(wid, wid+'.hapi.internal')
            hub = ThreadingHTTPServer(('127.0.0.1', 0), Hub)
            hub.workspace, hub.release = wid, threading.Event()
            cls.servers.append(hub)
            threading.Thread(target=hub.serve_forever, daemon=True).start()
            login = agent.Server(('127.0.0.1', 0), agent.Agent)
            login.origin, login.flow = helpers.ORIGIN, LoginFlow()
            cls.agents[wid] = login
            cls.servers.append(login)
            threading.Thread(target=login.serve_forever, daemon=True).start()
            rfb = RfbServer(('127.0.0.1', 0), RfbPeer)
            cls.servers.append(rfb)
            threading.Thread(target=rfb.serve_forever, daemon=True).start()
            viewer_port = available_port()
            viewer = subprocess.Popen(['websockify', f'127.0.0.1:{viewer_port}', f'127.0.0.1:{rfb.server_address[1]}'],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            cls.processes.append(viewer)
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', viewer_port), timeout=.1): break
                except OSError: time.sleep(.02)
            else: raise AssertionError('Synthetic websockify did not start')
            directory = cls.root/wid; directory.mkdir()
            for name in ['ca.pem', 'crl.pem']:
                (directory/name).write_bytes((cls.root/name).read_bytes())
            (directory/'server.pem').write_bytes((cls.root/(wid+'.pem')).read_bytes())
            (directory/'server.key').write_bytes((cls.root/(wid+'.key')).read_bytes())
            port = available_port(); cls.backends[wid] = port
            config = render(ROOT/'ansible/roles/hapi-workspace/templates/nginx.conf.j2', {
                'hapi_workspace_bind_address': '127.0.0.1', 'hapi_workspace_id': wid,
                'hapi_workspace_origin': helpers.ORIGIN, 'hapi_workspace_web_sha256': 'a'*64})
            config = config.replace('127.0.0.1:6082', f'127.0.0.1:{login.server_port}').replace('127.0.0.1:6081', f'127.0.0.1:{viewer_port}')
            config = config.replace('127.0.0.1:9443', f'127.0.0.1:{port}').replace('127.0.0.1:3006', f'127.0.0.1:{hub.server_port}')
            config = config.replace('/etc/hapi-workspace', str(directory)).replace('/run/hapi-workspace-proxy', str(directory))
            web = directory/'web'; web.mkdir()
            (web/'index.html').write_text('<html>synthetic workspace entry</html>')
            (web/'app.js').write_text('window.syntheticWorkspace = true;')
            config = config.replace('/opt/hapi-workspace/web/' + 'a'*64, str(web))
            cls.start_nginx(directory, config, port)
        directory = cls.root/'control'; directory.mkdir()
        (directory/'bridges').mkdir()
        cls.streams = stream_guard.StreamManager(cls.policy, cls.root/'routes', directory/'bridges')
        cls.streams.start()
        cls.port = available_port()
        config = render(ROOT/'ansible/roles/hapi-control-plane/templates/nginx.conf.j2', {
            'hapi_control_plane_origin': helpers.ORIGIN, 'hapi_control_plane_routes': cls.routes})
        config = config.replace('127.0.0.1:8080', f'127.0.0.1:{cls.port}')
        for route in cls.routes:
            config = config.replace(route['backend_address']+':9443', f"127.0.0.1:{cls.backends[route['workspace_id']]}")
        config = config.replace('/run/hapi-control-plane/auth.sock', str(cls.root/'auth.sock')).replace('/run/hapi-control-plane/routes', str(cls.root/'routes'))
        config = config.replace('/run/hapi-control-proxy', str(directory)).replace('/etc/hapi-control-plane', str(cls.root))
        (cls.root/'authorize.inc').write_text((ROOT/'ansible/roles/hapi-control-plane/templates/authorize.inc.j2').read_text())
        config = config.replace('/usr/local/lib/hapi-login-portal', str(ROOT/'ansible/roles/hapi-control-plane/files/hapi-login-portal'))
        cls.start_nginx(directory, config, cls.port)

    @classmethod
    def issue(cls, stem, name, client=False):
        now = datetime.datetime.now(datetime.timezone.utc)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
                .issuer_name(cls.ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(hours=1))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                     data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                     encipher_only=False, decipher_only=False), critical=True)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(cls.ca_key.public_key()), critical=False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .sign(cls.ca_key, hashes.SHA256()))
        (cls.root/(stem+'.pem')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (cls.root/(stem+'.key')).write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        return cert

    @classmethod
    def save(cls):
        cls.config_file.write_text(json.dumps(cls.config))

    @classmethod
    def start_nginx(cls, directory, config, port):
        file = directory/'nginx.conf'; file.write_text(config)
        check = subprocess.run(['nginx', '-t', '-c', str(file), '-p', str(directory)+'/'], capture_output=True, text=True)
        if check.returncode:
            raise AssertionError(check.stderr)
        process = subprocess.Popen(['nginx', '-c', str(file), '-p', str(directory)+'/', '-g', 'daemon off;'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        cls.processes.append(process)
        import socket
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.02)
        raise AssertionError('Nginx did not start')

    @classmethod
    def cleanup(cls):
        if hasattr(cls, 'streams'): cls.streams.close()
        for process in reversed(cls.processes):
            process.terminate(); process.wait(timeout=5); process.stderr.close()
        cls.auth_server.shutdown(); cls.auth_server.server_close()
        cls.policy.database.close()
        for server in cls.servers:
            if hasattr(server, 'release'): server.release.set()
            server.shutdown(); server.server_close()
        cls.temp.cleanup()

    def token(self, wid='alice', **claims):
        return helpers.AuthTest.token(self, wid, **claims)
    key = property(lambda self: helpers.AuthTest.key)

    def request(self, path='/', wid='alice', method='GET', extra=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        headers = {'Host': 'hapi.example.com', 'Cf-Access-Jwt-Assertion': self.token(wid)}
        headers.update(extra or {})
        connection.request(method, path, headers=headers)
        return connection, connection.getresponse()

    def test_real_nginx_routes_two_identities_and_strips_access_credentials(self):
        for wid in ['alice', 'bob']:
            connection, response = self.request('/api/sessions?machineId=other', wid, extra={'Cookie': 'CF_Authorization=sentinel', 'X-Hapi-Stream-Lease': 'forged', 'X-Hapi-Expected-Route': 'forged'})
            result = json.loads(response.read()); connection.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(result['workspace'], wid)
            self.assertIsNone(result['access_header']); self.assertIsNone(result['cookie'])
            self.assertEqual(result['path'], '/api/sessions?machineId=other')

    def test_enrollment_passes_real_nginx_without_granting_application_access(self):
        original = copy.deepcopy(self.config)
        saved_routes = copy.deepcopy(self.routes)
        nonce = '7' * 64
        path = '/_workspace/enroll/' + nonce
        token = self.token('charlie')
        try:
            self.config['shared_hub'] = True
            for route in self.routes:
                route['namespace'] = route['workspace_id']
            self.config['enrollments'] = [{'workspace_id': 'charlie', 'email': 'charlie@example.com',
                'request_id': 'c' * 32, 'generation': 1, 'nonce_sha256': hashlib.sha256(nonce.encode()).hexdigest(),
                'expires_at': int(time.time()) + 600}]
            self.save()
            connection, response = self.request(path, 'charlie', extra={'Cf-Access-Jwt-Assertion': token})
            self.assertEqual(response.status, 200)
            body = response.read(); connection.close()
            csrf = re.search(rb'name="csrf" value="([a-f0-9]+)"', body).group(1).decode()
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
            connection.request('POST', path, body='csrf=' + csrf, headers={'Host': 'hapi.example.com',
                'Cf-Access-Jwt-Assertion': token, 'Origin': helpers.ORIGIN,
                'Content-Type': 'application/x-www-form-urlencoded'})
            response = connection.getresponse()
            self.assertEqual(response.status, 303); response.read(); connection.close()
            connection, response = self.request(path, 'charlie', extra={'Cf-Access-Jwt-Assertion': token})
            self.assertEqual(response.status, 202); response.read(); connection.close()
            connection, response = self.request('/api/sessions', 'charlie', extra={'Cf-Access-Jwt-Assertion': token})
            self.assertEqual(response.status, 403); response.read(); connection.close()
            connection, response = self.request('/api/sessions', 'bob')
            self.assertEqual(response.status, 200); response.read(); connection.close()
        finally:
            for live, saved in zip(self.routes, saved_routes):
                live.clear(); live.update(saved)
            self.config.clear(); self.config.update(original); self.config['routes'] = self.routes
            self.save()

    def test_shared_hub_transport_requires_certificate_and_address_and_overwrites_namespace(self):
        hub = ThreadingHTTPServer(('127.0.0.1', 0), Hub)
        hub.workspace, hub.release = 'shared-hub', threading.Event()
        self.servers.append(hub)
        threading.Thread(target=hub.serve_forever, daemon=True).start()
        self.issue('shared-hub', 'hapi-hub.internal')
        self.issue('worker-alice', 'worker-alice', client=True)
        self.issue('worker-bob', 'worker-bob', client=True)
        shared = self.root / 'shared-transport'; shared.mkdir()
        for target, source in [('ca.pem', 'ca.pem'), ('crl.pem', 'crl.pem'),
                               ('certificate.pem', 'shared-hub.pem'), ('private.key', 'shared-hub.key')]:
            (shared / target).write_bytes((self.root / source).read_bytes())
        port = available_port()
        config = render(ROOT/'ansible/roles/hapi-shared-hub/templates/nginx.conf.j2', {
            'hapi_shared_hub_bind_address': '127.0.0.1', 'hapi_shared_hub_origin': helpers.ORIGIN,
            'hapi_shared_hub_agents': [
                {'id': 'worker-alice', 'address': '127.0.0.1', 'namespace': 'default', 'credential_id': 'alice'},
                {'id': 'worker-bob', 'address': '127.0.0.2', 'namespace': 'bob', 'credential_id': 'bob'}]})
        config = config.replace('127.0.0.1:9443', f'127.0.0.1:{port}').replace('127.0.0.1:3006', f'127.0.0.1:{hub.server_port}')
        config = config.replace('/run/hapi-hub-transport', str(shared)).replace('/etc/hapi-shared-hub', str(shared))
        self.start_nginx(shared, config, port)

        def direct(stem, source='127.0.0.1'):
            context = ssl.create_default_context(cafile=str(self.root/'ca.pem'))
            context.load_cert_chain(str(self.root/(stem+'.pem')), str(self.root/(stem+'.key')))
            raw = socket.create_connection(('127.0.0.1', port), timeout=3, source_address=(source, 0))
            tls = context.wrap_socket(raw, server_hostname='hapi-hub.internal')
            connection = http.client.HTTPConnection('hapi-hub.internal', timeout=3)
            connection.sock = tls
            try:
                connection.request('GET', '/api/sessions', headers={'Host': 'hapi-hub.internal',
                    'X-Hapi-Expected-Namespace': 'forged', 'X-Hapi-Expected-Credential': 'forged'})
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        status, raw = direct('worker-alice')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['namespace'], 'default')
        self.assertEqual(json.loads(raw)['credential_id'], 'alice')
        self.assertEqual(direct('worker-bob')[0], 403)
        status, raw = direct('worker-bob', '127.0.0.2')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['namespace'], 'bob')
        self.assertEqual(direct('other')[0], 403)
        self.assertIn(direct('revoked')[0], [400, 403])

        worker = self.root / 'worker-client'; worker.mkdir()
        for target, source in [('ca.pem', 'ca.pem'), ('crl.pem', 'crl.pem'),
                               ('certificate.pem', 'worker-alice.pem'), ('private.key', 'worker-alice.key')]:
            (worker / target).write_bytes((self.root / source).read_bytes())
        client_port = available_port()
        config = render(ROOT/'ansible/roles/hapi-hub-client/templates/nginx.conf.j2', {'hapi_hub_client_address': '127.0.0.1'})
        config = config.replace('127.0.0.1:3006', f'127.0.0.1:{client_port}').replace('127.0.0.1:9443', f'127.0.0.1:{port}')
        config = config.replace('/run/hapi-hub-client', str(worker)).replace('/etc/hapi-hub-client', str(worker))
        self.start_nginx(worker, config, client_port)
        connection = http.client.HTTPConnection('127.0.0.1', client_port, timeout=3)
        try:
            connection.request('GET', '/api/sessions', headers={'X-Hapi-Expected-Namespace': 'bob', 'X-Hapi-Expected-Credential': 'bob'})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            result = json.loads(response.read())
            self.assertEqual((result['namespace'], result['credential_id']), ('default', 'alice'))
        finally:
            connection.close()

    def test_custom_frontend_and_spa_routes_are_served_without_hub_token_page(self):
        for path in ['/', '/sessions/new']:
            connection, response = self.request(path)
            self.assertEqual(response.status, 200)
            self.assertIn(b'synthetic workspace entry', response.read())
            self.assertIn('text/html', response.getheader('Content-Type'))
            connection.close()
        connection, response = self.request('/app.js')
        self.assertEqual(response.status, 200)
        self.assertIn('javascript', response.getheader('Content-Type'))
        response.read(); connection.close()

    def test_real_proxy_blocks_missing_origin_and_reserved_routes(self):
        for path in ['/api/push/vapid-public-key', '/api/auth', '/api/login', '/api/login/start', '/websockify']:
            connection, response = self.request(path)
            self.assertEqual(response.status, 403); response.read(); connection.close()
        connection, response = self.request('/api/sessions', method='POST')
        self.assertEqual(response.status, 403); response.read(); connection.close()
        connection, response = self.request('/api/sessions', method='POST', extra={'Origin': helpers.ORIGIN})
        self.assertEqual(response.status, 200); response.read(); connection.close()

    def test_sse_is_delivered_before_upstream_completes(self):
        connection, response = self.request('/api/events')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.readline(), b'data: alice\n')
        self.assertFalse(self.servers[0].release.is_set())
        self.servers[0].release.set(); response.read(); connection.close()

    def test_websocket_upgrade_and_server_frame_keep_owner_binding(self):
        connection, response = self.request('/socket.io/?EIO=4&transport=websocket', 'bob', extra={
            'Origin': helpers.ORIGIN, 'Upgrade': 'websocket', 'Connection': 'Upgrade',
            'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==', 'Sec-WebSocket-Version': '13'})
        self.assertEqual(response.status, 101)
        self.assertEqual(response.fp.read(5), b'\x81\x03bob')
        response.close(); connection.close()

    def test_disabled_registry_route_is_denied_without_affecting_other_user(self):
        self.routes[0]['enabled'] = False; self.save()
        try:
            connection, response = self.request()
            self.assertEqual(response.status, 403); response.read(); connection.close()
            connection, response = self.request(wid='bob')
            self.assertEqual(response.status, 200); response.read(); connection.close()
        finally:
            self.routes[0]['enabled'] = True; self.save()

    def test_real_ticket_exchange_uses_mtls_and_returns_no_service_secret(self):
        # Loopback stands in for the private addresses in the registered snapshot.
        original = auth.HubConnection
        def connect(_address, name, context):
            connection = original('127.0.0.1', name, context)
            connection.port = self.backends[name.split('.')[0]]
            return connection
        token = self.token()
        with patch.object(auth, 'HubConnection', connect), patch.object(auth.Path, 'read_text', return_value='synthetic-service-token-' + 'x'*32):
            connection, identity_response = self.request('/_workspace/identity', extra={'Cf-Access-Jwt-Assertion': token})
            identity = json.loads(identity_response.read()); connection.close()
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
            connection.request('POST', '/_workspace/session', body=b'{}', headers={
                'Host': 'hapi.example.com', 'Origin': helpers.ORIGIN,
                'Cf-Access-Jwt-Assertion': token, 'Content-Type': 'application/json',
                'X-Hapi-CSRF': identity['csrf']})
            response = connection.getresponse(); raw = response.read(); connection.close()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(raw)['workspace']['workspace_id'], 'alice')
            self.assertNotIn(b'synthetic-service-token', raw)

    def live_socket(self, wid, token=None):
        connection, response = self.request('/socket.io/?live=1', wid, extra={
            'Cf-Access-Jwt-Assertion': token or self.token(wid), 'Origin': helpers.ORIGIN,
            'Upgrade': 'websocket', 'Connection': 'Upgrade',
            'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==', 'Sec-WebSocket-Version': '13'})
        self.assertEqual(response.status, 101)
        self.assertEqual(response.fp.read(len(wid)+2), bytes([0x81, len(wid)])+wid.encode())
        return connection, response

    def assert_cut(self, connection, response, started):
        connection.sock.settimeout(3)
        try:
            self.assertEqual(response.fp.read(1), b'')
            self.assertLess(time.monotonic()-started, 3)
        finally:
            response.close(); connection.close()

    def test_live_websocket_revocation_preserves_bob_and_blocks_stale_bridge(self):
        alice, a = self.live_socket('alice')
        bob, b = self.live_socket('bob')
        self.routes[0]['generation'] = 2; self.save()
        started = time.monotonic()
        try:
            self.assert_cut(alice, a, started)
            nonce = b'after-alice-cut'; mask = b'abcd'
            frame = bytes([0x81, 0x80 | len(nonce)])+mask+bytes(value ^ mask[i % 4] for i, value in enumerate(nonce))
            bob.sock.sendall(frame)
            self.assertEqual(b.fp.read(len(nonce)+2), bytes([0x81,len(nonce)])+nonce)
            connection, response = self.request('/api/sessions')
            self.assertEqual(response.status, 409)  # Registry changed before bridge reload.
            response.read(); connection.close()
        finally:
            self.routes[0]['generation'] = 1; self.save()
            a.close(); alice.close(); b.close(); bob.close()

    def test_failed_candidate_validation_preserves_the_live_registry_and_bob_stream(self):
        task = next(item for item in yaml.safe_load((ROOT/'ansible/roles/hapi-control-plane/tasks/main.yml').read_text())
                    if item.get('name') == 'Deploy the private route snapshot')
        parameters = copy.deepcopy(task['ansible.builtin.template'])
        self.assertIn('validate', parameters)
        parameters.update(src=str(ROOT/'ansible/roles/hapi-control-plane/templates/config.json.j2'), dest=str(self.config_file))
        parameters.pop('owner'); parameters.pop('group')
        parameters['validate'] = parameters['validate'].replace('/usr/bin/python3', sys.executable).replace(
            '/usr/local/lib/hapi-auth.py', str(ROOT/'ansible/roles/hapi-control-plane/files/hapi-auth.py'))
        candidate = copy.deepcopy(self.routes)
        candidate[1]['subject'] = candidate[0]['subject']
        before = self.config_file.read_bytes()
        mode = self.config_file.stat().st_mode
        bob, peer = self.live_socket('bob')
        try:
            result = ansible_template(parameters, {'hapi_control_plane_routes': candidate,
                'hapi_control_plane_origin': helpers.ORIGIN, 'hapi_control_plane_issuer': helpers.ISSUER,
                'hapi_control_plane_audience': helpers.AUD})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Duplicate workspace allocation', result.stdout)
            self.assertEqual(self.config_file.read_bytes(), before)
            self.assertEqual(self.config_file.stat().st_mode, mode)
            valid = {**parameters, 'dest': str(self.root/'validated-candidate.json')}
            accepted = ansible_template(valid, {'hapi_control_plane_routes': self.routes,
                'hapi_control_plane_origin': helpers.ORIGIN, 'hapi_control_plane_issuer': helpers.ISSUER,
                'hapi_control_plane_audience': helpers.AUD})
            self.assertEqual(accepted.returncode, 0, accepted.stdout+accepted.stderr)
            self.assertEqual(json.loads((self.root/'validated-candidate.json').read_text())['routes'], self.routes)
            nonce = b'bad-candidate-rejected'; mask = b'abcd'
            bob.sock.sendall(bytes([0x81, 0x80|len(nonce)])+mask+bytes(value ^ mask[i%4] for i,value in enumerate(nonce)))
            self.assertEqual(peer.fp.read(len(nonce)+2), bytes([0x81,len(nonce)])+nonce)
        finally:
            peer.close(); bob.close()

    def test_invalid_registry_closes_existing_streams_and_never_falls_back(self):
        connection, response = self.live_socket('alice')
        self.config_file.write_text('{invalid')
        try:
            self.assert_cut(connection, response, time.monotonic())
            failed, result = self.request('/api/sessions', 'bob')
            self.assertIn(result.status, [500, 503]); result.read(); failed.close()
        finally:
            self.save(); response.close(); connection.close()

    def test_live_sse_is_cut_on_disable_while_bob_requests_continue(self):
        connection, response = self.request('/api/events')
        self.assertEqual(response.readline(), b'data: alice\n')
        self.assertEqual(response.readline(), b'\n')
        self.routes[0]['enabled'] = False; self.save()
        started = time.monotonic()
        try:
            connection.sock.settimeout(3)
            try:
                response.read()
            except http.client.IncompleteRead:
                pass
            self.assertLess(time.monotonic()-started, 3)
            healthy, peer = self.request('/api/sessions', 'bob')
            self.assertEqual(peer.status, 200); peer.read(); healthy.close()
        finally:
            self.routes[0]['enabled'] = True; self.save()
            response.close(); connection.close()

    def test_access_expiry_and_logout_cut_already_upgraded_connections(self):
        token = self.token(exp=time.time()+1.2)
        connection, response = self.live_socket('alice', token)
        self.assert_cut(connection, response, time.monotonic())
        token = self.token()
        connection, response = self.live_socket('alice', token)
        self.policy.logout(token)
        self.assert_cut(connection, response, time.monotonic())
        healthy, peer = self.live_socket('bob')
        peer.close(); healthy.close()

    def test_login_page_assets_and_fixed_operations_share_the_same_owner(self):
        token = self.token()
        connection, response = self.request('/_workspace/login/', extra={'Cf-Access-Jwt-Assertion': token})
        page = response.read().decode(); connection.close()
        self.assertEqual(response.status, 200)
        self.assertIn('workspace-identity', page)
        self.assertIn('wss://hapi.example.com', response.getheader('Content-Security-Policy'))
        self.assertIn('/_workspace/login/guide.js', page)
        self.assertNotIn('VM502', page)
        for path in ['/guide.js', '/guide.css', '/core/rfb.js']:
            connection, response = self.request('/_workspace/login'+path)
            self.assertEqual(response.status, 200, path); response.read(); connection.close()
        connection, response = self.request('/_workspace/identity', extra={'Cf-Access-Jwt-Assertion': token})
        identity = json.loads(response.read()); connection.close()
        extra = {'Cf-Access-Jwt-Assertion': token, 'Origin': helpers.ORIGIN,
                 'X-Hapi-CSRF': identity['csrf'], 'Content-Type': 'application/json'}
        for action, body in [('start', {}), ('code', {'code': 'synthetic-code'})]:
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
            connection.request('POST', '/_workspace/login/api/login/'+action, json.dumps(body),
                               {'Host': 'hapi.example.com', **extra})
            response = connection.getresponse(); data = json.loads(response.read()); connection.close()
            self.assertEqual(response.status, 200, data)
        self.assertEqual(self.agents['alice'].flow.codes, ['synthetic-code'])
        self.assertEqual(self.agents['bob'].flow.codes, [])
        connection, response = self.request('/_workspace/login/api/login/cancel', 'bob', 'POST', extra={
            'Origin': helpers.ORIGIN, 'X-Hapi-CSRF': identity['csrf'], 'Content-Type': 'application/json'})
        self.assertEqual(response.status, 403); response.read(); connection.close()

    def test_parallel_novnc_modules_do_not_overflow_the_auth_socket(self):
        from concurrent.futures import ThreadPoolExecutor
        count = 64
        barrier = threading.Barrier(count)
        token = self.token()
        def request_module(index):
            barrier.wait(timeout=10)
            connection, response = self.request('/_workspace/login/core/rfb.js',
                extra={'Cf-Access-Jwt-Assertion': token})
            response.read(); connection.close()
            return response.status
        with ThreadPoolExecutor(max_workers=count) as pool:
            statuses = list(pool.map(request_module, range(count)))
        self.assertEqual(statuses, [200] * count)

    def test_real_novnc_import_graph_is_served_as_javascript(self):
        import re
        root = Path('/usr/share/novnc').resolve()
        if not (root/'core/rfb.js').is_file():
            self.skipTest('Requires the already installed noVNC client package')
        pending, seen = [root/'core/rfb.js'], set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            relative = path.relative_to(root).as_posix()
            connection, response = self.request('/_workspace/login/' + relative)
            raw = response.read(); connection.close()
            self.assertEqual(response.status, 200, relative)
            self.assertIn(response.getheader('Content-Type', '').split(';')[0],
                          ['application/javascript', 'text/javascript'], relative)
            self.assertEqual(raw, path.read_bytes(), relative)
            for name in re.findall(r"(?:from\s+|import\s*\(?\s*)['\"]([^'\"]+)['\"]", raw.decode()):
                if name.startswith('.'):
                    target = (path.parent/name).resolve()
                    if target.is_relative_to(root):
                        self.assertTrue(target.is_file(), str(target))
                        pending.append(target)
        self.assertGreater(len(seen), 20)

    def test_login_viewer_returns_real_websocket_rfb_banner_through_owner_route(self):
        connection, response = self.request('/_workspace/login/websockify', extra={
            'Cf-Access-Jwt-Assertion': self.token(exp=time.time()+1.2),
            'Origin': helpers.ORIGIN, 'Upgrade': 'websocket', 'Connection': 'Upgrade',
            'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==', 'Sec-WebSocket-Version': '13',
            'Sec-WebSocket-Protocol': 'binary'})
        self.assertEqual(response.status, 101)
        self.assertEqual(response.fp.read(14), b'\x82\x0cRFB 003.008\n')
        self.assert_cut(connection, response, time.monotonic())

    def test_large_response_is_drained_before_closing_the_relay(self):
        connection, response = self.request('/api/large')
        self.assertEqual(response.status, 200)
        self.assertEqual(len(response.read()), 2 * 1024 * 1024)
        connection.close()

    def test_mtls_rejects_wrong_server_name_other_client_and_revocation(self):
        def connect(stem, name='alice', target='alice'):
            context = ssl.create_default_context(cafile=str(self.root/'ca.pem'))
            if stem:
                context.load_cert_chain(str(self.root/(stem+'.pem')), str(self.root/(stem+'.key')))
            connection = auth.HubConnection('127.0.0.1', name+'.hapi.internal', context)
            connection.port = self.backends[target]
            return connection
        for stem, expected in [(None, 400), ('other', 403), ('revoked', 400)]:
            connection = connect(stem)
            try:
                connection.request('GET', '/', headers={'Host': 'alice.hapi.internal'})
                response = connection.getresponse(); response.read()
                self.assertEqual(response.status, expected)
            finally:
                connection.close()
        connection = connect('client', name='alice', target='bob')
        try:
            with self.assertRaises(ssl.SSLCertVerificationError):
                connection.connect()
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
