#!/usr/bin/env python3
"""Private Nginx authorization and HAPI ticket exchange for the VM500 prototype."""
import argparse
import base64
import hashlib
import hmac
import html
import importlib.machinery
import importlib.util
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import socketserver
import sqlite3
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class Denied(Exception):
    """Return a fixed denial without including credentials or upstream output."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def decode_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def unbase64(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid base64url')
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AccessVerifier:
    def __init__(self, issuer, audience, loader=None):
        if not re.fullmatch(r'https://[a-z0-9-]+\.cloudflareaccess\.com', issuer):
            raise ValueError('Expected an Access team origin')
        if not isinstance(audience, str) or not re.fullmatch(r'[a-f0-9]{64}', audience):
            raise ValueError('Expected an application AUD')
        self.issuer, self.audience = issuer, audience
        self.loader = loader or self.fetch_keys
        self.keys, self.expires, self.last_attempt = {}, 0, float('-inf')
        self.lock = threading.Lock()

    def fetch_keys(self):
        opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
        with opener.open(self.issuer + '/cdn-cgi/access/certs', timeout=5) as response:
            raw = response.read(131073)
        if len(raw) > 131072:
            raise ValueError('Oversized key set')
        return decode_json(raw)

    def key(self, kid):
        with self.lock:
            now = time.monotonic()
            if now >= self.expires or kid not in self.keys:
                # Unknown key IDs must not cause unbounded outbound requests.
                if now - self.last_attempt < 30:
                    raise Denied()
                self.last_attempt = now
                data = self.loader()
                keys = {}
                for item in data['keys']:
                    if item.get('kty') != 'RSA' or item.get('alg', 'RS256') != 'RS256':
                        continue
                    if item.get('use', 'sig') != 'sig':
                        continue
                    key_id = item['kid']
                    if key_id in keys:
                        raise ValueError('Duplicate key ID')
                    n, e = int.from_bytes(unbase64(item['n']), 'big'), int.from_bytes(unbase64(item['e']), 'big')
                    if not 2048 <= n.bit_length() <= 8192 or e < 3:
                        raise ValueError('Invalid RSA key')
                    keys[key_id] = rsa.RSAPublicNumbers(e, n).public_key()
                self.keys, self.expires = keys, now + 300
            if time.monotonic() >= self.expires or kid not in self.keys:
                raise Denied()
            return self.keys[kid]

    def verify(self, token):
        try:
            if not isinstance(token, str) or len(token) > 16384:
                raise Denied()
            encoded_header, encoded_payload, signature = token.split('.')
            header, claims = decode_json(unbase64(encoded_header)), decode_json(unbase64(encoded_payload))
            if header.get('alg') != 'RS256' or 'crit' in header or 'b64' in header:
                raise Denied()
            kid = header.get('kid')
            if not isinstance(kid, str) or not 1 <= len(kid) <= 256:
                raise Denied()
            self.key(kid).verify(unbase64(signature), (encoded_header + '.' + encoded_payload).encode(),
                                 padding.PKCS1v15(), hashes.SHA256())
            now = time.time()
            for field in ['exp', 'iat']:
                value = claims.get(field)
                if type(value) not in [int, float] or not math.isfinite(value):
                    raise Denied()
            if claims['exp'] <= now or claims['iat'] > now + 30 or claims['iat'] >= claims['exp']:
                raise Denied()
            if 'nbf' in claims:
                nbf = claims['nbf']
                if type(nbf) not in [int, float] or not math.isfinite(nbf) or nbf > now + 30:
                    raise Denied()
            audience = claims.get('aud')
            if audience != self.audience and not (isinstance(audience, list) and self.audience in audience):
                raise Denied()
            if claims.get('iss') != self.issuer:
                raise Denied()
            if not all(isinstance(claims.get(k), str) and claims[k] for k in ['sub', 'email']):
                raise Denied()
            return claims
        except (ValueError, KeyError, TypeError, InvalidSignature, AttributeError, OverflowError) as error:
            raise Denied() from error


def load_config(path):
    raw = Path(path).read_bytes()
    if len(raw) > 1048576:
        raise ValueError('Oversized configuration')
    config = decode_json(raw)
    if not re.fullmatch(r'https://[a-z0-9.-]+', config['origin']):
        raise ValueError('Expected an HTTPS origin')
    if type(config.get('shared_hub', False)) is not bool:
        raise ValueError('Invalid shared Hub mode')
    seen = {k: set() for k in ['workspace_id', 'email', 'subject', 'backend_address', 'backend_name']}
    if config.get('shared_hub', False):
        seen['namespace'] = set()
    for route in config['routes']:
        wid = route['workspace_id']
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', wid):
            raise ValueError('Invalid workspace ID')
        if not isinstance(route.get('namespace', 'default'), str) or not re.fullmatch(
                r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', route.get('namespace', 'default')):
            raise ValueError('Invalid Hub namespace')
        if route['email'] != route['email'].lower() or not re.fullmatch(r'[^\s@]+@[^\s@]+', route['email']):
            raise ValueError('Invalid registered email')
        # An empty subject is bound once, at the first verified Access login with this email.
        if not isinstance(route['subject'], str) or len(route['subject']) > 256:
            raise ValueError('Invalid Access subject')
        address = ipaddress.IPv4Address(route['backend_address'])
        if not any(address in ipaddress.ip_network(cidr) for cidr in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']):
            raise ValueError('Expected a private backend IPv4 address')
        if route['backend_name'] != wid + '.hapi.internal':
            raise ValueError('Unexpected backend service name')
        if type(route['generation']) is not int or route['generation'] < 1 or type(route['enabled']) is not bool:
            raise ValueError('Invalid route generation or state')
        for key in seen:
            value = route.get('namespace', 'default') if key == 'namespace' else route[key]
            if key == 'subject' and not value:
                continue
            if value in seen[key]:
                raise ValueError('Duplicate workspace allocation')
            seen[key].add(value)
    return config


class HubConnection(http.client.HTTPConnection):
    """Connect only to the registered private address; the caller fixes Host."""
    def __init__(self, address):
        super().__init__(address, port=9443, timeout=8)


class Policy:
    def __init__(self, config_path, verifier=None, revocations=None):
        self.config_path = config_path
        config = load_config(config_path)
        self.issuer, self.audience, self.origin = config['issuer'], config['audience'], config['origin']
        self.verifier = verifier or AccessVerifier(self.issuer, self.audience)
        self.csrf_key = secrets.token_bytes(32)
        self.database_lock = threading.Lock()
        self.database = sqlite3.connect(str(revocations) if revocations else ':memory:', check_same_thread=False)
        self.database.execute('CREATE TABLE IF NOT EXISTS revoked (sid TEXT PRIMARY KEY, expires REAL NOT NULL)')
        # First-login bindings for routes registered without a subject; never rewritten.
        self.database.execute('CREATE TABLE IF NOT EXISTS bindings (workspace TEXT PRIMARY KEY, email TEXT NOT NULL, '
                              'subject TEXT NOT NULL UNIQUE, bound REAL NOT NULL)')
        self.database.commit()

    def current_config(self):
        config = load_config(self.config_path)
        if (config['issuer'], config['audience'], config['origin']) != (self.issuer, self.audience, self.origin):
            raise Denied()
        return config

    def revoked(self, sid):
        with self.database_lock:
            return self.database.execute('SELECT 1 FROM revoked WHERE sid = ? AND expires > ?', (sid, time.time())).fetchone() is not None

    def logout(self, token):
        self.identity(token)
        claims = self.verifier.verify(token)
        with self.database_lock:
            self.database.execute('DELETE FROM revoked WHERE expires <= ?', (time.time(),))
            self.database.execute('INSERT OR REPLACE INTO revoked VALUES (?, ?)', (hashlib.sha256(token.encode()).hexdigest(), claims['exp']))
            self.database.commit()

    @staticmethod
    def route_fingerprint(route):
        return hashlib.sha256(json.dumps(route, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def lease(self, route, token):
        claims = self.verifier.verify(token)
        record = {'workspace': route['workspace_id'], 'route': self.route_fingerprint(route),
                  'sid': hashlib.sha256(token.encode()).hexdigest(), 'exp': claims['exp']}
        raw = base64.urlsafe_b64encode(json.dumps(record, separators=(',', ':')).encode()).decode().rstrip('=')
        signature = hmac.new(self.csrf_key, ('stream:' + raw).encode(), hashlib.sha256).hexdigest()
        return raw + '.' + signature

    def read_lease(self, value, workspace):
        if not isinstance(value, str) or len(value) > 2048:
            raise Denied()
        raw, signature = value.split('.')
        expected = hmac.new(self.csrf_key, ('stream:' + raw).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise Denied()
        record = decode_json(unbase64(raw))
        if record['workspace'] != workspace:
            raise Denied()
        self.check_lease(record)
        return record

    def check_lease(self, record, config=None):
        config = config or self.current_config()
        if record['exp'] <= time.time() or self.revoked(record['sid']):
            raise Denied()
        for route in config['routes']:
            if route['workspace_id'] == record['workspace'] and route['enabled'] and self.route_fingerprint(route) == record['route']:
                return
        raise Denied()

    def identity(self, token):
        config = self.current_config()
        if self.revoked(hashlib.sha256(token.encode()).hexdigest()):
            raise Denied()
        claims = self.verifier.verify(token)
        for route in config['routes']:
            if route['enabled'] and claims['email'].lower() == route['email'] and claims['sub'] == self.subject(route, claims, config):
                identity = hashlib.sha256((self.issuer + '\0' + claims['sub']).encode()).hexdigest()
                return route, {'workspace_id': route['workspace_id'], 'generation': route['generation'], 'identity': identity}
        raise Denied()

    def subject(self, route, claims, config):
        """The route's Access subject: fixed in the configuration, or bound at the first login."""
        if route['subject']:
            return route['subject']
        with self.database_lock:
            row = self.database.execute('SELECT email, subject FROM bindings WHERE workspace = ?', (route['workspace_id'],)).fetchone()
            if row:
                # A reused workspace ID with another email needs the administrator to clear it.
                return row[1] if row[0] == route['email'] else None
            # A subject already fixed or bound for another workspace is never bound again.
            if any(other['subject'] == claims['sub'] for other in config['routes']):
                return None
            if self.database.execute('SELECT 1 FROM bindings WHERE subject = ?', (claims['sub'],)).fetchone():
                return None
            self.database.execute('INSERT INTO bindings VALUES (?, ?, ?, ?)', (route['workspace_id'], route['email'], claims['sub'], time.time()))
            self.database.commit()
            return claims['sub']

    def csrf(self, token, workspace):
        message = json.dumps([token, workspace], sort_keys=True, separators=(',', ':')).encode()
        return hmac.new(self.csrf_key, message, hashlib.sha256).hexdigest()

    def exchange(self, route):
        config = load_config(self.config_path)
        secret = Path('/etc/hapi-control-plane/tokens', route['workspace_id']).read_text().strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,}', secret):
            raise ValueError('Invalid service credential')
        headers = {'Content-Type': 'application/json', 'Host': route['backend_name']}
        if config.get('shared_hub', False):
            connection = http.client.HTTPConnection('127.0.0.1', port=3006, timeout=8)
            headers['X-Hapi-Expected-Namespace'] = route.get('namespace', 'default')
        else:
            connection = HubConnection(route['backend_address'])
        try:
            connection.request('POST', '/api/auth', body=json.dumps({'accessToken': secret}),
                               headers=headers)
            response = connection.getresponse()
            raw = response.read(16385)
            if response.status != 200 or len(raw) > 16384:
                raise ValueError('Invalid ticket response')
            result = decode_json(raw)
            if not isinstance(result, dict):
                raise ValueError('Invalid ticket response')
            if not isinstance(result.get('token'), str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', result['token']):
                raise ValueError('Invalid ticket')
            if not isinstance(result.get('user'), dict):
                raise ValueError('Invalid user')
            return {'token': result['token'], 'user': result['user']}
        finally:
            connection.close()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def log_message(self, *_args):
        pass

    def send_json(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def one_header(self, name):
        values = self.headers.get_all(name, [])
        if len(values) != 1:
            raise Denied()
        return values[0]

    def perform(self):
        policy = self.server.policy
        if self.one_header('Host') != policy.origin.removeprefix('https://'):
            raise Denied()
        if self.path == '/health' and self.command == 'GET':
            load_config(policy.config_path)
            self.send_json(200, {'status': 'prototype', 'public_ready': False})
            return
        if len(self.headers.get_all('Origin', [])) > 1:
            raise Denied()
        token = self.one_header('Cf-Access-Jwt-Assertion')
        route, workspace = policy.identity(token)
        if self.command == 'GET' and self.path == '/authorize':
            method = self.one_header('X-Hapi-Method')
            origin = self.headers.get('Origin')
            upgrade = self.headers.get('Upgrade', '').lower()
            if method not in ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']:
                raise Denied()
            if (method not in ['GET', 'HEAD', 'OPTIONS'] or upgrade == 'websocket') and origin != policy.origin:
                raise Denied()
            if origin is not None and origin != policy.origin:
                raise Denied()
            if self.headers.get('X-Hapi-Resource') == 'login' and method not in ['GET', 'HEAD']:
                if not hmac.compare_digest(self.one_header('X-Hapi-CSRF'), policy.csrf(token, workspace)):
                    raise Denied()
            self.send_json(200, {}, {'X-Hapi-Stream-Lease': policy.lease(route, token),
                                    'X-Hapi-Upstream': 'hapi_' + route['workspace_id'].replace('-', '_'),
                                    'X-Hapi-Tls-Name': route['backend_name']})
        elif self.command == 'GET' and self.path == '/_workspace/login/':
            if self.headers.get('Origin') not in [None, policy.origin]:
                raise Denied()
            self.portal(workspace)
        elif self.command == 'GET' and self.path == '/_workspace/identity':
            if self.headers.get('Origin') not in [None, policy.origin]:
                raise Denied()
            self.send_json(200, {**workspace, 'csrf': policy.csrf(token, workspace)})
        elif self.command == 'POST' and self.path in ['/_workspace/session', '/_workspace/logout']:
            if self.one_header('Origin') != policy.origin or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise Denied()
            if not hmac.compare_digest(self.one_header('X-Hapi-CSRF'), policy.csrf(token, workspace)):
                raise Denied()
            if self.headers.get_all('Transfer-Encoding') or self.one_header('Content-Type') != 'application/json':
                raise Denied()
            length = self.one_header('Content-Length')
            if not length.isdecimal() or not 0 < int(length) <= 64:
                raise Denied()
            if decode_json(self.rfile.read(int(length))) != {}:
                raise Denied()
            if self.path == '/_workspace/logout':
                policy.logout(token)
                self.send_json(200, {'logged_out': True})
                return
            result = policy.exchange(route)
            # A disable or reassignment during the exchange must not issue a stale ticket.
            _, current = policy.identity(token)
            if current != workspace:
                raise Denied()
            self.send_json(200, {**result, 'workspace': workspace})
        else:
            self.send_json(404, {'error': 'unsupported_endpoint'})

    def portal(self, workspace):
        page = (Path(__file__).parent / 'hapi-login-portal/index.html').read_text()
        context = html.escape(json.dumps(workspace), quote=True)
        body = page.replace('{{workspace}}', context).replace('{{hapi_url}}', '/sessions').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' " +
                         self.server.policy.origin.replace('https:', 'wss:') +
                         "; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def dispatch(self):
        try:
            self.perform()
        except Denied:
            self.send_json(403, {'error': 'access_denied'})
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, http.client.HTTPException):
            self.send_json(503, {'error': 'workspace_unavailable'})

    do_GET = dispatch
    do_POST = dispatch


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    # HTTP/2 module graphs arrive in bursts; the Unix server default is only 5.
    request_queue_size = 128
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        pass  # Never emit request bodies or upstream exception details.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--socket', default='/run/hapi-control-plane/auth.sock')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--revocations', default='/var/lib/hapi-control-plane/revoked.sqlite3')
    parser.add_argument('--routes', default='/run/hapi-control-plane/routes')
    parser.add_argument('--bridges', default='/run/hapi-control-proxy/bridges')
    args = parser.parse_args()
    if args.check:
        checked = Policy(args.config)
        checked.database.close()
        print('PASS: prototype configuration is valid; public entry remains disabled')
        return
    policy = Policy(args.config, revocations=args.revocations)
    loader = importlib.machinery.SourceFileLoader('hapi_stream_guard', str(Path(__file__).with_name('hapi-stream-guard.py')))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    streams = module.StreamManager(policy, args.routes, args.bridges)
    if os.path.exists(args.socket):
        raise SystemExit('Socket already exists; refuse to replace an unknown endpoint')
    with Server(args.socket, Handler) as server:
        server.policy = policy
        os.chmod(args.socket, 0o660)
        streams.start()
        def stop(_signal, _frame):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            server.serve_forever()
        finally:
            streams.close()
            policy.database.close()


if __name__ == '__main__':
    main()
