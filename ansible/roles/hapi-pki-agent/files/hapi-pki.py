#!/usr/bin/python3
"""Renew existing HAPI TLS identities; never allocate a VM or export a leaf key."""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import ssl
import subprocess
import sys
import tempfile
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

UTC = dt.timezone.utc
POLICY = {'leaf_days': 365, 'ca_days': 1825, 'renew_days': 60, 'crl_days': 180, 'crl_refresh_days': 30}
# Paths, service identities and reload commands are not supplied by an HTTP caller.
SLOTS = {
    'gateway-client': ('control', '/etc/hapi-control-plane', 'client.pem', 'client.key', 'hapi-proxy', '/run/hapi-control-proxy'),
    'hub-server': ('control', '/etc/hapi-shared-hub', 'certificate.pem', 'private.key', 'hapi-hub', '/run/hapi-hub-transport'),
    'hub-client': ('worker', '/etc/hapi-hub-client', 'certificate.pem', 'private.key', 'hapi-hub-client', '/run/hapi-hub-client'),
    'login-server': ('worker', '/etc/hapi-ingress', 'certificate.pem', 'private.key', 'hapi-ingress', '/run/hapi-ingress'),
}


def need(value, code='pki-scope-or-state-mismatch'):
    if not value:
        raise ValueError(code)


def now():
    return dt.datetime.now(UTC)


def date(value, attribute):
    aware = getattr(value, attribute + '_utc', None)
    return aware if aware is not None else getattr(value, attribute).replace(tzinfo=UTC)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def pem(value):
    return value.public_bytes(serialization.Encoding.PEM).decode()


