#!/usr/bin/env python3
"""Offline lifecycle guards and real flock; no host service or secret access."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles/employee-workspace/files'
CONTRACT = FILES / 'desktop-contract.py'
# The production install copies this exact existing helper beside the service.
TEMP = tempfile.TemporaryDirectory(prefix='story3-lifecycle-')
INSTALLED = Path(TEMP.name)
shutil.copyfile(CONTRACT, INSTALLED / 'desktop-contract.py')
shutil.copyfile(FILES / 'desktop-service.py', INSTALLED / 'desktop-service.py')
spec = importlib.util.spec_from_file_location('desktop_service', INSTALLED / 'desktop-service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
cli_spec = importlib.util.spec_from_file_location('desktop_cli', FILES / 'workspace-desktop.py')
# Import the CLI while replacing only its fixed installed helper location.
real_spec = importlib.util.spec_from_file_location
with patch('importlib.util.spec_from_file_location', side_effect=lambda name, path: real_spec(name, INSTALLED / 'desktop-service.py') if str(path) == '/usr/local/lib/employee-workspace/desktop-service.py' else real_spec(name, path)):
    cli = importlib.util.module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)
cli.service = service
FIXTURE = json.loads((Path(__file__).parent / 'fixtures/desktop-lifecycle.json').read_text())



class DesktopTests(unittest.TestCase):
    def test_explicit_selection_and_bad_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            for mutation in (None, lambda c: c.update(vmid=501), lambda c: c['backend'].update(type='legacy-novnc'), lambda c: c['generation'].update(vmid=501), lambda c: c['backend'].update(generation_id='latest')):
                config = copy.deepcopy(FIXTURE)
                if mutation:
                    mutation(config)
                path.write_text(json.dumps(config))
                with patch.object(service, 'CONFIG', path), patch.object(service, 'secure_file'):
                    if mutation:
                        with self.assertRaises((service.Refused, ValueError)):
                            service.load_config()
                    else:
                        self.assertEqual(service.load_config()['vmid'], 502)

    def test_any_transition_marker_blocks_without_reading(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'transition.json'
            with patch.object(service, 'MARKER', marker):
                service.transition_guard()
                marker.write_text('corrupt')
                with self.assertRaises(service.Refused) as caught:
                    service.transition_guard()
                self.assertEqual(caught.exception.code, 75)
                self.assertEqual(marker.read_text(), 'corrupt')
                marker.unlink()
                marker.symlink_to('/missing')
                with self.assertRaises(service.Refused):
                    service.transition_guard()
        with patch.object(service, 'MARKER') as inaccessible:
            inaccessible.lstat.side_effect = PermissionError()
            with self.assertRaises(service.Refused) as caught:
                service.transition_guard()
            self.assertEqual(caught.exception.code, 75)

    def test_port_conflict_is_rejected(self):
        with patch.object(service.socket, 'socket') as factory:
            factory.return_value.__enter__.return_value.bind.side_effect = OSError()
            with self.assertRaises(service.Refused):
                service.port_guard(FIXTURE)

    def test_unapproved_installed_version_is_rejected(self):
        outputs = [subprocess.CompletedProcess([], 0, stdout='amd64\n'),
                   subprocess.CompletedProcess([], 0, stdout='1.4.0-1\n')]
        with patch.object(service.Path, 'read_text', return_value='ID=ubuntu\nVERSION_ID="26.04"\n'), patch.object(service, 'run', side_effect=outputs):
            with self.assertRaises(service.Refused):
                service.check_platform()

    def test_material_identity_and_authentication_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            authentication = Path(folder) / 'authentication.json'
            config = {'materials': {'trust_ref': Path(folder) / 'ca.pem', 'certificate_ref': Path(folder) / 'server.pem', 'private_key_ref': Path(folder) / 'server.key', 'authentication_ref': authentication}, 'backend': FIXTURE['backend']}
            for mismatch in (True, False):
                with self.subTest(key_mismatch=mismatch):
                    authentication.write_text(json.dumps({'username': 'synthetic', 'password': 'valid-synthetic' if mismatch else 'invalid\npassword'}))
                    outputs = [subprocess.CompletedProcess([], 0, stdout='CA:TRUE'), subprocess.CompletedProcess([], 0, stdout='DNS:localhost')]
                    outputs += [subprocess.CompletedProcess([], 0, stdout=b'') for _ in range(2)]
                    outputs += [subprocess.CompletedProcess([], 0, stdout=b'CERT_PUBLIC_KEY'), subprocess.CompletedProcess([], 0, stdout=b'OTHER_PUBLIC_KEY' if mismatch else b'CERT_PUBLIC_KEY')]
                    with patch.object(service, 'secure_file'), patch.object(service.grp, 'getgrnam'), patch.object(service.pwd, 'getpwnam'), patch.object(service.Path, 'stat'), patch.object(service, 'run', side_effect=outputs):
                        with self.assertRaises(service.Refused):
                            service.validate_materials(config)

    def test_material_files_reject_unsafe_ownership_mode_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'material'
            path.write_text('synthetic')
            path.chmod(0o600)
            self.assertEqual(service.secure_file(path, os.getuid(), 0o640), path)
            with self.assertRaises(service.Refused):
                service.secure_file(path, os.getuid() + 1, 0o640)
            path.chmod(0o666)
            with self.assertRaises(service.Refused):
                service.secure_file(path, os.getuid(), 0o640)
            path.chmod(0o600)
            link = path.with_name('link')
            link.symlink_to(path)
            with self.assertRaises(service.Refused):
                service.secure_file(link, os.getuid(), 0o640)

    def test_secret_group_must_be_employee_exclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'secret'
            path.write_text('synthetic')
            path.chmod(0o640)
            service.secure_file(path, os.getuid(), 0o640, group=path.stat().st_gid)
            with self.assertRaises(service.Refused):
                service.secure_file(path, os.getuid(), 0o640, group=path.stat().st_gid + 1)
            path.chmod(0o600)
            service.secure_file(path, os.getuid(), 0o640, group=path.stat().st_gid + 1)

    def test_root_candidate_rejects_employee_unreadable_materials(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder).resolve()
            path = directory / 'secret'
            path.write_text('synthetic')
            config = {'materials': {'private_key_ref': path}}
            with patch.object(service, 'secure_file'), patch.object(service.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=os.getuid() + 1)), patch.object(service.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=path.stat().st_gid)), patch.object(service, 'run') as run:
                path.chmod(0o600)
                with self.assertRaises(service.Refused):
                    service.validate_materials(config)
                path.chmod(0o640)
                directory.chmod(0o700)
                with self.assertRaises(service.Refused):
                    service.validate_materials(config)
                run.assert_not_called()

    def test_install_check_has_no_runtime_guards(self):
        with patch.object(service.sys, 'argv', ['service', 'check']), patch.object(service, 'load_config', return_value=FIXTURE), patch.object(service, 'check_platform') as platform, patch.object(service, 'validate_materials') as materials, patch.object(service, 'transition_guard') as marker, patch.object(service, 'profile_guard') as profile, patch.object(service, 'port_guard') as ports:
            service.main()
            platform.assert_called_once()
            materials.assert_called_once_with(FIXTURE)
            marker.assert_not_called()
            profile.assert_not_called()
            ports.assert_not_called()

    def test_candidate_validation_requires_root_and_checks_materials(self):
        with tempfile.TemporaryDirectory() as folder:
            candidate = Path(folder) / 'candidate'
            candidate.write_text(json.dumps(FIXTURE))
            with patch.object(service.sys, 'argv', ['service', 'validate-config', str(candidate)]), patch.object(service.os, 'geteuid', return_value=1000), patch.object(service, 'secure_file') as secure:
                with self.assertRaises(service.Refused):
                    service.main()
                secure.assert_not_called()
            with patch.object(service.sys, 'argv', ['service', 'validate-config', str(candidate)]), patch.object(service.os, 'geteuid', return_value=0), patch.object(service, 'secure_file', return_value=candidate), patch.object(service, 'validate_materials') as materials:
                service.main()
                self.assertEqual(materials.call_args[0][0]['backend'], FIXTURE['backend'])

    def test_targeted_autostart_preserves_other_entries_and_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder).resolve()
            directory = home / '.config/autostart'
            directory.mkdir(parents=True)
            blocked = directory / 'arbitrary-name.desktop'
            original = '[Desktop Entry]\nName=Preserve me\nExec=/usr/bin/env FOO=bar /usr/bin/firefox-esr --test\nHidden=false\nX-Keep=yes\n[Other]\nHidden=false\n'
            blocked.write_text(original)
            normal = directory / 'normal.desktop'
            normal.write_text('[Desktop Entry]\nExec=/usr/bin/touch harmless\n')
            with patch.object(service.Path, 'glob', autospec=True) as glob:
                glob.side_effect = lambda p, pattern: [] if str(p) == '/etc/xdg/autostart' else list(directory.iterdir())
                service.autostart_policy({'HOME': str(home)})
                self.assertEqual(blocked.read_text(), original.replace('Hidden=false', 'Hidden=true', 1))
                self.assertEqual(normal.read_text(), '[Desktop Entry]\nExec=/usr/bin/touch harmless\n')
    def test_invalid_unrelated_autostarts_are_skipped_but_known_names_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder).resolve()
            directory = home / '.config/autostart'
            system = home / 'system'
            directory.mkdir(parents=True)
            system.mkdir()
            cases = (('missing', None), ('encoding', b'\xff'), ('exec', b'[Desktop Entry]\nExec="unterminated\n'), ('config', b'Exec=unrelated\n'))
            known = ('firefox', 'xscreensaver', 'ibus', 'fcitx5')
            for (label, content), program in zip(cases, known):
                for name in ('unrelated-' + label, program):
                    path = directory / (name + '.desktop')
                    if content is None:
                        path.symlink_to(home / 'absent')
                    else:
                        path.write_bytes(content)
            original_path = service.Path
            with patch.object(service, 'Path', side_effect=lambda value: system if str(value) == '/etc/xdg/autostart' else original_path(value)):
                service.autostart_policy({'HOME': str(home)})
            for (label, content), program in zip(cases, known):
                path = directory / ('unrelated-' + label + '.desktop')
                if content is None:
                    self.assertTrue(path.is_symlink())
                else:
                    self.assertEqual(path.read_bytes(), content)
                self.assertEqual((directory / (program + '.desktop')).read_text(), '[Desktop Entry]\nHidden=true\n')
            self.assertFalse(list(directory.glob('.employee-autostart-*')))

    def test_valid_source_symlinks_are_replaced_without_writing_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder).resolve()
            directory = home / '.config/autostart'
            system = home / 'system'
            directory.mkdir(parents=True)
            system.mkdir()
            expected = {}
            for label, program, root in (('system', 'firefox', system), ('user', 'xscreensaver', directory), ('normal', '/usr/bin/touch harmless', directory)):
                target = home / (label + '-source')
                content = '[Desktop Entry]\nName=Preserved\nExec=' + program + '\nHidden=false\nX-Keep=yes\n'
                target.write_text(content)
                target.chmod(0o444)
                name = label + '.desktop'
                (root / name).symlink_to(target)
                expected[label] = (target, content, name)
            original_path = service.Path
            with patch.object(service, 'Path', side_effect=lambda value: system if str(value) == '/etc/xdg/autostart' else original_path(value)):
                service.autostart_policy({'HOME': str(home)})
            for label, (target, content, name) in expected.items():
                self.assertEqual(target.read_text(), content)
                if label == 'normal':
                    self.assertTrue((directory / name).is_symlink())
                else:
                    self.assertFalse((directory / name).is_symlink())
                    self.assertEqual((directory / name).read_text(), content.replace('Hidden=false', 'Hidden=true'))
            self.assertTrue((system / 'system.desktop').is_symlink())
            self.assertFalse(list(directory.glob('.employee-autostart-*')))

    def test_marker_is_rejected_before_opening_or_waiting_for_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'transition.json'
            marker.write_text('present')
            with patch.object(service, 'MARKER', marker), patch.object(service.os, 'open') as opened, patch.object(service.fcntl, 'flock') as flock:
                with self.assertRaises(service.Refused) as caught:
                    with service.startup_lock():
                        self.fail('Marker allowed entry')
                self.assertEqual(caught.exception.code, 75)
                opened.assert_not_called()
                flock.assert_not_called()

    def test_status_is_read_only_and_distinguishes_failure(self):
        with patch.object(cli, 'state', return_value='inactive'), patch.object(service.os.path, 'lexists', return_value=False), patch.object(cli, 'control') as control, patch.object(service, 'retire') as retire:
            self.assertEqual(cli.status(FIXTURE), 3)
            control.assert_not_called()
            retire.assert_not_called()
        with patch.object(cli, 'state', return_value='failed'):
            with self.assertRaises(service.Refused) as caught:
                cli.status(FIXTURE)
            self.assertEqual(caught.exception.code, 1)
        with patch.object(cli, 'state', return_value='active'), patch.object(service, 'live_session', side_effect=service.Refused('not ready')):
            with self.assertRaises(service.Refused):
                cli.status(FIXTURE)

    def test_stop_order_and_no_process_killing(self):
        calls = []
        with patch.object(service, 'load_config', return_value=FIXTURE), patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='loaded\n')), patch.object(cli, 'control', side_effect=lambda action, unit: calls.append((action, unit)) or 0):
            self.assertEqual(cli.main(['stop']), 0)
        self.assertEqual(calls, [('stop', service.BROWSER), ('stop', service.DESKTOP)])

    def test_root_is_rejected_before_reading_configuration(self):
        with patch.object(cli.os, 'geteuid', return_value=0), patch.object(service, 'load_config') as config:
            for action in ('start', 'status', 'stop'):
                with self.assertRaises(service.Refused) as caught:
                    cli.main([action])
                self.assertEqual(caught.exception.code, 64)
                self.assertIn('employee', str(caught.exception))
            config.assert_not_called()

    def test_stop_missing_browser_and_query_failure(self):
        for code, load, expected in ((0, 'not-found', [service.DESKTOP]), (1, '', []), (0, 'error', []), (0, 'loaded', [service.BROWSER])):
            calls = []
            with self.subTest(load=load), patch.object(service, 'load_config', return_value=FIXTURE), patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, stdout=load)), patch.object(cli, 'control', side_effect=lambda action, unit: calls.append(unit) or (1 if unit == service.BROWSER else 0)):
                if load == 'not-found':
                    self.assertEqual(cli.main(['stop']), 0)
                else:
                    with self.assertRaises(service.Refused):
                        cli.main(['stop'])
                self.assertEqual(calls, expected)

    def test_start_releases_lock_before_systemctl(self):
        held = []
        from contextlib import contextmanager
        @contextmanager
        def lock():
            held.append(True)
            try:
                yield
            finally:
                held.pop()
        def control(action, unit):
            self.assertFalse(held)
            return 0
        with patch.object(service, 'load_config', return_value=FIXTURE), patch.object(service, 'startup_lock', lock), patch.object(service, 'preflight') as check, patch.object(cli, 'state', return_value='inactive'), patch.object(cli, 'control', side_effect=control), patch.object(cli, 'status', return_value=0):
            self.assertEqual(cli.main(['start']), 0)
            check.assert_called_once_with(FIXTURE, running=False)

    def test_atomic_session_permissions_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.json'
            session = {'version': 1, 'ready': True, 'display': ':98', 'xauthority': '/run/employee-desktop/Xauthority', 'dbus_session_bus_address': 'unix:path=/run/employee-desktop/bus', 'xdg_runtime_dir': '/run/employee-desktop/xdg'}
            service.contract.publish_session(path, session)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), session)
            self.assertEqual(list(Path(folder).iterdir()), [path])
            with patch.object(service, 'SESSION', path):
                service.retire()
                service.retire()
            self.assertFalse(path.exists())

    def test_unmanaged_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            proc = Path(folder) / '123'
            proc.mkdir()
            (proc / 'cmdline').write_bytes(b'firefox\0--profile\0' + service.PROFILE.encode() + b'\0')
            (proc / 'cgroup').write_text('0::/user.slice/unmanaged')
            original = service.Path
            with patch.object(service, 'Path', side_effect=lambda p: original(folder) if p == '/proc' else original(p)):
                with self.assertRaises(service.Refused):
                    service.profile_guard()

    def test_real_firefox_lock_is_checked_without_deleting(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'profile'
            proc = Path(folder) / 'proc'
            profile.mkdir()
            proc.mkdir()
            lock = profile / '.parentlock'
            lock.touch()
            compatibility = profile / 'lock'
            signature = '127.0.0.1:+' + str(os.getpid())
            compatibility.symlink_to(signature)
            original = service.Path
            def paths(p):
                return proc if p == '/proc' else original(p)
            inactive = subprocess.CompletedProcess([], 3)
            with patch.object(service, 'PROFILE', str(profile)), patch.object(service, 'Path', side_effect=paths), patch.object(service.subprocess, 'run', return_value=inactive), patch.object(service.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=os.getuid())):
                service.profile_guard()
                # A separate process owns the real POSIX lock, not a mocked flag.
                child = subprocess.Popen(['python3', '-c', 'import fcntl,sys;f=open(sys.argv[1],"r+");fcntl.lockf(f,fcntl.LOCK_EX);print("ready",flush=True);sys.stdin.read()', str(lock)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                try:
                    self.assertEqual(child.stdout.readline().strip(), 'ready')
                    with self.assertRaises(service.Refused):
                        service.profile_guard()
                finally:
                    child.communicate('', timeout=5)
                self.assertTrue(lock.exists())
                service.profile_guard()
                self.assertEqual(os.readlink(compatibility), signature)
                lock.unlink()
                with self.assertRaises(service.Refused):
                    service.profile_guard()
                self.assertEqual(os.readlink(compatibility), signature)

    def test_profile_locks_use_fixed_employee_owner_for_root_and_employee_callers(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'profile'; profile.mkdir()
            proc = Path(folder) / 'proc'; proc.mkdir()
            lock = profile / '.parentlock'; lock.write_bytes(b'synthetic-only'); lock.chmod(0o600)
            compatibility = profile / 'lock'; signature = '127.0.0.1:+' + str(os.getpid())
            compatibility.symlink_to(signature)
            before = (lock.stat().st_ino, lock.read_bytes(), os.readlink(compatibility))
            original_path, original_fstat, original_lstat = service.Path, os.fstat, Path.lstat
            def paths(path):
                return proc if path == '/proc' else original_path(path)
            def owner(info, uid):
                fields = list(info); fields[4] = uid
                return os.stat_result(fields)
            for caller_uid in (0, 1001):
                for foreign in (None, 'regular', 'symlink'):
                    with self.subTest(caller_uid=caller_uid, foreign=foreign):
                        def fstat(fd):
                            return owner(original_fstat(fd), 2002 if foreign == 'regular' else 1001)
                        def lstat(path, *args, **kwargs):
                            info = original_lstat(path, *args, **kwargs)
                            return owner(info, 2002 if foreign == 'symlink' else 1001) if path == compatibility else info
                        with patch.object(service, 'PROFILE', str(profile)), patch.object(service, 'Path', side_effect=paths), patch.object(service.os, 'getuid', return_value=caller_uid), patch.object(service.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=1001)) as employee, patch.object(service.os, 'fstat', side_effect=fstat), patch.object(Path, 'lstat', lstat), patch.object(service.subprocess, 'run', return_value=subprocess.CompletedProcess([], 3)):
                            if foreign:
                                with self.assertRaises(service.Refused):
                                    service.profile_guard()
                            else:
                                service.profile_guard()
                            employee.assert_called_once_with('employee')
                        self.assertEqual((lock.stat().st_ino, lock.read_bytes(), os.readlink(compatibility)), before)

    def test_root_and_employee_guards_reject_real_active_posix_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'profile'; profile.mkdir()
            proc = Path(folder) / 'proc'; proc.mkdir()
            lock = profile / '.parentlock'; lock.touch(mode=0o600)
            original_path, original_fstat = service.Path, os.fstat
            def paths(path):
                return proc if path == '/proc' else original_path(path)
            def employee_fstat(fd):
                fields = list(original_fstat(fd)); fields[4] = 1001
                return os.stat_result(fields)
            child = subprocess.Popen(['python3', '-c', 'import fcntl,sys;f=open(sys.argv[1],"r+");fcntl.lockf(f,fcntl.LOCK_EX);print("ready",flush=True);sys.stdin.read()', str(lock)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                for caller_uid in (0, 1001):
                    with self.subTest(caller_uid=caller_uid), patch.object(service, 'PROFILE', str(profile)), patch.object(service, 'Path', side_effect=paths), patch.object(service.os, 'getuid', return_value=caller_uid), patch.object(service.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=1001)), patch.object(service.os, 'fstat', side_effect=employee_fstat), patch.object(service.subprocess, 'run', return_value=subprocess.CompletedProcess([], 3)):
                        with self.assertRaisesRegex(service.Refused, 'Unmanaged profile lock'):
                            service.profile_guard()
            finally:
                child.communicate('', timeout=5)
            self.assertTrue(lock.exists())

    def test_failed_atomic_publish_preserves_prior_record(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'session.json'
            target.write_text('prior')
            session = {'version': 1, 'ready': True, 'display': ':98', 'xauthority': '/run/employee-desktop/Xauthority', 'dbus_session_bus_address': 'unix:path=/run/employee-desktop/bus', 'xdg_runtime_dir': '/run/employee-desktop/xdg'}
            with patch.object(service.contract.os, 'replace', side_effect=OSError('simulated interrupted publication')):
                with self.assertRaises(OSError):
                    service.contract.publish_session(target, session)
            self.assertEqual(target.read_text(), 'prior')
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_readiness_rejects_dead_component(self):
        from unittest.mock import Mock
        child = Mock()
        child.poll.return_value = 1
        with patch.object(service, 'run') as run:
            with self.assertRaises(service.Refused):
                service.wait_x({}, [child], wm=True)
            run.assert_not_called()

    def test_static_unit_ownership_and_stop_dependency(self):
        unit = (FILES / 'employee-desktop.service').read_text()
        browser = (FILES / 'employee-browser-desktop.conf').read_text()
        for value in ('Type=notify', 'User=employee', 'Restart=no', 'KillMode=control-group', 'ExecStopPost='):
            self.assertIn(value, unit)
        self.assertNotIn('[Install]', unit)
        self.assertNotIn('firefox', unit.lower())
        for value in ('BindsTo=employee-desktop.service', 'After=employee-desktop.service', 'PartOf=employee-desktop.service', 'Restart=no'):
            self.assertIn(value, browser)


    def test_real_flock_serializes_processes(self):
        # Python 3.9 on macOS gives monotonic clocks a per-process origin.
        # Observe ordering in one shared journal instead of comparing clocks.
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / 'lock'
            journal = Path(folder) / 'events'
            lock.touch(mode=0o660)
            script = r"""import fcntl,os,sys,time
