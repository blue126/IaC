#!/usr/bin/env python3
"""Root-owned control-plane primitives; never import checkout code as root."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import urllib.request


class Refused(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise Refused('upstream redirects are forbidden')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def sha_file(path):
    with open(path, 'rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', value):
        raise Refused('invalid nonce or identifier')
    return value


def report_status(event):
    phases={'starting','isolation-verified','terraform-approval','ansible-approval',
            'apps-publish-approval','apps-google-approval','terraform-apply','ansible-deploy',
            'executing-approved-stage','notion-sync','prediction-finished','verified','failed'}
    if not isinstance(event,dict) or event.get('phase') not in phases:raise Refused('unrecognized job report phase')
    value=event.get('manifest_digest')
    if event['phase'].endswith('-approval') or value is not None:
        if not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None:raise Refused('invalid job report digest')
    return {key:event[key] for key in ['phase','manifest_digest','summary'] if key in event}


def private_file(path, owner=0):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022:
        raise Refused('control file has unsafe ownership, type or permissions')
    return path


def secret_file(path):
    path=private_file(path)
    if path.lstat().st_mode & 0o077:raise Refused('root secret must be owner-only')
    return path


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(canonical(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify(envelope, keys, purpose, now=None):
    """Verify Ed25519 detached signatures over the exact canonical payload."""
    now = int(time.time()) if now is None else now
    try:
        payload = envelope['payload']
        key = private_file(keys[envelope['key_id']])
        signature = base64.b64decode(envelope['signature'], validate=True)
        if payload['purpose'] != purpose:
            raise Refused('signature purpose mismatch')
        if not (payload['issued_at'] <= now < payload['expires_at']):
            raise Refused('expired or future authorization')
        if payload['expires_at'] - payload['issued_at'] > 1800:
            raise Refused('authorization lifetime exceeds policy')
        token(payload['nonce'])
    except (KeyError, TypeError, ValueError) as error:
        raise Refused('invalid signed authorization') from error
    with tempfile.TemporaryDirectory(prefix='jenkins-verify-') as directory:
        data, sig = Path(directory)/'data', Path(directory)/'sig'
        data.write_bytes(canonical(payload))
        sig.write_bytes(signature)
        result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey',
                                 str(key), '-rawin', '-in', str(data), '-sigfile', str(sig)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise Refused('invalid signature')
    return payload


def sign(payload, key_id, private_key):
    private_key=secret_file(private_key)
    with tempfile.TemporaryDirectory(prefix='jenkins-sign-') as directory:
        source, target = Path(directory)/'data', Path(directory)/'signature'
        source.write_bytes(canonical(payload))
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-inkey', str(private_key), '-rawin',
                        '-in', str(source), '-out', str(target)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        signature = base64.b64encode(target.read_bytes()).decode('ascii')
    return {'key_id': key_id, 'payload': payload, 'signature': signature}


def command(argv, **kwargs):
    return subprocess.run(argv, check=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=30, **kwargs).stdout.strip()


def read_job_bytes(path, owner, limit=65536):
    """Read a job-owned regular file without following links or waiting on FIFOs."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise Refused('unsafe job report') from error
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_size > limit:
            raise Refused('job report type, owner or size refused')
        data = os.read(fd, limit + 1)
        if len(data) > limit:
            raise Refused('job report exceeds size limit')
        return data
    finally:
        os.close(fd)


def read_job_report(path, owner, limit=65536):
    data=read_job_bytes(path,owner,limit)
    if data is None:return None
    try:event=json.loads(data)
    except (json.JSONDecodeError,UnicodeDecodeError):return None
    return report_status(event)
