#!/usr/bin/env python3
"""Synthetic VM502 presentation contracts, TLS bridge, and restored lifecycle tests."""
import ast
import base64
import copy
import importlib.util
import http.client
import json
import os
import secrets
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles/employee-workspace/files'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guide = load('oci_guide', FILES / 'login-guide.py')
cli = load('oci_browser', FILES / 'workspace-browser.py')
preparation = load('oci_preparation', FILES / 'prepare-desktop.py')


class OCITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_path = os.environ.get('PATH', '')
        existing_openssl = Path('/opt/homebrew/opt/openssl@3/bin/openssl')
        if os.uname().sysname == 'Darwin' and existing_openssl.is_file():
            os.environ['PATH'] = str(existing_openssl.parent) + os.pathsep + cls.original_path
        cls.temporary = tempfile.TemporaryDirectory(prefix='vm502-synthetic-')
        cls.base = Path(cls.temporary.name).resolve()
        cls.home = cls.base / 'home'; cls.home.mkdir(mode=0o700)
        cls.materials = cls.base / 'materials'
        cls.generation = cls.materials / 'generations/g-synthetic/502'
        cls.generation.mkdir(parents=True)
        for parent in (cls.materials, cls.materials / 'generations', cls.generation.parent, cls.generation):
            parent.chmod(0o755)
        ext = cls.base / 'openssl.cnf'
        ext.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ca\nprompt=no\n[dn]\nCN=Synthetic CA\n[ca]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n[leaf]\nbasicConstraints=critical,CA:FALSE\nsubjectAltName=DNS:localhost,IP:198.18.53.10\nextendedKeyUsage=serverAuth\n')
        def openssl(*args):
            subprocess.run(['openssl', *map(str, args)], check=True, capture_output=True)
        openssl('req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-config', ext,
                '-keyout', cls.base / 'ca.key', '-out', cls.generation / 'ca.pem')
        openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost',
                '-keyout', cls.generation / 'server.key', '-out', cls.base / 'server.csr')
        openssl('x509', '-req', '-in', cls.base / 'server.csr', '-CA', cls.generation / 'ca.pem',
                '-CAkey', cls.base / 'ca.key', '-CAcreateserial', '-days', '1', '-extfile', ext,
                '-extensions', 'leaf', '-out', cls.generation / 'server.pem')
        cls.authentication = {'username': 'synthetic', 'password': secrets.token_hex(16)}
        (cls.generation / 'authentication.json').write_text(json.dumps(cls.authentication))
        for path in cls.generation.iterdir():
            path.chmod(0o640 if path.name in ('server.key', 'authentication.json') else 0o644)
        cls.config = json.loads((Path(__file__).parent / 'fixtures/desktop-lifecycle.json').read_text())
        refs = {key: 'generations/g-synthetic/502/' + name for key, name in (
            ('trust_ref', 'ca.pem'), ('certificate_ref', 'server.pem'), ('private_key_ref', 'server.key'), ('authentication_ref', 'authentication.json'))}
        cls.config.update(materials_root=str(cls.materials), generation=dict(refs, vmid=502))
        cls.config['backend'].update(generation_id='g-synthetic', trust_ref=refs['trust_ref'])
        cls.path = cls.base / 'desktop.json'; cls.path.write_text(json.dumps(cls.config)); cls.path.chmod(0o644)
        cls.browser = cls.base / 'browser.json'; cls.browser.write_text(json.dumps({'mode': 'kasmvnc', 'viewer_url': 'https://hapi.synthetic.invalid'}))
        # Relocate only fixed config, marker and OS ownership identities. Production
        # certificate, generation, authentication, and socket checks remain intact.
        source = (FILES / 'desktop-service.py').read_text()
        source = source.replace("CONFIG = Path('/etc/employee-workspace-desktop.json')", 'CONFIG = Path(' + repr(str(cls.path)) + ')')
        source = source.replace("MARKER = Path('/var/lib/employee-workspace/transition.json')", 'MARKER = Path(' + repr(str(cls.base / 'marker')) + ')')
        source = source.replace('secure_file(CONFIG, 0)', 'secure_file(CONFIG, os.getuid())').replace('secure_file(path, 0,', 'secure_file(path, os.getuid(),')
        source = source.replace("pwd.getpwnam('employee')", 'pwd.getpwuid(os.getuid())').replace("grp.getgrnam('employee').gr_gid", 'os.getgid()')
        cls.service_path = cls.base / 'desktop-service.py'; cls.service_path.write_text(source)
        shutil.copyfile(FILES / 'desktop-contract.py', cls.base / 'desktop-contract.py')
        shutil.copyfile(FILES / 'desktop-targets.json', cls.base / 'desktop-targets.json')
        cls.service = load('oci_fixture_service', cls.service_path)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        os.environ['PATH'] = cls.original_path

    def test_material_generation_and_real_openssl_identity(self):
        config = self.service.validate_config_content(copy.deepcopy(self.config))
        self.assertEqual(self.service.validate_materials(config)['username'], 'synthetic')
        for change in (lambda c: c['backend'].update(port=6081),
                       lambda c: c['backend'].update(address='198.18.53.10'),
                       lambda c: c['backend'].update(tls_server_name='wrong.invalid'),
                       lambda c: c['backend'].update(generation_id='latest'),
                       lambda c: c.update(viewer_url='http://198.18.53.10:8443/')):
            candidate = copy.deepcopy(self.config); change(candidate)
            with self.assertRaises((ValueError, self.service.Refused)):
                self.service.validate_config_content(candidate)

    def test_hapi_viewer_is_preserved_and_desktop_url_is_independent(self):
        before = self.browser.read_bytes()
        with patch.object(cli, 'CONFIG', self.browser), patch.object(cli, 'DESKTOP_CONFIG', self.path):
            config = cli.configuration()
        self.assertEqual(config['viewer_url'], 'https://hapi.synthetic.invalid')
        self.assertEqual(config['desktop_viewer_url'], self.config['viewer_url'])
        self.assertEqual(self.browser.read_bytes(), before)

    def test_actual_tls_backend_and_basic_identity(self):
        client, server = socket.socketpair()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.generation / 'server.pem'), str(self.generation / 'server.key'))
        observed = []
        def backend():
            with context.wrap_socket(server, server_side=True) as connection:
                observed.append(connection.recv(64)); connection.sendall(b'fixture-rfb')
        thread = threading.Thread(target=backend); thread.start()
        try:
            with patch.object(guide, 'BROWSER_CONFIG', self.browser), patch.object(guide, 'DESKTOP_SERVICE', self.service_path), patch.object(guide.socket, 'create_connection', return_value=client) as connect:
                connection, headers = guide.viewer_connection()
                with connection:
                    connection.sendall(b'synthetic-only'); self.assertEqual(connection.recv(64), b'fixture-rfb')
                connect.assert_called_once_with(('127.0.0.1', 8444), timeout=10)
            self.assertEqual(headers[:3], ['Host: localhost', 'Origin: https://localhost:8444',
                                                  'Sec-WebSocket-Origin: https://localhost:8444'])
            self.assertEqual(headers[3], 'Sec-WebSocket-Protocol: binary')
            self.assertEqual(headers[4], 'Authorization: Basic ' + base64.b64encode(('synthetic:' + self.authentication['password']).encode()).decode())
        finally:
            client.close(); server.close(); thread.join(5)
        self.assertEqual(observed, [b'synthetic-only'])
        self.assertFalse(thread.is_alive())

    def test_websocket_forwards_fixed_backend_origin_headers_and_rejects_other_origin(self):
        handler = object.__new__(guide.Guide)
        handler.server = types.SimpleNamespace(origin='https://hapi.synthetic.invalid')
        handler.headers = http.client.HTTPMessage()
        for name, value in [('Origin', handler.server.origin), ('Upgrade', 'websocket'),
                            ('Sec-WebSocket-Version', '13'), ('Sec-WebSocket-Key', 'synthetic-key'),
                            ('Sec-WebSocket-Protocol', 'binary'), ('Sec-WebSocket-Origin', 'https://untrusted.invalid')]:
            handler.headers[name] = value
        handler.json_reply = Mock()
        upstream = Mock()
        upstream.recv.return_value = b'HTTP/1.1 404 Not Found\r\n\r\n'
        identity = ['Host: localhost', 'Origin: https://localhost:8444',
                    'Sec-WebSocket-Origin: https://localhost:8444', 'Sec-WebSocket-Protocol: binary', 'Authorization: Basic synthetic-only']
        with patch.object(guide, 'viewer_connection', return_value=(upstream, identity)):
            handler.websocket()
        request = upstream.sendall.call_args.args[0].decode()
        self.assertEqual(request.count('\r\nOrigin: https://localhost:8444\r\n'), 1)
        self.assertEqual(request.count('\r\nSec-WebSocket-Origin: https://localhost:8444\r\n'), 1)
        self.assertNotIn('untrusted.invalid', request)
        self.assertIn('Sec-WebSocket-Protocol: binary\r\n', request)
        handler.json_reply.assert_called_once()
        self.assertEqual(handler.json_reply.call_args.args[0], 503)
        upstream.close.assert_called_once()
        handler.json_reply.reset_mock()
        handler.headers.replace_header('Origin', 'https://untrusted.invalid')
        with patch.object(guide, 'viewer_connection') as connect:
            handler.websocket()
            connect.assert_not_called()
        self.assertEqual(handler.json_reply.call_args.args[0], 403)

    def test_kasm_subprotocol_adapts_only_the_backend_selection(self):
        response = (b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: fixture\r\n'
                    b'Sec-WebSocket-Protocol: binary\r\n\r\npending-frame')
        self.assertEqual(guide.kasm_upgrade_response(response, True), response)
        filtered = guide.kasm_upgrade_response(response, False)
        self.assertNotIn(b'Sec-WebSocket-Protocol:', filtered)
        self.assertTrue(filtered.endswith(b'\r\n\r\npending-frame'))
        self.assertIn(b'Sec-WebSocket-Accept: fixture', filtered)
        for invalid in (response.replace(b': binary', b': base64'), response.replace(b': binary', b': binary, base64')):
            with self.assertRaises(ValueError):
                guide.kasm_upgrade_response(invalid, True)

    def test_kasm_actual_upgrade_supports_no_offer_binary_offer_and_rejects_other_offer(self):
        for offer in (None, 'binary', 'base64'):
            with self.subTest(offer=offer):
                handler = object.__new__(guide.Guide)
                handler.server = types.SimpleNamespace(origin='https://hapi.synthetic.invalid')
                handler.headers = http.client.HTTPMessage()
                for name, value in [('Origin', handler.server.origin), ('Upgrade', 'websocket'),
                                    ('Sec-WebSocket-Version', '13'), ('Sec-WebSocket-Key', 'synthetic-key')]:
                    handler.headers[name] = value
                if offer is not None:
                    handler.headers['Sec-WebSocket-Protocol'] = offer
                handler.json_reply = Mock(); handler.wfile = Mock(); handler.connection = Mock()
                upstream = Mock()
                response = b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Protocol: binary\r\n\r\n'
                upstream.recv.side_effect = [response, b'']
                identity = ['Host: localhost', 'Origin: https://localhost:8444', 'Sec-WebSocket-Protocol: binary']
                with patch.object(guide, 'viewer_connection', return_value=(upstream, identity)), patch.object(guide.select, 'select', return_value=([upstream], [], [])):
                    handler.websocket()
                if offer == 'base64':
                    self.assertEqual(handler.json_reply.call_args.args[0], 403)
                    upstream.sendall.assert_not_called()
                    handler.connection.sendall.assert_not_called()
                else:
                    request = upstream.sendall.call_args.args[0]
                    self.assertEqual(request.count(b'Sec-WebSocket-Protocol: binary'), 1)
                    returned = handler.connection.sendall.call_args.args[0]
                    self.assertEqual(b'Sec-WebSocket-Protocol: binary' in returned, offer == 'binary')
                    handler.json_reply.assert_not_called()
                upstream.close.assert_called_once()

    def test_legacy_upgrade_keeps_client_protocol_without_kasm_filter(self):
        handler = object.__new__(guide.Guide)
        handler.server = types.SimpleNamespace(origin='https://hapi.synthetic.invalid')
        handler.headers = http.client.HTTPMessage()
        for name, value in [('Origin', handler.server.origin), ('Upgrade', 'websocket'),
                            ('Sec-WebSocket-Version', '13'), ('Sec-WebSocket-Protocol', 'base64')]:
            handler.headers[name] = value
        handler.json_reply = Mock(); handler.wfile = Mock(); handler.connection = Mock()
        upstream = Mock()
        response = b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Protocol: base64\r\n\r\n'
        upstream.recv.side_effect = [response, b'']
        with patch.object(guide, 'viewer_connection', return_value=(upstream, ['Host: 127.0.0.1:6081'])), patch.object(guide.select, 'select', return_value=([upstream], [], [])):
            handler.websocket()
        self.assertIn(b'Sec-WebSocket-Protocol: base64', upstream.sendall.call_args.args[0])
        self.assertEqual(handler.connection.sendall.call_args.args[0], response)

    def test_bad_ca_is_rejected_by_actual_tls_context(self):
        context = ssl.create_default_context(cafile=str(self.generation / 'ca.pem'))
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        with self.assertRaises(ssl.SSLError):
            ssl.create_default_context(cafile=str(self.generation / 'authentication.json'))

    def test_frontend_certificate_rejects_target_or_key_drift(self):
        frontend = {'address': '198.18.53.10', 'certificate': str(self.generation / 'server.pem'),
                    'private_key': str(self.generation / 'server.key'), 'ca': str(self.generation / 'ca.pem')}
        # OS identities are relocated; actual openssl checks are retained.
        actual_stat = Path.stat
        def stat(path, *args, **kwargs):
            info = actual_stat(path, *args, **kwargs)
            return types.SimpleNamespace(st_uid=0, st_mode=info.st_mode)
        with patch.object(Path, 'stat', stat):
            preparation.validate_frontend(frontend)
            for changed in (dict(frontend, address='198.18.53.11'), dict(frontend, private_key=str(self.base / 'ca.key'))):
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    preparation.validate_frontend(changed)

    def test_existing_self_signed_leaf_requires_its_exact_pin(self):
        cert = self.base / 'existing-frontend.pem'
        key = self.base / 'existing-frontend.key'
        subprocess.run(['openssl', 'req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-days', '1', '-subj', '/CN=198.18.53.10',
                        '-addext', 'basicConstraints=critical,CA:FALSE',
                        '-addext', 'subjectAltName=IP:198.18.53.10',
                        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
        key.chmod(0o600)
        pin = preparation.run(['openssl', 'x509', '-in', str(cert), '-noout', '-fingerprint', '-sha256']).split('=', 1)[1].replace(':', '').lower()
        config = dict(address='198.18.53.10', certificate=str(cert), private_key=str(key), ca=str(cert), pinned_sha256=pin)
        actual_stat = Path.stat
        def root_stat(path, *args, **kwargs):
            info = actual_stat(path, *args, **kwargs)
            return types.SimpleNamespace(st_uid=0, st_mode=info.st_mode)
        with patch.object(Path, 'stat', root_stat):
            preparation.validate_frontend(config)
            for change in (dict(pinned_sha256='0'*64), dict(address='198.18.53.11'), dict(ca=str(self.generation / 'ca.pem'))):
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    preparation.validate_frontend(dict(config, **change))
            config.pop('pinned_sha256')
            with self.assertRaisesRegex(ValueError, 'trust anchor'):
                preparation.validate_frontend(config)

    def test_trust_phase_does_not_touch_route_or_services(self):
        frontend = {'certificate': 'leaf', 'private_key': 'key', 'ca': 'ca', 'address': '198.18.53.10'}
        with patch.object(preparation, 'validate_frontend'), patch.object(preparation, 'install', side_effect=[True, True]) as install, patch.object(preparation, 'run') as run:
            preparation.trust(frontend)
        self.assertEqual([str(call.args[1]) for call in install.call_args_list], ['/etc/oci-hub/desktop.crt', '/etc/oci-hub/desktop.key'])
        self.assertEqual([call.args[0] for call in run.call_args_list], [['nginx', '-t'], ['systemctl', 'reload', 'nginx']])
        with patch.object(preparation, 'validate_frontend'), patch.object(preparation, 'install', return_value=False), patch.object(preparation, 'run') as run:
            self.assertFalse(preparation.trust(frontend))
            run.assert_called_once_with(['nginx', '-t'])

    def test_prepare_tasks_do_not_replace_active_definitions(self):
        text = (ROOT / 'ansible/roles/kasmvnc/tasks/presentation.yml').read_text()
        self.assertNotIn('ansible.builtin.apt', text)
        self.assertNotIn('workspace-login.py', text)
        self.assertIn("when: kasmvnc_presentation_phase == 'activate'", text)
        self.assertIn("when: kasmvnc_presentation_phase == 'trust'", text)
        self.assertNotIn('employee-access', text)
        self.assertIn('tasks_from: presentation', (ROOT / 'ansible/playbooks/prepare-vm502-desktop.yml').read_text())


class ProbeDiagnosticTests(unittest.TestCase):
    def test_embedded_bridge_diagnostics_are_bounded_and_exclude_headers(self):
        tree = ast.parse((ROOT / 'tests/oci-hub/test-desktop-network.py').read_text())
        assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == 'guide_worker' for target in node.targets))
        worker = ast.parse(ast.literal_eval(assignment.value))
        function = next(node for node in worker.body if isinstance(node, ast.FunctionDef) and node.name == 'connection')
        events = []
        peer = Mock()
        secret = b'synthetic-secret-not-to-be-exported'
        peer.recv.side_effect = [b'HTTP/1.1 101 Switching Protocols\r\nAuthorization: Basic ' + secret,
                                 b'\r\n\r\nfixture-rfb']
        diagnostic = load('handshake_diagnostics', ROOT / 'tests/oci-hub/test-desktop-network.py')
        namespace = {'actual_connection': lambda: (peer, ['private-identity']),
                     'diagnostic': diagnostic, 'expected_authorization': 'Basic fixture',
                     'event': lambda code, **fields: events.append(dict(code=code, **fields))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<synthetic-diagnostics>', 'exec'), namespace)
        returned, identity = namespace['connection']()
        returned.recv(4096); returned.recv(4096)
        self.assertEqual([event['code'] for event in events], ['backend-tls-connected', 'backend-websocket-http'])
        self.assertEqual(events[1]['status'], 101)
        self.assertEqual(events[1]['response']['status'], 101)
        self.assertNotIn(secret.decode(), json.dumps(events))
        self.assertEqual(identity, ['private-identity'])

    def test_request_shape_redacts_auth_and_key_and_checks_framing(self):
        diagnostic = load('request_diagnostics', ROOT / 'tests/oci-hub/test-desktop-network.py')
        credential = base64.b64encode(b'synthetic:never-export-this-password').decode()
        key = base64.b64encode(b'sixteen-byte-key').decode()
        request = ('GET /websockify HTTP/1.1\r\nHost: localhost\r\nOrigin: https://localhost:8444\r\n'
                   'Sec-WebSocket-Origin: https://10.234.0.2:8443\r\nSec-WebSocket-Version: 13\r\n'
                   'Sec-WebSocket-Protocol: binary\r\nUpgrade: websocket\r\nConnection: upgrade\r\n'
                   'Sec-WebSocket-Key: '+key+'\r\nAuthorization: Basic '+credential+'\r\n\r\n').encode()
        shape = diagnostic.websocket_request_shape(request, 'Basic '+credential)
        self.assertEqual(shape['authorization'], {'present': True, 'matches_material': True})
        self.assertEqual(shape['websocket_key'], {'count': 1, 'length': len(key), 'decoded_length': 16})
        self.assertTrue(shape['crlf']['header_terminated'])
        self.assertFalse(shape['crlf']['bare_linebreak'])
        self.assertEqual(shape['headers']['sec-websocket-origin'], ['https://10.234.0.2:8443'])
        serialized = json.dumps(shape)
        for forbidden in (credential, key, 'never-export-this-password'):
            self.assertNotIn(forbidden, serialized)
        malformed = diagnostic.websocket_request_shape(request.replace(b'\r\n', b'\n'))
        self.assertTrue(malformed['crlf']['bare_linebreak'])
        response = diagnostic.websocket_response_shape(b'HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: 9999\r\n\r\n'+
            ('Basic '+credential+' never-export-this-password '+('x'*2000)).encode(), 'Basic '+credential)
        self.assertEqual(response['status'], 404)
        self.assertTrue(response['body_truncated'])
        self.assertLessEqual(len(response['body_sample']), 512)
        for forbidden in (credential, 'never-export-this-password'):
            self.assertNotIn(forbidden, json.dumps(response))

    def test_http_embedded_diagnostics_have_real_crlf_and_no_raw_request_export(self):
        diagnostic = load('http_diagnostics', ROOT / 'tests/oci-hub/test-desktop-network.py')
        scripts = []
        with patch.object(diagnostic, 'invoke', side_effect=lambda ns, script: scripts.append(script) or {'status': 101}):
            diagnostic.http('synthetic-ns', Path('/synthetic/ca.pem'), path='/websockify')
        tree = ast.parse(scripts[0])
        fields = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str) and ' HTTP/1.1' in node.value]
        self.assertTrue(fields)
        self.assertIn('\r\n', fields[0])
        self.assertIn("response['request_shape']", scripts[0])


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='vm502-activation-')
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name).resolve()
        self.stage = self.base / 'stage'; self.stage.mkdir()
        self.lib = self.base / 'lib'; self.lib.mkdir()
        self.etc = self.base / 'etc'
        for path in ('systemd/system', 'nginx/conf.d', 'oci-hub'):
            (self.etc / path).mkdir(parents=True, exist_ok=True)
        self.bin = self.base / 'bin'; self.bin.mkdir()
        self.nginx = self.etc / 'nginx/conf.d/oci-hub-desktop.conf'
        self.nginx.write_text('old-noVNC-upstream')
        self.marker = self.base / 'maintenance.json'
        self.lock = self.base / 'lock'; self.lock.touch(); self.lock.chmod(0o660)
        for name in ('desktop-targets.json', 'desktop-service.py', 'desktop-contract.py', 'browser-service.py',
                     'workspace-browser.py', 'workspace-desktop.py', 'login-guide.py',
                     'employee-desktop.service', 'employee-browser.service', 'employee-browser-desktop.conf'):
            shutil.copyfile(FILES / name, self.stage / name)
        for name in ('desktop.json', 'backend-ca.crt', 'desktop.conf'):
            (self.stage / name).write_text('synthetic-' + name)
        self.browser = self.etc / 'employee-workspace-browser.json'
        self.original_browser = {'viewer_url': 'https://hapi.synthetic.invalid', 'viewer_access_note': 'keep', 'bind_address': '127.0.0.1'}
        self.browser.write_text(json.dumps(self.original_browser))
        self.module = Mock()
        for key, value in dict(STAGE=self.stage, LIB=self.lib, ETC=self.etc, LOCK=self.lock,
                               MARKER=self.marker, NGINX=self.nginx, BIN=self.bin, GUIDE=self.lib / 'guide.py').items():
            context = patch.object(preparation, key, value); context.start(); self.addCleanup(context.stop)
        for target, value in (('validate_stage', (self.module, {'vmid': 502}, {})), ('trust', False), ('configure_browser_entries', None)):
            context = patch.object(preparation, target, return_value=value); context.start(); self.addCleanup(context.stop)
        info = types.SimpleNamespace(st_uid=0, st_gid=os.getgid(), st_mode=0o100660)
        context = patch.object(preparation.os, 'fstat', return_value=info); context.start(); self.addCleanup(context.stop)
        context = patch.object(preparation.grp, 'getgrnam', return_value=types.SimpleNamespace(gr_gid=os.getgid())); context.start(); self.addCleanup(context.stop)
        self.active = False
        def metadata(argv, **kwargs):
            state = 'active' if self.active and 'employee-browser.service' in argv else 'inactive'
            return subprocess.CompletedProcess(argv, 0, stdout='LoadState=loaded\nActiveState=' + state + '\n')
        context = patch.object(preparation.subprocess, 'run', side_effect=metadata); context.start(); self.addCleanup(context.stop)
        self.fail = False
        def command(argv):
            if self.fail and argv == ['systemctl', 'daemon-reload']:
                raise RuntimeError('synthetic interruption')
            if '--property=User,Restart' in argv:
                return 'User=employee\nRestart=no'
            if '--property=LoadState' in argv:
                return 'loaded'
            if '--property=UnitFileState' in argv:
                return 'static'
            return ''
        context = patch.object(preparation, 'run', side_effect=command); context.start(); self.addCleanup(context.stop)

    def test_old_noVNC_active_is_rejected_before_any_mutation(self):
        self.active = True
        with self.assertRaises(ValueError):
            preparation.activate()
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.nginx.read_text(), 'old-noVNC-upstream')
        self.assertEqual(json.loads(self.browser.read_text()), self.original_browser)
        self.module.profile_guard.assert_not_called()

    def test_native_mosh_vm_without_login_guide_can_activate(self):
        original = preparation.run.side_effect
        def command(argv):
            if '--property=LoadState' in argv:
                return 'not-found'
            return original(argv)
        preparation.run.side_effect = command
        preparation.activate()
        self.assertFalse(self.marker.exists())
        self.assertNotIn(['systemctl', 'restart', 'employee-login-guide.service'],
                         [call.args[0] for call in preparation.run.call_args_list])

    def test_vm508_interruption_is_bound_to_its_own_vmid(self):
        with patch.object(preparation, 'validate_stage', return_value=(self.module, {'vmid': 508}, {})):
            self.fail = True
            with self.assertRaises(RuntimeError):
                preparation.activate()
            self.assertEqual(json.loads(self.marker.read_text()),
                             {'purpose': 'employee-presentation', 'vmid': 508})
            self.marker.write_text(json.dumps({'purpose': 'employee-presentation', 'vmid': 509}))
            with self.assertRaisesRegex(ValueError, 'Another maintenance'):
                preparation.activate()
            self.marker.write_text(json.dumps({'purpose': 'employee-presentation', 'vmid': 508}))
            self.fail = False
            preparation.activate()
            self.assertFalse(self.marker.exists())

    def test_interruption_closes_only_desktop_and_can_continue_forward(self):
        self.fail = True
        with self.assertRaises(RuntimeError):
            preparation.activate()
        self.assertTrue(self.marker.exists())
        self.assertFalse(self.nginx.exists())
        self.fail = False
        preparation.activate()
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.nginx.read_text(), 'synthetic-desktop.conf')
        self.assertEqual(json.loads(self.browser.read_text()), dict(self.original_browser, mode='kasmvnc'))
        before = self.browser.read_bytes()
        preparation.activate()
        self.assertEqual(self.browser.read_bytes(), before)
        self.assertFalse(self.marker.exists())

    def test_foreign_maintenance_marker_is_preserved(self):
        self.marker.write_text('another-maintenance-operation')
        with self.assertRaises(ValueError):
            preparation.activate()
        self.assertEqual(self.marker.read_text(), 'another-maintenance-operation')
        self.assertEqual(self.nginx.read_text(), 'old-noVNC-upstream')


def load_tests(loader, tests, pattern):
    for filename in ('test-desktop-lifecycle.py', 'test-browser-lifecycle.py'):
        tests.addTests(loader.loadTestsFromModule(load(filename[:-3].replace('-', '_'), Path(__file__).with_name(filename))))
    return tests


if __name__ == '__main__':
    unittest.main()
