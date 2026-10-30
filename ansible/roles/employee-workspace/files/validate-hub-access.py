#!/usr/bin/env python3
"""Validate exact native SSH sources and Ed25519 keys without shell input."""
import base64
import ipaddress
import json
import re
import struct
import sys


def validate(devices):
    if not isinstance(devices, list):
        raise ValueError('device roster must be a list')
    sources = set()
    for device in devices:
        address = str(ipaddress.IPv4Address(device['address']))
        if address != device['address'] or address in sources:
            raise ValueError('duplicate or noncanonical device source')
        sources.add(address)
        key = device['ssh_public_key']
        if not isinstance(key, str) or not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,2}(?: [^\r\n]+)?', key):
            raise ValueError('expected a single native Ed25519 public key')
        blob = base64.b64decode(key.split()[1], validate=True)
        prefix = struct.pack('!I', 11) + b'ssh-ed25519' + struct.pack('!I', 32)
        if len(blob) != len(prefix) + 32 or not blob.startswith(prefix):
            raise ValueError('invalid Ed25519 key encoding')


if __name__ == '__main__':
    try:
        validate(json.load(sys.stdin))
    except (KeyError, TypeError, ValueError):
        sys.exit('Hub authorization rejected; check exact device sources and public keys')
