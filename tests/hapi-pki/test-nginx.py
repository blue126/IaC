#!/usr/bin/env python3
"""Reach the real Unix PKI agent through the rendered private Nginx mTLS endpoint."""
import importlib.util
import json
from pathlib import Path
import shutil
import ssl
import subprocess
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('life', Path(__file__).with_name('test-lifecycle.py'))
life = importlib.util.module_from_spec(spec);spec.loader.exec_module(life)
spec = importlib.util.spec_from_file_location('proxy_fixture', ROOT / 'tests/hapi-workspace/test-proxy.py')
proxy = importlib.util.module_from_spec(spec);spec.loader.exec_module(proxy)


@unittest.skipUnless(shutil.which('nginx') and shutil.which('ansible'), 'requires the existing approved proxy Sandbox')
class NginxTest(life.LifecycleTest):
    # Reuse setup only; do not repeat the lifecycle cases in this suite.
    __unittest_skip__ = False

    def test_private_endpoint_reaches_agent_without_exposing_a_general_admin_api(self):
        agent = self.agents['worker'];run = self.root / 'nginx-run';run.mkdir()
        for child in ['body', 'proxy', 'fastcgi', 'uwsgi', 'scgi']:
            (run / child).mkdir()
        socket_path = self.root / 'worker.sock'
        server = life.pki.Server(str(socket_path), life.pki.Handler);server.agent = agent
        self.start(server)
        port = proxy.available_port()
        text = proxy.render(ROOT / 'ansible/roles/hapi-ingress/templates/nginx.conf.j2', {
            'hapi_ingress_backend_address': '127.0.0.1', 'hapi_ingress_id': 'vm502',
            'hapi_ingress_web_sha256': 'synthetic', 'hapi_ingress_origin': 'https://hapi.example.invalid'})
        folder = agent.path('/etc/hapi-ingress');(folder / 'pki').mkdir()
        snippet = proxy.render(ROOT / 'ansible/roles/hapi-pki-agent/templates/agent-location.conf.j2', {
            'hapi_pki_agent_control_address': '127.0.0.1'})
        (folder / 'pki/agent.conf').write_text(snippet.replace('/run/hapi-pki-agent/agent.sock', str(socket_path)))
        text = text.replace('/etc/hapi-ingress', str(folder)).replace('/run/hapi-ingress', str(run)).replace(':9443', ':' + str(port))
        config = self.root / 'nginx.conf';config.write_text(text)
        subprocess.run(['nginx', '-t', '-c', str(config)], check=True, capture_output=True)
        process = subprocess.Popen(['nginx', '-c', str(config), '-g', 'daemon off;'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait, 5);self.addCleanup(process.terminate)
        import time,socket,http.client
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.1):break
            except OSError:time.sleep(.02)
        self.aliases['10.77.0.2'] = ('127.0.0.1', port)
        transport = life.pki.Transport(self.config, self.authorities)
        target = self.config['targets'][1]
        value = transport.call(target, {'action': 'inspect'})
        self.assertEqual(set(value['materials']), {'hub-client', 'login-server'})
        self.assertNotIn('PRIVATE KEY', json.dumps(value))
        with self.assertRaises(ValueError):
            transport.call(target, {'action': 'inspect', 'path': '/etc/shadow'})



# Run only the integration case; the base suite is executed separately.
if __name__ == '__main__':
    suite = unittest.TestSuite([NginxTest('test_private_endpoint_reaches_agent_without_exposing_a_general_admin_api')])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