def spki(key):
    return hashlib.sha256(key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()


def private(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink(), 'private-material-permissions')
    info = path.stat();mode = info.st_mode & 0o777
    credentials = os.environ.get('CREDENTIALS_DIRECTORY')
    # systemd may expose service credentials as 0440 for the service user/root group.
    scoped_group_read = (credentials and path.parent.resolve() == Path(credentials).resolve() and
                         info.st_gid in {0, os.getegid()} and info.st_uid in {0, os.geteuid()})
    need(not mode & 0o037 and (not mode & 0o040 or scoped_group_read), 'private-material-permissions')
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate-json-key');result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique)


def atomic(path, data, mode=0o600):
    path = Path(path);need(not path.is_symlink())
    previous = path.stat() if path.exists() else None
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pki-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        if previous:
            os.chmod(name, previous.st_mode & 0o777)
            os.chown(name, previous.st_uid, previous.st_gid)
        else:
            os.chmod(name, mode)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save(path, value):
    atomic(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())


@contextlib.contextmanager
def lock(root):
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (root / 'lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def profile(value):
    need(set(value) == {'id', 'authority', 'cn', 'dns', 'ips', 'ca_spki'})
    need(value['id'] in SLOTS and value['authority'] in {'hub', 'login'})
    need(value['authority'] == ('hub' if value['id'].startswith('hub-') else 'login'))
    need(re.fullmatch(r'[A-Za-z0-9.-]{1,128}', value['cn']) and re.fullmatch(r'[a-f0-9]{64}', value['ca_spki']))
    need(isinstance(value['dns'], list) and len(value['dns']) <= 4 and len(set(value['dns'])) == len(value['dns']))
    need(all(re.fullmatch(r'[a-z0-9.-]{1,128}', item) for item in value['dns']))
    need(isinstance(value['ips'], list) and len(value['ips']) <= 4 and len(set(value['ips'])) == len(value['ips']))
    for address in value['ips']:
        ip = ipaddress.IPv4Address(address)
        need(any(ip in ipaddress.ip_network(n) for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']))
    if value['id'].endswith('client'):
        need(not value['dns'] and not value['ips'])
    else:
        need(value['cn'] in value['dns'])
    return value


def identity(value, p, csr=False):
    need(value.subject == x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, p['cn'])]))
    try:
        names = value.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        dns, ips = names.get_values_for_type(x509.DNSName), [str(ip) for ip in names.get_values_for_type(x509.IPAddress)]
        need(len(names) == len(dns) + len(ips))
    except x509.ExtensionNotFound:
        dns, ips = [], []
    need(sorted(dns) == sorted(p['dns']) and sorted(ips) == sorted(p['ips']))
    if not csr:
        need(not value.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        usage = ExtendedKeyUsageOID.CLIENT_AUTH if p['id'].endswith('client') else ExtendedKeyUsageOID.SERVER_AUTH
        need(list(value.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [usage])


def authority_check(certificate, crl, pin, at, check_dates=True):
    need(isinstance(certificate.public_key(), rsa.RSAPublicKey) and spki(certificate.public_key()) == pin)
    need(certificate.issuer == certificate.subject and certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    certificate.public_key().verify(certificate.signature, certificate.tbs_certificate_bytes, padding.PKCS1v15(), certificate.signature_hash_algorithm)
    need(crl.issuer == certificate.subject and crl.is_signature_valid(certificate.public_key()))
    if check_dates:
        need(date(certificate, 'not_valid_before') <= at < date(certificate, 'not_valid_after'))
        need(date(crl, 'last_update') <= at < date(crl, 'next_update'))


def issue(authority, key, csr_pem, p, at):
    certificate = x509.load_pem_x509_certificate(authority['certificate'].encode())
    csr = x509.load_pem_x509_csr(csr_pem.encode());need(csr.is_signature_valid)
    identity(csr, p, csr=True)
    need(spki(key.public_key()) == p['ca_spki'] == spki(certificate.public_key()))
    expiry = min(at + dt.timedelta(days=POLICY['leaf_days']), date(certificate, 'not_valid_after') - dt.timedelta(hours=1))
    need(expiry > at + dt.timedelta(days=POLICY['renew_days']))
    builder = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(certificate.subject)
        .public_key(csr.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(at - dt.timedelta(minutes=5)).not_valid_after(expiry)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(csr.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH if p['id'].endswith('client') else ExtendedKeyUsageOID.SERVER_AUTH]), critical=False))
    names = [x509.DNSName(name) for name in p['dns']] + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in p['ips']]
    if names:
        builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
    return pem(builder.sign(key, hashes.SHA256()))


def renew_authority(value, key, at, force=False):
    cert = x509.load_pem_x509_certificate(value['certificate'].encode())
    old = x509.load_pem_x509_crl(value['crl'].encode())
    need(spki(cert.public_key()) == spki(key.public_key()))
    need(old.issuer == cert.subject and old.is_signature_valid(cert.public_key()))
    result = dict(value)
    # Public-key pins do not change: key rollover is a separately approved operation.
    if force or date(cert, 'not_valid_after') <= at + dt.timedelta(days=POLICY['leaf_days'] + POLICY['renew_days']):
        builder = (x509.CertificateBuilder().subject_name(cert.subject).issuer_name(cert.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(at - dt.timedelta(minutes=5)).not_valid_after(at + dt.timedelta(days=POLICY['ca_days'])))
        for extension in cert.extensions:
            builder = builder.add_extension(extension.value, extension.critical)
        result['certificate'] = pem(builder.sign(key, hashes.SHA256()))
    if date(old, 'last_update') + dt.timedelta(days=POLICY['crl_refresh_days']) <= at or result['certificate'] != value['certificate']:
        try:
            number = old.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number
        except x509.ExtensionNotFound:
            number = 0
        builder = (x509.CertificateRevocationListBuilder().issuer_name(cert.subject)
            .last_update(at - dt.timedelta(minutes=1)).next_update(at + dt.timedelta(days=POLICY['crl_days']))
            .add_extension(x509.CRLNumber(number + 1), critical=False))
        for entry in old:
            builder = builder.add_revoked_certificate(entry)
        result['crl'] = pem(builder.sign(key, hashes.SHA256()))
    return result


class Agent:
    def __init__(self, config, root=Path('/'), runner=None):
        need(set(config) == {'version', 'role', 'profiles', 'probe'})
        need(config['version'] == 1 and config['role'] in {'control', 'worker'})
        self.config, self.root = config, Path(root)
        self.profiles = {p['id']: profile(p) for p in config['profiles']}
        need(len(self.profiles) == len(config['profiles']) == 2)
        need(set(self.profiles) == {ident for ident, row in SLOTS.items() if row[0] == config['role']})
        probe = config['probe'];need(set(probe) == {'address', 'name'})
        need(re.fullmatch(r'[a-z0-9.-]+', probe['name']))
        address = ipaddress.IPv4Address(probe['address'])
        need(any(address in ipaddress.ip_network(c) for c in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']))
        self.state = self.path('/var/lib/hapi-pki-agent')
        self.runner = runner or (lambda args: subprocess.run(args, check=True, capture_output=True, timeout=30))

    def path(self, value):
        return self.root / value.removeprefix('/')

    def files(self, ident):
        row = SLOTS[ident];folder = self.path(row[1])
        return {name: folder / filename for name, filename in [('certificate', row[2]), ('key', row[3]), ('ca', 'ca.pem'), ('crl', 'crl.pem')]}

    def inspect(self):
        result = {}
        for ident, p in self.profiles.items():
            files = self.files(ident)
            need(all(path.is_file() and not path.is_symlink() for path in files.values()))
            certificate = x509.load_pem_x509_certificate(files['certificate'].read_bytes())
            key = serialization.load_pem_private_key(files['key'].read_bytes(), password=None)
            identity(certificate, p);need(spki(key.public_key()) == spki(certificate.public_key()))
            result[ident] = {name: files[name].read_text() for name in ['certificate', 'ca', 'crl']}
            csr = x509.CertificateSigningRequestBuilder().subject_name(certificate.subject)
            try:
                csr = csr.add_extension(certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value, critical=False)
            except x509.ExtensionNotFound:
                pass
            result[ident]['csr'] = pem(csr.sign(key, hashes.SHA256()))
        return {'profiles': self.config['profiles'], 'materials': result}

    def reload(self):
        for ident in self.profiles:
            row = SLOTS[ident]
            pid_path = self.path(row[5] + '/nginx.pid')
            need(pid_path.is_file() and not pid_path.is_symlink(), 'managed-proxy-not-running')
            pid = pid_path.read_text().strip();need(pid.isdigit() and int(pid) > 1, 'invalid-managed-proxy-pid')
            os.kill(int(pid), 0)
            # Signal the existing master; do not create a PAM session or restart the service.
            argv = ['/usr/sbin/nginx', '-c', row[1] + '/nginx.conf', '-p', row[5] + '/']
            self.runner([*argv, '-t']);self.runner([*argv, '-s', 'reload'])

    def validate_material(self, ident, value, current, at):
        need(set(value) == {'certificate', 'ca', 'crl'})
        p = self.profiles[ident]
        ca = x509.load_pem_x509_certificate(value['ca'].encode());crl = x509.load_pem_x509_crl(value['crl'].encode())
        authority_check(ca, crl, p['ca_spki'], at)
        cert = x509.load_pem_x509_certificate(value['certificate'].encode());identity(cert, p)
        ca.public_key().verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), cert.signature_hash_algorithm)
        need(cert.issuer == ca.subject and spki(cert.public_key()) == spki(serialization.load_pem_private_key(self.files(ident)['key'].read_bytes(), password=None).public_key()))
        need(date(cert, 'not_valid_before') <= at < date(cert, 'not_valid_after') <= at + dt.timedelta(days=POLICY['leaf_days'], minutes=1))
        need(date(cert, 'not_valid_after') <= date(ca, 'not_valid_after'))
        old = x509.load_pem_x509_crl(current['crl'].encode())
        need({r.serial_number for r in old} <= {r.serial_number for r in crl})
        need(cert.serial_number not in {r.serial_number for r in crl})
        need(date(crl, 'last_update') >= date(old, 'last_update'))

    def operation(self, request):
        need(isinstance(request, dict) and request.get('action') in {'inspect', 'prepare', 'activate', 'rollback', 'probe'})
        with lock(self.state):
            action = request['action']
            if action == 'inspect':
                need(set(request) == {'action'});return self.inspect()
            if action == 'probe':
                need(set(request) == {'action', 'fingerprint'});return self.probe(request['fingerprint'])
            need(re.fullmatch(r'[a-f0-9]{32}', request.get('generation', '')))
            need(set(request) == ({'action', 'generation', 'materials'} if action == 'prepare' else {'action', 'generation'}))
            folder = self.state / request['generation'];folder.mkdir(mode=0o700, exist_ok=True)
            receipt = folder / 'transaction.json'
            if action == 'prepare':
                need(set(request['materials']) == set(self.profiles))
                current = self.inspect()['materials']
                for ident, value in request['materials'].items():
                    self.validate_material(ident, value, current[ident], now())
                candidate = {'before': {i: {k: v for k, v in row.items() if k != 'csr'} for i, row in current.items()},
                             'after': request['materials'], 'config': digest(self.config)}
                if receipt.exists():
                    need(read(receipt)['after'] == candidate['after'] and read(receipt)['config'] == candidate['config'])
                else:
                    save(receipt, candidate)
                return {'prepared': True}
            value = read(receipt);need(value['config'] == digest(self.config))
            active = self.state / 'managed.json'
            state = read(active) if active.exists() else {'generation': None, 'config': digest(self.config)}
            need(state['config'] == digest(self.config))
            current = self.inspect()['materials']
            for ident in self.profiles:
                for name in ['certificate', 'ca', 'crl']:
                    need(current[ident][name] in [value['before'][ident][name], value['after'][ident][name]], 'unmanaged-tls-drift')
            if action == 'activate':
                if state['generation'] != request['generation']:
                    need(all({k: v for k, v in current[i].items() if k != 'csr'} == value['before'][i] for i in self.profiles))
                destination = value['after']
                save(active, {'generation': request['generation'], 'config': digest(self.config), 'phase': 'activating'})
            else:
                need(state['generation'] == request['generation'], 'rollback-generation-mismatch')
                for ident in self.profiles:
                    live_crl = x509.load_pem_x509_crl(current[ident]['crl'].encode())
                    old_crl = x509.load_pem_x509_crl(value['before'][ident]['crl'].encode())
                    need({r.serial_number for r in live_crl} <= {r.serial_number for r in old_crl}, 'rollback-would-remove-revocation')
                destination = value['before']
            for ident, row in destination.items():
                for name, contents in row.items():
                    atomic(self.files(ident)[name], contents.encode())
            self.reload()
            save(active, {'generation': request['generation'], 'config': digest(self.config), 'phase': 'active' if action == 'activate' else 'rolled-back'})
            return {'activated': action == 'activate', 'rolled_back': action == 'rollback'}

    def probe(self, expected):
        need(re.fullmatch(r'[a-f0-9]{64}', expected))
        ident = 'gateway-client' if self.config['role'] == 'control' else 'hub-client'
        files = self.files(ident);p = self.config['probe']
        context = ssl.create_default_context(cafile=str(files['ca']));context.load_verify_locations(cafile=str(files['crl']))
        context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
        context.load_cert_chain(str(files['certificate']), str(files['key']))
        raw = socket.create_connection((p['address'], 9443), timeout=10)
        connection = http.client.HTTPConnection(p['name'], 9443, timeout=10)
        connection.sock = context.wrap_socket(raw, server_hostname=p['name'])
        path = '/api/login/status' if self.config['role'] == 'control' else '/health'
        try:
            need(hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest() == expected, 'wire-certificate-mismatch')
            connection.request('GET', path, headers={'Host': p['name']})
            response = connection.getresponse();need(response.status == 200, 'pki-peer-health-failed');response.read(8192)
        finally:
            connection.close()
        return {'peer_verified': True}


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=20);self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM);self.sock.settimeout(20);self.sock.connect(self.path)


