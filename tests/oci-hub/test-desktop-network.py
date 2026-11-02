#!/usr/bin/env python3
"""Explicit, synthetic OCI desktop TLS/WSS exercise; never install dependencies."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time
import types

sys.dont_write_bytecode = True
PIN = '73d701ef560d9ce447fccd5c8d4f4f4c2d9fcc604f1973349de0c7859eb0baf2'
TARGET = '10.234.0.2'
SECRET_MARKERS = ()
SECRET_OBSERVATIONS = {}
SOURCES = ('tests/oci-hub/test-desktop-network.py', 'tests/oci-hub/test-network.py',
           'tests/oci-hub/test-offline.py', 'tests/oci-hub/test-desktop-trust.py',
           'scripts/oci-hub/boundary.py',
           'ansible/roles/employee-workspace/files/login-guide.py',
           'ansible/roles/employee-workspace/files/desktop-service.py',
           'ansible/roles/employee-workspace/files/desktop-contract.py',
           'ansible/roles/oci-hub-spoke/templates/desktop.conf.j2')



def websocket_request_shape(data, expected_authorization=None):
    """Describe a synthetic handshake without exporting keys or authentication."""
    import base64
    import re
    import json
    head, separator, _ = bytes(data[:16384]).partition(b'\r\n\r\n')
    lines = head.split(b'\r\n')
    start = lines[0].decode('ascii', 'replace').split(' ') if lines else []
    headers = {}
    malformed = 0
    for line in lines[1:]:
        key, colon, value = line.partition(b':')
        if not colon:
            malformed += 1
            continue
        headers.setdefault(key.decode('ascii', 'replace').lower(), []).append(value.strip().decode('ascii', 'replace'))
    allowed = ('host', 'origin', 'sec-websocket-origin', 'sec-websocket-version',
               'sec-websocket-protocol', 'upgrade', 'connection')
    result = {'method': start[0][:16] if start else '',
              'path': start[1][:256] if len(start)>1 else '',
              'http_version': start[2][:16] if len(start)>2 else '',
              'crlf': {'header_terminated': bool(separator),
                       'bare_linebreak': b'\r' in head.replace(b'\r\n', b'') or b'\n' in head.replace(b'\r\n', b''),
                       'malformed_header_count': malformed, 'request_line_fields': len(start)},
              'headers': {key: [value[:256] for value in headers.get(key, [])[:4]] for key in allowed}}
    keys = headers.get('sec-websocket-key', [])
    key = keys[0] if len(keys)==1 else ''
    try:
        decoded = len(base64.b64decode(key, validate=True)) if len(key)<=256 else None
    except ValueError:
        decoded = None
    result['websocket_key'] = {'count': len(keys), 'length': len(key), 'decoded_length': decoded}
    auth = headers.get('authorization', [])
    result['authorization'] = {'present': bool(auth), 'matches_material': bool(expected_authorization) and auth == [expected_authorization]}
    # Even allowlisted fields must never reflect the synthetic credential.
    serialized = json.dumps(result)
    if expected_authorization:
        values = [expected_authorization, expected_authorization.partition(' ')[2]]
        try:
            credentials = base64.b64decode(values[1], validate=True).decode()
            values += [credentials, credentials.partition(':')[2]]
        except (ValueError, UnicodeError):
            pass
        for secret in values:
            if secret:
                serialized = serialized.replace(secret, '[redacted synthetic secret]')
    return json.loads(serialized)


def websocket_response_shape(data, expected_authorization=None):
    """Record fixed response fields and at most 512 redacted body characters."""
    import base64
    import re
    header, separator, body = bytes(data[:16384]).partition(b'\r\n\r\n')
    lines = header.decode('ascii', 'replace').split('\r\n')
    first = lines[0].split(' ') if lines else []
    headers = {}
    for line in lines[1:]:
        key, colon, value = line.partition(':')
        if colon: headers[key.lower()] = value.strip()
    text = body[:1024].decode('utf-8', 'replace')
    values = []
    if expected_authorization:
        values = [expected_authorization, expected_authorization.partition(' ')[2]]
        try:
            credentials = base64.b64decode(values[1], validate=True).decode()
            values += [credentials, credentials.partition(':')[2]]
        except (ValueError, UnicodeError):
            pass
    for secret in values:
        if secret: text = text.replace(secret, '[redacted synthetic secret]')
    text = re.sub(r'(?i)Basic\s+[A-Za-z0-9+/=]+', 'Basic [redacted]', text)
    text = ''.join(c for c in text if c in '\n\r\t' or 32 <= ord(c) < 127)[:512]
    return {'status': int(first[1]) if len(first)>1 and first[1].isdigit() else 0,
            'header_terminated': bool(separator),
            'content_type': headers.get('content-type', '')[:128],
            'content_length': headers.get('content-length', '')[:16] if headers.get('content-length', '').isdigit() else None,
            'authentication_challenge': 'www-authenticate' in headers,
            'websocket_protocol': headers.get('sec-websocket-protocol', '')[:128],
            'body_bytes_observed': len(body), 'body_sample': text,
            'body_truncated': len(body)>1024 or len(text)>=512}

def need(ok, message):
    if not ok:
        raise ValueError(message)


def command(args, data=None, check=True, timeout=30):
    result = subprocess.run(list(map(str, args)), input=data, text=True,
                            capture_output=True, timeout=timeout)
    # Commands can contain synthetic secrets; never echo argv, stdin or stderr.
    need(not check or result.returncode == 0,
         'Operation failed: '+Path(str(args[0])).name+' exit='+str(result.returncode))
    return result


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def private_bytes(path):
    data = path.read_bytes()
    need(hashlib.sha256(data).hexdigest() == PIN, 'Private helper digest mismatch')
    return data


def load_private(path):
    data = private_bytes(path)
    module = types.ModuleType('private_probe')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def observe_secrets(scope, value):
    if not SECRET_MARKERS:
        return True
    data = value.encode() if isinstance(value, str) else value
    absent = not any(marker in data for marker in SECRET_MARKERS)
    observation = SECRET_OBSERVATIONS.setdefault(scope, {'checked_buffers': 0, 'secret_absent': True})
    observation['checked_buffers'] += 1
    observation['secret_absent'] &= absent
    return absent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(args):
    need(sys.platform == 'linux' and os.geteuid() == 0, 'Linux root required')
    need(args.helper_sha256 == PIN, 'Private helper digest mismatch')
    private_bytes(args.helper)
    need(args.repo.is_absolute() and args.repo.is_dir(), 'Explicit absolute repository required')
    need(args.run_root.is_absolute() and args.run_root.parent == Path('/run') and
         args.run_root.name.startswith('vm502-story10-'), 'Task-specific /run root required')
    for path in (args.run_root, Path(str(args.run_root)+'-evidence')):
        need(not path.exists() and not path.is_symlink(), 'Output path conflict')
    for part in (args.run_root.parent, *args.run_root.parent.parents):
        need(not part.is_symlink(), 'Symlink runtime parent rejected')
    for binary in ('ip', 'nft', 'sysctl', 'systemd-run', 'systemctl', 'openssl',
                   'Xkasmvnc', 'xfce4-session', 'dbus-daemon', 'firefox', 'xauth',
                   'xprop', 'kasmvncpasswd', 'nginx', 'runuser', 'dpkg-query'):
        need(shutil.which(binary), 'Missing prerequisite: '+binary)
    import jinja2
    release = Path('/etc/os-release').read_text()
    need('ID=ubuntu' in release and 'VERSION_ID="26.04"' in release and
         os.uname().machine == 'x86_64', 'Approved Ubuntu 26.04 x86_64 environment required')
    caps = re.search(r'^CapEff:\s*([0-9a-f]+)$', Path('/proc/self/status').read_text(), re.M)
    need(caps and all(int(caps[1], 16) & (1 << bit) for bit in (12, 21)),
         'CAP_NET_ADMIN and CAP_SYS_ADMIN required')
    owner = pwd.getpwnam('employee')
    need(owner.pw_uid != 0, 'Unprivileged employee account required')
    need(Path('/usr/share/kasmvnc/www/index.html').is_file(), 'KasmVNC assets required')
    need(Path('/usr/lib/firefox/distribution').is_dir() and
         not Path('/usr/lib/firefox/distribution').is_symlink(), 'Firefox distribution mount point required')
    need(Path('/etc/oci-hub').is_dir() and not Path('/etc/oci-hub').is_symlink(),
         'Existing non-symlink OCI material mount point required')
    need(not Path('/tmp/.X11-unix/X98').exists(), 'X98 conflict')
    need(command(['systemctl', 'is-system-running'], check=False).stdout.strip() in
         ('running', 'degraded'), 'Systemd runtime required')
    versions = {}
    for name, argv in {'nginx': ['nginx', '-v'], 'firefox': ['firefox', '--version'],
                       'openssl': ['openssl', 'version'],
                       'xfce': ['dpkg-query', '-W', '-f=${Version}', 'xfce4'],
                       'xfce4-session': ['dpkg-query', '-W', '-f=${Version}', 'xfce4-session'],
                       'ip': ['ip', '-Version'], 'nft': ['nft', '--version'],
                       'systemd': ['systemctl', '--version'], 'kasm': ['Xkasmvnc', '-version']}.items():
        result = command(argv, check=False)
        versions[name] = (result.stdout+result.stderr).strip()[:600]
    for name, expected in {'nginx': '1.28.3', 'firefox': '159', 'xfce': '4.20.1', 'kasm': '1.5.0'}.items():
        need(expected in versions[name], 'Approved version mismatch: '+name)
    manifest_path = args.repo/'source-manifest.json'
    need(manifest_path.is_file() and not manifest_path.is_symlink(), 'Payload source-manifest.json required')
    manifest = json.loads(manifest_path.read_text())
    need(re.fullmatch(r'[0-9a-f]{40}', manifest.get('baseline', '')), 'Manifest baseline required')
    sources = {p: sha(args.repo/p) for p in SOURCES}
    need(manifest.get('files') == sources and manifest.get('helper_sha256') == PIN,
         'Payload manifest input mismatch')
    return {'status': 'preflight-passed', 'runtime': 'not-executed',
            'os': os.uname().sysname, 'architecture': os.uname().machine,
            'os_release_sha256': sha(Path('/etc/os-release')),
            'versions': versions, 'jinja2': jinja2.__version__,
            'helper_sha256': PIN, 'sources': sources,
            'baseline': manifest['baseline'], 'payload_revision': manifest.get('revision'),
            'manifest_sha256': sha(manifest_path),
            'write_scope': {'runtime': str(args.run_root),
                            'evidence': str(args.run_root)+'-evidence',
                            'namespaces_units_veth': 'generated task-exclusive s10 prefix',
                            'display': ':98; synthetic Xauthority only'},
            'target': TARGET, 'device': '10.235.0.2', 'uid': os.geteuid(),
            'network': 'existing veth fixture; not real OCI WireGuard'}



def nginx_temp_metadata():
    """Inspect directory identities only; never open cache files or follow links."""
    values = {}
    def inspect(path, depth):
        try:
            info = path.lstat()
        except FileNotFoundError:
            values[str(path)] = {'exists': False}
            return
        values[str(path)] = {'exists': True, 'uid': info.st_uid, 'gid': info.st_gid,
                             'mode': stat.S_IMODE(info.st_mode), 'inode': info.st_ino}
        if depth == 0 or not stat.S_ISDIR(info.st_mode):
            return
        # Nginx hash levels use short hexadecimal directory names. Temporary
        # cache filenames and their contents are intentionally outside this snapshot.
        with os.scandir(path) as entries:
            children = sorted(entry.name for entry in entries
                              if re.fullmatch(r'[0-9a-f]{1,2}', entry.name)
                              and (entry.is_dir(follow_symlinks=False) or entry.is_symlink()))
        for name in children:
            inspect(path/name, depth-1)
    inspect(Path('/var/lib/nginx'), 0)
    for name in ('body', 'proxy', 'fastcgi', 'uwsgi', 'scgi'):
        inspect(Path('/var/lib/nginx')/name, 3)
    return values


def metadata(repo):
    """Read only non-secret host network and service metadata."""
    commands = {'links': ['ip', '-j', 'link'], 'addresses': ['ip', '-j', 'address'],
                'routes': ['ip', '-j', 'route', 'show', 'table', 'all'],
                'nft': ['nft', '-j', 'list', 'ruleset'], 'netns': ['ip', 'netns', 'list'],
                'services': ['systemctl', 'show', 'employee-browser.service',
                             'employee-desktop.service', 'nginx.service',
                             '-p', 'ActiveState', '-p', 'SubState', '-p', 'UnitFileState']}
    boundary = load('metadata_boundary', repo/'scripts/oci-hub/boundary.py')
    values = {}
    for key, argv in commands.items():
        value = command(argv).stdout
        if key == 'nft':
            value = json.dumps(boundary.canonical(json.loads(value)), sort_keys=True)
        values[key] = hashlib.sha256(value.encode()).hexdigest()
    values['nginx_global_temp_directories'] = nginx_temp_metadata()
    return values



def nginx_errors(path):
    """Keep only a bounded, redacted tail of this task's synthetic nginx log."""
    if not path.is_file() or path.is_symlink():
        return {'available': False}
    with path.open('rb') as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell()-8192))
        raw = stream.read(8192)
        observe_secrets('nginx_log', raw)
        value = raw.decode('utf-8', errors='replace')
    value = re.sub(r'(?s)-----BEGIN .*?-----END [^-]+-----', '[redacted key material]', value)
    lines = []
    for line in value.splitlines():
        if not re.match(r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} \[', line):
            lines.append('[redacted non-nginx log line]')
            continue
        if re.search(r'authorization|password|private.?key|\bkey\b|\bbasic\s|\bbearer\s', line, re.I):
            lines.append('[redacted sensitive log line]')
        else:
            lines.append(re.sub(r'[A-Za-z0-9+/=_-]{32,}', '[redacted token]', line))
    return {'available': True, 'tail': '\n'.join(lines)[-4000:]}


def certificate(root, label, issuer=None, san=None):
    key, cert = root/(label+'.key'), root/(label+'.crt')
    if issuer is None:
        config = root/(label+'.cnf')
        config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ca\n'
                          '[dn]\nCN=synthetic-'+label+'\n[ca]\n'
                          'basicConstraints=critical,CA:TRUE\n'
                          'keyUsage=critical,keyCertSign,cRLSign\n'
                          'subjectKeyIdentifier=hash\n'
                          'authorityKeyIdentifier=keyid:always\n')
        command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                 '-config', config, '-keyout', key, '-out', cert])
    else:
        csr = root/(label+'.csr')
        command(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes',
                 '-subj', '/CN=synthetic-'+label, '-keyout', key, '-out', csr])
        ext = root/(label+'.ext')
        ext.write_text('basicConstraints=critical,CA:FALSE\n'
                       'keyUsage=critical,digitalSignature,keyEncipherment\n'
                       'subjectKeyIdentifier=hash\n'
                       'authorityKeyIdentifier=keyid:always\n'
                       'subjectAltName='+san+'\nextendedKeyUsage=serverAuth\n')
        command(['openssl', 'x509', '-req', '-in', csr, '-CA', root/(issuer+'.crt'),
                 '-CAkey', root/(issuer+'.key'), '-set_serial', str(secrets.randbits(120)),
                 '-days', '1', '-extfile', ext, '-out', cert])
    return cert, key