f = open(sys.argv[1], 'r+')
print('ready', flush=True)
sys.stdin.readline()
fcntl.flock(f, fcntl.LOCK_EX)
fd = os.open(sys.argv[2], os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
for event in ('enter', 'exit'):
    os.write(fd, (event + ':' + str(os.getpid()) + '\n').encode())
    if event == 'enter':
        time.sleep(.12)
os.close(fd)
"""
            children = [subprocess.Popen(['python3', '-c', script, str(lock), str(journal)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) for _ in range(3)]
            try:
                for child in children:
                    self.assertEqual(child.stdout.readline().strip(), 'ready')
                # Release all contenders only after every process is ready.
                for child in children:
                    child.stdin.write('go\n')
                    child.stdin.flush()
                for child in children:
                    child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 0)
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=5)
                    child.stdin.close()
                    child.stdout.close()
            events = [line.split(':') for line in journal.read_text().splitlines()]
            self.assertEqual(len(events), 6)
            entrants = []
            for index in range(0, 6, 2):
                event, pid = events[index]
                self.assertEqual(event, 'enter')
                self.assertEqual(events[index + 1], ['exit', pid])
                entrants.append(int(pid))
            self.assertCountEqual(entrants, [child.pid for child in children])


if __name__ == '__main__':
    unittest.main()
