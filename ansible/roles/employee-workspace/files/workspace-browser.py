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
DESKTOP_CONTROL = Path("/usr/local/bin/workspace-desktop")
RUNTIME = Path("/run/employee-browser")
CONFIG = Path("/etc/employee-workspace-browser.json")
DESKTOP_CONFIG = Path("/etc/employee-workspace-desktop.json")

def systemctl(*args, check=True):
    return subprocess.run(["sudo", "-n", "systemctl", *args, UNIT], check=check,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)

def active():
    return systemctl("is-active", "--quiet", check=False).returncode == 0

def ready():
    return active() and (RUNTIME / "browser-ready").is_file()

class Unavailable(RuntimeError):
    def __init__(self, message, code=69):
        super().__init__(message)
        self.code = code


def configuration():
    config = json.loads(CONFIG.read_text())
    mode = config.get('mode', 'legacy-novnc')
    if mode not in ('legacy-novnc', 'kasmvnc'):
        raise ValueError('未知的显式浏览器后端。')
    if mode == 'kasmvnc':
        desktop = json.loads(DESKTOP_CONFIG.read_text())
        config['desktop_viewer_url'] = desktop['viewer_url']
        parsed = urlsplit(config['desktop_viewer_url'])
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.port != 8443
                or parsed.path != '/' or parsed.query or parsed.fragment
                or parsed.username is not None or parsed.password is not None):
            raise ValueError('Kasm 浏览器入口配置无效。')
    return config


def kasm():
    return configuration().get('mode', 'legacy-novnc') == 'kasmvnc'


def desktop_start():
    result = subprocess.run([str(DESKTOP_CONTROL), 'start'], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=50)
    if result.returncode:
        raise Unavailable('桌面维护中。' if result.returncode == 75 else '桌面尚未就绪。',
                          75 if result.returncode == 75 else 69)


def control_open(url):
    request = {'version': 1, 'action': 'open', 'url': url}
    data = (json.dumps(request, ensure_ascii=False) + '\n').encode('utf-8')
    if len(data) > 8192:
        raise Unavailable('网页地址过长。', 64)
    ensure_started()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(25)
            peer.connect(str(RUNTIME / 'control.sock'))
            peer.sendall(data)
            response = bytearray()
            while b'\n' not in response and len(response) <= 8192:
                chunk = peer.recv(8193 - len(response))
                if not chunk:
                    break
                response.extend(chunk)
        result = json.loads(response.decode('utf-8'))
        if result == {'version': 1, 'status': 'opened', 'exit_code': 0}:
            return
        if result == {'version': 1, 'status': 'rejected', 'exit_code': 64}:
            # Preserve the external transition status when maintenance raced open.
            desktop_start()
            raise Unavailable('网页请求被拒绝。', 64)
    except (OSError, ValueError, UnicodeError):
        raise Unavailable('浏览器控制连接不可用。') from None
    raise Unavailable('浏览器控制响应无效。')


def kasm_status():
    result = subprocess.run(['/usr/bin/systemctl', 'show', '--property=ActiveState',
                             '--value', UNIT], capture_output=True, text=True, timeout=30)
    if result.returncode:
        print('浏览器状态不可用，请重试或联系管理员。')
        return 69
    state = result.stdout.strip()
    if state == 'inactive':
        print('浏览器已停止。使用 workspace-browser start 启动。')
        return 3
    if state == 'failed':
        print('浏览器启动失败，请联系管理员；个人配置保留。')
        return 1
    if state != 'active' or not (RUNTIME / 'browser-ready').is_file() or not (RUNTIME / 'control.sock').is_socket():
        print('浏览器尚未就绪，请稍后运行 workspace-browser status。')
        return 69
    return None


def ensure_started():
    if kasm():
        # Always take the established mode/lock/marker path, including active opens.
        desktop_start()
        result = systemctl('start', check=False)
        if result.returncode:
            desktop_start()
            raise Unavailable('浏览器尚未就绪。')
        if not ready() or not (RUNTIME / 'control.sock').is_socket():
            raise Unavailable('浏览器尚未就绪。')
        return
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
    if kasm():
        control_open(url)
        return
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
    configuration()
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
            if kasm():
                status = kasm_status()
                if status is not None:
                    return status
            elif not ready():
                print("浏览器未运行。使用 workspace-browser start 启动。")
                return 1
        elif args.action == "open":
            open_url(args.url)
        else:
            ensure_started()
        print(configuration().get("viewer_access_note", "浏览器正在运行。保持 WireGuard 开启，在本机浏览器打开："))
        print(configuration().get("desktop_viewer_url", configuration()["viewer_url"]))
        print("关闭本机网页或 SSH 不会关闭 VM 浏览器；结束使用请运行 workspace-browser stop。")
        return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # Avoid exporting URLs, profile contents or subprocess argument lists.
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "操作未完成，请重试或联系管理员。"
        print(message, file=sys.stderr)
        raise SystemExit(exc.code if isinstance(exc, Unavailable) else 2)
