#!/usr/bin/env python3
"""Real synthetic certificate generation and immutable material reuse."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('materials', ROOT / 'ansible/roles/kasmvnc/files/prepare-materials.py')
materials = importlib.util.module_from_spec(spec);spec.loader.exec_module(materials)


class Materials(unittest.TestCase):
    def setUp(self):
        self.mask = os.umask(0o077)
        self.addCleanup(os.umask, self.mask)
        folder = tempfile.TemporaryDirectory(prefix='desktop-update-synthetic-')
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        self.frontend = self.base / 'frontend'; self.frontend.mkdir()
        self.output = self.base / 'update-vars.json'
        self.root = self.base / 'materials'
        subprocess.run(['openssl', 'req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=198.18.53.10', '-addext', 'subjectAltName=IP:198.18.53.10',
                        '-keyout', str(self.frontend / 'desktop.key'), '-out', str(self.frontend / 'desktop.crt')],
                       check=True, capture_output=True)
        self.pin = materials.fingerprint(self.frontend / 'desktop.crt')
        # Relocate OS ownership only; retain actual crypto, files and modes.
        actual_stat = Path.stat
        def root_stat(path, *args, **kwargs):
            info = actual_stat(path, *args, **kwargs)
            return types.SimpleNamespace(st_uid=0, st_mode=info.st_mode & ~0o022)
        for context in (patch.object(materials, 'ROOT', self.root), patch.object(materials, 'FRONTEND', self.frontend),
                        patch.object(materials, 'OUTPUT', self.output), patch.object(Path, 'stat', root_stat),
                        patch.object(materials.os, 'chown'),
                        patch.object(materials.grp, 'getgrnam', return_value=types.SimpleNamespace(gr_gid=os.getgid()))):
            context.start(); self.addCleanup(context.stop)

    def test_generation_is_independent_and_reused_without_rotation(self):
        import json
        materials.prepare(508, '198.18.53.10', 'g-synthetic', self.pin)
        generation = self.root / 'generations/g-synthetic/508'
        before = {p.name:p.read_bytes() for p in generation.iterdir()}
        for directory in (self.root, self.root / 'generations', generation.parent, generation):
            self.assertEqual(os.stat(directory).st_mode & 0o777, 0o755)
        subprocess.run(['openssl', 'verify', '-CAfile', str(generation / 'ca.pem'), '-verify_hostname', 'localhost',
                        str(generation / 'server.pem')], check=True, capture_output=True)
        materials.prepare(508, '198.18.53.10', 'g-synthetic', self.pin)
        self.assertEqual(before, {p.name:p.read_bytes() for p in generation.iterdir()})
        variables = json.loads(self.output.read_text())
        self.assertEqual(variables['employee_desktop_config']['generation']['vmid'], 508)
        self.assertEqual(variables['employee_desktop_frontend']['pinned_sha256'], self.pin)
        self.assertEqual(os.stat(generation / 'server.key').st_mode & 0o777, 0o640)
        self.assertEqual(os.stat(self.output).st_mode & 0o777, 0o600)

    def test_wrong_frontend_pin_cannot_create_materials(self):
        with self.assertRaisesRegex(ValueError, 'fingerprint changed'):
            materials.prepare(508, '198.18.53.10', 'g-synthetic', '0'*64)
        self.assertFalse(self.root.exists())

    def test_symlink_generation_cannot_be_reused(self):
        parent = self.root / 'generations/g-synthetic'
        parent.mkdir(parents=True)
        (parent / '508').symlink_to(self.frontend, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink generation'):
            materials.prepare(508, '198.18.53.10', 'g-synthetic', self.pin)


if __name__ == '__main__': unittest.main()