class Transport:
    def __init__(self, config, authorities):
        self.config, self.authorities = config, authorities

    def call(self, target, request):
        if target['id'] == 'control':
            connection = UnixConnection('/run/hapi-pki-agent/agent.sock');path = '/op'
        else:
            authority = self.authorities['login']
            with tempfile.TemporaryDirectory(prefix='hapi-pki-trust-') as folder:
                trust = Path(folder) / 'trust.pem';trust.write_text(authority['certificate'] + authority['crl'])
                context = ssl.create_default_context(cafile=str(trust))
            context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF
            credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
            context.load_cert_chain(str(credentials / 'control-client.pem'), str(credentials / 'control-client.key'))
            connection = http.client.HTTPConnection(target['name'], 9443, timeout=20)
            raw = socket.create_connection((target['address'], 9443), timeout=20)
            connection.sock = context.wrap_socket(raw, server_hostname=target['name']);path = '/_hapi_pki/op'
        try:
            connection.request('POST', path, body=json.dumps(request).encode(), headers={'Content-Type': 'application/json', 'Host': 'localhost' if target['id'] == 'control' else target['name']})
            response = connection.getresponse();body = response.read(1048577)
            need(response.status == 200 and len(body) <= 1048576, 'agent-request-failed')
            result = json.loads(body);need(result.get('ok') is True, 'agent-operation-failed')
            return result['result']
        finally:
            connection.close()


