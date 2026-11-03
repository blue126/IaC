#!/usr/bin/env python3
"""Shared VM-local Claude authorization flow, extracted from the deployed pilot."""
import fcntl
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import time

SELF = Path(__file__).resolve()
LOGIN = Path('/usr/local/bin/workspace-login')
BROWSER_READY = Path('/run/employee-browser/browser-ready')

class FlowError(ValueError):
    """A fixed, user-facing message that contains no subprocess output."""


def read_auth():
    # Reuse the existing helper's validation and subscription-source checks.
    loader = importlib.machinery.SourceFileLoader('workspace_login', str(LOGIN))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    data = module.auth_status()
    return module.subscription_login(data), data.get('authMethod', 'none')


class Flow:
    def __init__(self, cache=None, auth=None):
        self.cache = cache or Path.home() / '.cache/workspace-login-guide'
        self.cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.auth = auth or read_auth
        self.lock = threading.RLock()
        self.runtime = None
        self.state = 'idle'
        self.started = 0
        self.authenticated = False
        self.auth_method = 'none'
        self.checked = 0

    def tmux(self, *args, data=None):
        return subprocess.run(['tmux', '-S', str(self.runtime / 'tmux.sock'), *args],
                              input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=6, check=False)

    def active(self):
        return self.runtime is not None and self.tmux('has-session', '-t', 'guide').returncode == 0

    def check_auth(self):
        try:
            self.authenticated, self.auth_method = self.auth()
            self.checked = time.monotonic()
            return True
        except (OSError, ValueError, subprocess.SubprocessError):
            self.authenticated, self.auth_method = False, 'unknown'
            return False

    def status(self):
        with self.lock:
            if self.state == 'running':
                result = self.runtime / 'result'
                if result.exists():
                    self.state = ('success' if result.read_text() == '0' and
                                  self.check_auth() and self.authenticated else 'failed')
                    self.tmux('kill-server')
                elif time.monotonic() - self.started > 1800:
                    self.cancel()
                    self.state = 'expired'
                elif not self.active():
                    self.state = 'failed'
            elif time.monotonic() - self.checked > 3:
                self.check_auth()
            if self.state == 'success' and not self.authenticated:
                self.state = 'idle'  # A completed flow must not hide later expiry or source changes.
            state = self.state
            if self.auth_method == 'unknown' and state == 'idle':
                state = 'unknown'
            elif self.authenticated and state != 'running':
                state = 'success'
            elif self.auth_method not in ('none', 'claude.ai', 'unknown') and state == 'idle':
                state = 'blocked'
            return {'state': state, 'authenticated': self.authenticated,
                    'viewer_ready': state == 'running' and BROWSER_READY.is_file()}

    def start(self):
        with self.lock:
            if self.status()['state'] == 'running':
                return self.status()
            if not self.check_auth():
                raise FlowError('无法确认 Claude 登录状态，请稍后重试。')
            if self.authenticated:
                self.state = 'success'
                return self.status()
            if self.auth_method not in ('none', 'claude.ai'):
                raise FlowError('当前使用其他认证来源，请联系管理员核对；不会覆盖现有配置。')
            cache = Path.home() / '.cache/workspace-login'
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            with (cache / 'lock').open('a+') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise FlowError('已有登录流程正在运行，请先完成或取消原流程。') from None
            self.clear_runtime()
            self.runtime = Path(tempfile.mkdtemp(prefix='flow-', dir=self.cache))
            config = self.runtime / 'tmux.conf'
            config.write_text('set-option -g history-limit 0\n')
            command = shlex.join([sys.executable, str(SELF), '--worker', str(self.runtime)])
            if self.tmux('-f', str(config), 'new-session', '-d', '-s', 'guide', '-x', '100', '-y', '35',
                         command).returncode:
                self.clear_runtime()
                raise FlowError('无法启动授权，请稍后重试。')
            self.started, self.state = time.monotonic(), 'running'
            return self.status()

    def code(self, value):
        if (not isinstance(value, str) or not 1 <= len(value) <= 4096 or
                any(ord(c) < 33 or ord(c) > 126 for c in value)):
            raise FlowError('请粘贴官方页面提供的单行授权码。')
        with self.lock:
            if self.state != 'running' or not self.active() or not BROWSER_READY.is_file():
                raise FlowError('当前没有等待授权的登录流程。')
            # Secrets go through stdin into this flow's private tmux socket, never argv.
            if self.tmux('load-buffer', '-b', 'auth-code', '-',
                         data=(value + '\n').encode()).returncode:
                raise FlowError('授权码未能提交，请重试。')
            try:
                if self.tmux('paste-buffer', '-d', '-b', 'auth-code', '-t', 'guide').returncode:
                    raise FlowError('授权码未能提交，请重试。')
            finally:
                self.tmux('delete-buffer', '-b', 'auth-code')

    def cancel(self):
        with self.lock:
            if self.runtime is not None:
                if self.active():
                    # Detach the existing helper so its own cleanup runs before teardown.
                    self.tmux('send-keys', '-t', 'guide', 'C-b', 'd')
                    deadline = time.monotonic() + 5
                    while self.active() and time.monotonic() < deadline:
                        time.sleep(.1)
                self.tmux('kill-server')
            self.state = 'cancelled'
            self.clear_runtime()

    def clear_runtime(self):
        if self.runtime is not None:
            import shutil
            shutil.rmtree(self.runtime)
            self.runtime = None

    def close(self):
        self.cancel()


def worker(value):
    runtime = Path(value)
    info = runtime.stat()
    if not runtime.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Invalid private flow directory')
    result = subprocess.run([str(LOGIN)], check=False)
    (runtime / 'result.next').write_text(str(result.returncode))
    (runtime / 'result.next').replace(runtime / 'result')


if __name__ == '__main__':
    os.umask(0o077)
    if os.geteuid() == 0 or len(sys.argv) != 3 or sys.argv[1] != '--worker':
        raise SystemExit('Only the employee-owned authorization worker is supported')
    worker(sys.argv[2])
