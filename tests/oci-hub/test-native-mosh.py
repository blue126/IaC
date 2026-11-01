#!/usr/bin/env python3
"""Exercise the rendered native launcher without starting a real Mosh session."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

import jinja2

ROOT = Path(__file__).resolve().parents[2]


def main():
    template = ROOT / 'ansible/roles/oci-hub-mosh/templates/workspace-mosh.j2'
    rendered = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(template.read_text()).render(
        oci_hub_mosh_network_timeout=604800, oci_hub_spoke_address='10.234.0.2/32')
    with tempfile.TemporaryDirectory(prefix='oci-native-mosh-') as directory:
        base = Path(directory)
        stub = base / 'mosh-server'
        stub.write_text('#!/usr/bin/env python3\nimport json,os,sys\nprint(json.dumps({"args":sys.argv[1:],"timeout":os.environ["MOSH_SERVER_NETWORK_TMOUT"]}))\n')
        stub.chmod(0o755)
        launcher = base / 'workspace-mosh'
        launcher.write_text(rendered.replace('/usr/bin/mosh-server', str(stub)))
        launcher.chmod(0o755)
        def invoke(args):
            return subprocess.run([str(launcher), *args], capture_output=True, text=True, env=dict(os.environ))
        assert json.loads(invoke(['--version']).stdout)['args'] == ['--version']
        args = ['new', '-s', '-c', '256', '-l', 'LANG=C.UTF-8', '-p', '60030:60039']
        result = json.loads(invoke(args).stdout)
        assert result == {'args': ['new', '-i', '10.234.0.2', *args[1:]], 'timeout': '604800'}
        assert invoke([]).returncode == 2
        assert invoke(['unsupported']).returncode == 2
        print('PASS: rendered native Mosh binding, network timeout, client startup arguments and version probe; no session key generated')


if __name__ == '__main__':
    main()
