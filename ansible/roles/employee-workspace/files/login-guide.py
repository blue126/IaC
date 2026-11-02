#!/usr/bin/python3
"""Owner-only loopback login guide behind the existing Access/JWT ingress."""
import argparse
import base64
import ssl
import fcntl
import html
import http.server
import importlib.machinery
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import select
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit

SELF = Path(__file__).resolve()
LOGIN = Path('/usr/local/bin/workspace-login')
ASSETS = SELF.parent / 'login-guide'
BROWSER_READY = Path('/run/employee-browser/browser-ready')
VIEWER = ('127.0.0.1', 6081)
NOVNC = Path('/usr/share/novnc')
BROWSER_CONFIG = Path('/etc/employee-workspace-browser.json')
DESKTOP_SERVICE = Path('/usr/local/lib/employee-workspace/desktop-service.py')


def viewer_connection():
    """Keep the existing noVNC/RFB frontend; authenticate only the TLS backend."""
    config = json.loads(BROWSER_CONFIG.read_text())
    if config.get('mode', 'legacy-novnc') == 'legacy-novnc':
        return socket.create_connection(VIEWER, timeout=10), [
            'Host: 127.0.0.1:6081']
    if config.get('mode') != 'kasmvnc':
        raise ValueError('Unsupported viewer backend')
    path = DESKTOP_SERVICE
    spec = importlib.util.spec_from_file_location('desktop_service', path)
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)
    try:
        desktop = service.load_config()
        authentication = service.validate_materials(desktop)
        service.transition_guard()
    except service.Refused:
        raise ValueError('Desktop backend unavailable') from None
    context = ssl.create_default_context(cafile=str(desktop['materials']['trust_ref']))
    raw = socket.create_connection(('127.0.0.1', 8444), timeout=10)
    try:
        connection = context.wrap_socket(raw, server_hostname='localhost')
    except BaseException:
        raw.close()
        raise
    basic = base64.b64encode((authentication['username'] + ':' + authentication['password']).encode()).decode()
    return connection, ['Host: localhost', 'Origin: https://localhost:8444',
                        'Sec-WebSocket-Origin: https://localhost:8444',
                        'Sec-WebSocket-Protocol: binary',
                        'Authorization: Basic ' + basic]


def kasm_upgrade_response(response, offered_binary):
    """Do not advertise an upstream-only subprotocol to an unoffering browser."""
    header, separator, pending = response.partition(b'\r\n\r\n')
    if not separator:
        raise ValueError('Incomplete backend upgrade')
    lines = header.split(b'\r\n')
    protocols = [line.partition(b':')[2].strip() for line in lines[1:]
                 if line.partition(b':')[0].lower() == b'sec-websocket-protocol']
    if protocols and protocols != [b'binary']:
        raise ValueError('Unsupported backend subprotocol')
    if not offered_binary:
        lines = [line for line in lines if line.partition(b':')[0].lower() != b'sec-websocket-protocol']
    return b'\r\n'.join(lines) + separator + pending


class FlowError(ValueError):
    """A fixed, user-facing message that contains no subprocess output."""


def read_auth():
    # Reuse the existing helper's validation and subscription-source checks.
    loader = importlib.machinery.SourceFileLoader('workspace_login', str(LOGIN))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    data = module.auth_status()
    return module.subscription_login(data), data.get('authMethod', 'none')


