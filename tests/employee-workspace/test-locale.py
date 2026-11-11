#!/usr/bin/env python3
"""Run the actual workspace locale tasks against temporary files, then check sshd accepts the drop-in."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / 'ansible/roles/employee-workspace'
DROPIN = '/etc/ssh/sshd_config.d/05-employee-locale.conf'


def main():
    with tempfile.TemporaryDirectory(prefix='workspace-locale-') as directory:
        base = Path(directory)
        locale_file, dropin = base / 'default-locale', base / '05-employee-locale.conf'
        stub = base / 'locale'

        def tasks():
            # Execute the repository task bodies, redirecting only their targets and probes.
            text = (ROLE / 'tasks/locale.yml').read_text()
            text = text.replace('/etc/default/locale', str(locale_file)).replace(DROPIN, str(dropin))
            text = text.replace('argv: [locale, -a]', f'argv: [{stub}, -a]').replace('/usr/sbin/sshd -t', '/usr/bin/true')
            body = yaml.safe_load(text)
            for task in body:
                task.get('ansible.builtin.copy', {}).pop('owner', None)
                task.get('ansible.builtin.copy', {}).pop('group', None)
            return body

        (base / 'inventory.yml').write_text(yaml.safe_dump({'all': {'hosts': {'vm': {'ansible_connection': 'local'}}}}))
        env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'tests/ci/fixtures/ansible.cfg'))

        def apply(locales, expect_success=True):
            stub.write_text('#!/bin/sh\nprintf "%s\\n" ' + ' '.join(f"'{name}'" for name in locales) + '\n')
            stub.chmod(0o755)
            play = [{'name': 'Exercise actual workspace locale', 'hosts': 'vm', 'gather_facts': False,
                     'tasks': tasks(),
                     'handlers': [{'name': 'Reload workspace SSH', 'ansible.builtin.command': '/usr/bin/true'}]}]
            (base / 'play.yml').write_text(yaml.safe_dump(play, sort_keys=False))
            p = subprocess.run(['ansible-playbook', '-i', str(base / 'inventory.yml'), str(base / 'play.yml')],
                               env=env, capture_output=True, text=True)
            if (p.returncode == 0) != expect_success:
                raise AssertionError(p.stdout + p.stderr)
            return p.stdout

        # An image that has only the built-in C.UTF-8 (no locale-gen) still qualifies.
        locale_file.write_text('LANG=POSIX\nLC_ALL=C\n')
        first = apply(['C', 'C.utf8', 'POSIX'])
        assert locale_file.read_text() == 'LANG=C.UTF-8\n', locale_file.read_text()
        assert 'RUNNING HANDLER [Reload workspace SSH]' in first
        lines = [line for line in dropin.read_text().splitlines() if line and not line.startswith('#')]
        assert lines == ['AcceptEnv LANG LC_*'], lines
        second = apply(['C', 'C.UTF-8', 'POSIX'])
        assert 'changed=0' in second and 'RUNNING HANDLER' not in second, second
        # Without C.UTF-8 the play stops before touching anything.
        locale_file.write_text('LANG=POSIX\n')
        apply(['C', 'POSIX'], expect_success=False)
        assert locale_file.read_text() == 'LANG=POSIX\n'
        print('PASS: locale tasks write LANG=C.UTF-8 and the AcceptEnv drop-in, rerun without changes, and refuse a host without C.UTF-8')
        check_sshd(base, dropin)


def check_sshd(base, dropin):
    """The drop-in restores AcceptEnv even when sshd_config lost it, and coexists with the Mosh drop-in."""
    sshd = shutil.which('sshd') or ('/usr/sbin/sshd' if Path('/usr/sbin/sshd').exists() else None)
    if not sshd or not shutil.which('ssh-keygen'):
        print('NOT RUN: sshd effective-configuration check needs sshd and ssh-keygen')
        return
    import jinja2
    dropins = base / 'sshd_config.d'
    dropins.mkdir()
    shutil.copy(dropin, dropins / '05-employee-locale.conf')
    mosh = (ROOT / 'ansible/roles/oci-hub-mosh/templates/sshd-mosh.conf.j2').read_text()
    (dropins / '10-mosh.conf').write_text(jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(mosh).render(
        oci_hub_mosh_network_timeout=604800))
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(base / 'host-key')], check=True)
    for accepted in ('', 'AcceptEnv LANG LC_* COLORTERM NO_COLOR\n'):
        config = base / 'sshd_config'
        config.write_text(f'Include {dropins}/*.conf\nHostKey {base / "host-key"}\n{accepted}')
        subprocess.run([sshd, '-t', '-f', str(config)], check=True)
        effective = subprocess.run([sshd, '-T', '-f', str(config), '-C', 'user=employee,host=localhost,addr=127.0.0.1'],
                                   check=True, capture_output=True, text=True).stdout.splitlines()
        assert 'acceptenv LANG' in effective and 'acceptenv LC_*' in effective, effective
        assert 'setenv MOSH_SERVER_NETWORK_TMOUT=604800' in effective and 'setenv LC_CTYPE=C.UTF-8' in effective
    print('PASS: sshd -t accepts the locale drop-in; employee sessions accept LANG and LC_* with or without the stock AcceptEnv')


if __name__ == '__main__':
    main()