def controller_config(value):
    need(set(value) == {'version', 'authorities', 'targets'})
    need(value['version'] == 1 and set(value['authorities']) == {'hub', 'login'})
    need(len(value['targets']) == 2 and {t['id'] for t in value['targets']} == {'control', 'worker'})
    for target in value['targets']:
        need(set(target) == ({'id', 'profiles'} if target['id'] == 'control' else {'id', 'profiles', 'address', 'name'}))
        need({p['id'] for p in target['profiles']} == {i for i, row in SLOTS.items() if row[0] == target['id']})
        need(len(target['profiles']) == 2)
        for p in target['profiles']:
            profile(p)
        if target['id'] == 'worker':
            address = ipaddress.IPv4Address(target['address'])
            need(any(address in ipaddress.ip_network(n) for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']))
            need(target['name'] == next(p['cn'] for p in target['profiles'] if p['id'] == 'login-server'))
    for ident, authority in value['authorities'].items():
        need(set(authority) == {'certificate', 'crl'})
        certificate = x509.load_pem_x509_certificate(authority['certificate'].encode())
        crl = x509.load_pem_x509_crl(authority['crl'].encode())
        authority_check(certificate, crl, spki(certificate.public_key()), now(), check_dates=False)
        need(all(p['ca_spki'] == spki(certificate.public_key()) for t in value['targets']
                 for p in t['profiles'] if p['authority'] == ident))
    return value


class Controller:
    def __init__(self, config, root, keys, transport_factory=Transport):
        self.config = controller_config(config);self.root = Path(root)
        self.keys, self.transport_factory = keys, transport_factory
        self.binding = digest(config)

    def run(self, at=None):
        try:
            return self._run(at)
        except Exception as error:
            if self.root.exists():
                save(self.root / 'health.json', {'ok': False, 'reason': 'pki-check-or-rollout-failed',
                                               'error_type': type(error).__name__, 'checked_at': now().isoformat()})
            raise

    def _run(self, at=None):
        at = at or now()
        with lock(self.root):
            public = self.root / 'authorities.json';transaction = self.root / 'transaction.json'
            authorities = read(public) if public.exists() else self.config['authorities']
            for ident, value in authorities.items():
                active_ca = x509.load_pem_x509_certificate(value['certificate'].encode())
                need(spki(self.keys[ident].public_key()) == spki(active_ca.public_key()))
                authority_check(active_ca, x509.load_pem_x509_crl(value['crl'].encode()), spki(self.keys[ident].public_key()), at)
            transport = self.transport_factory(self.config, authorities)
            pending = read(transaction) if transaction.exists() else None
            if pending and pending['status'] != 'verified':
                need(pending['binding'] == self.binding, 'pending-pki-config-changed')
                if pending['status'] == 'reconciliation-required':
                    # Retry only this generation's guarded rollback. Agents reject unknown file changes.
                    for target in reversed(self.config['targets']):
                        if target['id'] in pending['activation_intents']:
                            transport.call(target, {'action': 'rollback', 'generation': pending['id']})
                    pending['status'] = 'retryable';save(transaction, pending)
                plan = pending
            else:
                proposals = {i: renew_authority(value, self.keys[i], at, force=not public.exists()) for i, value in authorities.items()}
                materials, changed = {}, False
                for target in self.config['targets']:
                    observed = transport.call(target, {'action': 'inspect'})
                    need(observed['profiles'] == target['profiles'], 'agent-profile-changed')
                    result = {}
                    for p in target['profiles']:
                        row = observed['materials'][p['id']];ca = proposals[p['authority']]
                        certificate = x509.load_pem_x509_certificate(row['certificate'].encode());identity(certificate, p)
                        issuer = x509.load_pem_x509_certificate(ca['certificate'].encode())
                        need(certificate.issuer == issuer.subject, 'existing-leaf-issuer-mismatch')
                        issuer.public_key().verify(certificate.signature, certificate.tbs_certificate_bytes,
                                                   padding.PKCS1v15(), certificate.signature_hash_algorithm)
                        csr = x509.load_pem_x509_csr(row['csr'].encode())
                        need(spki(csr.public_key()) == spki(certificate.public_key()), 'csr-existing-key-mismatch')
                        crl = x509.load_pem_x509_crl(ca['crl'].encode())
                        deployed_crl = x509.load_pem_x509_crl(row['crl'].encode())
                        need({r.serial_number for r in crl} == {r.serial_number for r in deployed_crl},
                             'revocation-change-needs-separate-publication')
                        need(certificate.serial_number not in {r.serial_number for r in crl}, 'revoked-identity-needs-operator')
                        renew = not public.exists() or ca['certificate'] != row['ca'] or date(certificate, 'not_valid_after') <= at + dt.timedelta(days=POLICY['renew_days'])
                        leaf = issue(ca, self.keys[p['authority']], row['csr'], p, at) if renew else row['certificate']
                        result[p['id']] = {'certificate': leaf, 'ca': ca['certificate'], 'crl': ca['crl']}
                        changed |= any(result[p['id']][name] != row[name] for name in result[p['id']])
                    materials[target['id']] = result
                if not changed:
                    self.verify(transport, materials)
                    save(self.root / 'health.json', {'ok': True, 'changed': False, 'verified_at': at.isoformat()})
                    return {'ok': True, 'changed': False}
                plan = {'id': secrets.token_hex(16), 'binding': self.binding, 'authorities': proposals,
                        'materials': materials, 'status': 'preparing', 'activation_intents': []}
                save(transaction, plan)
            try:
                for target in self.config['targets']:
                    transport.call(target, {'action': 'prepare', 'generation': plan['id'], 'materials': plan['materials'][target['id']]})
                plan['status'] = 'activating';save(transaction, plan)
                for target in self.config['targets']:
                    if target['id'] not in plan['activation_intents']:
                        plan['activation_intents'].append(target['id']);save(transaction, plan)
                    transport.call(target, {'action': 'activate', 'generation': plan['id']})
                transport.authorities = plan['authorities']
                self.verify(transport, plan['materials'])
                save(public, plan['authorities'])
                plan['status'] = 'verified';save(transaction, plan)
                save(self.root / 'health.json', {'ok': True, 'changed': True, 'generation': plan['id'], 'verified_at': at.isoformat()})
                return {'ok': True, 'changed': True, 'generation': plan['id']}
            except Exception:
                rollback_ok = True
                for target in reversed(self.config['targets']):
                    if target['id'] in plan['activation_intents']:
                        try:
                            transport.call(target, {'action': 'rollback', 'generation': plan['id']})
                        except Exception:
                            rollback_ok = False
                plan['status'] = 'retryable' if rollback_ok else 'reconciliation-required';save(transaction, plan)
                save(self.root / 'health.json', {'ok': False, 'reason': plan['status'], 'generation': plan['id']})
                raise ValueError('pki-rollout-not-verified') from None

    def verify(self, transport, materials):
        for target in self.config['targets']:
            peer = materials['worker']['login-server'] if target['id'] == 'control' else materials['control']['hub-server']
            certificate = x509.load_pem_x509_certificate(peer['certificate'].encode())
            for attempt in range(3):
                try:
                    transport.call(target, {'action': 'probe', 'fingerprint': certificate.fingerprint(hashes.SHA256()).hex()})
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(.5)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        try:
            need(self.path == '/op' and self.headers.get('Content-Type') == 'application/json')
            need(self.headers.get('Transfer-Encoding') is None and len(self.headers.get_all('Content-Length', [])) == 1)
            length = int(self.headers.get('Content-Length', '0'));need(0 < length <= 1048576)
            result = self.server.agent.operation(json.loads(self.rfile.read(length)))
            body = json.dumps({'ok': True, 'result': result}).encode();status = 200
        except Exception:
            body = b'{"ok":false,"reason":"pki-operation-refused"}';status = 409
        self.send_response(status);self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)));self.send_header('Cache-Control', 'no-store')
        self.end_headers();self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    def get_request(self):
        connection, address = super().get_request();connection.settimeout(30)
        return connection, address


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['agent', 'controller', 'check-agent', 'check-controller'])
    parser.add_argument('--config', required=True)
    args = parser.parse_args();config = read(args.config)
    if args.mode.startswith('check-'):
        Agent(config) if args.mode == 'check-agent' else controller_config(config)
        print('{"ok":true}');return
    if args.mode == 'agent':
        agent = Agent(config)
        path = Path('/run/hapi-pki-agent/agent.sock')
        with lock(agent.state / 'server'):
            if path.exists():
                need(path.is_socket());path.unlink()
            with Server(str(path), Handler) as server:
                server.agent = agent;os.chmod(path, 0o660);server.serve_forever()
    else:
        credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
        keys = {ident: private(credentials / (ident + '.key')) for ident in ['hub', 'login']}
        result = Controller(config, '/var/lib/hapi-pki-controller', keys).run()
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        diagnostic = {'ok': False, 'reason': 'pki-operation-failed', 'error_type': type(error).__name__}
        if re.fullmatch(r'[a-z][a-z0-9-]{1,100}', str(error)):
            diagnostic['reason'] = str(error)
        if diagnostic['reason'] == 'private-material-permissions' and os.environ.get('CREDENTIALS_DIRECTORY'):
            directory = Path(os.environ['CREDENTIALS_DIRECTORY'])
            diagnostic['credential_modes'] = {name: oct((directory / (name + '.key')).stat().st_mode & 0o777)
                                               for name in ['hub', 'login']}
        print(json.dumps(diagnostic))
        raise SystemExit(1) from None
