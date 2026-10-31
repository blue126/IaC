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
           'ansible/roles/oci-hub-spoke/templates/desktop.conf.j2')


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
         path='/', headers=None, identity=None, plain=False):
    script = '''import socket,ssl,json,base64
s=socket.socket();s.settimeout(2);s.bind((SOURCE,0));data=b''
try:
 s.connect((DEST,PORT))
 if not PLAIN:s=ssl.create_default_context(cafile=CA).wrap_socket(s,server_hostname=IDENTITY)
 request='GET '+PATH+' HTTP/1.1\\r\\nHost: '+DEST+':8443\\r\\n'
 if not any(k.lower()=='connection' for k in HEADERS):request+='Connection: close\\r\\n'
 for k,v in HEADERS.items():
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
if data:response['_buffer']=base64.b64encode(data).decode()
print(json.dumps(response))
'''
    values = {'SOURCE': source, 'DEST': destination, 'PORT': port, 'PLAIN': plain,
              'CA': str(ca), 'IDENTITY': identity or destination, 'PATH': path, 'HEADERS': headers or {}}
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
            config = root/'nginx.conf'
            config.write_text('pid '+str(root/'nginx.pid')+';\nerror_log '+str(root/'nginx-error.log')+' error;\n'
                              'events {}\nhttp { access_log off; client_body_temp_path '+str(root/'body')+';\n'+rendered+
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
