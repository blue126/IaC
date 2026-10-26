#!/usr/bin/env python3
"""Validate system secrets on the controller without printing secret material."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def validate(config):
    encoded = config['wireguard_private_key'].strip()
    if len(base64.b64decode(encoded, validate=True)) != 32:
        raise ValueError('Invalid WireGuard private key')
    public = base64.b64encode(X25519PrivateKey.from_private_bytes(base64.b64decode(encoded, validate=True)).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    if public in {device['wireguard_public_key'] for device in config['devices'].values()}:
        raise ValueError('Gateway and device WireGuard keys must differ')
    derived = set()
    with tempfile.TemporaryDirectory(prefix='employee-secret-preflight-') as directory:
        path = Path(directory) / 'key'
        path.touch(mode=0o600)
        for name, device in config['devices'].items():
            if not device['enabled'] or config['networks'][device['employee']]['disabled']:
                continue
            path.write_text(config['private_keys'][name])
            result = subprocess.run(['ssh-keygen', '-y', '-P', '', '-f', str(path)], text=True, capture_output=True, check=True)
            key = ' '.join(result.stdout.split()[:2])
            if not key.startswith('ssh-ed25519 ') or key in derived:
                raise ValueError('System SSH credentials must be distinct Ed25519 keys')
            derived.add(key)


if __name__ == '__main__':
    try:
        validate(json.load(sys.stdin))
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError):
        print('System credential preflight failed; check required unique unencrypted keys.', file=sys.stderr)
        sys.exit(1)
