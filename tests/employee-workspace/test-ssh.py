#!/usr/bin/env python3
"""Real OpenSSH/SFTP tests in a disconnected netns using temporary accounts/keys."""
import importlib.util
import copy
import json
import os
from pathlib import Path
import pwd
import select
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import yaml

HERE = Path(__file__).resolve().parent
ROLE = HERE.parents[1] / 'ansible/roles/employee-access'
spec = importlib.util.spec_from_file_location('offline', HERE / 'test-offline.py')
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)


def run(*args, check=True, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, check=check, **kwargs)


def main():
    if os.geteuid() != 0 or sys.argv[1:] not in [['--run-isolated-ssh'], ['--inside']]:
        raise SystemExit('Use root in the authorized Sandbox with --run-isolated-ssh')
    if sys.argv[1:] == ['--run-isolated-ssh']:
        return subprocess.call(['unshare', '--net', '--fork', sys.executable, str(Path(__file__).resolve()), '--inside'])
    Path('/run/sshd').mkdir(mode=0o755, exist_ok=True)
    run('ip', 'link', 'set', 'lo', 'up')
    suffix = uuid.uuid4().hex[:8]
    group = 'ed-test-' + suffix
    accounts = ['ed-a-' + suffix, 'ed-b-' + suffix, 'ed-c-' + suffix]
    try:
        pwd.getpwnam('employee')
        raise SystemExit('The isolated test requires an unused employee account')
    except KeyError:
        pass
    created, processes, logs, results = [], [], [], []
    with tempfile.TemporaryDirectory(prefix='employee-ssh-', dir='/run') as temp:
        base = Path(temp)
        base.chmod(0o755)
        access = base / 'access'
        for directory in [access, access / 'devices', access / 'keys', access / 'authorized-keys', base / 'empty']:
            directory.mkdir(mode=0o755)
        # Only the deployment path differs; dispatcher logic is unchanged.
        dispatcher = base / 'dispatcher.py'
        dispatcher.write_text((ROLE / 'files/employee-dispatch.py').read_text().replace("ROOT = Path('/etc/employee-access')", 'ROOT = Path(' + repr(str(access)) + ')'))
        dispatcher.chmod(0o755)

        def key(name):
            path = base / name
            run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(path))
            return path

        def daemon(name, config):
            path = base / (name + '.conf')
            path.write_text(config)
            validation = run('/usr/sbin/sshd', '-t', '-f', str(path), check=False)
            if validation.returncode:
                raise RuntimeError(validation.stderr)
            log = open(base / (name + '.log'), 'w+')
            logs.append(log)
            process = subprocess.Popen(['/usr/sbin/sshd', '-D', '-e', '-f', str(path)], stdout=log, stderr=log)
            processes.append(process)

        def wait_port(port):
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        return
                except OSError:
                    time.sleep(0.03)
            raise AssertionError('Test listener did not start')

        def check(label, ok):
            results.append({'case': label, 'passed': bool(ok)})
            print(json.dumps(results[-1]), flush=True)
            if not ok:
                for log in logs:
                    log.flush()
                    log.seek(0)
                    print(log.read()[-5000:], file=sys.stderr)
                raise AssertionError(label)

        try:
            run('groupadd', group)
            home = base / 'employee-home'
            home.mkdir()
            run('useradd', '-U', '-M', '-d', str(home), '-s', '/bin/bash', '-p', '*', 'employee')
            created.append('employee')
            os.chown(home, pwd.getpwnam('employee').pw_uid, pwd.getpwnam('employee').pw_gid)
            data_dir = home / 'data'
            data_dir.mkdir()
            os.chown(data_dir, pwd.getpwnam('employee').pw_uid, pwd.getpwnam('employee').pw_gid)
            run('ip', 'route', 'add', 'local', '127.0.0.3/32', 'dev', 'lo', 'src', '127.0.0.3', 'table', 'local')

            host, changed_host, unknown = key('host'), key('changed-host'), key('unknown')
            inner_authorized = base / 'inner-authorized'
            inner_authorized.write_text('')
            private_keys = {}
            credentials = []
            for account in accounts:
                run('useradd', '-M', '-d', str(base / 'empty'), '-s', '/bin/sh', '-g', group, '-p', '*', account)
                created.append(account)
                private_keys[account] = key(account)
                credential = key('inner-' + account)
                credentials.append({'name': account, 'employee': 'bob' if account == accounts[2] else 'alice', 'path': str(credential), 'enabled': True})
            # Execute the real workspace authorization task across separate plays.
            bob_credential, skipped_credential = Path(credentials[2]['path']), key('inner-skipped')
            credentials += [
                {'name': 'skipped', 'employee': 'alice', 'path': str(skipped_credential), 'enabled': False},
            ]
            authorization = yaml.safe_load((ROLE.parent / 'employee-workspace/tasks/authorization.yml').read_text())
            authorization[0]['ansible.builtin.copy']['dest'] = str(inner_authorized)
            bob_authorized = base / 'bob-authorized'
            bob_authorization = copy.deepcopy(authorization)
            bob_authorization[0]['ansible.builtin.copy']['dest'] = str(bob_authorized)
            env = dict(os.environ, ANSIBLE_CONFIG=str(HERE.parents[1] / 'tests/ci/fixtures/ansible.cfg'))
            inventory = base / 'inventory.yml'
            inventory.write_text(yaml.safe_dump({'all': {'hosts': {
                'gateway': {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
                    'employee_access_networks_json': json.dumps({'alice': {'gateway': '127.0.0.1'}, 'bob': {'gateway': '127.0.0.3'}})},
                'workspace': {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable},
            }}}))
            for name in ('device.yml', 'revoke.yml'):
                (base / name).write_text((ROLE / ('tasks/' + name)).read_text().replace('/etc/employee-access', str(access)))
            roster = {c['name']: {'employee': c['employee'], 'enabled': True, 'ssh_public_key': private_keys[c['name']].with_suffix('.pub').read_text().strip()} for c in credentials if c['name'] in accounts}
            system_keys = {c['name']: Path(c['path']).read_text() for c in credentials if c['name'] in accounts}
            def publish_devices():
                device_play = base / 'publish.yml'
                device_play.write_text(yaml.safe_dump([{'hosts': 'gateway', 'gather_facts': False,
                    'vars': {'employee_access_networks': {'alice': {'ip': '127.0.0.2', 'disabled': False}, 'bob': {'ip': '127.0.0.3', 'disabled': False}}, 'employee_access_private_keys': system_keys},
                    'tasks': [{'name': 'Execute actual device deployment', 'ansible.builtin.include_tasks': str(base / 'device.yml'), 'loop': [{'key': k, 'value': v} for k, v in roster.items()], 'loop_control': {'loop_var': 'employee_device'}}]}]))
                result = run('/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(device_play), env=env, check=False, input='')
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)
            publish_devices()
            check('actual-device-task-publishes-fixed-targets', json.loads((access / 'devices' / (accounts[0] + '.json')).read_text())['host'] == '127.0.0.2' and json.loads((access / 'devices' / (accounts[2] + '.json')).read_text())['host'] == '127.0.0.3')
            plays = [
                {'name': 'Derive actual enabled public keys on the gateway', 'hosts': 'gateway', 'gather_facts': False,
                 'tasks': [{'name': 'Derive device public credentials', 'ansible.builtin.command': {'argv': ['ssh-keygen', '-y', '-f', '{{ item.value.path }}']},
                            'loop': [{'key': c['name'], 'value': c} for c in credentials], 'when': 'item.value.enabled', 'register': 'employee_access_derived_keys', 'changed_when': False}]},
                {'name': 'Render real workspace authorization from another play', 'hosts': 'workspace', 'gather_facts': False,
                 'vars': {'employee_workspace_gateway': 'gateway', 'employee_workspace_id': 'alice', 'employee_workspace_user': 'employee'}, 'tasks': authorization},
            ]
            plays.append({'name': 'Render Bob authorization from gateway results', 'hosts': 'workspace', 'gather_facts': False,
                          'vars': {'employee_workspace_gateway': 'gateway', 'employee_workspace_id': 'bob', 'employee_workspace_user': 'employee'}, 'tasks': bob_authorization})
            playbook = base / 'authorization.yml'
            playbook.write_text(yaml.safe_dump(plays))
            result = run('/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(playbook), env=env, check=False, input='')
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            check('actual-ansible-cross-play-authorization', inner_authorized.read_text().count('from="127.0.0.1"') == 2 and bob_credential.with_suffix('.pub').read_text().split()[1] not in inner_authorized.read_text() and skipped_credential.with_suffix('.pub').read_text().split()[1] not in inner_authorized.read_text())
            known = access / 'known-hosts'
            known.write_text('employee-alice ' + host.with_suffix('.pub').read_text() + 'employee-bob ' + host.with_suffix('.pub').read_text())
            outer_known = base / 'outer-known'
            outer_known.write_text('[127.0.0.1]:2222 ' + host.with_suffix('.pub').read_text())
            outer = offline.render('sshd-config.j2').replace('Port 22\n', 'Port 2222\n').replace('ListenAddress 10.230.0.1', 'ListenAddress 127.0.0.1').replace('/run/employee-sshd.pid', str(base / 'outer.pid')).replace('/etc/ssh/ssh_host_ed25519_key', str(host)).replace('/etc/employee-access/authorized-keys/%u', str(access / 'authorized-keys/%u')).replace('AllowGroups employee-devices', 'AllowGroups ' + group).replace('/usr/local/lib/employee-dispatch.py', str(dispatcher))
            inner = f"""
Port 22
ListenAddress 127.0.0.2
PidFile {base}/inner.pid
HostKey {host}
AuthorizedKeysFile {inner_authorized}
StrictModes yes
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
PermitRootLogin prohibit-password
AllowUsers employee
PrintMotd no
Subsystem sftp /usr/lib/openssh/sftp-server
AllowTcpForwarding yes
AllowStreamLocalForwarding yes
AllowAgentForwarding yes
PermitTunnel yes
"""
            # Negative tests share loopback; disable only the test daemon's source penalties.
            outer += '\nPerSourcePenalties no\n'
            daemon('inner', inner)
            daemon('bob-inner', inner.replace('ListenAddress 127.0.0.2', 'ListenAddress 127.0.0.3').replace(str(inner_authorized), str(bob_authorized)).replace(str(base / 'inner.pid'), str(base / 'bob-inner.pid')))
            daemon('outer', outer)
            wait_port(2222)
            opts = ['-F', '/dev/null', '-p', '2222', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(outer_known), '-o', 'ConnectTimeout=3', '-o', 'IdentitiesOnly=yes']

            def argv(account, extra=()):
                return ['ssh'] + opts + ['-i', str(private_keys[account])] + list(extra) + [account + '@127.0.0.1']

            def ssh(account, command=None, stdin=None, extra=()):
                return run(*(argv(account, extra) + ([command] if command is not None else [])), input=stdin, check=False, timeout=10)

            result = ssh(accounts[0], stdin="printf 'MANAGED-SHELL\\n'; exit\n", extra=['-T'])
            check('interactive-fixed-vm', result.returncode == 0 and 'MANAGED-SHELL' in result.stdout)
            check('actual-bob-cross-play-authorization', bob_authorized.read_text().count('from="127.0.0.3"') == 1 and bob_credential.with_suffix('.pub').read_text().split()[1] in bob_authorized.read_text() and Path(credentials[0]['path']).with_suffix('.pub').read_text().split()[1] not in bob_authorized.read_text())
            bob_opts = ['-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-i', str(bob_credential)]
            own = run('ssh', *bob_opts, '-b', '127.0.0.3', 'employee@127.0.0.3', 'true', check=False, timeout=10)
            check('actual-bob-own-authorization-works', own.returncode == 0)
            denied = run('ssh', *bob_opts, '-b', '127.0.0.1', 'employee@127.0.0.3', 'true', check=False, timeout=10)
            check('actual-bob-wrong-source-denied', denied.returncode != 0 and 'Permission denied' in denied.stderr)
            for label, credential, bind in [('bob-key', bob_credential, '127.0.0.1'), ('skipped-key', skipped_credential, '127.0.0.1'), ('wrong-source', Path(credentials[0]['path']), '127.0.0.4')]:
                denied = run('ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-i', str(credential), '-b', bind, 'employee@127.0.0.2', 'true', check=False, timeout=10)
                check('actual-workspace-authorization-denies-' + label, denied.returncode != 0 and 'Permission denied' in denied.stderr)
            result = ssh(accounts[2], stdin='printf "%s\n" "$SSH_CONNECTION"; exit\n', extra=['-T'])
            check('managed-bob-fixed-target', result.returncode == 0 and '127.0.0.3 22' in result.stdout)
            # Rotate the existing administrator through the production shared task.
            admin = 'ed-admin-' + suffix
            admin_home = base / 'admin-home'
            admin_home.mkdir()
            run('useradd', '-M', '-d', str(admin_home), '-s', '/bin/sh', '-g', group, '-p', '*', admin)
            created.append(admin)
            os.chown(admin_home, pwd.getpwnam(admin).pw_uid, 0)
            old_admin, new_admin = key('old-admin'), key('new-admin')
            admin_play = base / 'admin-rotation.yml'
            def reconcile_admin(public):
                admin_play.write_text(yaml.safe_dump([{'hosts': 'gateway', 'gather_facts': False, 'vars': {'employee_admin_user': admin, 'employee_admin_public_keys': [public]}, 'tasks': [{'name': 'Reconcile actual administrator keys', 'ansible.builtin.include_tasks': str(ROLE / 'tasks/admin-keys.yml')}]}]))
                result = run('/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(admin_play), env=env, check=False, input='')
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)
            reconcile_admin(old_admin.with_suffix('.pub').read_text().strip())
            admin_config = inner.replace('ListenAddress 127.0.0.2', 'ListenAddress 127.0.0.4').replace(str(inner_authorized), str(admin_home / '.ssh/authorized_keys')).replace('AllowUsers employee', 'AllowUsers ' + admin).replace(str(base / 'inner.pid'), str(base / 'admin.pid'))
            daemon('admin', admin_config)
            time.sleep(0.1)
            def admin_login(credential):
                return run('ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-i', str(credential), admin + '@127.0.0.4', 'true', check=False, timeout=10)
            check('old-admin-key-positive-control', admin_login(old_admin).returncode == 0)
            reconcile_admin(new_admin.with_suffix('.pub').read_text().strip())
            check('new-admin-key-logs-in-after-reconciliation', admin_login(new_admin).returncode == 0)
            check('old-admin-key-revoked-after-reconciliation', admin_login(old_admin).returncode != 0)
            for command in ['id', 'ssh bob@127.0.0.3', 'employee-sftp;id', 'employee-sftp\n', '$(id)', 'scp -t /tmp']:
                result = ssh(accounts[0], command=command)
                check('reject-command-' + repr(command), result.returncode != 0 and 'Access denied.' in result.stderr)
            result = run('ssh', *opts, '-i', str(unknown), accounts[0] + '@127.0.0.1', check=False, timeout=10)
            check('unknown-key', result.returncode != 0 and 'Permission denied' in result.stderr)
            result = run('ssh', *opts, '-i', str(private_keys[accounts[0]]), 'ed-unknown-' + suffix + '@127.0.0.1', check=False, timeout=10)
            check('unknown-device-account', result.returncode != 0)
            source, target, downloaded = base / 'source', data_dir / 'target', base / 'downloaded'
            source.write_text('SFTP-FIXED-MAPPING\n')
            sftp_opts = ['-F', '/dev/null', '-P', '2222', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(outer_known), '-o', 'IdentityFile=' + str(private_keys[accounts[0]])]
            result = run('sftp', *sftp_opts, '-b', '-', accounts[0] + '@127.0.0.1', input=f'put {source} {target}\nget {target} {downloaded}\n', check=False, timeout=10)
            check('sftp-roundtrip', result.returncode == 0 and downloaded.exists() and downloaded.read_text() == source.read_text())
            for label, options in [
                ('stdio-forward', ['-W', '127.0.0.2:22']),
                ('remote-forward', ['-N', '-o', 'ExitOnForwardFailure=yes', '-R', '127.0.0.1:2299:127.0.0.2:22']),
                ('remote-streamlocal', ['-N', '-o', 'ExitOnForwardFailure=yes', '-R', str(base / 'remote.sock') + ':127.0.0.2:22']),
            ]:
                result = ssh(accounts[0], extra=options)
                check(label + '-denied-with-permissive-guest', result.returncode != 0 and ('prohibited' in result.stderr or 'forwarding failed' in result.stderr))
            for label, options, port in [
                ('local-forward', ['-L', '127.0.0.1:2297:127.0.0.2:22'], 2297),
                ('dynamic-forward', ['-D', '127.0.0.1:2298'], 2298),
            ]:
                proc = subprocess.Popen(argv(accounts[0], ['-N'] + options), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(proc)
                wait_port(port)
                with socket.create_connection(('127.0.0.1', port), timeout=2) as sock:
                    sock.settimeout(2)
                    if label == 'dynamic-forward':
                        sock.sendall(b'\x05\x01\x00')
                        check('socks-local-handshake', sock.recv(2) == b'\x05\x00')
                        sock.sendall(b'\x05\x01\x00\x01\x7f\x00\x00\x02\x00\x16')
                    try:
                        data = sock.recv(100)
                    except ConnectionResetError:
                        data = b''
                    check(label + '-denied', not data.startswith(b'SSH-') and (not data or data[:2] != b'\x05\x00'))
                proc.terminate()
                proc.wait(timeout=5)
            known.write_text('employee-alice ' + changed_host.with_suffix('.pub').read_text())
            result = ssh(accounts[0], stdin='exit\n', extra=['-T'])
            check('changed-host-key-fails-closed', result.returncode != 0 and 'HOST IDENTIFICATION HAS CHANGED' in result.stderr)
            known.write_text('employee-alice ' + host.with_suffix('.pub').read_text() + 'employee-bob ' + host.with_suffix('.pub').read_text())
            mapping = access / 'devices' / (accounts[0] + '.json')
            saved = mapping.read_text()
            mapping.unlink()
            result = ssh(accounts[0], stdin='exit\n', extra=['-T'])
            check('missing-map-fails-closed', result.returncode != 0 and 'Access denied' in result.stderr)
            mapping.write_text(saved)
            reassignment_sessions = []
            for account in accounts[:2]:
                proc = subprocess.Popen(argv(account, ['-T']), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(proc)
                proc.stdin.write("printf 'MAPPING-READY\\n'; read ignored\n")
                proc.stdin.flush()
                ready, _, _ = select.select([proc.stdout], [], [], 8)
                check('mapping-change-positive-session-' + account, bool(ready) and 'MAPPING-READY' in proc.stdout.readline())
                reassignment_sessions.append(proc)
            roster[accounts[0]]['employee'] = 'bob'
            publish_devices()
            reassignment_sessions[0].wait(timeout=5)
            check('actual-device-reassignment-kills-old-session', reassignment_sessions[0].returncode != 0)
            check('actual-device-reassignment-preserves-other-device', reassignment_sessions[1].poll() is None)
            # Reconcile both workspace authorizations after moving the device.
            plays[0]['tasks'][0]['loop'][0]['value']['employee'] = 'bob'
            playbook.write_text(yaml.safe_dump(plays))
            run('/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(playbook), env=env, input='')
            result = ssh(accounts[0], stdin='printf "%s\n" "$SSH_CONNECTION"; exit\n', extra=['-T'])
            check('reassigned-device-reaches-only-bob-target', result.returncode == 0 and '127.0.0.3 22' in result.stdout)
            roster[accounts[0]]['employee'] = 'alice'
            publish_devices()
            plays[0]['tasks'][0]['loop'][0]['value']['employee'] = 'alice'
            playbook.write_text(yaml.safe_dump(plays))
            run('/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(playbook), env=env, input='')
            sessions = []
            for account in accounts:
                proc = subprocess.Popen(argv(account, ['-T']), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(proc)
                proc.stdin.write("printf 'SESSION-READY\\n'; read ignored\n")
                proc.stdin.flush()
                ready, _, _ = select.select([proc.stdout], [], [], 8)
                check('active-session-' + account, bool(ready) and 'SESSION-READY' in proc.stdout.readline())
                sessions.append(proc)
            sftp_session = subprocess.Popen(['sftp'] + sftp_opts + [accounts[0] + '@127.0.0.1'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append(sftp_session)
            sftp_session.stdin.write(b'pwd\n')
            sftp_session.stdin.flush()
            output = b''
            until = time.monotonic() + 5
            while time.monotonic() < until and b'Remote working directory:' not in output:
                ready, _, _ = select.select([sftp_session.stdout], [], [], 0.2)
                if ready:
                    output += os.read(sftp_session.stdout.fileno(), 4096)
            check('active-sftp-session', b'Remote working directory:' in output)
            # Execute the production revoke task; relocate only its file destinations.
            revoke = yaml.safe_load((ROLE / 'tasks/revoke.yml').read_text().replace('/etc/employee-access', str(access)))
            revoke_play = base / 'revocation-play.yml'
            revoke_play.write_text(yaml.safe_dump([{'name': 'Revoke actual device', 'hosts': 'gateway', 'gather_facts': False, 'vars': {'employee_revoke_account': accounts[0]}, 'tasks': revoke}]))
            result = run('/opt/iac-venv/bin/ansible-playbook', '-i', str(inventory), str(revoke_play), env=env, check=False, input='')
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            check('actual-ansible-device-revocation', not mapping.exists() and not (access / 'keys' / accounts[0]).exists() and (access / 'authorized-keys' / accounts[0]).read_text() == '')
            sessions[0].wait(timeout=5)
            check('revocation-kills-existing-session', sessions[0].returncode != 0)
            revoked_target = data_dir / 'revoked-upload'
            sftp_session.stdin.write(f'put {source} {revoked_target}\n'.encode())
            sftp_session.stdin.flush()
            sftp_session.stdin.close()
            sftp_session.wait(timeout=5)
            check('revocation-kills-existing-sftp', sftp_session.returncode != 0 and not revoked_target.exists())
            check('other-device-session-survives', sessions[1].poll() is None)
            result = ssh(accounts[0], stdin='exit\n', extra=['-T'])
            check('revoked-device-cannot-reconnect', result.returncode != 0)
            result = ssh(accounts[1], stdin="printf 'OTHER-DEVICE\\n'; exit\n", extra=['-T'])
            check('other-device-can-reconnect', result.returncode == 0 and 'OTHER-DEVICE' in result.stdout)
            roster[accounts[0]]['enabled'] = False
            publish_devices()
            publish_devices()
            check('ordinary-deploy-keeps-revoked-device-files-absent', not mapping.exists() and not (access / 'keys' / accounts[0]).exists() and not (access / 'authorized-keys' / accounts[0]).read_text())
            result = ssh(accounts[0], stdin='exit\n', extra=['-T'])
            check('ordinary-deploy-does-not-restore-revoked-login', result.returncode != 0)
            result = ssh(accounts[2], stdin='exit\n', extra=['-T'])
            check('ordinary-deploy-preserves-bob-login', result.returncode == 0)
            print(json.dumps({'passed': len(results), 'scope': 'isolated real OpenSSH/SFTP; no production or OAuth claim'}), flush=True)
        finally:
            for account in created:
                run('pkill', '-KILL', '-u', account, check=False)
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for log in logs:
                log.close()
            for account in reversed(created):
                run('userdel', account, check=False)
            run('groupdel', group, check=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
