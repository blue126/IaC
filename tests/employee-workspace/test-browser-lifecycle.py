#!/usr/bin/env python3
"""Real private AF_UNIX framing plus isolated CLI lifecycle regression."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles/employee-workspace/files'
TEMP = tempfile.TemporaryDirectory(prefix='story4-browser-')
INSTALL = Path(TEMP.name)
for name in ('desktop-service.py', 'browser-service.py'):
    shutil.copyfile(FILES / name, INSTALL / name)
shutil.copyfile(FILES / 'desktop-contract.py', INSTALL / 'desktop-contract.py')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


browser = load('browser', INSTALL / 'browser-service.py')
cli = load('browser_cli', FILES / 'workspace-browser.py')


class Peer:
    """macOS test adapter: real stream I/O, Linux kernel peer identity fixture."""
    def __init__(self, peer, uid):
        self.peer, self.uid = peer, uid
    def getsockopt(self, *args):
        return struct.pack('3i', os.getpid(), self.uid, os.getgid())
    def __getattr__(self, name):
        return getattr(self.peer, name)


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='s4-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def exchange(self, payloads, uid=None, execute=None):
        path = self.base / 'control.sock'
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(path))
        os.chmod(path, 0o600)
        server.listen(16)
        errors = []
        def worker():
            try:
                for _ in payloads:
                    peer, _ = server.accept()
                    with peer:
                        browser.handle(Peer(peer, os.getuid() if uid is None else uid))
            except BaseException as exc:
                errors.append(exc)
        with patch.object(browser.socket, 'SO_PEERCRED', 17, create=True), patch.object(browser.service, 'startup_lock', contextlib.nullcontext), patch.object(browser.service, 'transition_guard'), patch.object(browser, 'environment', return_value={'DISPLAY': ':98'}), patch.object(browser.subprocess, 'run', side_effect=execute) as run:
            thread = threading.Thread(target=worker)
            thread.start()
            replies = []
            try:
                for payload in payloads:
                    with socket.socket(socket.AF_UNIX) as client:
                        client.settimeout(5)
                        client.connect(str(path))
                        client.sendall(payload)
                        try:
                            client.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
                        response = bytearray()
                        while not response.endswith(b'\n'):
                            chunk = client.recv(8192)
                            if not chunk:
                                break
                            response.extend(chunk)
                        replies.append(json.loads(response))
            finally:
                thread.join(timeout=5)
                server.close()
                path.unlink()
            self.assertFalse(thread.is_alive())
            self.assertFalse(errors, errors)
            return replies, run.call_args_list

    def test_invalid_frames_and_recovery_on_real_socket(self):
        valid = b'{"version":1,"action":"open","url":"https://example.test/"}\n'
        invalid = [b'\xff\n', b'{bad}\n', b'{}\n', b'{}', b'x' * 8192 + b'\n', valid + valid,
                   b'{"version":1,"version":1,"action":"open","url":"https://example.test/"}\n']
        for value in ('file:///tmp/a', 'https://user:secret@example.test/', 'https://example.test:bad/',
                      'https://example.test/with space', 'https://example.test/\\bad', 'https://example.test/\n'):
            invalid.append((json.dumps({'version': 1, 'action': 'open', 'url': value}) + '\n').encode())
        for field in ('transaction_id', 'environment', 'command'):
            invalid.append((json.dumps({'version': 1, 'action': 'open', 'url': 'https://example.test/', field: 'forbidden'}) + '\n').encode())
        replies, calls = self.exchange(invalid + [valid])
        self.assertTrue(all(r == {'version': 1, 'status': 'rejected', 'exit_code': 64} for r in replies[:-1]))
        self.assertEqual(replies[-1], {'version': 1, 'status': 'opened', 'exit_code': 0})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[0], ['firefox', '--profile', browser.service.PROFILE, '--new-tab', 'https://example.test/'])

    def test_failed_open_and_disconnected_client_do_not_poison_next_request(self):
        valid = b'{"version":1,"action":"open","url":"https://example.test/"}\n'
        replies, _ = self.exchange([valid, valid], execute=[subprocess.CalledProcessError(1, 'redacted'), None])
        self.assertEqual([r['exit_code'] for r in replies], [64, 0])
        left, right = socket.socketpair()
        right.close()
        with left, patch.object(browser.socket, 'SO_PEERCRED', 17, create=True):
            browser.handle(Peer(left, os.getuid()))
        self.assertEqual(self.exchange([valid])[0][0]['exit_code'], 0)

    def test_other_identity_is_rejected_before_read_or_execution(self):
        replies, calls = self.exchange([b''], uid=os.getuid() + 1000)
        self.assertEqual(replies[0]['exit_code'], 64)
        self.assertFalse(calls)

    def test_readiness_skips_disappeared_window_then_finds_firefox(self):
        child = Mock()
        child.poll.return_value = None
        root = subprocess.CompletedProcess([], 0, stdout='0x1, 0x2')
        vanished = subprocess.CalledProcessError(1, ['xprop', '-id', '0x1'])
        visible = subprocess.CompletedProcess([], 0, stdout='_NET_WM_PID(CARDINAL) = 123\nWM_CLASS(STRING) = "Navigator", "firefox"')
        with patch.object(browser.service, 'run', side_effect=[root, vanished, visible]) as run, patch.object(browser.Path, 'read_text', return_value='0::/system.slice/employee-browser.service'):
            self.assertTrue(browser.firefox_ready(child, {'DISPLAY': ':98'}))
            self.assertEqual(run.call_args_list[-1].args[0], ['xprop', '-id', '0x2', '_NET_WM_PID', 'WM_CLASS'])

    def test_disappeared_windows_allow_next_readiness_poll_but_real_failures_propagate(self):
        child = Mock()
        child.poll.return_value = None
        root = subprocess.CompletedProcess([], 0, stdout='0x1')
        vanished = subprocess.CalledProcessError(1, ['xprop', '-id', '0x1'])
        with patch.object(browser.service, 'run', side_effect=[root, vanished, root, vanished]) as run, patch.object(browser.Path, 'read_text', return_value='0::/system.slice/employee-browser.service'):
            self.assertFalse(browser.firefox_ready(child, {}))
            self.assertFalse(browser.firefox_ready(child, {}))
            self.assertEqual(run.call_count, 4)
        with patch.object(browser.service, 'run', side_effect=subprocess.CalledProcessError(1, ['xprop', '-root'])), self.assertRaises(subprocess.CalledProcessError):
            browser.firefox_ready(child, {})
        child.poll.return_value = 1
        with patch.object(browser.service, 'run') as run, self.assertRaises(browser.service.Refused):
            browser.firefox_ready(child, {})
        run.assert_not_called()

    def test_environment_uses_only_live_desktop_fields(self):
        live = {'DISPLAY': ':98', 'XAUTHORITY': '/run/employee-desktop/Xauthority', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/employee-desktop/bus', 'XDG_RUNTIME_DIR': '/run/employee-desktop/xdg'}
        with patch.dict(os.environ, {'DISPLAY': ':99', 'LD_PRELOAD': 'caller', 'DBUS_SESSION_BUS_ADDRESS': 'caller'}), patch.object(browser.service, 'live_session', return_value=live):
            env = browser.environment()
        self.assertEqual({k: env[k] for k in live}, live)
        self.assertNotIn('LD_PRELOAD', env)
        self.assertEqual(env['GNUPGHOME'], '/home/employee/.gnupg')

    def test_kasm_cli_starts_desktop_before_browser_and_never_runs_firefox(self):
        control = self.base / 'control.sock'
        peer = socket.socket(socket.AF_UNIX)
        peer.bind(str(control))
        self.addCleanup(peer.close)
        with patch.object(cli, 'RUNTIME', self.base), patch.object(cli, 'kasm', return_value=True), patch.object(cli, 'ready', return_value=True), patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            cli.ensure_started()
        self.assertEqual(run.call_args_list[0].args[0], [str(cli.DESKTOP_CONTROL), 'start'])
        self.assertEqual(run.call_args_list[1].args[0][-2:], ['start', cli.UNIT])
        self.assertTrue(all('firefox' not in str(call) for call in run.call_args_list))

    def test_kasm_status_distinguishes_stopped_failed_pending_and_ready(self):
        ready = self.base / 'browser-ready'
        ready.touch()
        peer = socket.socket(socket.AF_UNIX)
        peer.bind(str(self.base / 'control.sock'))
        self.addCleanup(peer.close)
        for state, rc, expected, message in (('inactive', 0, 3, '已停止'), ('failed', 0, 1, '启动失败'), ('activating', 0, 69, '尚未就绪'), ('deactivating', 0, 69, '尚未就绪'), ('active', 0, None, ''), ('active', 1, 69, '状态不可用')):
            with self.subTest(state=state, query_rc=rc), patch.object(cli, 'RUNTIME', self.base), patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], rc, stdout=state + '\n')) as run, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.kasm_status(), expected)
                self.assertIn(message, output.getvalue())
                self.assertEqual(run.call_args.args[0], ['/usr/bin/systemctl', 'show', '--property=ActiveState', '--value', cli.UNIT])
        ready.unlink()
        with patch.object(cli, 'RUNTIME', self.base), patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='active\n')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.kasm_status(), 69)
            self.assertIn('尚未就绪', output.getvalue())
        ready.touch()
        (self.base / 'control.sock').unlink()
        with patch.object(cli, 'RUNTIME', self.base), patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='active\n')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.kasm_status(), 69)

    def test_status_routes_kasm_and_preserves_legacy_exit_code(self):
        for mode, code in (('kasmvnc', 3), ('legacy-novnc', 1)):
            with self.subTest(mode=mode), patch.object(cli.sys, 'argv', ['workspace-browser', 'status']), patch.object(cli.os, 'geteuid', return_value=1000), patch.object(cli.Path, 'home', return_value=self.base), patch.object(cli, 'configuration', return_value={'mode': mode}), patch.object(cli, 'kasm_status', return_value=3) as status, patch.object(cli, 'ready', return_value=False), patch.object(cli, 'ensure_started') as start, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), code)
                self.assertEqual(status.call_count, 1 if mode == 'kasmvnc' else 0)
                start.assert_not_called()

    def test_transition_and_connection_statuses(self):
        for status, expected in ((75, 75), (1, 69)):
            with patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], status)):
                with self.assertRaises(cli.Unavailable) as caught:
                    cli.desktop_start()
                self.assertEqual(caught.exception.code, expected)
        with patch.object(cli, 'ensure_started'), patch.object(cli, 'RUNTIME', self.base):
            with self.assertRaises(cli.Unavailable) as caught:
                cli.control_open('https://example.test/')
            self.assertEqual(caught.exception.code, 69)

    def test_legacy_keeps_original_lifecycle_without_desktop_access(self):
        for config in ({'viewer_url': 'http://legacy.test:8443/vnc.html'}, {'mode': 'legacy-novnc', 'viewer_url': 'https://legacy.test:8443/'}):
            path = self.base / 'config'
            path.write_text(json.dumps(config))
            with patch.object(cli, 'CONFIG', path), patch.object(cli, 'active', return_value=True), patch.object(cli, 'ready', return_value=True), patch.object(cli, 'desktop_start') as start:
                cli.ensure_started()
                self.assertEqual(cli.configuration()['viewer_url'], config['viewer_url'])
                start.assert_not_called()


    def test_unit_preserves_stop_direction_and_firefox_cgroup_owner(self):
        unit = (FILES / 'employee-browser.service').read_text()
        for field in ('Type=notify', 'User=employee', 'Restart=no', 'KillMode=control-group', 'BindsTo=employee-desktop.service', 'After=employee-desktop.service', 'PartOf=employee-desktop.service'):
            self.assertIn(field, unit)
        self.assertNotIn('[Install]', unit)
        self.assertNotIn('employee-browser', (FILES / 'employee-desktop.service').read_text())


if __name__ == '__main__':
    unittest.main()