class Flow:
    def __init__(self, cache=None, auth=None):
        self.cache = cache or Path.home() / '.cache/workspace-login-guide'
        self.cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.auth = auth or read_auth
        self.lock = threading.RLock()
        self.runtime = None
        self.state = 'idle'
        self.started = 0
        self.authenticated = False
        self.auth_method = 'none'
        self.checked = 0

    def tmux(self, *args, data=None):
        return subprocess.run(['tmux', '-S', str(self.runtime / 'tmux.sock'), *args],
                              input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=6, check=False)

    def active(self):
        return self.runtime is not None and self.tmux('has-session', '-t', 'guide').returncode == 0

    def check_auth(self):
        try:
            self.authenticated, self.auth_method = self.auth()
            self.checked = time.monotonic()
            return True
        except (OSError, ValueError, subprocess.SubprocessError):
            self.authenticated, self.auth_method = False, 'unknown'
            return False

    def status(self):
        with self.lock:
            if self.state == 'running':
                result = self.runtime / 'result'
                if result.exists():
                    self.state = ('success' if result.read_text() == '0' and
                                  self.check_auth() and self.authenticated else 'failed')
                    self.tmux('kill-server')
                elif time.monotonic() - self.started > 1800:
                    self.cancel()
                    self.state = 'expired'
                elif not self.active():
                    self.state = 'failed'
            elif time.monotonic() - self.checked > 3:
                self.check_auth()
            state = self.state
            if self.auth_method == 'unknown' and state == 'idle':
                state = 'unknown'
            elif self.authenticated and state != 'running':
                state = 'success'
            elif self.auth_method not in ('none', 'claude.ai', 'unknown') and state == 'idle':
                state = 'blocked'
            return {'state': state, 'authenticated': self.authenticated,
                    'viewer_ready': state == 'running' and BROWSER_READY.is_file()}

    def start(self):
        with self.lock:
            if self.status()['state'] == 'running':
                return self.status()
            if not self.check_auth():
                raise FlowError('无法确认 Claude 登录状态，请稍后重试。')
            if self.authenticated:
                self.state = 'success'
                return self.status()
            if self.auth_method not in ('none', 'claude.ai'):
                raise FlowError('当前使用其他认证来源，请联系管理员核对；不会覆盖现有配置。')
            cache = Path.home() / '.cache/workspace-login'
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            with (cache / 'lock').open('a+') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise FlowError('已有登录流程正在运行，请先完成或取消原流程。') from None
            self.clear_runtime()
            self.runtime = Path(tempfile.mkdtemp(prefix='flow-', dir=self.cache))
            config = self.runtime / 'tmux.conf'
            config.write_text('set-option -g history-limit 0\n')
            command = shlex.join([sys.executable, str(SELF), '--worker', str(self.runtime)])
            if self.tmux('-f', str(config), 'new-session', '-d', '-s', 'guide', '-x', '100', '-y', '35',
                         command).returncode:
                self.clear_runtime()
                raise FlowError('无法启动授权，请稍后重试。')
            self.started, self.state = time.monotonic(), 'running'
            return self.status()

    def code(self, value):
        if (not isinstance(value, str) or not 1 <= len(value) <= 4096 or
                any(ord(c) < 33 or ord(c) > 126 for c in value)):
            raise FlowError('请粘贴官方页面提供的单行授权码。')
        with self.lock:
            if self.state != 'running' or not self.active() or not BROWSER_READY.is_file():
                raise FlowError('当前没有等待授权的登录流程。')
            # Secrets go through stdin into this flow's private tmux socket, never argv.
            if self.tmux('load-buffer', '-b', 'auth-code', '-',
                         data=(value + '\n').encode()).returncode:
                raise FlowError('授权码未能提交，请重试。')
            try:
                if self.tmux('paste-buffer', '-d', '-b', 'auth-code', '-t', 'guide').returncode:
                    raise FlowError('授权码未能提交，请重试。')
            finally:
                self.tmux('delete-buffer', '-b', 'auth-code')

    def cancel(self):
        with self.lock:
            if self.runtime is not None:
                if self.active():
                    # Detach the existing helper so its own cleanup runs before teardown.
                    self.tmux('send-keys', '-t', 'guide', 'C-b', 'd')
                    deadline = time.monotonic() + 5
                    while self.active() and time.monotonic() < deadline:
                        time.sleep(.1)
                self.tmux('kill-server')
            self.state = 'cancelled'
            self.clear_runtime()

    def clear_runtime(self):
        if self.runtime is not None:
            import shutil
            shutil.rmtree(self.runtime)
            self.runtime = None

    def close(self):
        self.cancel()


