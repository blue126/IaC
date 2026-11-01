#!/usr/bin/env python3
"""Check real public certificate/CRL expiry without live credentials or network."""
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'ansible/roles/hapi-health/files/hapi-health.py'
spec = importlib.util.spec_from_file_location('health', SOURCE)
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)
UTC = datetime.timezone.utc


class HealthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'synthetic-health-fixture')])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hapi-health-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime.datetime.now(UTC).replace(microsecond=0)
        self.config = {'version': 1, 'minimum_valid_days': 14, 'network': False, 'tls': []}

    def material(self, kind, expires, begins=-1):
        path = self.root / (kind + '.pem')
        start = self.now + datetime.timedelta(days=begins)
        end = self.now + datetime.timedelta(days=expires)
        if kind == 'certificate':
            value = (x509.CertificateBuilder().subject_name(self.name).issuer_name(self.name)
                     .public_key(self.key.public_key()).serial_number(1)
                     .not_valid_before(start).not_valid_after(end).sign(self.key, hashes.SHA256()))
        else:
            value = (x509.CertificateRevocationListBuilder().issuer_name(self.name)
                     .last_update(start).next_update(end).sign(self.key, hashes.SHA256()))
        path.write_bytes(value.public_bytes(serialization.Encoding.PEM))
        self.config['tls'].append({'label': kind, 'kind': kind, 'path': str(path)})
        return path

    def test_real_openssl_accepts_fresh_certificate_and_crl(self):
        self.material('certificate', 40)
        self.material('crl', 30)
        result = health.check(self.config, self.now)
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['checks']), 2)

    def test_near_expired_and_not_yet_valid_material_fail_without_hiding_other_checks(self):
        self.material('certificate', 40)
        self.material('crl', 3)
        result = health.check(self.config, self.now)
        self.assertFalse(result['ok'])
        self.assertTrue(result['checks'][0]['ok'])
        self.assertEqual(result['checks'][1]['reason'], 'expires-soon')
        self.config['tls'] = []
        self.material('crl', -1, begins=-2)
        self.assertEqual(health.check(self.config, self.now)['checks'][0]['reason'], 'outside-validity-period')
        self.config['tls'] = []
        self.material('certificate', 40, begins=1)
        self.assertFalse(health.check(self.config, self.now)['ok'])

    def test_malformed_public_material_returns_only_safe_diagnostics(self):
        path = self.material('certificate', 40)
        path.write_text('private-error-sentinel-not-for-journal')
        result = health.check(self.config, self.now)
        self.assertFalse(result['ok'])
        self.assertNotIn('private-error-sentinel', json.dumps(result))

    def test_network_drift_and_timeout_are_reported_without_running_writes(self):
        self.config['network'] = True
        expected = ['/usr/bin/python3', '/usr/local/lib/hapi-network.py', 'verify']
        for status in (0, 1):
            with patch.object(health, 'execute', return_value=subprocess.CompletedProcess(expected, status)) as run:
                self.assertEqual(health.check(self.config)['ok'], status == 0)
                run.assert_called_once_with(expected)
        with patch.object(health, 'execute', side_effect=subprocess.TimeoutExpired(expected, 20)):
            self.assertFalse(health.check(self.config)['ok'])

    def test_invalid_or_duplicate_scope_is_refused(self):
        self.material('certificate', 40)
        for change in ({'minimum_valid_days': 0}, {'network': 'true'}, {'extra': True},
                       {'tls': self.config['tls'] * 2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                health.validate(self.config | change)
        path = self.root / 'config.json'
        path.write_text('{"version":1,"version":1}')
        with self.assertRaises(ValueError):
            health.load(path)

    def test_validation_checks_schema_before_material_is_available(self):
        path = self.material('certificate', 40)
        path.unlink()
        config = self.root / 'config.json'
        config.write_text(json.dumps(self.config))
        result = subprocess.run(['python3', str(SOURCE), '--validate', str(config)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        result = subprocess.run(['python3', str(SOURCE), str(config)], capture_output=True)
        self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
