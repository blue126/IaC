#!/usr/bin/env python3
"""Exercise the rendered native launcher without starting a real Mosh session."""
import json
import os
from pathlib import Path
import subprocess
import shutil
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
        check_sshd_dropin(base)


def check_sshd_dropin(base):
    """System mosh-server gets the timeout only through the employee SSH session."""
    template = ROOT / 'ansible/roles/oci-hub-mosh/templates/sshd-mosh.conf.j2'
    dropin = base / '10-mosh.conf'
    dropin.write_text(jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(
        template.read_text()).render(oci_hub_mosh_network_timeout=604800))
    lines = [line.strip() for line in dropin.read_text().splitlines() if line.strip() and not line.startswith('#')]
    assert lines == ['Match User employee', 'SetEnv MOSH_SERVER_NETWORK_TMOUT=604800', 'Match all'], lines
    sshd = shutil.which('sshd') or ('/usr/sbin/sshd' if Path('/usr/sbin/sshd').exists() else None)
    if not sshd or not shutil.which('ssh-keygen'):
        print('NOT RUN: sshd effective-configuration check needs sshd and ssh-keygen')
        return
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(base / 'host-key')], check=True)
    # A directive after the drop-in must stay global (the Match block is closed).
    (base / 'sshd_config').write_text(f'HostKey {base / "host-key"}\nInclude {dropin}\nPasswordAuthentication no\n')
    subprocess.run([sshd, '-t', '-f', str(base / 'sshd_config')], check=True)
    def effective(user):
        return subprocess.run([sshd, '-T', '-f', str(base / 'sshd_config'), '-C', f'user={user},host=localhost,addr=127.0.0.1'],
                              check=True, capture_output=True, text=True).stdout.splitlines()
    employee, other = effective('employee'), effective('other')
    assert 'setenv MOSH_SERVER_NETWORK_TMOUT=604800' in employee
    assert not any(line.startswith('setenv MOSH_SERVER_NETWORK_TMOUT') for line in other)
    assert 'passwordauthentication no' in employee and 'passwordauthentication no' in other
    print('PASS: sshd -t accepts the Mosh drop-in; only employee sessions carry MOSH_SERVER_NETWORK_TMOUT')


if __name__ == '__main__':
    main()
