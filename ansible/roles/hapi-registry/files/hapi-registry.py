#!/usr/bin/python3
"""Render VM500's per-employee HAPI registries from the executor's desired list (story 5.24).

stdin: {"static_ids": [...], "employees": [{id, email, address, token}]} — the D1 employee
catalog plus BWS Runner tokens. Entries listed in static_ids (the owner pilot) are kept as
they are; every other entry is exactly the employee list. Each file is validated with the
existing checkers before it replaces the live one. Prints {"changed": bool}."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CONFIG = Path('/etc/hapi-control-plane/config.json')
TOKENS = Path('/etc/hapi-control-plane/tokens')
CREDENTIALS = Path('/etc/hapi-shared-hub/credentials.json')
AGENTS = Path('/etc/hapi-shared-hub/agents.json')
# VM500's host firewall drops 9443 unless a worker rule names the source; this renderer owns those rules.
FIREWALL = Path('/etc/employee-access.nft')
WORKER_RULE = 'hapi-shared-hub-worker-'


def render(desired, config, credentials, agents):
    static = set(desired['static_ids'])
    employees = desired['employees']
    routes = [r for r in config['routes'] if r['workspace_id'] in static] + [
        {'workspace_id': e['id'], 'email': e['email'], 'subject': '', 'enabled': True, 'generation': 1,
         'backend_address': e['address'], 'backend_name': e['id'] + '.hapi.internal', 'namespace': e['id']}
        for e in employees]
    rows = [r for r in credentials['credentials'] if r['id'] in static] + [
        {'id': e['id'], 'token': e['token'], 'namespace': e['id'], 'generation': 1, 'enabled': True} for e in employees]
    workers = [a for a in agents['agents'] if a['id'] in static] + [
        {'id': e['id'], 'address': e['address'], 'namespace': e['id'], 'credential_id': e['id']} for e in employees]
    tokens = {e['id']: e['token'] for e in employees}
    return {**config, 'routes': routes}, {'version': 1, 'credentials': rows}, {'version': 1, 'agents': workers}, tokens


def firewall(current, agents, hub_address):
    """The host firewall with exactly one 9443 accept per worker address; other rules unchanged."""
    def worker(item):
        return item.get('add', {}).get('rule', {}).get('comment', '').startswith(WORKER_RULE)
    def match(protocol, field, value):
        return {'match': {'op': '==', 'left': {'payload': {'protocol': protocol, 'field': field}}, 'right': value}}
    rules = [item for item in current['nftables'] if not worker(item)]
    for address in sorted({a['address'] for a in agents['agents']}):
        rules.append({'add': {'rule': {'family': 'inet', 'table': 'employee_access', 'chain': 'input',
                                       'expr': [match('ip', 'saddr', address), match('ip', 'daddr', hub_address),
                                                match('tcp', 'dport', 9443), {'accept': None}],
                                       'comment': WORKER_RULE + address}}})
    return {**current, 'nftables': rules}


def stage(path, value, group, mode):
    """A validated-later candidate beside the live file; returns (temp path, changed)."""
    data = json.dumps(value, indent=2, sort_keys=True) + '\n'
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    with os.fdopen(fd, 'w') as stream:
        stream.write(data)
    os.chown(temp, 0, group); os.chmod(temp, mode)
    return temp, not path.exists() or path.read_text() != data


def check(argv):
    subprocess.run(argv, check=True, capture_output=True)


def main():
    import grp, pwd
    desired = json.load(sys.stdin)
    emails = [e['email'] for e in desired['employees']]
    if len(set(emails)) != len(emails):
        raise SystemExit('One HAPI route per email')
    config, credentials, agents, tokens = render(desired, json.loads(CONFIG.read_text()),
                                                 json.loads(CREDENTIALS.read_text()), json.loads(AGENTS.read_text()))
    rules = firewall(json.loads(FIREWALL.read_text()), agents, desired['hub_address'])
    proxy, hub = grp.getgrnam('hapi-proxy').gr_gid, grp.getgrnam('hapi-hub').gr_gid
    auth = pwd.getpwnam('hapi-auth').pw_uid
    staged = []
    try:
        # Every candidate is written and checked before any live file changes.
        for path, value, group in ((CREDENTIALS, credentials, hub), (AGENTS, agents, hub), (CONFIG, config, proxy)):
            staged.append((path,) + stage(path, value, group, 0o640))
        staged.append((FIREWALL,) + stage(FIREWALL, rules, 0, 0o600))
        check(['/usr/bin/python3', '/usr/local/lib/hapi-hub-config.py', 'credentials', staged[0][1]])
        check(['/usr/bin/python3', '/usr/local/lib/hapi-hub-config.py', 'agents', staged[1][1]])
        with tempfile.TemporaryDirectory() as bindings:
            for name, (_, temp, _) in zip(('credentials.json', 'agents.json'), staged[:2]):
                # The validator rejects world-readable files; these root-only copies are 0600.
                copy = Path(bindings, name); copy.write_text(Path(temp).read_text()); copy.chmod(0o600)
            check(['/usr/bin/python3', '/usr/local/lib/hapi-hub-config.py', 'bindings', bindings])
        check(['/usr/bin/python3', '/usr/local/lib/hapi-auth.py', '--check', '--config', staged[2][1]])
        check(['/usr/sbin/nft', '--check', '--json', '--file', staged[3][1]])
        changed = False
        # Tokens first: a new route must find its token when the snapshot names it.
        for wid, token in tokens.items():
            path = TOKENS / wid
            if not path.exists() or path.read_text() != token + '\n':
                fd, temp = tempfile.mkstemp(prefix='.' + wid + '.', dir=TOKENS)
                with os.fdopen(fd, 'w') as stream:
                    stream.write(token + '\n')
                os.chown(temp, auth, proxy); os.chmod(temp, 0o400); os.replace(temp, path); changed = True
        for path, temp, differs in staged:
            if differs:
                os.replace(temp, path); changed = True
        # The file is the whole ruleset (delete and re-add the table), so reloading is atomic and idempotent;
        # it runs every time so a rerun applies a file whose earlier reload failed.
        check(['/usr/bin/systemctl', 'reload', 'employee-firewall'])
        # A retired employee's token goes last, after no route names it.
        kept = {r['workspace_id'] for r in config['routes']}
        for path in TOKENS.iterdir():
            if path.name not in kept and not path.name.startswith('.'):
                path.unlink(); changed = True
    finally:
        for _, temp, _ in staged:
            if os.path.exists(temp):
                os.unlink(temp)
    print(json.dumps({'changed': changed}))


if __name__ == '__main__':
    main()
