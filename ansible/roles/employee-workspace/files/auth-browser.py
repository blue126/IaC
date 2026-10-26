#!/usr/bin/python3
"""Run this employee's VM-local Firefox and private display."""
import ipaddress
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

def stop(_signal, _frame):
    raise KeyboardInterrupt

def run(runtime, url, persistent=False):
    os.umask(0o077)
    info = runtime.stat()
    if os.geteuid() == 0 or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Expected private employee runtime")
    config = json.loads(Path("/etc/employee-workspace-browser.json").read_text())
    address = str(ipaddress.IPv4Address(config["bind_address"]))
    profile = Path.home() / ".local/share/employee-workspace/firefox"
    profile.mkdir(parents=True, mode=0o700, exist_ok=True)
    profile.chmod(0o700)
    authority = runtime / "Xauthority"
    authority.touch(mode=0o600)
    env = dict(os.environ, DISPLAY=":99", XAUTHORITY=str(authority),
               MOZ_ENABLE_WAYLAND="0", XDG_RUNTIME_DIR=str(runtime))
    subprocess.run(["xauth", "-f", str(authority), "add", ":99", ".", secrets.token_hex(16)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes = []
    def start(args):
        process = subprocess.Popen(args, env=env, start_new_session=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(process)
        return process
    def wait_port(host, port):
        for _ in range(60):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("Authorization component stopped")
            try:
                with socket.create_connection((host, port), timeout=.2):
                    return
            except OSError:
                time.sleep(.1)
        raise RuntimeError("Authorization component not ready")
    try:
        start(["Xvfb", ":99", "-screen", "0", "1366x768x24", "-nolisten", "tcp",
               "-auth", str(authority)])
        for _ in range(60):
            if Path("/tmp/.X11-unix/X99").exists():
                break
            if processes[0].poll() is not None:
                raise RuntimeError("Virtual display unavailable")
            time.sleep(.1)
        start(["openbox", "--sm-disable"])
        start(["x11vnc", "-display", ":99", "-auth", str(authority), "-localhost",
               "-no6", "-rfbport", "5901", "-forever", "-shared", "-nopw", "-noxdamage",
               "-norc", "-xkb"])
        wait_port("127.0.0.1", 5901)
        start(["websockify", "--web=/usr/share/novnc", address + ":6081", "127.0.0.1:5901"])
        wait_port(address, 6081)
        if persistent:
            (runtime / "browser-environment.json").write_text(json.dumps({
                key: env[key] for key in ("DBUS_SESSION_BUS_ADDRESS",) if key in env
            }))
        browser = start(["firefox", "--new-instance" if persistent else "--no-remote", "--profile", str(profile),
                         "--width", "1366", "--height", "768", url])
        (runtime / "browser-ready").write_text(config["viewer_url"])
        deadline = None if persistent else time.monotonic() + 1800
        while browser.poll() is None and (deadline is None or time.monotonic() < deadline):
            if any(p.poll() is not None for p in processes[:-1]):
                raise RuntimeError("Authorization component stopped")
            time.sleep(.2)
        return 0 if browser.poll() == 0 else 1
    finally:
        # Kill only groups created by this invocation; never touch other browsers.
        for process in reversed(processes):
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in reversed(processes):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()

if __name__ == "__main__":
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    try:
        raise SystemExit(run(Path(sys.argv[1]), sys.argv[2], "--persistent" in sys.argv[3:]))
    except KeyboardInterrupt:
        raise SystemExit(1)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("图形授权窗口未能启动或已关闭，请重新运行 workspace-login。", file=sys.stderr)
        raise SystemExit(1)
