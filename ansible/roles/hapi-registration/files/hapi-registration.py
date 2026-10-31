#!/usr/bin/python3
"""Merge one request-owned HAPI worker into the VM500 application control plane."""
import copy
import grp
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HUB = Path('/etc/hapi-shared-hub')
GATEWAY = Path('/etc/hapi-control-plane')
OWNERS = Path('/var/lib/hapi-application/registrations')


def need(value):
    if not value:
        raise ValueError('HAPI registration ownership or state mismatch')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def atomic(path, data, uid=None, gid=None, mode=None):
    path = Path(path)
    need(not path.is_symlink())
    if path.exists():
        info = path.stat()
        uid, gid, mode = info.st_uid, info.st_gid, info.st_mode & 0o777
    need(uid is not None and gid is not None and mode is not None)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.hapi-publish-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chown(name, uid, gid);os.chmod(name, mode);os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True)


def transport_config(text, agents):
    for variable, field in [('hapi_namespace', 'namespace'), ('hapi_credential', 'credential_id')]:
        pattern = r'(    map "\$remote_addr\|\$ssl_client_s_dn" \$' + variable + r' \{\n)(.*?)(    \}\n)'
        rows = '        default "";\n' + ''.join(
            f'        "{a["address"]}|CN={a["id"]}" "{a[field]}";\n' for a in agents)
        text, count = re.subn(pattern, lambda match: match[1] + rows + match[3], text, flags=re.S)
        need(count == 1)
    return text


def append_worker(registry, agents, row, agent):
    need(row['id'] == agent['id'] == agent['credential_id'] and row['namespace'] == agent['namespace'])
    need(row['namespace'] != 'default' and row['enabled'] is True)
    existing = [r for r in registry['credentials'] if r['id'] == row['id']]
    need(not existing or existing == [row])
    need(not any(r['id'] != row['id'] and r['namespace'] == row['namespace'] for r in registry['credentials']))
    peers = [r for r in agents['agents'] if r['id'] == agent['id']]
    need(not peers or peers == [agent])
    return ({**registry, 'credentials': registry['credentials'] if existing else [*registry['credentials'], row]},
            {**agents, 'agents': agents['agents'] if peers else [*agents['agents'], agent]})


def pending_config(config, entry):
    need(not any(r['workspace_id'] == entry['workspace_id'] or r['email'] == entry['email'] for r in config['routes']))
    old = [e for e in config.get('enrollments', []) if e['workspace_id'] == entry['workspace_id']]
    need(not old or old == [entry] or (len(old) == 1 and old[0]['expires_at'] <= time.time() and
         all(old[0][key] == entry[key] for key in ['workspace_id', 'request_id', 'email', 'generation'])))
    return {**config, 'enrollments': [e for e in config.get('enrollments', []) if e['workspace_id'] != entry['workspace_id']] + [entry]}


def active_config(config, route, proof):
    need((route['workspace_id'], route['email'], route['subject'], route['generation']) ==
         (proof['workspace_id'], proof['email'], proof['subject'], proof['generation']))
    existing = [r for r in config['routes'] if r['workspace_id'] == route['workspace_id']]
    need(not existing or [{k: v for k, v in existing[0].items() if k != 'enabled'}] ==
         [{k: v for k, v in route.items() if k != 'enabled'}])
    routes = [route if r['workspace_id'] == route['workspace_id'] else r for r in config['routes']]
    if not existing:
        routes.append(route)
    return {**config, 'routes': routes,
            'enrollments': [e for e in config.get('enrollments', []) if e['workspace_id'] != route['workspace_id']]}


