#!/usr/bin/env python3
"""Exercise trusted internal HTTP routing, identity binding, SSE and WebSocket peers."""
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

TESTS = Path(__file__).parent
spec = importlib.util.spec_from_file_location('auth_tests', TESTS / 'test-auth.py')
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)
auth, ROOT = helpers.auth, helpers.ROOT
spec = importlib.util.spec_from_file_location('stream_guard', ROOT/'ansible/roles/hapi-control-plane/files/hapi-stream-guard.py')
stream_guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(stream_guard)
spec = importlib.util.spec_from_file_location('login_agent', ROOT/'ansible/roles/hapi/files/claude-login-agent.py')
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
    executable = ROOT / '.venv/bin/ansible'
    if not executable.is_file():
        raise RuntimeError('Use this worktree project toolchain; run scripts/setup-dev-env.sh first')
    with tempfile.TemporaryDirectory(prefix='hapi-ansible-') as folder:
        variables = Path(folder)/'vars.json'; variables.write_text(json.dumps(values))
        env = {**os.environ, 'ANSIBLE_CONFIG': str(ROOT/'tests/ci/fixtures/ansible.cfg'),
               'ANSIBLE_LOCAL_TEMP': str(Path(folder)/'local'), 'ANSIBLE_REMOTE_TEMP': str(Path(folder)/'remote'),
               'ANSIBLE_COLLECTIONS_PATH': str(ROOT/'ansible/collections')}
        return subprocess.run([str(executable), 'localhost', '-i', 'localhost,', '-c', 'local',
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

@unittest.skipUnless(shutil.which('nginx') and (ROOT / '.venv/bin/ansible').is_file(),
                     'requires Nginx and this worktree repository toolchain')
class ProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        helpers.AuthTest.setUpClass()
        cls.temp = tempfile.TemporaryDirectory(prefix='hapi-proxy-', dir='/tmp')
        cls.root = Path(cls.temp.name)
        cls.processes, cls.servers = [], []
        cls.routes = [helpers.route('alice', 2), helpers.route('bob', 3)]
        cls.config_file = cls.root/'registry.json'
        cls.config = {'origin': helpers.ORIGIN, 'issuer': helpers.ISSUER, 'audience': helpers.AUD, 'routes': cls.routes}
        cls.save()
        cls.verifier = auth.AccessVerifier(helpers.ISSUER, helpers.AUD, lambda: helpers.AuthTest.jwks)
        cls.policy = auth.Policy(cls.config_file, cls.verifier)
        cls.auth_server = auth.Server(str(cls.root/'auth.sock'), auth.Handler)
        cls.auth_server.policy = cls.policy
        cls.addClassCleanup(cls.cleanup)
        threading.Thread(target=cls.auth_server.serve_forever, daemon=True).start()
        cls.backends = {}; cls.backend_configs = {}
        cls.agents = {}
        for route in cls.routes:
            wid = route['workspace_id']
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
            viewer_port = hub.server_port
            if shutil.which('websockify'):
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
            port = available_port(); cls.backends[wid] = port
            config = render(ROOT/'ansible/roles/hapi/templates/ingress.nginx.conf.j2', {
                'hapi_control_address': '127.0.0.1', 'hapi_bind_address': '127.0.0.1', 'hapi_workspace_id': wid,
                'hapi_origin': helpers.ORIGIN, 'hapi_web_sha256': 'a'*64, 'hapi_desktop_address': '127.0.0.1'})
            # The viewer is the VM's KasmVNC entry on 8443; the synthetic one is plain websockify.
            config = config.replace('127.0.0.1:6082', f'127.0.0.1:{login.server_port}').replace('https://127.0.0.1:8443/websockify', f'http://127.0.0.1:{viewer_port}/websockify')
            config = config.replace('127.0.0.1:9443', f'127.0.0.1:{port}').replace('127.0.0.1:3006', f'127.0.0.1:{hub.server_port}')
            config = config.replace('/etc/hapi-ingress', str(directory)).replace('/run/hapi-ingress', str(directory))
            web = directory/'web'; web.mkdir()
            (web/'index.html').write_text('<html>synthetic workspace entry</html>')
            (web/'app.js').write_text('window.syntheticWorkspace = true;')
            config = config.replace('/opt/hapi-ingress/web/' + 'a'*64, str(web))
            cls.backend_configs[wid] = config
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
        kasm = cls.root/'kasm'; (kasm/'assets').mkdir(parents=True)
        (kasm/'index.html').write_text('<html>synthetic Kasm client</html>')
        (kasm/'assets/ui.js').write_text('window.syntheticKasm = true;')
        config = config.replace('/usr/local/lib/hapi-kasm-client-1.5.0/usr/share/kasmvnc/www', str(kasm))
        cls.start_nginx(directory, config, cls.port)

    @classmethod
    def save(cls):
        cls.config_file.write_text(json.dumps(cls.config))

    @classmethod
    def start_nginx(cls, directory, config, port):
        version = subprocess.run(['nginx', '-V'], capture_output=True, text=True).stderr
        import re
        conf = re.search(r'--conf-path=([^ ]+)', version)
        if conf:
            config = config.replace('/etc/nginx/mime.types', str(Path(conf.group(1)).parent/'mime.types'))
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

    def test_shared_hub_transport_binds_actual_peer_and_overwrites_identity_headers(self):
        hub = ThreadingHTTPServer(('127.0.0.1', 0), Hub)
        hub.workspace, hub.release = 'shared', threading.Event()
        self.servers.append(hub);threading.Thread(target=hub.serve_forever, daemon=True).start()
        directory = self.root/'shared-http';directory.mkdir()
        port = available_port()
        config = render(ROOT/'ansible/roles/hapi-shared-hub/templates/nginx.conf.j2', {
            'hapi_shared_hub_bind_address': '127.0.0.1', 'hapi_shared_hub_origin': helpers.ORIGIN,
            'hapi_shared_hub_agents': [{'id': 'alice', 'address': '127.0.0.1', 'namespace': 'alice', 'credential_id': 'alice'}]})
        config = config.replace('/run/hapi-hub-transport', str(directory)).replace('127.0.0.1:3006', f'127.0.0.1:{hub.server_port}').replace('127.0.0.1:9443', f'127.0.0.1:{port}')
        self.start_nginx(directory, config, port)
        client = self.root/'client-http';client.mkdir();client_port = available_port()
        candidate = render(ROOT/'ansible/roles/hapi/templates/hub-client.nginx.conf.j2', {'hapi_control_address': '127.0.0.1'})
        candidate = candidate.replace('/run/hapi-hub-client', str(client)).replace('127.0.0.1:3006', f'127.0.0.1:{client_port}').replace('127.0.0.1:9443', f'127.0.0.1:{port}')
        self.start_nginx(client, candidate, client_port)
        for endpoint in [port, client_port]:
            connection = http.client.HTTPConnection('127.0.0.1', endpoint, timeout=3)
            connection.request('GET', '/api/sessions', headers={'Host': 'hapi-hub.internal',
                'X-Hapi-Expected-Namespace': 'bob', 'X-Hapi-Expected-Credential': 'bob', 'X-Forwarded-For': '10.77.0.99'})
            response = connection.getresponse();value = json.loads(response.read());connection.close()
            self.assertEqual(response.status, 200)
            self.assertEqual((value['namespace'], value['credential_id']), ('alice', 'alice'))
        denied = self.root/'shared-denied';denied.mkdir();denied_port = available_port()
        candidate = config.replace(str(directory), str(denied)).replace(f'127.0.0.1:{port}', f'127.0.0.1:{denied_port}').replace('"127.0.0.1" "alice"', '"127.0.0.2" "alice"')
        self.start_nginx(denied, candidate, denied_port)
        connection = http.client.HTTPConnection('127.0.0.1', denied_port, timeout=3)
        connection.request('GET', '/health', headers={'Host': 'hapi-hub.internal','X-Forwarded-For':'127.0.0.2'})
        response = connection.getresponse();response.read();connection.close();self.assertEqual(response.status,403)

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

    def test_real_ticket_exchange_uses_private_http_and_returns_no_service_secret(self):
        # Loopback stands in for the private addresses in the registered snapshot.
        original = auth.HubConnection
        def connect(address):
            name = next(route['workspace_id'] for route in self.routes if route['backend_address'] == address)
            connection = original('127.0.0.1')
            connection.port = self.backends[name]
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
        parameters = {'validate': '/usr/bin/python3 /usr/local/lib/hapi-auth.py --config %s --check', 'mode': '0640',
                      'src': str(ROOT/'ansible/roles/hapi-control-plane/templates/config.json.j2'), 'dest': str(self.config_file)}
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
        paths = ['/guide.js', '/guide.css']
        for path in paths:
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

    def test_kasm_client_is_served_from_the_control_plane_behind_access(self):
        connection, response = self.request('/_workspace/login/kasm/index.html')
        body = response.read().decode(); connection.close()
        self.assertEqual(response.status, 200)
        self.assertIn('synthetic Kasm client', body)
        policy = response.getheader('Content-Security-Policy')
        self.assertIn("frame-ancestors 'self'", policy)
        self.assertIn('wss://hapi.example.com', policy)
        self.assertEqual(response.getheader('Cache-Control'), 'no-store')
        self.assertEqual(response.getheader('X-Content-Type-Options'), 'nosniff')
        connection, response = self.request('/_workspace/login/kasm/assets/ui.js')
        self.assertEqual(response.status, 200); self.assertIn('javascript', response.getheader('Content-Type'))
        response.read(); connection.close()
        connection, response = self.request('/_workspace/login/kasm/index.html', extra={'Cf-Access-Jwt-Assertion': 'forged'})
        self.assertIn(response.status, (401, 403)); response.read(); connection.close()
        connection, response = self.request('/_workspace/login/kasm/index.html', method='POST')
        self.assertEqual(response.status, 403); response.read(); connection.close()

    def test_shared_hub_bridge_keeps_the_viewer_on_the_workspace(self):
        config = render(ROOT/'ansible/roles/hapi-control-plane/templates/nginx.conf.j2', {
            'hapi_control_plane_origin': helpers.ORIGIN, 'hapi_control_plane_routes': self.routes,
            'hapi_control_plane_shared_hub': True})
        bridge = config.split('location = /websockify {', 1)
        self.assertIn('proxy_pass http://127.0.0.1:3006;', bridge[0])
        self.assertIn(f"proxy_pass http://{self.routes[0]['backend_address']}:9443;", bridge[1].split('}', 1)[0])
        self.assertIn('location = /_workspace/login/websockify {', config)

    def test_parallel_client_assets_do_not_overflow_the_auth_socket(self):
        from concurrent.futures import ThreadPoolExecutor
        count = 64
        barrier = threading.Barrier(count)
        token = self.token()
        def request_module(index):
            barrier.wait(timeout=10)
            connection, response = self.request('/_workspace/login/kasm/assets/ui.js',
                extra={'Cf-Access-Jwt-Assertion': token})
            response.read(); connection.close()
            return response.status
        with ThreadPoolExecutor(max_workers=count) as pool:
            statuses = list(pool.map(request_module, range(count)))
        self.assertEqual(statuses, [200] * count)

    def test_login_viewer_returns_real_websocket_rfb_banner_through_owner_route(self):
        if not shutil.which('websockify'):
            self.skipTest('websockify is not installed in this native test environment')
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

    def test_private_login_ingress_requires_actual_control_peer_and_registered_host(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.backends['alice'], timeout=3)
        connection.request('GET', '/', headers={'Host': 'bob.hapi.internal'})
        response = connection.getresponse();response.read();connection.close();self.assertEqual(response.status,421)
        directory = self.root/'ingress-denied';directory.mkdir();port = available_port()
        config = self.backend_configs['alice'].replace(str(self.root/'alice'), str(directory)).replace(
            f'127.0.0.1:{self.backends["alice"]}', f'127.0.0.1:{port}').replace('"127.0.0.1" 1;', '"127.0.0.2" 1;')
        self.start_nginx(directory,config,port)
        connection = http.client.HTTPConnection('127.0.0.1',port,timeout=3)
        connection.request('GET','/api/login/status',headers={'Host':'alice.hapi.internal','X-Forwarded-For':'127.0.0.2','X-Hapi-Login-Service':'verified-proxy'})
        response=connection.getresponse();response.read();connection.close();self.assertEqual(response.status,403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
