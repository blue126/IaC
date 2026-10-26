#!/usr/bin/python3
"""Run personal Claude authorization with a VM-local browser in one terminal."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

SELF = Path(__file__).resolve()
OPENER = SELF.parent.parent / "lib/employee-workspace/open-auth-browser"
SESSION = "login"
BROWSER_CONTROL = SELF.parent / "workspace-browser"


def tmux(runtime, *args, check=True):
    return subprocess.run(
        ["tmux", "-S", str(runtime / "tmux.sock"), *args],
        check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def require_runtime(value):
    runtime = Path(value)
    info = runtime.stat()
    if not runtime.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Invalid private login directory")
    return runtime


def auth_status():
    result = subprocess.run(
        ["claude", "auth", "status"], capture_output=True, text=True, timeout=20,
    )
    data = json.loads(result.stdout)
    if (result.returncode not in (0, 1) or not isinstance(data.get("loggedIn"), bool)
            or (result.returncode == 0) != data["loggedIn"]):
        raise ValueError("Cannot read authentication status")
    return data


def subscription_login(data):
    return data["loggedIn"] and data.get("authMethod") == "claude.ai"


def browser_running():
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            if item.stat().st_uid == os.getuid() and (item / "comm").read_text().strip() == "browsh":
                return True
        except (OSError, ProcessLookupError):
            continue
    return False


def close_browser(runtime):
    tmux(runtime, "send-keys", "-t", SESSION + ":browser", "C-c", check=False)
    for _ in range(80):
        if tmux(runtime, "list-panes", "-t", SESSION + ":browser", check=False).returncode:
            break
        time.sleep(0.1)


def open_browser(url):
    runtime = require_runtime(os.environ["WORKSPACE_LOGIN_RUNTIME"])
    parsed = urlsplit(url)
    accepted = {
        ("claude.com", "/cai/oauth/authorize"),
        ("claude.ai", "/oauth/authorize"),
    }
    if (parsed.scheme != "https" or (parsed.hostname, parsed.path) not in accepted
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        (runtime / "browser-error").touch(mode=0o600)
        return 1
    try:
        # Prevent duplicate opener calls from launching a second browser instance.
        marker = runtime / "browser-opened"
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        return 0
    try:
        tmux(runtime, "new-window", "-t", SESSION, "-n", "browser", "-d",
             str(SELF), "--browser", str(runtime), url)
    except subprocess.CalledProcessError:
        (runtime / "browser-error").touch(mode=0o600)
        return 1
    return 0


def browser_worker(value, url):
    runtime = require_runtime(value)
    for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        result = subprocess.run([str(BROWSER_CONTROL), "open", url],
                                capture_output=True, text=True, timeout=55)
        if result.returncode:
            (runtime / "browser-error").touch(mode=0o600)
            return 1
        # The browser service belongs to the employee, not this authorization flow.
        lines = [line for line in result.stdout.splitlines() if line.startswith("http://")]
        if not lines:
            (runtime / "browser-error").touch(mode=0o600)
            return 1
        (runtime / "browser-ready").write_text(lines[0])
        while True:
            time.sleep(.2)
    except KeyboardInterrupt:
        return 0
    except (OSError, subprocess.SubprocessError):
        (runtime / "browser-error").touch(mode=0o600)
        return 1


def login_worker(value):
    runtime = require_runtime(value)
    env = dict(os.environ, BROWSER=str(OPENER), WORKSPACE_LOGIN_RUNTIME=str(runtime))
    state = "failed"
    process = None
    try:
        print("正在启动 VM 内图形 Firefox。请保留本终端；取消可按 Ctrl+B，松开后按 d。", flush=True)
        process = subprocess.Popen(["claude", "auth", "login"], env=env)
        deadline = time.monotonic() + 45
        expires = time.monotonic() + 1800
        shown = False
        while process.poll() is None:
            if not shown and (runtime / "browser-ready").exists():
                print("\n请在本机浏览器打开：" + (runtime / "browser-ready").read_text().strip(), flush=True)
                print("画面中的 Firefox 在你的澳洲 VM；在画面内完成登录。若页面给出授权码，回本终端粘贴。", flush=True)
                shown = True
            if time.monotonic() > expires:
                print("授权超过 30 分钟，本次 Claude 授权已取消，请重新运行 workspace-login；日常浏览器继续保留。", flush=True)
                break
            if (runtime / "browser-error").exists():
                print("无法自动打开本次授权页面，请重新运行 workspace-login。", flush=True)
                break
            if time.monotonic() > deadline and not (runtime / "browser-opened").exists():
                print("未能取得浏览器打开请求，本次登录已停止；请反馈此提示。", flush=True)
                break
            time.sleep(0.2)
        else:
            if process.returncode == 0 and subscription_login(auth_status()):
                state = "success"
    except KeyboardInterrupt:
        state = "cancelled"
    except (OSError, ValueError, subprocess.SubprocessError):
        state = "failed"
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        (runtime / "result").write_text(state)
        close_browser(runtime)
        tmux(runtime, "kill-session", "-t", SESSION, check=False)
    return 0 if state == "success" else 1


def check_dependencies():
    return all(shutil.which(name) for name in ("claude", "firefox", "tmux", "Xvfb", "xauth", "x11vnc", "websockify", "openbox", "dbus-run-session")) and OPENER.is_file() and BROWSER_CONTROL.is_file()


def interrupted(_signum, _frame):
    raise KeyboardInterrupt


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--open-url":
        return open_browser(sys.argv[-1])
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        return login_worker(sys.argv[2])
    if len(sys.argv) > 1 and sys.argv[1] == "--browser":
        return browser_worker(sys.argv[2], sys.argv[3])

    parser = argparse.ArgumentParser(description="启动 VM 图形浏览器完成本人 Claude 授权。")
    parser.add_argument("--check", action="store_true", help="仅检查安装，不读取认证状态或开始登录")
    args = parser.parse_args()
    if not check_dependencies():
        print("登录助手缺少必要文件或命令，请联系管理员。", file=sys.stderr)
        return 2
    if args.check:
        print("workspace-login: ready")
        return 0
    if os.geteuid() == 0:
        print("请以 employee 身份运行 workspace-login，不要使用 sudo。", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("请在交互式 SSH 终端运行 workspace-login。", file=sys.stderr)
        return 2

    os.umask(0o077)
    cache = Path.home() / ".cache/workspace-login"
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (cache / "lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("已有登录流程正在运行，请返回原来的窗口。", file=sys.stderr)
            return 2
        try:
            current = auth_status()
        except (OSError, ValueError, subprocess.SubprocessError):
            print("无法确认认证状态，请自行运行 claude auth status --text 查看错误后重试。", file=sys.stderr)
            return 2
        if subscription_login(current):
            print("已保存 Claude 订阅登录，无需再次授权。")
            return subprocess.call(["claude", "auth", "status", "--text"])
        if current.get("authMethod") not in ("none", "claude.ai"):
            print("当前使用其他认证来源；请先自行检查 claude auth status --text，助手不会覆盖它。", file=sys.stderr)
            return 2
        if browser_running():
            print("已有 Browsh 在运行，请先在旧浏览器按 Ctrl+Q 退出，再运行 workspace-login。", file=sys.stderr)
            return 2

        for signum in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, interrupted)
        with tempfile.TemporaryDirectory(prefix="session-", dir=cache) as value:
            runtime = Path(value)
            config = runtime / "tmux.conf"
            config.write_text("set-option -g history-limit 0\nset-option -g status-right 'Cancel: Ctrl+B then d'\n")
            env = dict(os.environ)
            env.pop("TMUX", None)
            size = shutil.get_terminal_size((100, 30))
            success = False
            try:
                subprocess.run(
                    ["tmux", "-S", str(runtime / "tmux.sock"), "-f", str(config),
                     "new-session", "-d", "-s", SESSION, "-n", "auth",
                     "-x", str(size.columns), "-y", str(size.lines),
                     str(SELF), "--worker", str(runtime)],
                    env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                subprocess.run(
                    ["tmux", "-S", str(runtime / "tmux.sock"), "attach-session", "-t", SESSION],
                    env=env, check=False,
                )
                success = (runtime / "result").exists() and (runtime / "result").read_text() == "success"
            except KeyboardInterrupt:
                pass
            except (OSError, subprocess.SubprocessError):
                print("登录会话未能正常启动。", file=sys.stderr)
            finally:
                close_browser(runtime)
                tmux(runtime, "kill-server", check=False)
            if success:
                print("Claude 登录成功。")
                return subprocess.call(["claude", "auth", "status", "--text"])
            print("登录未完成或已取消。可重新运行 workspace-login；日常浏览器继续保留，关闭请用 workspace-browser stop。", file=sys.stderr)
            return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, ValueError, OSError):
        print("登录助手无法完成当前操作，请重试或反馈错误。", file=sys.stderr)
        raise SystemExit(2)
