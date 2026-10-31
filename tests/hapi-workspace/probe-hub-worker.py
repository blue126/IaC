#!/usr/bin/env python3
"""Verify fixed identity through the actual worker-to-Hub mTLS transport."""
import base64
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import tempfile


def main():
    identity = json.loads(Path('/etc/hapi-hub-probe/identity.json').read_bytes())
    with tempfile.TemporaryDirectory(prefix='hapi-hub-probe-') as folder:
        root = Path(folder)
        for name, value in [('client.pem', identity['certificate']), ('client.key', identity['private_key'])]:
            path = root / name
            path.write_text(value)
            path.chmod(0o600)
        context = ssl.create_default_context(cadata=identity['ca'])
        context.load_cert_chain(root / 'client.pem', root / 'client.key')

        class Connection(http.client.HTTPSConnection):
            def connect(self):
                raw = socket.create_connection((identity['hub'], 9443), timeout=5)
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)

        def request(path, token=None, jwt=None):
            connection = Connection(identity['server_name'], port=9443, context=context, timeout=5)
            headers = {'Host': identity['server_name'], 'X-Hapi-Expected-Namespace': 'forged',
                       'X-Hapi-Expected-Credential': 'forged'}
            if jwt:
                headers['Authorization'] = 'Bearer ' + jwt
            body = None
            if token is not None:
                headers['Content-Type'] = 'application/json'
                body = json.dumps({'accessToken': token})
            try:
                connection.request('POST' if body else 'GET', path, body=body, headers=headers)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        assert request('/health')[0] == 200
        status, raw = request('/api/auth', identity['token'])
        assert status == 200, 'Registered worker authentication denied'
        jwt = json.loads(raw)['token']
        claims = json.loads(base64.urlsafe_b64decode(jwt.split('.')[1] + '=='))
        assert claims['ns'] == identity['namespace'] and claims['cid'] == identity['credential_id']
        assert claims.get('cver')
        assert request('/api/auth', identity['token'] + ':foreign')[0] in (401, 403)
        assert request('/api/sessions', jwt=jwt)[0] == 200
        assert request('/api/voice/token', jwt=jwt)[0] == 403
        connection = Connection(identity['server_name'], port=9443, context=ssl.create_default_context(cadata=identity['ca']), timeout=5)
        try:
            connection.request('GET', '/health', headers={'Host': identity['server_name']})
            response = connection.getresponse()
            assert response.status in (400, 401, 403)
            response.read()
        except (ssl.SSLError, http.client.RemoteDisconnected):
            pass
        finally:
            connection.close()
        blocked = []
        for host, port in [('192.168.1.140', 22), ('192.168.1.52', 8006)]:
            try:
                with socket.create_connection((host, port), timeout=1):
                    raise AssertionError('Worker reached a protected management endpoint')
            except (TimeoutError, OSError):
                blocked.append(host + ':' + str(port))
        print(json.dumps({'worker': identity['id'], 'namespace': claims['ns'], 'credential_id': claims['cid'],
                          'real_mtls_health': True, 'server_fixed_namespace': True, 'suffix_escalation_denied': True,
                          'unauthenticated_transport_denied': True, 'protected_endpoints_blocked': blocked}))


if __name__ == '__main__':
    os.umask(0o077)
    main()