# The worker has no production paths or control sockets. Its entire HOME is synthetic.
WORKER = r'''
import os,subprocess,time,pathlib,sys
home=pathlib.Path(os.environ['HOME']);env=dict(os.environ,DISPLAY=':98',XAUTHORITY=str(home/'Xauthority'))
x=subprocess.Popen(['Xkasmvnc',':98','-geometry','1024x768','-AcceptSetDesktopSize','0','-depth','24','-interface','127.0.0.1','-websocketPort','8444','-rfbport','-1','-SecurityTypes','None','-publicIP','127.0.0.1','-httpd','/usr/share/kasmvnc/www','-KasmPasswordFile',str(home/'password'),'-cert',str(home/'server.crt'),'-key',str(home/'server.key'),'-sslOnly','1','-nolisten','tcp','-auth',str(home/'Xauthority')],env=env)
for _ in range(100):
 if x.poll() is not None:sys.exit(1)
 if subprocess.run(['xprop','-root'],env=env,capture_output=True).returncode==0:break
 time.sleep(.1)
else:sys.exit(1)
try:(home/'bus').unlink()
except FileNotFoundError:pass
env['DBUS_SESSION_BUS_ADDRESS']=subprocess.check_output(['dbus-daemon','--session','--fork','--address=unix:path='+str(home/'bus'),'--print-address'],text=True).strip()
wm=subprocess.Popen(['xfce4-session'],env=env)
for _ in range(150):
 if 'window id' in subprocess.run(['xprop','-root','_NET_SUPPORTING_WM_CHECK'],env=env,capture_output=True,text=True).stdout:break
 time.sleep(.1)
else:sys.exit(1)
f=subprocess.Popen(['firefox','--new-instance','--profile',str(home/'profile'),'--marionette','about:blank'],env=env)
while all(p.poll() is None for p in (x,wm,f)):time.sleep(.2)
sys.exit(1)
'''


