#!/usr/bin/env python3
"""Offline documentation exercise, not a runtime trust API or real-device UAT.

Reuse Story8's TemporaryDirectory/OpenSSL certificate pattern and synthetic
198.18.53.0/24 targets. Never read inventory, credentials or user profiles.
"""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from urllib.parse import urlsplit


TARGET = '198.18.53.10'
OTHER_TARGET = '198.18.53.11'
TARGET_URL = f'https://{TARGET}:8443/'


def openssl(*args):
    return subprocess.run(['openssl', *map(str, args)], capture_output=True,
                          check=True, timeout=30)


def ca_fingerprint(ca):
    der = openssl('x509', '-in', ca, '-outform', 'DER').stdout
    return hashlib.sha256(der).hexdigest()


def explain_trust(*, ca, reference, source, leaf, assigned_ip, url):
    """Illustrate the guide's checks with synthetic inputs only."""
    if ca is None or not ca.is_file():
        return 'missing-ca'
    if not source:
        return 'missing-independent-source'
    if not reference:
        return 'missing-reference-fingerprint'
    normalized = re.sub(r'[\s:]', '', reference).lower()
    if normalized != ca_fingerprint(ca):
        return 'ca-fingerprint-mismatch'
    parsed = urlsplit(url)
    if parsed.hostname == '10.230.0.1':
        return 'retired-shared-url'
    if parsed.scheme != 'https':
        return 'https-required'
    if url != f'https://{assigned_ip}:8443/':
        return 'assigned-target-url-mismatch'
    try:
        openssl('verify', '-CAfile', ca, '-purpose', 'sslserver', leaf)
    except subprocess.CalledProcessError:
        return 'certificate-chain-rejected'
    # Decode actual signed certificate extensions, never a claimed fixture SAN.
    decoded = openssl('x509', '-in', leaf, '-noout', '-text').stdout.decode()
    san = re.search(r'X509v3 Subject Alternative Name:[^\n]*\n([^\n]*)', decoded)
    ips = re.findall(r'IP Address:([0-9.]+)', san.group(1)) if san else []
    if assigned_ip not in ips:
        return 'target-ip-san-mismatch'
    return 'accepted-synthetic-only'


class DesktopTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='oci-desktop-trust-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        # All keys, CSRs and certificates are generated inside this private temp.
        cls.ca = cls.make_ca('trusted-synthetic-ca')
        cls.other_ca = cls.make_ca('other-synthetic-ca')
        cls.leaf = cls.make_leaf('target', TARGET)
        cls.wrong_san = cls.make_leaf('wrong-san', OTHER_TARGET)
        cls.reference = ca_fingerprint(cls.ca)

    @classmethod
    def make_ca(cls, name):
        config = cls.base / f'{name}.cnf'
        config.write_text('[req]\nprompt=no\ndistinguished_name=dn\n'
                          'x509_extensions=ca\n[dn]\nCN=' + name + '\n[ca]\n'
                          'basicConstraints=critical,CA:TRUE\n'
                          'keyUsage=critical,keyCertSign,cRLSign\n'
                          'subjectKeyIdentifier=hash\n')
        cert = cls.base / f'{name}.pem'
        openssl('req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-days', '1', '-config', config,
                '-keyout', cls.base / f'{name}.key', '-out', cert)
        return cert

    @classmethod
    def make_leaf(cls, name, ip):
        key = cls.base / f'{name}.key'
        csr = cls.base / f'{name}.csr'
        cert = cls.base / f'{name}.pem'
        extensions = cls.base / f'{name}.ext'
        # Correct CN on the wrong-SAN leaf proves that CN cannot replace IP SAN.
        openssl('req', '-new', '-newkey', 'rsa:2048', '-nodes',
                '-subj', f'/CN={TARGET}', '-keyout', key, '-out', csr)
        extensions.write_text('basicConstraints=critical,CA:FALSE\n'
                              'keyUsage=critical,digitalSignature,keyEncipherment\n'
                              'extendedKeyUsage=serverAuth\n'
                              f'subjectAltName=IP:{ip}\n')
        openssl('x509', '-req', '-in', csr, '-CA', cls.ca,
                '-CAkey', cls.base / 'trusted-synthetic-ca.key',
                '-set_serial', '1' if ip == TARGET else '2', '-days', '1',
                '-extfile', extensions, '-out', cert)
        return cert

    def check_reason(self, expected, **changes):
        device = {'device_id': 'synthetic-device-001',
                  'os_browser': 'synthetic-os/synthetic-browser',
                  'owner': 'synthetic-owner', 'assigned_ip': TARGET}
        inputs = dict(ca=self.ca, reference=self.reference,
                      source='synthetic-independent-reference', leaf=self.leaf,
                      assigned_ip=device['assigned_ip'], url=TARGET_URL)
        inputs.update(changes)
        self.assertEqual(explain_trust(**inputs), expected)

    def test_correct_der_fingerprint_chain_ip_san_and_url(self):
        self.check_reason('accepted-synthetic-only')
        # Cross-check Python's DER digest with OpenSSL's X.509 fingerprint.
        output = openssl('x509', '-in', self.ca, '-noout', '-fingerprint', '-sha256')
        formatted = output.stdout.decode().strip().split('=', 1)[1]
        self.assertEqual(formatted.replace(':', '').lower(), self.reference)
        self.check_reason('accepted-synthetic-only', reference=formatted.lower())

    def test_wrong_ca_rejects_chain_even_with_matching_ca_reference(self):
        self.check_reason('certificate-chain-rejected', ca=self.other_ca,
                          reference=ca_fingerprint(self.other_ca))

    def test_wrong_independent_fingerprint(self):
        self.check_reason('ca-fingerprint-mismatch', reference='00' * 32)

    def test_wrong_ip_san_even_with_correct_cn_and_valid_chain(self):
        openssl('verify', '-CAfile', self.ca, '-purpose', 'sslserver', self.wrong_san)
        self.check_reason('target-ip-san-mismatch', leaf=self.wrong_san)

    def test_another_target_url(self):
        self.check_reason('assigned-target-url-mismatch',
                          url=f'https://{OTHER_TARGET}:8443/')

    def test_missing_public_ca(self):
        for ca in (None, self.base / 'missing.pem'):
            with self.subTest(ca_present=ca is not None):
                self.check_reason('missing-ca', ca=ca)

    def test_missing_independent_source(self):
        self.check_reason('missing-independent-source', source='')

    def test_missing_reference_fingerprint(self):
        self.check_reason('missing-reference-fingerprint', reference='')

    def test_http_downgrade(self):
        self.check_reason('https-required', url=f'http://{TARGET}:8443/')

    def test_retired_shared_urls(self):
        for url in ('https://10.230.0.1:8443/',
                    'http://10.230.0.1:8443/vnc.html#autoconnect=1'):
            with self.subTest(url=url):
                self.check_reason('retired-shared-url', url=url)

    def test_old_path_loopback_and_backend_port_are_not_fallbacks(self):
        for url in (TARGET_URL + 'vnc.html', 'https://127.0.0.1:8444/',
                    f'https://{TARGET}:8444/'):
            with self.subTest(url=url):
                self.check_reason('assigned-target-url-mismatch', url=url)


if __name__ == '__main__':
    unittest.main()
