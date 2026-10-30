#!/usr/bin/python3
"""Keep the personal browser display on one workspace without restarting apps."""
import argparse
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

NS = 'http://openbox.org/3.4/rc'
ET.register_namespace('', NS)


def tag(name):
    return '{' + NS + '}' + name


def child(parent, name, text=None):
    node = parent.find(tag(name))
    if node is None:
        node = ET.SubElement(parent, tag(name))
    if text is not None:
        node.text = text
    return node


def configure(source, target):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(source.read_bytes(), parser=parser)
    if root.tag != tag('openbox_config'):
        raise ValueError('Unexpected Openbox configuration')
    desktops = child(root, 'desktops')
    child(desktops, 'number', '1')
    child(desktops, 'firstdesk', '1')
    # Wheel events belong to the browser, never desktop switching or window shading.
    for context in root.findall('./' + tag('mouse') + '/' + tag('context')):
        for binding in list(context.findall(tag('mousebind'))):
            if binding.get('button', '').split('-')[-1] in ('Up', 'Down'):
                context.remove(binding)
    apps = child(root, 'applications')
    app = next((n for n in apps.findall(tag('application'))
                if n.get('class') == 'firefox' and n.get('type') == 'normal'), None)
    if app is None:
        app = ET.SubElement(apps, tag('application'), {'class': 'firefox', 'type': 'normal'})
    child(app, 'desktop', '1')
    child(app, 'maximized', 'yes')
    child(app, 'focus', 'yes')
    ET.indent(root, space='  ')
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'
    if target.exists() and target.read_bytes() == data:
        return False
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = target.with_name('rc.xml.before-login-guide')
    if not backup.exists():
        fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(source.read_bytes())
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.chmod(0o600)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def desktop_state(env):
    response = subprocess.run(['xprop', '-root', '_NET_NUMBER_OF_DESKTOPS',
                               '_NET_CURRENT_DESKTOP'], env=env, capture_output=True,
                              text=True, check=True, timeout=5)
    values = {}
    for key in ('_NET_NUMBER_OF_DESKTOPS', '_NET_CURRENT_DESKTOP'):
        match = re.search(r'^' + key + r'\([^\n]*\)\s*=\s*(\d+)\s*$',
                          response.stdout, re.MULTILINE)
        if not match:
            raise ValueError('Cannot read browser workspace state')
        values[key] = int(match[1])
    return values['_NET_NUMBER_OF_DESKTOPS'], values['_NET_CURRENT_DESKTOP']


def apply_policy(changed, env):
    if not changed and desktop_state(env) == (1, 0):
        return False
    subprocess.run(['openbox', '--reconfigure'], env=env, check=True, timeout=10,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Openbox reads the configured desktop count only at startup. Apply the same
    # policy to the live session via EWMH, without restarting the WM or its apps.
    set_live_desktop(env)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if desktop_state(env) == (1, 0):
            return True
        time.sleep(.1)
    raise ValueError('Single browser workspace policy did not take effect')


def set_live_desktop(env):
    class Data(ctypes.Union):
        _fields_ = [('l', ctypes.c_long * 5)]

    class ClientMessage(ctypes.Structure):
        _fields_ = [('type', ctypes.c_int), ('serial', ctypes.c_ulong),
                    ('send_event', ctypes.c_int), ('display', ctypes.c_void_p),
                    ('window', ctypes.c_ulong), ('message_type', ctypes.c_ulong),
                    ('format', ctypes.c_int), ('data', Data)]

    class Event(ctypes.Union):
        _fields_ = [('client', ClientMessage), ('pad', ctypes.c_long * 24)]

    library = ctypes.util.find_library('X11')
    if not library:
        raise ValueError('X11 client library is unavailable')
    x11 = ctypes.CDLL(library)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                              ctypes.c_long, ctypes.POINTER(Event)]
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    # Xlib reads XAUTHORITY from this process, rather than a subprocess env.
    previous = os.environ.get('XAUTHORITY')
    if 'XAUTHORITY' in env:
        os.environ['XAUTHORITY'] = env['XAUTHORITY']
    display = x11.XOpenDisplay(env['DISPLAY'].encode())
    try:
        if not display:
            raise ValueError('Cannot open the personal browser display')
        root = x11.XDefaultRootWindow(display)
        for name, value in ((b'_NET_CURRENT_DESKTOP', 0), (b'_NET_NUMBER_OF_DESKTOPS', 1)):
            event = Event()
            event.client.type = 33
            event.client.display = display
            event.client.window = root
            event.client.message_type = x11.XInternAtom(display, name, 0)
            event.client.format = 32
            event.client.data.l[0] = value
            if not x11.XSendEvent(display, root, 0, (1 << 20) | (1 << 19), ctypes.byref(event)):
                raise ValueError('Cannot apply the single browser workspace')
        x11.XSync(display, 0)
    finally:
        if display:
            x11.XCloseDisplay(display)
        if previous is None:
            os.environ.pop('XAUTHORITY', None)
        else:
            os.environ['XAUTHORITY'] = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if os.geteuid() == 0 or Path.home() != Path('/home/employee'):
        raise ValueError('Run as the personal employee account')
    os.umask(0o077)
    env = dict(os.environ, DISPLAY=':99', XAUTHORITY='/run/employee-browser/Xauthority')
    target = Path.home() / '.config/openbox/rc.xml'
    if args.verify:
        if desktop_state(env) != (1, 0):
            raise ValueError('Browser workspace policy is not active')
        print('PASS single browser workspace; no desktop input sent')
        return
    changed = configure(target if target.exists() else Path('/etc/xdg/openbox/rc.xml'), target)
    applied = False
    if Path(env['XAUTHORITY']).is_file():
        applied = apply_policy(changed, env)
    print(json.dumps({'changed': changed or applied, 'live_applied': applied}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, ET.ParseError, subprocess.SubprocessError):
        print('Browser workspace configuration failed; personal browser was not restarted.')
        raise SystemExit(1)
