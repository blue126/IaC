#!/usr/bin/env python3
"""Validate rendered systemd units offline without starting any service."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('render', ROOT / 'tests/hapi-workspace/test-proxy.py')
render = importlib.util.module_from_spec(spec);spec.loader.exec_module(render)


class UnitTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ansible') and shutil.which('systemd-analyze'), 'requires existing Sandbox validation tools')
    def test_actual_systemd_parser_accepts_the_rendered_units(self):
        values = {'hapi_pki_agent_config': {'role': 'control', 'probe': {'address': '10.77.0.2'}},
                  'hapi_pki_controller_config': {'targets': [{'id': 'worker', 'address': '10.77.0.2'}]}}
        with tempfile.TemporaryDirectory(prefix='hapi-pki-units-') as folder:
            root = Path(folder)
            sources = [('hapi-pki-agent.service', 'hapi-pki-agent/templates/agent.service.j2'),
                       ('hapi-pki-controller.service', 'hapi-pki-controller/templates/controller.service.j2'),
                       ('hapi-pki-controller.timer', 'hapi-pki-controller/templates/controller.timer.j2')]
            for name, source in sources:
                (root / name).write_text(render.render(ROOT / 'ansible/roles' / source, values))
            env = os.environ | {'SYSTEMD_UNIT_PATH': str(root) + ':/usr/lib/systemd/system:/lib/systemd/system'}
            result = subprocess.run(['systemd-analyze', 'verify', *[str(root / name) for name, _ in sources]], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            controller = (root / 'hapi-pki-controller.service').read_text()
            self.assertIn('User=hapi-pki', controller)
            self.assertNotIn('BWS_ACCESS_TOKEN', controller)


if __name__ == '__main__':
    unittest.main()
