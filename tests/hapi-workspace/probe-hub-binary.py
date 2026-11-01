#!/usr/bin/env python3
"""Smoke-test the compiled Hub in a disposable loopback-only home."""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time


def probe(binary, digest):
    if hashlib.sha256(Path(binary).read_bytes()).hexdigest() != digest:
        raise ValueError('Binary digest mismatch')
    with tempfile.TemporaryDirectory(prefix='hapi-binary-smoke-') as scratch:
        root = Path(scratch)
        registry = root / 'credentials.json'
        alice, bob, master = (secrets.token_urlsafe(40) for _ in range(3))
        rows = {'version': 1, 'credentials': [
            {'id': 'alice', 'token': alice, 'namespace': 'default', 'generation': 1, 'enabled': True},
            {'id': 'bob', 'token': bob, 'namespace': 'bob', 'generation': 1, 'enabled': True}]}
        registry.write_text(json.dumps(rows))
        registry.chmod(0o600)
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        environment = {'PATH': '/usr/bin:/bin', 'HOME': scratch, 'HAPI_HOME': scratch,
                       'CLI_API_TOKEN': master, 'HAPI_TENANT_CREDENTIALS_FILE': str(registry),
                       'HAPI_LISTEN_HOST': '127.0.0.1', 'HAPI_LISTEN_PORT': str(port),
                       'HAPI_PUBLIC_URL': 'https://hapi.willfan.me',
                       'HAPI_IOS_PUSH': 'off', 'HAPI_ANDROID_PUSH': 'off', 'HAPI_DISABLE_PEER_TOOLS': '1'}
        process = subprocess.Popen([binary, '--no-relay'], cwd=scratch, env=environment,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def request(path, namespace=None, credential=None, jwt=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
            headers = {}
            if namespace is not None:
                headers['X-Hapi-Expected-Namespace'] = namespace
            if jwt:
                headers['Authorization'] = 'Bearer ' + jwt
            body = None
            if credential is not None:
                headers['Content-Type'] = 'application/json'
                body = json.dumps({'accessToken': credential})
            try:
                connection.request('POST' if body else 'GET', path, body=body, headers=headers)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise ValueError('Compiled Hub exited during startup')
                try:
                    if request('/health')[0] == 200:
                        break
                except OSError:
                    pass
                time.sleep(.1)
            else:
                raise ValueError('Compiled Hub did not become healthy')
            assert request('/')[0] == 200, 'Embedded frontend missing'
            status, raw = request('/api/auth', 'default', alice)
            assert status == 200, 'Valid tenant denied'
            jwt = json.loads(raw)['token']
            claims = json.loads(base64.urlsafe_b64decode(jwt.split('.')[1] + '=='))
            assert claims['ns'] == 'default' and claims['cid'] == 'alice' and claims['cver']
            assert request('/api/auth', 'bob', alice)[0] in (401, 403), 'Foreign tenant accepted'
            assert request('/api/auth', 'default', master)[0] in (401, 403), 'Master token accepted'
            assert request('/api/auth', 'default', alice + ':bob')[0] in (401, 403), 'Suffix escalation accepted'
            assert request('/api/sessions', 'default', jwt=jwt)[0] == 200
            assert request('/api/sessions', 'bob', jwt=jwt)[0] in (401, 403), 'Foreign JWT accepted'
            assert request('/api/voice/token', 'default', jwt=jwt)[0] == 403
            rows['credentials'][0]['enabled'] = False
            candidate = root / 'next.json'
            candidate.write_text(json.dumps(rows))
            candidate.chmod(0o600)
            candidate.replace(registry)
            assert request('/api/sessions', 'default', jwt=jwt)[0] in (401, 403), 'Revoked JWT accepted'
            assert request('/api/auth', 'bob', bob)[0] == 200, 'Other tenant affected'
            return {'compiled_hub_smoke_passed': True, 'loopback_only': True,
                    'synthetic_credentials': True, 'production_data_accessed': False, 'artifact_sha256': digest}
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary')
    parser.add_argument('sha256')
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(probe(args.binary, args.sha256)))
