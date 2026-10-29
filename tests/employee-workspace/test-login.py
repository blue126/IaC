#!/usr/bin/env python3
"""Exercise workspace-login with real tmux/PTYS and synthetic OAuth programs."""
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ansible/roles/employee-workspace/files"

CLAUDE = r'''#!/usr/bin/python3
import json,os,subprocess,sys,time
from pathlib import Path
p=Path(os.environ["LOGIN_FIXTURE"])
scenario=os.environ["LOGIN_SCENARIO"]
state=p/"authenticated"
if sys.argv[1:3]==["auth","status"]:
    if scenario=="bad-status":
        print("invalid")
        print("fixture-private-error",file=sys.stderr)
        raise SystemExit(3)
    logged=state.exists() or scenario=="already"
    method="api_key" if scenario=="other-source" else ("claude.ai" if logged else "none")
    logged=logged or scenario=="other-source"
    if "--text" in sys.argv: print("Fixture subscription status")
    else: print(json.dumps({"loggedIn":logged,"authMethod":method}))
    raise SystemExit(0 if logged else 1)
if sys.argv[1:3]!=["auth","login"]: raise SystemExit(9)
(p/"login-started").write_text("yes")
url="https://claude.com/cai/oauth/authorize?state=fixture-private-state"
if scenario=="bad-url": url="https://example.invalid/oauth/authorize?state=fixture-private-state"
print("Open OAuth URL: "+url,flush=True)
print("OAuth stderr: "+url+"&debug=fixture-private-stderr",file=sys.stderr,flush=True)
(p/"auth-log-mode").write_text(oct(os.stat("/proc/self/fd/1").st_mode & 0o777))
if scenario=="cli-error": raise SystemExit(7)
rc=subprocess.call([os.environ["BROWSER"],url])
if rc: raise SystemExit(8)
if scenario=="manual":
    print("FIXTURE_CODE_PROMPT",flush=True)
    if input().strip()!="fixture-code": raise SystemExit(6)
    state.write_text("yes")
while not state.exists(): time.sleep(.1)
raise SystemExit(0)
'''
BROWSER = r'''#!/usr/bin/python3
import os,subprocess,sys,time
from pathlib import Path
p=Path(os.environ["LOGIN_FIXTURE"])
assert sys.argv[1]=="open", "Authorization must not stop the employee browser"
(p/"browser-url").write_text(sys.argv[2])
if not (p/"browser-pid").exists():
    child=subprocess.Popen(["sleep","60"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,start_new_session=True)
    (p/"browser-pid").write_text(str(child.pid))
(p/"browser-started").write_text("yes")
if os.environ["LOGIN_SCENARIO"]=="success":
    time.sleep(.4)
    (p/"authenticated").write_text("yes")
print("http://10.230.0.1:8443/vnc.html",flush=True)
'''



