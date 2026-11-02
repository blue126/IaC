#!/usr/bin/env python3
"""Version-one desktop contracts; no inventory ownership is duplicated here."""
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from urllib.parse import urlsplit


def require(ok, message):
    if not ok:
        raise ValueError(message)


def approved_vmids():
    # Explicit VMIDs plus the employee workspace VMID scheme (every workspace has a desktop).
    targets = json.loads(Path(__file__).with_name('desktop-targets.json').read_text())
    first, last = targets.get('approved_vmid_range', [0, -1])
    return sorted(set(targets['approved_vmids']) | set(range(first, last + 1)))


def validate_backends(config):
    backends = config['desktop_backends']
    expected = {str(n['vmid']): n for n in config['networks'].values()}
    require(type(backends) is dict and set(backends) == set(expected), 'Backend VMIDs must exactly match existing networks')
    generations = config.get('desktop_generations', {})
    require(type(generations) is dict, 'Generations must be a map')
    for vmid, backend in backends.items():
        common = {'type', 'address', 'port', 'client_path', 'route_enabled'}
        require(type(backend) is dict, 'Backend must be a map')
        kind = backend.get('type')
        require(kind in ('kasmvnc', 'legacy-novnc'), 'Explicit backend type required')
        fields = common | ({'generation_id', 'tls_server_name', 'trust_ref'} if kind == 'kasmvnc' else set())
        require(set(backend) == fields, 'Unexpected or missing backend fields')
        require(isinstance(backend['address'], str), 'Backend address must be a string')
        require(vmid in {str(value) for value in approved_vmids()} and backend['address'] == expected[vmid]['ip'] == '127.0.0.1', 'Only approved VM loopback is permitted')
        require(type(backend['port']) is int and backend['port'] == 8444, 'Backend port must be 8444')
        require(backend['client_path'] == '/', 'Client entry must be canonical root')
        require(type(backend['route_enabled']) is bool, 'Route state must be boolean')
        require(not backend['route_enabled'] or not expected[vmid]['disabled'], 'Disabled VM cannot have an enabled route')
        if kind == 'kasmvnc':
            generation = backend['generation_id']
            require(isinstance(generation, str) and re.fullmatch(r'g-[a-z0-9][a-z0-9-]{0,47}', generation) is not None, 'Require immutable generation ID; latest is forbidden')
            require(generation in generations, 'Missing pinned generation')
            entry = generations[generation]
            require(type(entry) is dict and set(entry) == {'vmid', 'trust_ref', 'certificate_ref', 'private_key_ref', 'authentication_ref'}, 'Generation must pin all material references')
            require(type(entry['vmid']) is int and str(entry['vmid']) == vmid, 'Generation VMID mismatch')
            require(backend['trust_ref'] == entry['trust_ref'], 'Generation trust mismatch')
            for field in ('trust_ref', 'certificate_ref', 'private_key_ref', 'authentication_ref'):
                require(entry[field] == f'generations/{generation}/{vmid}/' + {'trust_ref': 'ca.pem', 'certificate_ref': 'server.pem', 'private_key_ref': 'server.key', 'authentication_ref': 'authentication.json'}[field], 'Noncanonical material reference')
            require(backend['tls_server_name'] == 'localhost', 'Backend TLS identity mismatch')
    require(set(generations) == {b['generation_id'] for b in backends.values() if b['type'] == 'kasmvnc'}, 'Unreferenced generation')


def select_backend(config, device_name, target=None):
    validate_backends(config)
    device = config['devices'][device_name]
    net = config['networks'][device['employee']]
    vmid = str(net['vmid'])
    require(device['enabled'] and not net['disabled'], 'Device or employee disabled')
    require(target is None or str(target) == vmid, 'Target override denied')
    backend = config['desktop_backends'][vmid]
    require(backend['route_enabled'], 'Route disabled')
    return backend


def validate_open(request):
    require(type(request) is dict and set(request) == {'version', 'action', 'url'}, 'Invalid control fields')
    require(type(request['version']) is int and request['version'] == 1 and request['action'] == 'open', 'Unsupported control action')
    url = request['url']
    require(isinstance(url, str) and 0 < len(url) <= 4096 and not any(ord(c) <= 32 or ord(c) == 127 for c in url), 'Invalid URL encoding')
    parsed = urlsplit(url)
    require(parsed.scheme in ('http', 'https') and parsed.hostname and parsed.username is None and parsed.password is None and '\\' not in url, 'Require a web URL without credentials')
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError('Invalid URL port') from exc
    return url


def validate_session(session):
    require(type(session) is dict and set(session) == {'version', 'ready', 'display', 'xauthority', 'dbus_session_bus_address', 'xdg_runtime_dir'}, 'Invalid session fields')
    require(type(session['version']) is int and session['version'] == 1 and session['ready'] is True, 'Desktop not ready')
    require(isinstance(session['display'], str) and re.fullmatch(r':[0-9]+', session['display']) is not None, 'Invalid DISPLAY')
    for key in ('xauthority', 'xdg_runtime_dir'):
        require(isinstance(session[key], str) and session[key].startswith('/run/') and '..' not in Path(session[key]).parts, 'Invalid runtime path')
    bus = session['dbus_session_bus_address']
    address = re.fullmatch(r'unix:path=(/run/[A-Za-z0-9_./-]+)(?:,guid=[0-9a-fA-F]{32})?', bus) if isinstance(bus, str) else None
    require(address is not None and '..' not in Path(address.group(1)).parts, 'Invalid session bus')
    return {'DISPLAY': session['display'], 'XAUTHORITY': session['xauthority'], 'DBUS_SESSION_BUS_ADDRESS': session['dbus_session_bus_address'], 'XDG_RUNTIME_DIR': session['xdg_runtime_dir']}


def publish_session(path, session):
    validate_session(session)
    path = Path(path)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(session, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_transition(marker):
    require(type(marker) is dict and set(marker) == {'version', 'transaction_id', 'vmid', 'phase', 'from_generation', 'to_generation'}, 'Invalid transition fields')
    require(type(marker['version']) is int and marker['version'] == 1, 'Invalid transition version')
    try:
        require(str(uuid.UUID(marker['transaction_id'])) == marker['transaction_id'], 'Noncanonical transaction UUID')
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid transaction UUID') from None
    require(type(marker['vmid']) is int and marker['vmid'] > 0, 'Invalid transition VMID')
    require(marker['phase'] in ('transitioning', 'failed'), 'Invalid transition phase')
    for key in ('from_generation', 'to_generation'):
        require(isinstance(marker[key], str) and re.fullmatch(r'g-[a-z0-9][a-z0-9-]{0,47}', marker[key]) is not None, 'Pinned transition generation required')
    require(marker['from_generation'] != marker['to_generation'], 'Transition generations must differ')
    return marker


def external_start_exit(marker=None):
    # A marker blocks external start even if malformed; only internal lock holders recover it.
    return 75 if marker is not None else 0
