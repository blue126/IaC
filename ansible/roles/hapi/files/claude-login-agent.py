#!/usr/bin/env python3
"""Expose fixed personal-authorization operations behind the VM mTLS proxy."""
import argparse
import http.server
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import threading
from urllib.parse import urlsplit

loader = importlib.machinery.SourceFileLoader('claude_login_flow', str(Path(__file__).with_name('claude-login-flow.py')))
flow_module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(flow_module)


class Agent(http.server.BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, *_args):
        pass

    def reply(self, status, value):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    @staticmethod
    def public_state(value):
        if (not isinstance(value, dict) or value.get('state') not in
                ['idle', 'running', 'success', 'failed', 'cancelled', 'expired', 'unknown', 'blocked'] or
                type(value.get('authenticated')) is not bool or type(value.get('viewer_ready')) is not bool):
            raise ValueError()
        return {key: value[key] for key in ['state', 'authenticated', 'viewer_ready']}

    def trusted(self, mutation=False):
        return (self.headers.get_all('Host', []) == [urlsplit(self.server.origin).netloc]
                and self.headers.get_all('X-Hapi-Login-Service', []) == ['verified-proxy']
                and len(self.headers.get_all('Origin', [])) <= 1
                and (self.headers.get('Origin') == self.server.origin if mutation else
                     self.headers.get('Origin') in [None, self.server.origin]))

    def do_GET(self):
        if not self.trusted():
            return self.reply(403, {'error': '入口验证失败。'})
        if self.path != '/api/login/status':
            return self.reply(404, {'error': '操作不存在。'})
        try:
            self.reply(200, self.public_state(self.server.flow.status()))
        except Exception:
            self.reply(503, {'error': '授权状态暂时不可用。'})

    def do_POST(self):
        if not self.trusted(mutation=True):
            return self.reply(403, {'error': '入口验证失败。'})
        if self.path not in ['/api/login/start', '/api/login/code', '/api/login/cancel']:
            return self.reply(404, {'error': '操作不存在。'})
        try:
            lengths = self.headers.get_all('Content-Length', [])
            if (self.headers.get_all('Transfer-Encoding') or len(lengths) != 1 or
                    not lengths[0].isdecimal() or not 0 < int(lengths[0]) <= 8192 or
                    self.headers.get_all('Content-Type', []) != ['application/json']):
                raise ValueError()
            body = json.loads(self.rfile.read(int(lengths[0])))
            if not isinstance(body, dict) or set(body) != ({'code'} if self.path.endswith('/code') else set()):
                raise ValueError()
            if self.path.endswith('/start'):
                result = self.server.flow.start()
            else:
                if self.path.endswith('/code'):
                    self.server.flow.code(body['code'])
                else:
                    self.server.flow.cancel()
                result = self.server.flow.status()
            self.reply(200, self.public_state(result))
        except flow_module.FlowError as error:
            self.reply(400, {'error': str(error)})
        except ValueError:
            self.reply(400, {'error': '请求格式无效。'})
        except Exception:
            self.reply(503, {'error': '授权服务暂时不可用。'})


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    args = parser.parse_args()
    origin = urlsplit(args.origin)
    if os.geteuid() == 0 or origin.scheme != 'https' or origin.netloc != origin.hostname or origin.path or origin.query or origin.fragment:
        raise SystemExit('Run as employee with the approved HTTPS origin')
    os.umask(0o077)
    with Server(('127.0.0.1', 6082), Agent) as server:
        server.origin, server.flow = args.origin, flow_module.Flow()
        def stop(_signal, _frame):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            server.serve_forever()
        finally:
            server.flow.close()


if __name__ == '__main__':
    main()