def invoke(ns, script, timeout=30):
    return json.loads(command(['ip', 'netns', 'exec', ns, 'python3', '-B', '-c', script],
                              timeout=timeout).stdout)


def browser(ns, helper, port, method, params):
    script = ('import sys;sys.dont_write_bytecode=True;import pathlib,hashlib,types,json;'
              'p=pathlib.Path('+repr(str(helper))+');data=p.read_bytes();'
              '\nif hashlib.sha256(data).hexdigest()!='+repr(PIN)+':raise ValueError("Private helper digest mismatch")\n'
              'm=types.ModuleType("private_probe");m.__file__=str(p);'
              'exec(compile(data,str(p),"exec"),m.__dict__);'
              'd=m.Marionette('+str(port)+');'
              'print(json.dumps(d.call('+repr(method)+','+repr(params)+')));d.sock.close()')
    response = invoke(ns, script)
    return response.get('value', response) if isinstance(response, dict) else response


def js(ns, helper, port, script):
    return browser(ns, helper, port, 'WebDriver:ExecuteScript', {'script': script, 'args': []})


def wait(check, message):
    for _ in range(100):
        try:
            value = check()
            if value:
                return value
        except (ValueError, OSError, subprocess.TimeoutExpired):
            pass
        time.sleep(.15)
    raise ValueError(message)


def http(ns, ca, source='10.235.0.2', destination=TARGET, port=8443,
         path='/', headers=None, identity=None, plain=False, authentication_file=None):
    import inspect
    script = inspect.getsource(websocket_request_shape) + '''\nimport socket,ssl,json,base64
s=socket.socket();s.settimeout(2);s.bind((SOURCE,0));data=b''
headers=dict(HEADERS);expected_authorization=None
if AUTH_FILE:
 from pathlib import Path
 auth=json.loads(Path(AUTH_FILE).read_text())
 expected_authorization='Basic '+base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
 headers['Authorization']=expected_authorization
try:
 s.connect((DEST,PORT))
 if not PLAIN:s=ssl.create_default_context(cafile=CA).wrap_socket(s,server_hostname=IDENTITY)
 request='GET '+PATH+' HTTP/1.1\\r\\nHost: '+DEST+':8443\\r\\n'
 if not any(k.lower()=='connection' for k in headers):request+='Connection: close\\r\\n'
 for k,v in headers.items():
  if k.lower()=='host':request=request.replace('Host: '+DEST+':8443','Host: '+v)
  else:request+=k+': '+v+'\\r\\n'
 s.sendall((request+'\\r\\n').encode());data=b''
 while len(data)<65536:
  try:chunk=s.recv(min(4096,65536-len(data)))
  except socket.timeout:break
  if not chunk:break
  data+=chunk
  if data.startswith(b'HTTP/1.1 101') and b'\\r\\n\\r\\n' in data:break
 response={'status':int(data.split()[1]),'challenge':b'www-authenticate:' in data.lower()}
except ssl.SSLCertVerificationError:response={'rejected':'tls-verification'}
except (OSError,ValueError,IndexError):response={'rejected':'transport'}
finally:s.close()
if 'request' in locals():response['request_shape']=websocket_request_shape((request+'\\r\\n').encode(),expected_authorization)
if data:response['_buffer']=base64.b64encode(data).decode()
print(json.dumps(response))
'''
    values = {'SOURCE': source, 'DEST': destination, 'PORT': port, 'PLAIN': plain,
              'CA': str(ca), 'IDENTITY': identity or destination, 'PATH': path, 'HEADERS': headers or {},
              'AUTH_FILE': str(authentication_file) if authentication_file else None}
    # Replace identifiers as tokens, avoiding changes inside inserted values.
    script = re.sub(r'\b('+ '|'.join(values)+r')\b', lambda m: repr(values[m[0]]), script)
    response = invoke(ns, script)
    if '_buffer' in response:
        response['backend_secret_absent'] = observe_secrets('http_response', base64.b64decode(response.pop('_buffer')))
    return response



def tcp(ns, source, destination, port):
    # Match the existing routed fixture's connect-only probes; no TLS fallback.
    script = """import socket,json
s=socket.socket();s.settimeout(2);s.bind((SOURCE,0))
try:
 s.connect((DEST,PORT));connected=True
except OSError:connected=False
finally:s.close()
print(json.dumps({'tcp_connected':connected}))
"""
    values = {'SOURCE': source, 'DEST': destination, 'PORT': port}
    script = re.sub(r'\b('+ '|'.join(values)+r')\b', lambda m: repr(values[m[0]]), script)
    return invoke(ns, script)


