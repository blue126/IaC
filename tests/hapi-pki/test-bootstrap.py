#!/usr/bin/env python3
"""Verify source-bound and reversible installation of the private PKI endpoint."""
import hashlib
import os
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'ansible/roles/hapi-pki-agent/files/hapi-pki-configure-nginx.py')
bootstrap = importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hapi-pki-bootstrap-');self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.config = folder / 'nginx.conf';self.config.write_text('server {\n        server_name vm502.hapi.internal;\n}\n')
        self.original = self.config.read_bytes();self.sha = hashlib.sha256(self.original).hexdigest()
        self.snippet = folder / 'agent.conf';self.candidate = folder / 'candidate.conf';self.candidate.write_text('location = /_hapi_pki/op { }\n')
        self.addCleanup(patch.stopall)
        patch.object(bootstrap, 'PATH', self.config).start();patch.object(bootstrap, 'SNIPPET', self.snippet).start();patch.object(bootstrap, 'CANDIDATE', self.candidate).start()

    def test_first_install_and_repeat_both_validate_reload_and_preserve_the_base(self):
        with patch.object(bootstrap.subprocess, 'run') as run:
            self.assertTrue(bootstrap.configure('vm502.hapi.internal', self.sha))
            self.assertFalse(bootstrap.configure('vm502.hapi.internal', self.sha))
            self.assertEqual(run.call_count, 4)
        self.assertEqual(self.config.read_text().replace(bootstrap.LINE, ''), self.original.decode())
        self.assertEqual(self.snippet.read_bytes(), self.candidate.read_bytes())

    def test_validation_failure_restores_both_existing_files(self):
        self.snippet.write_text('old endpoint\n');old = self.snippet.read_bytes()
        with patch.object(bootstrap.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['synthetic-nginx'])):
            with self.assertRaises(subprocess.CalledProcessError):
                bootstrap.configure('vm502.hapi.internal', self.sha)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(self.snippet.read_bytes(), old)

    def test_systemd_group_read_is_limited_to_the_scoped_credential_directory(self):
        spec = importlib.util.spec_from_file_location('pki_permissions', ROOT / 'ansible/roles/hapi-pki-agent/files/hapi-pki.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        key = module.rsa.generate_private_key(public_exponent=65537, key_size=2048)
        path = self.config.parent / 'signer.key'
        path.write_bytes(key.private_bytes(module.serialization.Encoding.PEM, module.serialization.PrivateFormat.PKCS8, module.serialization.NoEncryption()))
        path.chmod(0o440)
        with patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': str(path.parent)}):
            self.assertEqual(module.spki(module.private(path).public_key()), module.spki(key.public_key()))
            path.chmod(0o444)
            with self.assertRaises(ValueError):module.private(path)
            path.chmod(0o460)
            with self.assertRaises(ValueError):module.private(path)
        path.chmod(0o440)
        with patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': str(path.parent / 'different')}):
            with self.assertRaises(ValueError):module.private(path)
        path.chmod(0o600)
        module.private(path)

    def test_unknown_configuration_change_or_symlink_is_not_overwritten(self):
        self.config.write_text(self.original.decode() + '# unrelated change\n')
        before = self.config.read_bytes()
        with self.assertRaises(ValueError):
            bootstrap.configure('vm502.hapi.internal', self.sha)
        self.assertEqual(self.config.read_bytes(), before);self.assertFalse(self.snippet.exists())
        self.config.write_bytes(self.original);self.snippet.symlink_to(self.candidate)
        with self.assertRaises(ValueError):
            bootstrap.configure('vm502.hapi.internal', self.sha)


if __name__ == '__main__':
    unittest.main()
