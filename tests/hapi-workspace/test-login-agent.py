#!/usr/bin/env python3
"""Fixed-agent HTTP boundaries and extracted real tmux/PTY login-flow regressions."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT/'ansible/roles/claude-login-agent/files'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


AGENT = load('agent', FILES/'claude-login-agent.py')
FIXTURE = load('existing_login_fixture', ROOT/'tests/employee-workspace/test-login.py')
FIXTURE.SOURCE = FILES


class AgentBoundary(unittest.TestCase):
    def setUp(self):
        class Flow:
            def __init__(self): self.actions = []
            def status(self): return {'state': 'idle', 'authenticated': False, 'viewer_ready': False}
            def start(self): self.actions.append('start'); return self.status()
            def code(self, value): self.actions.append(value)
            def cancel(self): self.actions.append('cancel')
        self.server = AGENT.Server(('127.0.0.1', 0), AGENT.Agent)
        self.server.origin, self.server.flow = 'https://hapi.example.com', Flow()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)

    def request(self, path, body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        client.request('POST' if body is not None else 'GET', path, body, headers or {})
        response = client.getresponse(); raw = response.read(); client.close()
        return response.status, raw

    def test_only_fixed_authenticated_proxy_operations_are_available(self):
        headers = {'Host': 'hapi.example.com', 'X-Hapi-Login-Service': 'verified-proxy',
                   'Origin': 'https://hapi.example.com', 'Content-Type': 'application/json'}
        self.assertEqual(self.request('/api/login/status')[0], 403)
        self.assertEqual(self.request('/api/login/start', '{}', headers)[0], 200)
        self.assertEqual(self.request('/api/login/start', '{"command":"whoami"}', headers)[0], 400)
        self.assertEqual(self.request('/shell', '{}', headers)[0], 404)
        self.assertEqual(self.request('/', headers=headers)[0], 404)
        self.assertEqual(self.server.flow.actions, ['start'])
        self.assertEqual(self.request('/api/login/code', '{"code":"x"}', {**headers, 'Origin': 'https://other.example'})[0], 403)


@unittest.skipUnless(shutil.which('tmux'), 'requires the approved real tmux runtime')
class Authorization(unittest.TestCase):
    def setUp(self):
        method = next(name for name in dir(FIXTURE.LoginFlow) if name.startswith('test_'))
        self.fixture = FIXTURE.LoginFlow(method); self.fixture.setUp()
        self.base = self.fixture.base
        # The newer shared helper also requires the private D-Bus launcher.
        if not (self.base/'bin/dbus-run-session').exists():
            (self.base/'bin/dbus-run-session').symlink_to('/bin/true')
        source = (FILES/'claude-login-flow.py').read_text().replace(
            "LOGIN = Path('/usr/local/bin/workspace-login')", 'LOGIN = Path('+repr(str(self.base/'bin/workspace-login'))+')')
        source = source.replace("Path('/run/employee-browser/browser-ready')", 'Path('+repr(str(self.base/'browser-started'))+')')
        target = self.base/'flow.py'; target.write_text(source)
        self.module = load('extracted_flow', target)
        self.env = patch.dict(os.environ, {**self.fixture.env, 'LOGIN_SCENARIO': 'manual', 'TERM': 'xterm-256color'})
        self.env.start()
        self.flow = self.module.Flow(cache=self.base/'guide-cache')

    def tearDown(self):
        self.flow.close(); self.env.stop(); self.fixture.tearDown()

    def wait(self, predicate):
        deadline = time.monotonic()+12
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.1)
        self.fail('Synthetic authorization did not reach the expected state')

    def test_existing_or_other_authentication_is_never_overwritten(self):
        os.environ['LOGIN_SCENARIO'] = 'already'
        self.assertTrue(self.flow.start()['authenticated'])
        self.assertFalse((self.base/'login-started').exists())
        os.environ['LOGIN_SCENARIO'] = 'other-source'
        with self.assertRaises(ValueError): self.flow.start()

    def test_completed_login_becomes_retryable_or_blocked_after_authentication_changes(self):
        for method, expected in [('none', 'idle'), ('unknown', 'unknown'), ('api_key', 'blocked')]:
            self.flow.state, self.flow.authenticated, self.flow.checked = 'success', True, 0
            self.flow.auth = lambda method=method: (False, method)
            result = self.flow.status()
            self.assertEqual(result['state'], expected)
            self.assertFalse(result['authenticated'])

    def test_manual_code_uses_real_private_tmux_and_preserves_browser(self):
        self.assertEqual(self.flow.start()['state'], 'running')
        self.wait(lambda: (self.base/'browser-started').exists())
        self.assertEqual(self.flow.start()['state'], 'running')
        self.flow.code('fixture-code')
        self.wait(lambda: self.flow.status()['state']=='success')
        self.assertNotIn('fixture-private-state', json.dumps(self.flow.status()))
        self.assertEqual((self.base/'auth-log-mode').read_text(), '0o600')
        os.kill(int((self.base/'browser-pid').read_text()), 0)

    def test_cancel_and_timeout_preserve_the_daily_browser(self):
        self.flow.start(); self.wait(lambda: (self.base/'browser-started').exists())
        self.flow.started = time.monotonic()-1801
        self.assertEqual(self.flow.status()['state'], 'expired')
        self.assertIsNone(self.flow.runtime)
        os.kill(int((self.base/'browser-pid').read_text()), 0)
        self.flow.start(); self.flow.cancel()
        self.assertEqual(self.flow.status()['state'], 'cancelled')
        os.kill(int((self.base/'browser-pid').read_text()), 0)

    def test_unreadable_status_and_control_character_codes_fail_closed(self):
        os.environ['LOGIN_SCENARIO'] = 'bad-status'
        self.assertEqual(self.flow.status()['state'], 'unknown')
        with self.assertRaises(ValueError): self.flow.start()
        for code in ['', None, 'bad\ncommand', 'bad\x02d']:
            with self.assertRaises(ValueError): self.flow.code(code)


if __name__ == '__main__':
    unittest.main(verbosity=2)