class Guide(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    rbufsize = 0

    def log_message(self, *_args):
        pass  # Never log request bodies, auth codes or query strings.

    def reply(self, status, body, content_type='application/json; charset=utf-8', nonce=''):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if status >= 400:
            self.close_connection = True
            self.send_header('Connection', 'close')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        nonce_source = " 'nonce-" + nonce + "'" if nonce else ''
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'" + nonce_source +
                         "; style-src 'self'" + nonce_source + "; "
                         "connect-src 'self' " + self.server.origin.replace('https:', 'wss:') +
                         "; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def json_reply(self, status, value):
        self.reply(status, json.dumps(value, ensure_ascii=False).encode())

    def trusted_host(self):
        return self.headers.get_all('Host', []) == [urlsplit(self.server.origin).netloc]

    def authorized_request(self, mutation=False):
        return (self.trusted_host() and
                secrets.compare_digest(self.headers.get('X-Login-CSRF', '').encode(), self.server.csrf.encode()) and
                len(self.headers.get_all('Origin', [])) <= 1 and
                (self.headers.get('Origin') == self.server.origin if mutation else
                 self.headers.get('Origin') in (None, self.server.origin)))

    def do_GET(self):
        if not self.trusted_host():
            return self.json_reply(403, {'error': '入口主机名不匹配。'})
        if self.path == '/':
            page = (ASSETS / 'index.html').read_text().replace('{{csrf}}', self.server.csrf)
            page = page.replace('{{hapi_url}}', html.escape(self.server.hapi_url, quote=True))
            return self.reply(200, page.encode(), 'text/html; charset=utf-8')
        if self.path in ('/guide.js', '/guide.css'):
            name = self.path[1:]
            kind = 'text/javascript' if name.endswith('.js') else 'text/css'
            return self.reply(200, (ASSETS / name).read_bytes(), kind + '; charset=utf-8')
        if self.path == '/api/login/status':
            if not self.authorized_request():
                return self.json_reply(403, {'error': '请刷新授权页面后重试。'})
            return self.json_reply(200, self.server.flow.status())
        if self.path == '/websockify':
            return self.websocket()
        path = unquote(urlsplit(self.path).path)
        if ('..' in path.split('/') or '\\' in path or '\x00' in path or path.endswith('/')):
            return self.json_reply(404, {'error': '页面不存在。'})
        if (path in ('/vnc.html', '/vnc_lite.html', '/defaults.json', '/mandatory.json') or
                path.startswith(('/app/', '/core/', '/vendor/', '/include/'))):
            return self.static_proxy()
        self.json_reply(404, {'error': '页面不存在。'})

    def do_POST(self):
        if not self.authorized_request(mutation=True):
            return self.json_reply(403, {'error': '请刷新授权页面后重试。'})
        try:
            sizes = self.headers.get_all('Content-Length', [])
            if (self.headers.get('Transfer-Encoding') or len(sizes) != 1 or
                    not 0 < int(sizes[0]) <= 8192 or
                    self.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
                raise ValueError('请求格式无效。')
            data = json.loads(self.rfile.read(int(sizes[0])))
            if not isinstance(data, dict):
                raise ValueError('请求格式无效。')
            if self.path == '/api/login/start':
                return self.json_reply(200, self.server.flow.start())
            if self.path == '/api/login/cancel':
                self.server.flow.cancel()
            elif self.path == '/api/login/code':
                self.server.flow.code(data.get('code'))
            else:
                return self.json_reply(404, {'error': '操作不存在。'})
            self.json_reply(200, self.server.flow.status())
        except FlowError as exc:
            self.json_reply(400, {'error': str(exc)})
        except ValueError:
            self.json_reply(400, {'error': '请求格式无效，请刷新页面后重试。'})
        except (OSError, subprocess.SubprocessError):
            self.json_reply(503, {'error': '授权服务暂时不可用，请稍后重试。'})

    def static_proxy(self):
        try:
            # Assets must be available even while the personal browser is stopped.
            path = (NOVNC / unquote(urlsplit(self.path).path).lstrip('/')).resolve()
            roots = (NOVNC.resolve(), Path('/usr/share/javascript'))
            if (not any(path.is_relative_to(root) for root in roots) or
                    not path.is_file() or path.stat().st_size > 5 * 1024 * 1024):
                return self.json_reply(404, {'error': '资源不存在。'})
            kind = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
            body, nonce = path.read_bytes(), ''
            if path.suffix == '.html':
                # Packaged legacy noVNC pages contain trusted inline module bootstraps.
                nonce = secrets.token_urlsafe(24)
                body = re.sub(rb'<(script|style)(?=[\s>])',
                              lambda m: m[0] + b' nonce="' + nonce.encode() + b'"',
                              body, flags=re.IGNORECASE)
            self.reply(200, body, kind, nonce=nonce)
        except OSError:
            self.json_reply(404, {'error': '资源不存在。'})

    def websocket(self):
        if (self.headers.get('Origin') != self.server.origin or
                self.headers.get('Upgrade', '').lower() != 'websocket' or
                self.headers.get('Sec-WebSocket-Version') != '13'):
            return self.json_reply(403, {'error': '远程画面请求无效。'})
        upstream = None
        switched = False
        try:
            upstream, identity = viewer_connection()
            headers = ['GET /websockify HTTP/1.1', *identity,
                       'Upgrade: websocket', 'Connection: Upgrade', 'Sec-WebSocket-Version: 13']
            fixed_binary = 'Sec-WebSocket-Protocol: binary' in identity
            offered_protocols = self.headers.get('Sec-WebSocket-Protocol', '')
            offered_binary = 'binary' in [value.strip() for value in offered_protocols.split(',')]
            if fixed_binary and (len(self.headers.get_all('Sec-WebSocket-Protocol', [])) > 1
                                 or (offered_protocols and not offered_binary)):
                return self.json_reply(403, {'error': '远程画面子协议不受支持。'})
            for name in ('Sec-WebSocket-Key', 'Sec-WebSocket-Protocol'):
                value = self.headers.get(name, '')
                if '\r' in value or '\n' in value or len(value) > 256:
                    raise ValueError('Invalid WebSocket header')
                if value and not (fixed_binary and name == 'Sec-WebSocket-Protocol'):
                    headers.append(name + ': ' + value)
            upstream.sendall(('\r\n'.join(headers) + '\r\n\r\n').encode())
            response = b''
            while b'\r\n\r\n' not in response:
                chunk = upstream.recv(4096)
                if not chunk or len(response) > 16384:
                    raise ValueError('Invalid WebSocket response')
                response += chunk
            if not response.startswith(b'HTTP/1.1 101 '):
                return self.json_reply(503, {'error': '远程浏览器尚未就绪。'})
            if fixed_binary:
                response = kasm_upgrade_response(response, offered_binary)
            self.wfile.flush()
            self.connection.sendall(response)
            switched, self.close_connection = True, True
            expires = time.monotonic() + 3600
            while time.monotonic() < expires:
                ready = [upstream] if isinstance(upstream, ssl.SSLSocket) and upstream.pending() else select.select([self.connection, upstream], [], [], 10)[0]
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    target = upstream if source is self.connection else self.connection
                    target.sendall(data)
                    expires = time.monotonic() + 3600
        except (OSError, ValueError):
            if not switched:
                self.json_reply(503, {'error': '远程画面暂时不可用。'})
        finally:
            if upstream is not None:
                upstream.close()


def worker(value):
    runtime = Path(value)
    info = runtime.stat()
    if not runtime.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Invalid private flow directory')
    result = subprocess.run([str(LOGIN)], check=False)
    (runtime / 'result.next').write_text(str(result.returncode))
    (runtime / 'result.next').replace(runtime / 'result')


def main():
    os.umask(0o077)
    if os.geteuid() == 0:
        raise ValueError('Run the personal login guide as the employee account')
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        worker(sys.argv[2])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--hapi-url', required=True)
    args = parser.parse_args()
    for value in (args.origin, args.hapi_url):
        url = urlsplit(value)
        if (url.scheme != 'https' or not url.hostname or url.netloc != url.hostname or
                url.path not in ('', '/') or url.query or url.fragment):
            raise ValueError('Expected an HTTPS origin')
    flow = Flow()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 6082), Guide)
    server.origin, server.hapi_url = args.origin.rstrip('/'), args.hapi_url
    server.csrf, server.flow = secrets.token_urlsafe(32), flow
    def stop(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        flow.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Login guide failed; sensitive details withheld.', file=sys.stderr)
        raise SystemExit(1)