def execute(args, result):
    global SECRET_MARKERS
    SECRET_MARKERS = ()
    SECRET_OBSERVATIONS.clear()
    root = args.run_root
    evidence = Path(str(root)+'-evidence')
    before = metadata(args.repo)
    units = []
    created = False
    evidence_owned = False
    result.update(status='failed', runtime='executed', matrix={}, evidence_layer='isolated-real-TLS-WSS-desktop',
                  not_run=['real OCI WireGuard peers', 'real device trust', 'revocation/maintenance',
                           'Story12 personal OAuth/China-network UAT'])
    try:
        root.mkdir(mode=0o755); created = True
        identity = (root.stat().st_dev, root.stat().st_ino)
        evidence.mkdir(mode=0o700)
        evidence_owned = True
        evidence_identity = (evidence.stat().st_dev, evidence.stat().st_ino)
        os.umask(0o077)
        owner = pwd.getpwnam('employee'); ownership = (owner.pw_uid, owner.pw_gid)
        materials = root/'materials'; materials.mkdir()
        certificate(materials, 'frontend-ca'); certificate(materials, 'backend-ca')
        certificate(materials, 'desktop', 'frontend-ca', 'IP:'+TARGET)
        certificate(materials, 'backend', 'backend-ca', 'DNS:localhost')
        certificate(materials, 'wrong-identity', 'backend-ca', 'DNS:wrong.invalid')
        distribution = root/'distribution'; distribution.mkdir(mode=0o755)
        os.chmod(distribution, 0o755)
        (distribution/'policies.json').write_text(json.dumps({'policies': {
            'Certificates': {'Install': [str(materials/'frontend-ca.crt')]},
            'DisableAppUpdate': True, 'DisableTelemetry': True, 'DisableFirefoxStudies': True}}))
        os.chmod(distribution/'policies.json', 0o644)
        os.chmod(materials, 0o755); os.chmod(materials/'frontend-ca.crt', 0o644)
        for role, port in (('desktop', 2829), ('client', 2828)):
            home = root/role; home.mkdir(mode=0o700); os.chown(home, *ownership)
            for folder in ('xdg', '.config', '.cache', '.local', 'gnupg', 'profile'):
                (home/folder).mkdir(mode=0o700); os.chown(home/folder, *ownership)
            prefs = 'user_pref("marionette.port",'+str(port)+');\nuser_pref("browser.shell.checkDefaultBrowser",false);\n'
            (home/'profile/user.js').write_text(prefs); os.chown(home/'profile/user.js', *ownership)
        password = secrets.token_urlsafe(24)
        basic = base64.b64encode(('synthetic:'+password).encode()).decode()
        SECRET_MARKERS = tuple(value.encode() for value in
                               (password, 'synthetic:'+password, basic, 'Basic '+basic))
        desktop = root/'desktop'
        (desktop/'Xauthority').touch(); os.chown(desktop/'Xauthority', *ownership)
        command(['runuser', '-u', 'employee', '--', 'xauth', '-f', desktop/'Xauthority', 'source', '-'],
                data='add :98 . '+secrets.token_hex(16)+'\n')
        command(['runuser', '-u', 'employee', '--', 'kasmvncpasswd', '-u', 'synthetic', '-w', desktop/'password'],
                data=password+'\n'+password+'\n')
        for source, dest in (('backend.crt', 'server.crt'), ('backend.key', 'server.key')):
            shutil.copyfile(materials/source, desktop/dest); os.chown(desktop/dest, *ownership)
        (root/'worker.py').write_text(WORKER); os.chmod(root/'worker.py', 0o644)
        helper = load_private(args.helper); helper.RUN = root
        network = load('network_fixture', args.repo/'tests/oci-hub/test-network.py')
        prefix = 's10'+secrets.token_hex(3)
        result['resources'] = {'namespaces': [prefix+s for s in ('h', 'u', 'v')],
                               'veth_names': [prefix+s for s in ('u', 'up', 'v', 'vp')], 'units': [],
                               'runtime': str(root), 'evidence': str(evidence)}
        def start(role, namespace, argv, home=None, extra=None):
            name = prefix+'-'+role
            need(command(['systemctl', 'show', name, '-p', 'LoadState', '--value']).stdout.strip() == 'not-found',
                 'Transient unit conflict')
            units.append(name)
            result['resources']['units'].append(name)
            if home:
                # start_unit provides ProtectHome, the distribution bind and bounded lifetime.
                helper.start_unit(name, namespace, ['env', 'GNUPGHOME='+str(home/'gnupg'),
                                  'PYTHONDONTWRITEBYTECODE=1', *map(str, argv)], True, home)
            else:
                command(['systemd-run', '--collect', '--unit='+name, '-p', 'RuntimeMaxSec=240',
                         '-p', 'KillMode=control-group', '-p', 'TimeoutStopSec=10', '-p', 'ProtectHome=yes',
                         '-p', 'NetworkNamespacePath=/run/netns/'+namespace,
                         '-p', 'BindReadOnlyPaths='+str(materials)+':/etc/oci-hub',
                         *map(str, argv)])
            return name
        cleanup_errors = result.setdefault('cleanup_errors', [])
        def stop_units():
            failed = []
            for unit in list(reversed(units)):
                try:
                    command(['systemctl', 'stop', unit])
                    units.remove(unit)
                except Exception as error:
                    failed.append(unit)
                    cleanup_errors.append('stop '+unit+':'+type(error).__name__)
            if failed:
                raise RuntimeError('Owned unit cleanup failed')
        with network.hub_topology(prefix, stop_units) as (hub, users, vms, policy, receipt):
            start('desktop', vms, ['python3', '-B', root/'worker.py'], desktop)
            from jinja2 import Environment, StrictUndefined
            env = Environment(undefined=StrictUndefined); env.filters['regex_escape'] = re.escape
            template = (args.repo/SOURCES[-1]).read_text()
            rendered = env.from_string(template).render(oci_hub_spoke_address=TARGET+'/32',
                oci_hub_desktop_backend_basic=base64.b64encode(('synthetic:'+password).encode()).decode())
            # Run the production login bridge with synthetic references and HOME.
            guide_files = args.repo/'ansible/roles/employee-workspace/files'
            guide_root = root/'guide'; guide_root.mkdir(mode=0o755); os.chmod(guide_root, 0o755)
            generation_id = 'g-story12-synthetic'
            material_root = guide_root/'materials'
            generation = material_root/'generations'/generation_id/'502'
            generation.mkdir(parents=True, mode=0o755)
            for parent in (material_root, material_root/'generations', generation.parent, generation):
                os.chmod(parent, 0o755)
            refs = {'trust_ref': 'ca.pem', 'certificate_ref': 'server.pem',
                    'private_key_ref': 'server.key', 'authentication_ref': 'authentication.json'}
            for source, target in (('backend-ca.crt', 'ca.pem'), ('backend.crt', 'server.pem'), ('backend.key', 'server.key')):
                shutil.copyfile(materials/source, generation/target)
            (generation/'authentication.json').write_text(json.dumps({'username': 'synthetic', 'password': password}))
            for path in generation.iterdir():
                os.chown(path, 0, owner.pw_gid)
                os.chmod(path, 0o640 if path.name in ('server.key', 'authentication.json') else 0o644)
            pinned = {key: 'generations/'+generation_id+'/502/'+value for key, value in refs.items()}
            descriptor = {'type': 'kasmvnc', 'address': '127.0.0.1', 'port': 8444,
                'client_path': '/', 'route_enabled': True, 'generation_id': generation_id,
                'tls_server_name': 'localhost', 'trust_ref': pinned['trust_ref']}
            desktop_config = {'vmid': 502, 'backend': descriptor, 'generation': dict(pinned, vmid=502),
                              'materials_root': str(material_root), 'viewer_url': 'https://'+TARGET+':8443/'}
            (guide_root/'desktop.json').write_text(json.dumps(desktop_config))
            (guide_root/'browser.json').write_text(json.dumps({'mode': 'kasmvnc', 'viewer_url': 'https://hapi.synthetic.invalid'}))
            (guide_root/'desktop-service.py').write_text((guide_files/'desktop-service.py').read_text().replace(
                "CONFIG = Path('/etc/employee-workspace-desktop.json')", "CONFIG = Path("+repr(str(guide_root/'desktop.json'))+")").replace("MARKER = Path('/var/lib/employee-workspace/transition.json')", "MARKER = Path("+repr(str(guide_root/'transition.json'))+")"))
            shutil.copyfile(guide_files/'desktop-contract.py', guide_root/'desktop-contract.py')
            for path in guide_root.iterdir():
                if path.is_file(): os.chmod(path, 0o644)
            guide_worker = """import importlib.util,http.server,json,sys,threading,time,re
from pathlib import Path
from urllib.parse import urlsplit
spec=importlib.util.spec_from_file_location('actual_guide',sys.argv[1]);guide=importlib.util.module_from_spec(spec);spec.loader.exec_module(guide)
root=Path(sys.argv[2]);guide.BROWSER_CONFIG=root/'browser.json';guide.DESKTOP_SERVICE=root/'desktop-service.py'
dspec=importlib.util.spec_from_file_location('synthetic_diagnostics',sys.argv[4]);diagnostic=importlib.util.module_from_spec(dspec);dspec.loader.exec_module(diagnostic)
auth=json.loads((root/'materials/generations/g-story12-synthetic/502/authentication.json').read_text())
expected_authorization='Basic '+__import__('base64').b64encode((auth['username']+':'+auth['password']).encode()).decode()
events=[];lock=threading.Lock();diagnostics=Path.home()/'guide-diagnostics.json'
def event(code,**fields):
 with lock:
  events.append(dict(code=code,**fields));events[:]=events[-128:]
  diagnostics.write_text(json.dumps(events))
actual_connection=guide.viewer_connection
def connection():
 try:
  peer,identity=actual_connection()
 except Exception as error:
  event('backend-connect-rejected',error_type=type(error).__name__[:64]);raise
 event('backend-tls-connected')
 original=peer.recv;send=peer.sendall;header=bytearray();complete=False
 def transmit(value,*args,**kwargs):
  event('backend-websocket-request',shape=diagnostic.websocket_request_shape(value,expected_authorization))
  return send(value,*args,**kwargs)
 peer.sendall=transmit
 def receive(*args,**kwargs):
  nonlocal complete
  value=original(*args,**kwargs)
  if not complete:
   header.extend(value[:max(0,16384-len(header))])
   if b'\\r\\n\\r\\n' in header or not value or len(header)>=16384:
    first=bytes(header).split(b'\\r\\n',1)[0].split()
    status=int(first[1]) if len(first)>1 and first[1].isdigit() else 0
    event('backend-websocket-http',status=status,response=diagnostic.websocket_response_shape(header,expected_authorization));header.clear();complete=True
  return value
 peer.recv=receive
 return peer,identity
guide.viewer_connection=connection
class DiagnosticGuide(guide.Guide):
 def reply(self,status,body,kind='application/json; charset=utf-8',nonce=''):
  path=urlsplit(self.path).path
  event('guide-http',path=path[:256] if re.fullmatch(r'/[A-Za-z0-9_./-]*',path) else '[invalid-path]',status=status)
  if nonce and kind.startswith('text/html'):
   boot="<script nonce=\""+nonce+"\">window.__fixtureErrors=[];for(let k of ['error','unhandledrejection'])window.addEventListener(k,e=>{window.__fixtureErrors.push(String(e.message||e.reason||k).slice(0,512));window.__fixtureErrors=window.__fixtureErrors.slice(-16)});</script>"
   body=body.replace(b'<head>',b'<head>'+boot.encode(),1)
  return super().reply(status,body,kind,nonce)
class DiagnosticServer(http.server.ThreadingHTTPServer):
 def handle_error(self,request,client_address):
  event('guide-handler-error',error_type=sys.exc_info()[0].__name__[:64])
flow=guide.Flow(cache=Path.home()/'guide-cache',auth=lambda:(True,'claude.ai'))
server=DiagnosticServer(('127.0.0.1',6082),DiagnosticGuide)
server.origin=sys.argv[3];server.hapi_url='https://hapi.synthetic.invalid';server.csrf='synthetic-csrf';server.flow=flow
event('guide-listening');server.serve_forever()
"""
            (root/'guide-worker.py').write_text(guide_worker); os.chmod(root/'guide-worker.py', 0o644)
            start('guide', vms, ['python3', '-B', root/'guide-worker.py', guide_files/'login-guide.py',
                                guide_root, 'https://'+TARGET+':8443', args.repo/SOURCES[0]], desktop)
            # Route the same-origin synthetic HAPI mount to the unmodified Guide paths.
            rendered = rendered.replace('    location / {',
                '    location ^~ /hapi/ {\n'
                '        proxy_pass http://127.0.0.1:6082/;\n'
                '        proxy_http_version 1.1;\n'
                '        proxy_set_header Host '+TARGET+':8443;\n'
                '        proxy_set_header Origin $http_origin;\n'
                '        proxy_set_header Upgrade $http_upgrade;\n'
                '        proxy_set_header Connection "upgrade";\n'
                '        proxy_read_timeout 3600s;\n'
                '    }\n    location / {')
            config = root/'nginx.conf'
            config.write_text('pid '+str(root/'nginx.pid')+';\nerror_log '+str(root/'nginx-error.log')+' error;\n'
                              'events {}\nhttp { access_log off;\n'
                              'client_body_temp_path '+str(root/'body')+';\n'
                              'proxy_temp_path '+str(root/'proxy')+';\n'
                              'fastcgi_temp_path '+str(root/'fastcgi')+';\n'
                              'uwsgi_temp_path '+str(root/'uwsgi')+';\n'
                              'scgi_temp_path '+str(root/'scgi')+';\n'+rendered+
                              '\nserver { listen 10.234.0.3:8443; return 204; }\n}\n')
            nginx_unit = start('nginx', vms, ['nginx', '-c', config, '-p', root, '-g', 'daemon off;'])
            def positive():
                reply = http(users, materials/'frontend-ca.crt')
                result['last_https_probe'] = reply
                return reply if reply.get('status') == 200 and not reply['challenge'] else None
            wait(positive, 'Positive HTTPS unavailable')
            result['matrix']['https'] = {'actual': positive(), 'layer': 'isolated-TLS-HTTP',
                'expected': '200 without authentication challenge', 'action': 'GET assigned overlay HTTPS root'}
            wss = {'Upgrade': 'websocket', 'Connection': 'Upgrade', 'Origin': 'https://'+TARGET+':8443',
                   'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
                   'Sec-WebSocket-Protocol': 'binary',
                   'Sec-WebSocket-Origin': 'https://'+TARGET+':8443'}
            def record(name, reply, expected, expectation, action, layer='isolated-TLS-HTTP'):
                result['matrix'][name] = {'actual': reply, 'expected': expectation,
                                         'action': action, 'layer': layer}
                need(expected(reply), 'Matrix failed: '+name)
                control = positive()
                result['matrix'][name]['positive_control'] = control
                need(control, 'Positive control failed: '+name)
            record('wss', http(users, materials/'frontend-ca.crt', path='/websockify', headers=wss),
                   lambda r: r.get('status') == 101, '101', 'Upgrade /websockify with current overlay Origin',
                   'isolated-TLS-WSS')
            # Diagnostic-only direct positive-shaped handshake to the same Kasm:
            # credentials are read inside the child from synthetic material, never argv.
            direct_headers = dict(wss, Host='localhost', Origin='https://localhost:8444', Connection='upgrade')
            result['matrix']['wss-direct-diagnostic'] = {'actual': http(vms, materials/'backend-ca.crt',
                source='127.0.0.1', destination='127.0.0.1', port=8444, identity='localhost',
                path='/websockify', headers=direct_headers, authentication_file=generation/'authentication.json'),
                'layer': 'synthetic-request-comparison-only',
                'action': 'Send the successful overlay probe headers through the existing nginx header substitutions'}
            # Bounded one-field counterfactuals preserve the direct comparison
            # shape and are evidence only; the real noVNC acceptance remains below.
            counterfactuals = {}
            for label, changes in (('without-binary', {'Sec-WebSocket-Protocol': None}),
                                   ('connection-case', {'Connection': 'Upgrade'}),
                                   ('legacy-origin-localhost', {'Sec-WebSocket-Origin': 'https://localhost:8444'})):
                changed = dict(direct_headers)
                for key, value in changes.items():
                    if value is None: changed.pop(key, None)
                    else: changed[key] = value
                counterfactuals[label] = http(vms, materials/'backend-ca.crt',
                    source='127.0.0.1', destination='127.0.0.1', port=8444, identity='localhost',
                    path='/websockify', headers=changed, authentication_file=generation/'authentication.json')
            result['matrix']['wss-counterfactual-diagnostic'] = {'actual': counterfactuals,
                'layer': 'synthetic-one-field-request-comparison-only'}
            other_positive = tcp(users, '10.235.0.3', '10.234.0.3', 8443)
            need(other_positive['tcp_connected'], 'Other-target owned-source TCP control unavailable')
            record('other-target', tcp(users, '10.235.0.2', '10.234.0.3', 8443),
                   lambda r: r['tcp_connected'] is False, 'TCP refused',
                   'Connect device .2 to other workspace .3:8443', 'routed-TCP')
            need(tcp(users, '10.235.0.3', '10.234.0.3', 8443)['tcp_connected'],
                 'Other-target owned-source TCP control lost')
            result['matrix']['other-target']['owned_source_positive_control'] = other_positive
            record('backend-direct', tcp(users, '10.235.0.2', TARGET, 8444),
                   lambda r: r['tcp_connected'] is False, 'TCP refused',
                   'Connect device .2 directly to target overlay:8444', 'routed-TCP')
            for name, options, rejection in [
                    ('wrong-source', {'source': '10.235.0.3'}, 'transport'),
                    ('wrong-ca', {'ca': materials/'backend-ca.crt'}, 'tls-verification'),
                    ('wrong-san', {'identity': 'wrong.invalid'}, 'tls-verification')]:
                opts = dict(ca=materials/'frontend-ca.crt'); opts.update(options)
                record(name, http(users, **opts), lambda r: r.get('rejected') == rejection,
                       rejection, 'GET assigned HTTPS root with '+name,
                       'routed-transport' if rejection == 'transport' else 'isolated-TLS-HTTP')
            record('http', http(users, materials/'frontend-ca.crt', plain=True),
                   lambda r: r.get('status') == 400, '400 plaintext on active TLS port rejected',
                   'Send plaintext HTTP to active target overlay:8443', 'plaintext-to-TLS-entry')
            for name, path, headers in [('host', '/', {'Host': 'wrong.invalid'}),
                                        ('origin', '/', {'Origin': 'https://wrong.invalid'}),
                                        ('api', '/api', {}), ('api-child', '/api/session', {}),
                                        ('wss-host', '/websockify', dict(wss, Host='wrong.invalid')),
                                        ('wss-origin', '/websockify', dict(wss, Origin='https://wrong.invalid'))]:
                record(name, http(users, materials/'frontend-ca.crt', path=path, headers=headers),
                       lambda r: r.get('status') == 403, '403', 'GET '+path+' with '+name)
            # Validate old URL purely as input; never contact VM500.
            old = 'https://10.230.0.1:8443/?target=501'
            trust = load('trust_fixture', args.repo/'tests/oci-hub/test-desktop-trust.py')
            trust_input = dict(ca=materials/'frontend-ca.crt',
                reference=trust.ca_fingerprint(materials/'frontend-ca.crt'),
                source='synthetic-independent-channel', leaf=materials/'desktop.crt', assigned_ip=TARGET)
            offline_control = trust.explain_trust(**trust_input, url='https://'+TARGET+':8443/')
            need(offline_control == 'accepted-synthetic-only', 'Trust positive control failed')
            reason = trust.explain_trust(**trust_input, url=old)
            need(reason == 'retired-shared-url', 'Old URL accepted')
            result['matrix']['old-url'] = {'input': old, 'rejected': reason,
                                           'layer': 'offline-input', 'positive_control': offline_control,
                                           'expected': 'retired-shared-url', 'action': 'Check old URL as input only'}
            start('client', users, ['firefox', '--headless', '--no-remote', '--profile', root/'client/profile',
                                    '--marionette', 'about:blank'], root/'client')
            wait(lambda: js(vms, args.helper, 2829, 'return true;'), 'Backend browser unavailable')
            wait(lambda: js(users, args.helper, 2828, 'return true;'), 'Client browser unavailable')
            html = '<title>Story10 synthetic</title><textarea id="input" autofocus></textarea>'
            browser(vms, args.helper, 2829, 'WebDriver:Navigate',
                    {'url': 'data:text/html;base64,'+base64.b64encode(html.encode()).decode()})
            canvas = '''let b=document.querySelector('#noVNC_connect_button_2, #noVNC_connect_button');
if(b&&!document.documentElement.classList.contains('noVNC_connected'))b.click();
let c=Array.from(document.querySelectorAll('canvas')).find(e=>e.id!=='noVNC_multiMonitorWidget'&&e.width>0&&e.height>0&&e.getBoundingClientRect().width>0);
return document.documentElement.classList.contains('noVNC_connected')&&c?{width:c.width,height:c.height}:null;'''
            for phase, value in (('initial', 'story10-input'), ('reconnect', '-reconnected')):
                browser(users, args.helper, 2828, 'WebDriver:Navigate', {'url': 'https://'+TARGET+':8443/'})
                dimensions = wait(lambda: js(users, args.helper, 2828, canvas), 'Real canvas unavailable')
                js(vms, args.helper, 2829, 'document.querySelector("#input").focus();return true;')
                js(users, args.helper, 2828, 'let c=Array.from(document.querySelectorAll("canvas")).find(e=>e.id!=="noVNC_multiMonitorWidget"&&e.width>0&&e.height>0);c.tabIndex=0;c.focus();return true;')
                actions = [a for char in value for a in ({'type': 'keyDown', 'value': char}, {'type': 'keyUp', 'value': char})]
                browser(users, args.helper, 2828, 'WebDriver:PerformActions',
                        {'actions': [{'type': 'key', 'id': 'keyboard', 'actions': actions}]})
                expected = 'story10-input'+('-reconnected' if phase == 'reconnect' else '')
                wait(lambda: js(vms, args.helper, 2829, 'return document.querySelector("#input").value;') == expected,
                     'Desktop input round trip failed: '+phase)
                picture = browser(users, args.helper, 2828, 'WebDriver:TakeScreenshot',
                                  {'id': None, 'full': False, 'scroll': False})
                (evidence/(phase+'.png')).write_bytes(base64.b64decode(picture))
                for scope, namespace, port in (('frontend_dom', users, 2828), ('backend_dom', vms, 2829)):
                    dom = js(namespace, args.helper, port, 'return document.documentElement.outerHTML.slice(0,131072);')
                    observe_secrets(scope, dom)
                result['matrix'][phase] = {'canvas': dimensions, 'input_round_trip': True,
                    'accept_insecure_certs_requested': False, 'screenshot': phase+'.png',
                    'layer': 'isolated-real-desktop', 'expected': 'canvas and retained input round trip',
                    'action': 'Navigate/reconnect and type into real backend Firefox'}
                browser(users, args.helper, 2828, 'WebDriver:Navigate', {'url': 'about:blank'})
            # The existing distribution noVNC RFB client must render the Kasm
            # stream, deliver input, and reconnect through the real Guide bridge.
            bridge_canvas = """let c=document.querySelector('canvas');
return c&&c.width>0&&c.height>0&&document.querySelector('#status')?.textContent.includes('Connected')?{width:c.width,height:c.height}:null;"""
            def bridge_failure(phase):
                """Retain only bounded synthetic browser state and fixed bridge codes."""
                diagnosis = {'layer': 'isolated-HAPI-diagnostic'}
                state_script = """return {ready:document.readyState,title:document.title.slice(0,256),
status:document.querySelector('#status')?.textContent.slice(0,512)||null,
errors:(window.__fixtureErrors||[]).slice(-16),
canvas:Array.from(document.querySelectorAll('canvas')).slice(0,4).map(c=>({width:c.width,height:c.height,visible:c.getBoundingClientRect().width>0})),
resources:performance.getEntriesByType('resource').slice(-64).map(e=>{let u=new URL(e.name);return {path:u.origin===location.origin?u.pathname.slice(0,256):'[other-origin]',type:e.initiatorType,status:e.responseStatus||0,size:e.transferSize}})};"""
                try:
                    diagnosis['browser'] = js(users, args.helper, 2828, state_script)
                    dom = js(users, args.helper, 2828, 'return document.documentElement.outerHTML.slice(0,65536);')
                    observe_secrets('hapi_failure_dom', dom)
                    for marker in SECRET_MARKERS:
                        dom = dom.replace(marker.decode(), '[redacted synthetic secret]')
                    (evidence/(phase+'-failed-dom.html')).write_text(dom)
                    picture = browser(users, args.helper, 2828, 'WebDriver:TakeScreenshot',
                                      {'id': None, 'full': False, 'scroll': False})
                    (evidence/(phase+'-failed.png')).write_bytes(base64.b64decode(picture))
                    diagnosis['artifacts'] = [phase+'-failed-dom.html', phase+'-failed.png']
                except Exception as error:
                    diagnosis['browser_diagnostic_error'] = type(error).__name__
                try:
                    path = desktop/'guide-diagnostics.json'
                    diagnosis['bridge'] = json.loads(path.read_text()[:65536]) if path.is_file() else [{'code': 'guide-diagnostics-absent'}]
                except Exception as error:
                    diagnosis['bridge_diagnostic_error'] = type(error).__name__
                # HTTP status/content type for entry and its discovered local modules
                # distinguishes a missing asset, an incorrect mount, and RFB failure.
                paths = ['/hapi/vnc_lite.html', '/hapi/core/rfb.js']
                paths += [entry['path'] for entry in diagnosis.get('browser', {}).get('resources', [])
                          if entry['path'].startswith('/hapi/') and entry['path'] not in paths]
                resource_script = """import http.client,ssl,json
connection=http.client.HTTPSConnection(DEST,8443,context=ssl.create_default_context(cafile=CA),timeout=3)
results=[]
for path in PATHS:
 connection.request('GET',path,headers={'Host':DEST+':8443'})
 response=connection.getresponse();response.read(1048576)
 results.append({'path':path,'status':response.status,'content_type':response.getheader('Content-Type','')[:128]})
 connection.close()
print(json.dumps(results))
"""
                values = {'DEST': TARGET, 'CA': str(materials/'frontend-ca.crt'), 'PATHS': paths[:32]}
                resource_script = re.sub(r'\b('+ '|'.join(values)+r')\b', lambda m: repr(values[m[0]]), resource_script)
                try:
                    diagnosis['http_resources'] = invoke(users, resource_script)
                except Exception as error:
                    diagnosis['resource_diagnostic_error'] = type(error).__name__
                observe_secrets('hapi_failure_diagnostic', json.dumps(diagnosis))
                result['matrix'][phase+'-diagnostic'] = diagnosis

            for phase, text in (('hapi-initial', '-hapi'), ('hapi-reconnect', '-again')):
                browser(users, args.helper, 2828, 'WebDriver:Navigate',
                    {'url': 'https://'+TARGET+':8443/hapi/vnc_lite.html?autoconnect=true&resize=scale&path=hapi/websockify'})
                try:
                    dimensions = wait(lambda: js(users, args.helper, 2828, bridge_canvas), 'HAPI noVNC canvas unavailable')
                except Exception:
                    bridge_failure(phase)
                    raise
                js(vms, args.helper, 2829, 'document.querySelector("#input").focus();return true;')
                js(users, args.helper, 2828, 'let c=document.querySelector("canvas");c.tabIndex=0;c.focus();return true;')
                actions = [a for char in text for a in ({'type': 'keyDown', 'value': char}, {'type': 'keyUp', 'value': char})]
                browser(users, args.helper, 2828, 'WebDriver:PerformActions',
                    {'actions': [{'type': 'key', 'id': 'keyboard', 'actions': actions}]})
                expected = 'story10-input-reconnected-hapi'+('-again' if phase == 'hapi-reconnect' else '')
                wait(lambda: js(vms, args.helper, 2829, 'return document.querySelector("#input").value;') == expected,
                     'HAPI noVNC input round trip failed: '+phase)
                picture = browser(users, args.helper, 2828, 'WebDriver:TakeScreenshot',
                                  {'id': None, 'full': False, 'scroll': False})
                (evidence/(phase+'.png')).write_bytes(base64.b64decode(picture))
                dom = js(users, args.helper, 2828, 'return document.documentElement.outerHTML.slice(0,131072);')
                observe_secrets('hapi_frontend_dom', dom)
                result['matrix'][phase] = {'canvas': dimensions, 'input_round_trip': True,
                    'screenshot': phase+'.png', 'layer': 'isolated-production-Guide-distribution-noVNC',
                    'accept_insecure_certs_requested': False}
                browser(users, args.helper, 2828, 'WebDriver:Navigate', {'url': 'about:blank'})
            # Exercise all four unchanged control routes with synthetic auth only.
            api_script = """import http.client,json,ssl
c=http.client.HTTPSConnection(DEST,8443,context=ssl.create_default_context(cafile=CA))
results={}
for method,path,body,csrf,origin,expected in CASES:
 headers={'Content-Type':'application/json','Host':DEST+':8443','X-Login-CSRF':csrf,'Origin':origin}
 c.request(method,'/hapi'+path,body=json.dumps(body),headers=headers)
 r=c.getresponse();r.read();results[path+':'+csrf+':'+origin]=r.status
 if r.status!=expected:raise ValueError('Synthetic control API mismatch')
print(json.dumps(results))
"""
            cases = [('GET', '/api/login/status', {}, 'synthetic-csrf', 'https://'+TARGET+':8443', 200),
                     ('POST', '/api/login/start', {}, 'synthetic-csrf', 'https://'+TARGET+':8443', 200),
                     ('POST', '/api/login/cancel', {}, 'synthetic-csrf', 'https://'+TARGET+':8443', 200),
                     ('POST', '/api/login/code', {'code': 'invalid'}, 'synthetic-csrf', 'https://'+TARGET+':8443', 400),
                     ('POST', '/api/login/start', {}, 'wrong', 'https://'+TARGET+':8443', 403),
                     ('POST', '/api/login/start', {}, 'synthetic-csrf', 'https://wrong.invalid', 403)]
            values = {'DEST': TARGET, 'CA': str(materials/'frontend-ca.crt'), 'CASES': cases}
            api_script = re.sub(r'\b('+ '|'.join(values)+r')\b', lambda m: repr(values[m[0]]), api_script)
            result['matrix']['hapi-controls'] = {'actual': invoke(users, api_script),
                'layer': 'isolated-production-Guide-synthetic-auth', 'real_oauth': False}
            # Fault only the synthetic mounted upstream material, keeping the template intact.
            for fault, replacement in (('upstream-ca', materials/'frontend-ca.crt'),
                                       ('upstream-identity', materials/'wrong-identity.crt')):
                upstream_control = positive()
                need(upstream_control, 'HTTPS control before upstream fault failed')
                if fault == 'upstream-ca':
                    original = (materials/'backend-ca.crt').read_bytes()
                    (materials/'backend-ca.crt').write_bytes(replacement.read_bytes())
                else:
                    original = (desktop/'server.crt').read_bytes()
                    (desktop/'server.crt').write_bytes(replacement.read_bytes())
                    shutil.copyfile(materials/'wrong-identity.key', desktop/'server.key')
                    os.chown(desktop/'server.key', *ownership)
                    command(['systemctl', 'stop', units[0]])
                    units.pop(0)
                    start('desktop-fault', vms, ['python3', '-B', root/'worker.py'], desktop)
                    def wrong_identity_backend_ready():
                        response = http(vms, materials/'backend-ca.crt', source='127.0.0.1',
                                        destination='127.0.0.1', port=8444, identity='wrong.invalid',
                                        headers={'Host': 'localhost:8444'})
                        return response if response.get('status') in (200, 401) else None
                    backend_control = wait(wrong_identity_backend_ready,
                                           'Wrong-identity backend TLS positive control unavailable')
                    result['matrix']['upstream-identity-backend-positive'] = {
                        'actual': backend_control, 'tls_identity': 'wrong.invalid',
                        'trust': 'backend-ca', 'credentials_sent': False, 'layer': 'isolated-loopback-TLS',
                        'expected': '200 or 401 after strict wrong.invalid identity verification',
                        'action': 'GET loopback:8444 without credentials using matching wrong identity'}
                command(['systemctl', 'kill', '--signal=HUP', '--kill-whom=main', nginx_unit])
                reply = wait(lambda: (r if (r := http(users, materials/'frontend-ca.crt',
                    path='/websockify', headers=wss)).get('status') == 502 else None), 'Upstream fault did not close')
                result['matrix'][fault] = {'actual': reply, 'positive_control_before': upstream_control,
                    'layer': 'isolated-TLS-WSS', 'expected': '502',
                    'action': 'Change synthetic '+fault+' then request WSS'}
                if fault == 'upstream-ca':
                    (materials/'backend-ca.crt').write_bytes(original)
                    command(['systemctl', 'kill', '--signal=HUP', '--kill-whom=main', nginx_unit])
                    wait(positive, 'Upstream CA recovery failed')
            stop_units()
        result['status'] = 'passed'
    except Exception as exc:
        result['error'] = type(exc).__name__+': '+str(exc)
        if isinstance(exc, RuntimeError) and str(exc).startswith('Owned resource cleanup failed:'):
            result.setdefault('cleanup_errors', []).append(str(exc))
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        cleanup = [not result.get('cleanup_errors')]
        for unit in list(reversed(units)):
            try:
                command(['systemctl', 'stop', unit])
                cleanup.append(command(['systemctl', 'is-active', unit], check=False).stdout.strip()
                               not in ('active', 'activating', 'deactivating'))
            except Exception as error:
                cleanup.append(False)
                result.setdefault('cleanup_errors', []).append('final stop '+unit+':'+type(error).__name__)
        if 'resources' in result:
            try:
                existing = {line.split()[0] for line in command(['ip', 'netns', 'list']).stdout.splitlines()}
                result['remaining_namespaces'] = sorted(existing.intersection(result['resources']['namespaces']))
                cleanup.append(not result['remaining_namespaces'])
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                cleanup.append(False)
                result.setdefault('cleanup_errors', []).append('namespace inventory:'+type(error).__name__)
            result['remaining_units'] = []
            for name in result['resources']['units']:
                try:
                    if command(['systemctl', 'is-active', name], check=False).stdout.strip() in ('active', 'activating', 'deactivating'):
                        result['remaining_units'].append(name)
                except Exception as error:
                    result['remaining_units'].append(name)
                    result.setdefault('cleanup_errors', []).append('unit inventory '+name+':'+type(error).__name__)
            cleanup.append(not result['remaining_units'])
        result['non_task_metadata_before'] = before
        try:
            result['non_task_metadata_after'] = metadata(args.repo)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            result['non_task_metadata_after'] = None
        result['non_task_metadata_unchanged'] = before == result['non_task_metadata_after']
        if created:
            try:
                result['nginx_errors'] = nginx_errors(root/'nginx-error.log')
            except OSError:
                result['nginx_errors'] = {'available': False, 'read_error': True}
            try:
                current = root.lstat()
                safe = (current.st_dev, current.st_ino) == identity and not root.is_symlink()
                if safe and not result.get('remaining_units', units):
                    shutil.rmtree(root)
            except OSError as error:
                cleanup.append(False)
                result.setdefault('cleanup_errors', []).append('runtime:'+type(error).__name__)
            result['runtime_removed'] = not root.exists() and not root.is_symlink()
        result['cleanup_passed'] = all(cleanup) and result.get('runtime_removed', False) and result['non_task_metadata_unchanged']
        if not result['cleanup_passed']:
            result['status'] = 'failed'
        observe_secrets('result', json.dumps(result, sort_keys=True))
        result['backend_secret_observations'] = SECRET_OBSERVATIONS.copy()
        required_scopes = ('http_response', 'frontend_dom', 'backend_dom', 'nginx_log', 'result')
        result['backend_secret_absent'] = all(SECRET_OBSERVATIONS.get(scope, {}).get('secret_absent', False)
                                               for scope in required_scopes)
        if not result['backend_secret_absent']:
            result['status'] = 'failed'
        serialized = json.dumps(result, sort_keys=True)
        for marker in SECRET_MARKERS:
            serialized = serialized.replace(marker.decode(), '[redacted synthetic secret]')
        result = json.loads(serialized)
        if (evidence_owned and evidence.is_dir() and not evidence.is_symlink() and
                (evidence.stat().st_dev, evidence.stat().st_ino) == evidence_identity):
            (evidence/'result.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        result = preflight(args)
        if args.execute:
            signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError('Interrupted')))
            signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(RuntimeError('Interrupted')))
            result = execute(args, result)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] in ('passed', 'preflight-passed') else 1
    except Exception as exc:
        print(json.dumps({'status': 'rejected', 'error': type(exc).__name__+': '+str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
