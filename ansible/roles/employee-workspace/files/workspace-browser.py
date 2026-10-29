#!/usr/bin/python3
"""Control the employee browser independently of SSH and Claude authorization."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

UNIT = "employee-browser.service"
RUNTIME = Path("/run/employee-browser")
CONFIG = Path("/etc/employee-workspace-browser.json")

def systemctl(*args, check=True):
    return subprocess.run(["sudo", "-n", "systemctl", *args, UNIT], check=check,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

def active():
    return systemctl("is-active", "--quiet", check=False).returncode == 0

def ready():
    return active() and (RUNTIME / "browser-ready").is_file()

def configuration():
    return json.loads(CONFIG.read_text())

def ensure_started():
    if not active():
        # An older temporary authorization session may still own the display/profile.
        try:
            with socket.create_connection((configuration()["bind_address"], 6081), timeout=.3):
                raise RuntimeError("旧图形会话仍在运行，请先完成或取消旧登录，再启动日常浏览器。")
        except (ConnectionRefusedError, TimeoutError, OSError):
            pass
        systemctl("start")
    for _ in range(150):
        if ready():
            return
        if not active():
            raise RuntimeError("浏览器未能启动，请联系管理员；助手不会删除个人配置。")
        time.sleep(.1)
    raise RuntimeError("浏览器启动尚未就绪，请运行 workspace-browser status 查看状态。")

def open_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password):
        raise ValueError("请提供完整的 http:// 或 https:// 地址。")
    # Parse the port before invoking Firefox; malformed URLs fail without starting it.
    parsed.port
    ensure_started()
    profile = Path.home() / ".local/share/employee-workspace/firefox"
    env = dict(os.environ, DISPLAY=":99", XAUTHORITY=str(RUNTIME / "Xauthority"),
               MOZ_ENABLE_WAYLAND="0", XDG_RUNTIME_DIR=str(RUNTIME))
    env.update(json.loads((RUNTIME / "browser-environment.json").read_text()))
    subprocess.run(["firefox", "--profile", str(profile), "--new-tab", url],
                   env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=20)

def main():
    parser = argparse.ArgumentParser(description="启动、查看和关闭自己的澳洲 VM 浏览器。")
    parser.add_argument("action", choices=("start", "stop", "status", "open"))
    parser.add_argument("url", nargs="?")
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise ValueError("请以 employee 身份运行，不要使用 sudo。")
    if (args.action == "open") != (args.url is not None):
        parser.error("只有 open 操作需要一个网页地址。")
    os.umask(0o077)
    cache = Path.home() / ".cache/workspace-browser"
    cache.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (cache / "lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == "stop":
            systemctl("stop")
            print("浏览器已关闭，个人配置与已保存登录态保留。")
            return 0
        if args.action == "status":
            if not ready():
                print("浏览器未运行。使用 workspace-browser start 启动。")
                return 1
        elif args.action == "open":
            open_url(args.url)
        else:
            ensure_started()
        config = configuration()
        print(config.get("viewer_access_note", "浏览器正在运行。保持 WireGuard 开启，在本机浏览器打开："))
        print(config["viewer_url"])
        print("关闭本机网页或 SSH 不会关闭 VM 浏览器；结束使用请运行 workspace-browser stop。")
        return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # Avoid exporting URLs, profile contents or subprocess argument lists.
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "操作未完成，请重试或联系管理员。"
        print(message, file=sys.stderr)
        raise SystemExit(2)