class LoginFlow(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workspace-login-tests-")
        self.base = Path(self.temporary.name)
        (self.base / "bin").mkdir()
        (self.base / "lib/employee-workspace").mkdir(parents=True)
        (self.base / "home").mkdir()
        for target, content in [
            (self.base / "bin/workspace-login", (SOURCE / "workspace-login.py").read_text()),
            (self.base / "bin/claude", CLAUDE),
            (self.base / "bin/workspace-browser", BROWSER),
            (self.base / "lib/employee-workspace/open-auth-browser",
             "#!/bin/bash\nexec " + str(self.base / "bin/workspace-login") + ' --open-url "$@"\n'),
        ]:
            target.write_text(content)
            target.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.base / "home"),
                        LOGIN_FIXTURE=str(self.base),
                        PATH=str(self.base / "bin") + ":" + os.environ["PATH"])
        for name in ("firefox", "Xvfb", "xauth", "x11vnc", "websockify", "openbox"):
            (self.base / "bin" / name).symlink_to("/bin/true")
        self.clients = []

    def tearDown(self):
        for process, master in self.clients:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            os.close(master)
        marker = self.base / "browser-pid"
        if marker.exists():
            try:
                os.kill(int(marker.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
        self.temporary.cleanup()

    def launch(self, scenario):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
        env = dict(self.env, LOGIN_SCENARIO=scenario, TERM="xterm-256color")
        process = subprocess.Popen(
            [str(self.base / "bin/workspace-login")],
            stdin=slave, stdout=slave, stderr=slave, env=env,
            start_new_session=True,
            preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0),
        )
        os.close(slave)
        self.clients.append((process, master))
        return process, master

    def drive(self, scenario, actions=None, client=None):
        process, master = client or self.launch(scenario)
        data = bytearray()
        actions = list(actions or [])
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if select.select([master], [], [], .1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                data.extend(chunk)
            for trigger, payload in actions[:]:
                if trigger in data:
                    os.write(master, payload)
                    actions.remove((trigger, payload))
            if process.poll() is not None:
                break
        process.wait(timeout=3)
        self.assertFalse(actions, "Expected terminal interaction was not reached")
        self.assertNotIn(b"/oauth/authorize", data)
        self.assertNotIn(b"fixture-private-state", data)
        self.assertNotIn(b"fixture-private-stderr", data)
        if (self.base / "auth-log-mode").exists():
            self.assertEqual((self.base / "auth-log-mode").read_text(), "0o600")
        return process.returncode, bytes(data)

    def assert_clean(self):
        self.assertEqual(list((self.base / "home/.cache/workspace-login").glob("session-*")), [])
        marker = self.base / "browser-pid"
        if marker.exists():
            os.kill(int(marker.read_text()), 0)
        for p in (self.base / "home/.cache/workspace-login").rglob("*"):
            if p.is_file():
                self.assertNotIn(b"fixture-private-state", p.read_bytes())
                self.assertNotIn(b"fixture-code", p.read_bytes())

    def test_success_uses_real_opener_and_returns_to_terminal(self):
        rc, _ = self.drive("success")
        self.assertEqual(rc, 0)
        self.assertTrue((self.base / "authenticated").exists())
        self.assertTrue((self.base / "browser-started").exists())
        self.assertEqual((self.base / "browser-url").read_text(),
                         "https://claude.com/cai/oauth/authorize?state=fixture-private-state")
        self.assert_clean()

    def test_saved_subscription_skips_login_and_browser(self):
        rc, _ = self.drive("already")
        self.assertEqual(rc, 0)
        self.assertFalse((self.base / "login-started").exists())
        self.assertFalse((self.base / "browser-started").exists())

    def test_manual_code_uses_same_terminal_with_browser_retained(self):
        rc, _ = self.drive("manual", [
            ("若页面给出授权码，回本终端粘贴后按回车。".encode(), b"fixture-code\n"),
        ])
        self.assertEqual(rc, 0)
        self.assert_clean()

    def test_detach_cancels_and_preserves_another_tmux_server(self):
        socket = str(self.base / "other.sock")
        subprocess.run(["tmux", "-S", socket, "new-session", "-d", "-s", "other", "sleep", "60"], check=True)
        try:
            self.env["TMUX"] = socket + ",1,0"
            rc, _ = self.drive("cancel", [(b"http://10.230.0.1:8443", b"\x02d")])
            self.assertEqual(rc, 1)
            self.assertFalse((self.base / "authenticated").exists())
            self.assertEqual(subprocess.run(["tmux", "-S", socket, "has-session", "-t", "other"]).returncode, 0)
            self.assert_clean()
        finally:
            subprocess.run(["tmux", "-S", socket, "kill-server"], check=False)

    def test_sigterm_cleans_authorization_and_preserves_browser(self):
        client = self.launch("cancel")
        deadline = time.monotonic() + 8
        while not (self.base / "browser-started").exists() and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue((self.base / "browser-started").exists())
        client[0].send_signal(signal.SIGTERM)
        rc, _ = self.drive("cancel", client=client)
        self.assertEqual(rc, 1)
        self.assert_clean()

    def test_invalid_authorization_host_does_not_open_browser(self):
        rc, _ = self.drive("bad-url")
        self.assertEqual(rc, 1)
        self.assertFalse((self.base / "browser-started").exists())
        self.assert_clean()

    def test_cli_failure_does_not_report_success(self):
        rc, _ = self.drive("cli-error")
        self.assertEqual(rc, 1)
        self.assert_clean()

    def test_other_credential_source_is_not_overwritten(self):
        rc, _ = self.drive("other-source")
        self.assertEqual(rc, 2)
        self.assertFalse((self.base / "login-started").exists())

    def test_unreadable_status_does_not_start_login_or_leak_stderr(self):
        rc, output = self.drive("bad-status")
        self.assertEqual(rc, 2)
        self.assertFalse((self.base / "login-started").exists())
        self.assertNotIn(b"fixture-private-error", output)


class BrowserInstructions(unittest.TestCase):
    def output(self, config):
        spec = importlib.util.spec_from_file_location("workspace_browser", SOURCE / "workspace-browser.py")
        browser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(browser)
        with tempfile.TemporaryDirectory(prefix="workspace-browser-config-") as value:
            config_path = Path(value) / "browser.json"
            config_path.write_text(json.dumps(config))
            output = io.StringIO()
            with patch.object(browser, "CONFIG", config_path), \
                    patch.object(browser, "ready", return_value=True), \
                    patch.object(browser.Path, "home", return_value=Path(value)), \
                    patch.object(browser.sys, "argv", ["workspace-browser", "status"]), \
                    patch("sys.stdout", output):
                self.assertEqual(browser.main(), 0)
            return output.getvalue()

    def test_legacy_viewer_keeps_wireguard_instructions(self):
        output = self.output({"viewer_url": "http://10.230.0.1:8443/vnc.html"})
        self.assertIn("保持 WireGuard 开启", output)
        self.assertIn("http://10.230.0.1:8443/vnc.html", output)

    def test_vm502_uses_configured_administrator_tunnel_instructions(self):
        output = self.output({
            "viewer_url": "http://127.0.0.1:16081/vnc.html",
            "viewer_access_note": "依赖当前管理员电脑 SSH 通道；不是员工公网登录入口。",
        })
        self.assertIn("依赖当前管理员电脑 SSH 通道", output)
        self.assertIn("不是员工公网登录入口", output)
        self.assertIn("http://127.0.0.1:16081/vnc.html", output)
        self.assertNotIn("WireGuard", output)


if __name__ == "__main__":
    if os.geteuid() == 0:
        raise SystemExit("Run these isolated fixtures as a non-root user.")
    if not shutil.which("tmux"):
        raise SystemExit("Use an approved environment with tmux already installed.")
    unittest.main()
