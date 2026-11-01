#!/usr/bin/python3
"""Check live PVE allocations before HAPI writes; never persist raw VM config."""
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import sys

spec = importlib.util.spec_from_file_location('boundary', Path(__file__).with_name('hapi-network.py'))
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)


def properties(value):
    result = {}
    for field in value.split(','):
        key, separator, item = field.partition('=')
        boundary.require(separator and key not in result, 'Malformed guest network property')
        result[key] = item
    return result


def collect(c, api):
    guests = []
    for row in api('get', '/cluster/resources', type='vm'):
        boundary.require(row.get('type') in ('qemu', 'lxc'), 'Unknown guest type in cluster snapshot')
        node, vmid = row['node'], row['vmid']
        boundary.require(re.fullmatch(r'[a-z][a-z0-9-]{0,31}', node) and
                         type(vmid) is int and vmid > 0, 'Invalid cluster guest reference')
        raw = api('get', f'/nodes/{node}/{row["type"]}/{vmid}/config')
        # The API also returns credential fields. Retain only topology and gate
        # properties in memory and do not log or serialize the raw response.
        config = {key: value for key, value in raw.items()
                  if key in ('name', 'hostname', 'onboot', 'hookscript', 'args') or
                  re.fullmatch(r'(?:net|ipconfig|hostpci|usb)[0-9]+', key)}
        if 'args' in config:
            config['args'] = bool(config['args'])
        guests.append({'node': node, 'vmid': vmid, 'type': row['type'], 'config': config})
    links = json.loads(boundary.run('ip', '-d', '-j', 'address', 'show'))
    return {'guests': guests, 'links': links}


def check(c, snapshot):
    access_bridge = c.get('attachment') == 'access-bridge'
    boundary.require(set(snapshot) == {'guests', 'links'} and
                     isinstance(snapshot['guests'], list) and isinstance(snapshot['links'], list),
                     'Complete guest and host-link snapshots are required')
    occupied = set()
    for guest in snapshot['guests']:
        boundary.require(set(guest) == {'node', 'vmid', 'type', 'config'} and
                         guest['type'] in ('qemu', 'lxc') and isinstance(guest['config'], dict) and
                         type(guest['vmid']) is int and guest['vmid'] > 0 and
                         re.fullmatch(r'[a-z][a-z0-9-]{0,31}', guest['node']), 'Incomplete guest snapshot')
        vmid, config = guest['vmid'], guest['config']
        boundary.require(vmid not in occupied, 'Duplicate VMID in cluster snapshot')
        occupied.add(vmid)
        for w in c['workspaces']:
            own = vmid == w['vmid']
            if own:
                boundary.require(guest['node'] == c['node'] and guest['type'] == 'qemu',
                                 'Workspace VMID is occupied on another node or by an LXC')
                boundary.binding(c, w, config)
            else:
                boundary.require(config.get('name', config.get('hostname')) != 'hapi-' + w['id'],
                                 'Workspace name is occupied by another guest')
            subnet = ipaddress.ip_interface(w['address']).network
            for key, value in config.items():
                if not re.fullmatch(r'(?:net|ipconfig)[0-9]+', key):
                    continue
                values = properties(value)
                if key.startswith('net'):
                    macs = [v.lower() for v in values.values()
                            if re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', v)]
                    boundary.require(own or w['mac'] not in macs, 'Workspace MAC is already allocated')
                    boundary.require(access_bridge or own or values.get('bridge') != w['vnet'], 'Workspace VNet is used by another guest')
                    # Native tagged/trunk guests also occupy the approved bridge's VLAN.
                    if not access_bridge and values.get('bridge') == c['bridge']:
                        ranges = values.get('trunks', '').split(';') + [values.get('tag', '')]
                        for item in filter(None, ranges):
                            limits = item.split('-')
                            boundary.require(len(limits) in (1, 2) and all(x.isdigit() for x in limits),
                                             'Cannot inspect a guest VLAN allocation')
                            low, high = int(limits[0]), int(limits[-1])
                            boundary.require(not low <= w['vlan'] <= high, 'VLAN is used by a native guest NIC')
                ip = values.get('ip')
                if ip and ip not in ('dhcp', 'manual'):
                    used = ipaddress.ip_interface(ip)
                    collision = used.ip == ipaddress.ip_interface(w['address']).ip if access_bridge else used.network.overlaps(subnet)
                    boundary.require(own or not collision,
                                     'Workspace subnet overlaps a declared guest address')
    links = snapshot['links']
    indexes = {link['ifindex']: link['ifname'] for link in links}
    trunk = next((link for link in links if link['ifname'] == c['bridge']), None)
    boundary.require(trunk is not None, 'Reviewed trunk is absent from the live host snapshot')
    for link in links:
        for w in c['workspaces']:
            subnet = ipaddress.ip_interface(w['address']).network
            for addr in link.get('addr_info', []):
                if addr.get('family') == 'inet':
                    collision = addr['local'] == str(ipaddress.ip_interface(w['address']).ip) if access_bridge else ipaddress.ip_address(addr['local']) in subnet
                    boundary.require(not collision,
                                     'Workspace subnet overlaps a PVE host address')
            info = link.get('linkinfo', {})
            if info.get('info_kind') != 'vlan':
                continue
            parent = link.get('link', indexes.get(link.get('link_index')))
            if parent == c['bridge'] and info.get('info_data', {}).get('id') == w['vlan']:
                boundary.require(link['ifname'] == c['bridge'] + '.' + str(w['vlan']) and
                                 link.get('master') == w['vnet'], 'VLAN is used by an unmanaged host interface')
    return boundary.digest(snapshot)


if __name__ == '__main__':
    try:
        boundary.require(len(sys.argv) == 3, 'Usage: hapi-preflight.py MANIFEST SNAPSHOT | collect MANIFEST')
        if sys.argv[1] == 'collect':
            def readonly_api(method, path, **fields):
                boundary.require(method == 'get', 'Read-only discovery cannot mutate PVE')
                args = ['pvesh', 'get', path, '--output-format', 'json']
                for key, value in fields.items():
                    args += ['--' + key, str(value)]
                return json.loads(boundary.run(*args))
            c = boundary.load(sys.argv[2])
            snapshot = collect(c, readonly_api)
            check(c, snapshot)
            print(json.dumps(snapshot, indent=2))
        else:
            print(check(boundary.load(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())))
    except (ValueError, KeyError, TypeError, OSError) as error:
        sys.exit('HAPI allocation check refused: ' + str(error))