def main():
    os.umask(0o077)
    command = read(sys.argv[1]);owner = command['owner'];wid = owner['workspace_id']
    need(command['kind'] == 'hapi-application-on-vm500' and command['vmid'] == 500)
    need(re.fullmatch(r'[a-z][a-z0-9-]{0,31}', wid) and re.fullmatch(r'[a-f0-9]{32}', owner['request_id']))
    need(wid not in {'control-plane', 'hub'})
    need(type(owner['vmid']) is int and owner['vmid'] > 502)
    need(owner['namespace'] == 'workspace_' + wid.replace('-', '_'))
    ip = ipaddress.IPv4Address(owner['address'])
    need(any(ip in ipaddress.ip_network(n) for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']))
    need(owner['address'] != command['server_address'])
    spec = importlib.util.spec_from_file_location('auth_config', '/usr/local/lib/hapi-auth.py')
    auth = importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
    config = auth.load_config(GATEWAY / 'config.json')
    need(config.get('shared_hub') and config['origin'] == command['origin'])
    need((config['issuer'], config['audience']) == (command['issuer'], command['audience']))
    action = command['action']
    need(action in {'register', 'enroll', 'proof', 'enable', 'block'})
    OWNERS.mkdir(parents=True, mode=0o700, exist_ok=True)
    marker = OWNERS / (wid + '.json')
    if marker.exists():
        need(read(marker) == owner)
    elif action == 'block':
        need(not any(r['workspace_id'] == wid for r in config['routes']))
        print(json.dumps({'changed': False}));return
    elif action == 'register':
        need(not any(r['workspace_id'] == wid or r['email'] == command['email'] for r in config['routes']))
    else:
        raise ValueError('Register this request before publishing identity')
    changed = False
    if action == 'register':
        material = command['material'];need(material['owner'] == owner)
        need(set(material) == {'owner', 'api_token', 'ca', 'crl'})
        row = command['credential']
        need(row['id'] == 'hapi-' + wid and row['namespace'] == owner['namespace'] and row['token'] == material['api_token'])
        before = read(HUB / 'credentials.json');agents = read(HUB / 'agents.json')
        agent = {'id': 'hapi-' + wid, 'address': owner['address'], 'namespace': owner['namespace'], 'credential_id': row['id']}
        registry, new_agents = append_worker(before, agents, row, agent)
        need(all(command['registry_rows'].get(r['id']) == digest(r) for r in registry['credentials']))
        text = (HUB / 'nginx.conf').read_text()
        need(transport_config(text, agents['agents']) == text)
        proxy = transport_config(text, new_agents['agents'])
        extension_spec = importlib.util.spec_from_file_location('hapi_firewall', '/usr/local/lib/hapi-firewall.py')
        extension = importlib.util.module_from_spec(extension_spec);extension_spec.loader.exec_module(extension)
        extension.rule(owner['address'], command['server_address'])
        policy_path = Path('/etc/hapi-application/firewall.json')
        policy = read(policy_path) if policy_path.exists() else {
            'version': 1, 'server': command['server_address'], 'workers': []}
        need(policy['version'] == 1 and policy['server'] == command['server_address'])
        if owner['address'] not in policy['workers']:
            policy = {**policy, 'workers': [*policy['workers'], owner['address']]}
        stage = OWNERS / (wid + '-stage');stage.mkdir(mode=0o700, exist_ok=True)
        for name, value in [('credentials.json', registry), ('agents.json', new_agents), ('firewall.json', policy)]:
            (stage / name).write_bytes(encoded(value))
        (stage / 'nginx.conf').write_text(proxy)
        run('/usr/bin/python3', '/usr/local/lib/hapi-hub-config.py', 'credentials', str(stage / 'credentials.json'))
        run('/usr/bin/python3', '/usr/local/lib/hapi-hub-config.py', 'agents', str(stage / 'agents.json'))
        run('/usr/sbin/nginx', '-t', '-c', str(stage / 'nginx.conf'), '-p', '/run/hapi-hub-transport/')
        if not marker.exists():
            atomic(marker, encoded(owner), 0, 0, 0o600)
        for path, data in [(HUB / 'credentials.json', encoded(registry)), (HUB / 'agents.json', encoded(new_agents)),
                           (HUB / 'nginx.conf', proxy.encode()), (policy_path, encoded(policy))]:
            if not path.exists() or path.read_bytes() != data:
                atomic(path, data, 0, 0, 0o600);changed = True
        # Public trust only: leave existing issuers and CRLs in the bundle.
        for path, pem in [(GATEWAY / 'ca.pem', material['ca']), (GATEWAY / 'crl.pem', material['crl']),
                          (HUB / 'ca.pem', material['ca']), (HUB / 'crl.pem', material['crl'])]:
            old = path.read_text()
            blocks = re.findall(r'-----BEGIN [^-]+-----.*?-----END [^-]+-----', old + '\n' + pem, re.S)
            new = '\n'.join(dict.fromkeys(blocks)) + '\n'
            if old != new:
                atomic(path, new.encode());changed = True
        # Reapply even after a lost receipt or a base firewall reload.
        extension.apply()
        # A previous publication may have lost its reload receipt after writing files.
        run('/usr/sbin/runuser', '-u', 'hapi-hub', '--', '/usr/sbin/nginx', '-s', 'reload',
            '-c', str(HUB / 'nginx.conf'), '-p', '/run/hapi-hub-transport/')
    elif action in {'enroll', 'enable', 'block'}:
        blocked_fingerprints = None
        if action == 'enroll':
            entry = command['enrollment']
            need((entry['workspace_id'], entry['request_id'], entry['email']) == (wid, owner['request_id'], command['email']))
            need(entry['expires_at'] > time.time())
            with sqlite3.connect('file:/var/lib/hapi-control-plane/revoked.sqlite3?mode=ro', uri=True) as db:
                db.row_factory = sqlite3.Row
                saved = db.execute('SELECT * FROM verified_enrollments WHERE request_id=?', (owner['request_id'],)).fetchone()
                need(saved is None or all(saved[key] == value for key, value in entry.items()))
            candidate = pending_config(config, entry)
        elif action == 'enable':
            proof = command['proof'];route = command['route']
            need(proof['request_id'] == owner['request_id'] and proof['issuer'] == config['issuer'] and proof['audience'] == config['audience'])
            need(route['workspace_id'] == wid and route['email'] == command['email'] and route['namespace'] == owner['namespace'] and
                 route['backend_address'] == owner['address'] and route['enabled'] is True)
            with sqlite3.connect('file:/var/lib/hapi-control-plane/revoked.sqlite3?mode=ro', uri=True) as db:
                db.row_factory = sqlite3.Row
                saved = db.execute('SELECT * FROM verified_enrollments WHERE request_id=? AND nonce_sha256=?',
                    (owner['request_id'], proof['nonce_sha256'])).fetchone()
                need(saved is not None and dict(saved) == proof)
            candidate = active_config(config, route, proof)
        else:
            candidate = copy.deepcopy(config)
            candidate['enrollments'] = [e for e in candidate.get('enrollments', []) if e['workspace_id'] != wid]
            for route in candidate['routes']:
                if route['workspace_id'] == wid:
                    need(route['email'] == command['email'])
                    previous_fingerprint = digest(route)
                    route['enabled'] = False
                    blocked_fingerprints = (previous_fingerprint, digest(route))
        stage = OWNERS / (wid + '-config.json');stage.write_bytes(encoded(candidate))
        auth.load_config(stage)
        if action == 'enable':
            need(command['expected_config_digest'] == digest(config))
            proxy = OWNERS / (wid + '-proxy.conf');proxy.write_text(command['proxy_config'])
            run('/usr/sbin/nginx', '-t', '-c', str(proxy), '-p', '/run/hapi-control-proxy/')
            tokens = GATEWAY / 'tokens' / wid
            token = command['api_token']
            need(re.fullmatch(r'[A-Za-z0-9_-]{32,256}', token))
            registered = [r for r in read(HUB / 'credentials.json')['credentials'] if r['id'] == 'hapi-' + wid]
            need(len(registered) == 1 and registered[0]['namespace'] == owner['namespace'] and
                 registered[0]['token'] == token and registered[0]['enabled'])
            if tokens.exists():
                need(tokens.read_text().strip() == token)
            else:
                atomic(tokens, (token + '\n').encode(), pwd.getpwnam('hapi-auth').pw_uid,
                       grp.getgrnam('hapi-proxy').gr_gid, 0o600)
            atomic(Path('/etc/hapi-control-plane/nginx.conf'), command['proxy_config'].encode())
        if candidate != config:
            atomic(GATEWAY / 'config.json', encoded(candidate));changed = True
        if action == 'block' and blocked_fingerprints and blocked_fingerprints[0] != blocked_fingerprints[1]:
            # Access is already closed by the authoritative registry above.
            # Keep the private bridge fingerprint in sync for an idempotent retry.
            live_proxy = GATEWAY / 'nginx.conf'
            text = live_proxy.read_text()
            if text.count(blocked_fingerprints[0]) == 1:
                new_proxy = text.replace(blocked_fingerprints[0], blocked_fingerprints[1])
                check = OWNERS / (wid + '-blocked-proxy.conf');check.write_text(new_proxy)
                run('/usr/sbin/nginx', '-t', '-c', str(check), '-p', '/run/hapi-control-proxy/')
                atomic(live_proxy, new_proxy.encode())
                run('/usr/sbin/runuser', '-u', 'hapi-proxy', '--', '/usr/sbin/nginx', '-s', 'reload',
                    '-c', str(live_proxy), '-p', '/run/hapi-control-proxy/')
        if action == 'enable':
            run('/usr/sbin/runuser', '-u', 'hapi-proxy', '--', '/usr/sbin/nginx', '-s', 'reload',
                '-c', '/etc/hapi-control-plane/nginx.conf', '-p', '/run/hapi-control-proxy/')
    else:
        with sqlite3.connect('file:/var/lib/hapi-control-plane/revoked.sqlite3?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            proof = db.execute('SELECT * FROM verified_enrollments WHERE request_id=?', (owner['request_id'],)).fetchone()
        print(json.dumps({'proof': dict(proof) if proof else None}));return
    print(json.dumps({'changed': changed, 'workspace_id': wid}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('HAPI VM500 registration refused; no secret values logged') from None
