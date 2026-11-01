#!/usr/bin/python3
"""Create HAPI-owned VLAN VNets under the PVE SDN global lock."""
import importlib.util
import json
from pathlib import Path
import sys
import time

spec = importlib.util.spec_from_file_location('boundary', Path(__file__).with_name('hapi-network.py'))
boundary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boundary)
preflight_spec = importlib.util.spec_from_file_location('allocation', Path(__file__).with_name('hapi-preflight.py'))
allocation = importlib.util.module_from_spec(preflight_spec)
preflight_spec.loader.exec_module(allocation)


class SDN:
    def __init__(self, state):
        self.state = state
        self.token = None

    def snapshot(self, c):
        return allocation.collect(c, self.api)

    def api(self, method, path, **fields):
        if self.token and method in ('create', 'set', 'delete'):
            fields['lock-token'] = self.token
        args = ['pvesh', method, path, '--output-format', 'json']
        for key, value in fields.items():
            args += ['--' + key, str(value)]
        return json.loads(boundary.run(*args) or 'null')

    def inspect(self, collection, key, identifier, desired):
        rows = self.api('get', collection)
        current = next((r for r in rows if r[key] == identifier), None)
        ledger = json.loads(self.state.read_text()) if self.state.exists() else {}
        resource = collection + '/' + identifier
        if current is not None:
            boundary.require(ledger.get(resource) == desired, 'Refusing to adopt unowned SDN object')
            config = self.api('get', resource)
            boundary.require(all(str(config.get(k, 0 if v == 0 else '')) == str(v)
                                 for k, v in desired.items()), 'Owned SDN topology drift')
            return True
        boundary.require(resource not in ledger or ledger[resource] == desired, 'SDN allocation changed')
        return False

    def ensure(self, collection, key, identifier, desired):
        if self.inspect(collection, key, identifier, desired):
            return False
        ledger = json.loads(self.state.read_text()) if self.state.exists() else {}
        resource = collection + '/' + identifier
        # Record intent before the API write so a successful write followed by a
        # lost response can be reconciled, never silently assigned to someone else.
        boundary.require(resource not in ledger or ledger[resource] == desired, 'SDN allocation changed')
        ledger[resource] = desired
        boundary.atomic(self.state, ledger)
        self.api('create', collection, **{key: identifier}, **desired)
        return True

    def reconcile(self, c):
        if c.get('attachment') == 'access-bridge':
            snapshot = self.snapshot(c)
            allocation.check(c, snapshot)
            bridge = self.api('get', f'/nodes/{c["node"]}/network/{c["bridge"]}')
            boundary.require(bridge.get('type') == 'bridge' and bridge.get('active'), 'Existing access bridge is not active')
            return False
        # Older PVE versions lacking this lock fail before any resource write.
        self.token = self.api('create', '/cluster/sdn/lock', **{'allow-pending': 0})
        boundary.require(isinstance(self.token, str) and self.token, 'SDN lock token unavailable')
        operation = self.state.with_name('sdn-operation.json')
        stage = 'preflight'
        def checkpoint(status, **fields):
            boundary.atomic(operation, {'manifest': boundary.digest(c), 'stage': stage, 'status': status, **fields})
        try:
            checkpoint('running')
            snapshot = self.snapshot(c)
            snapshot_digest = allocation.check(c, snapshot)
            bridge = self.api('get', f'/nodes/{c["node"]}/network/{c["bridge"]}')
            boundary.require(bridge.get('type') == 'bridge' and int(bridge.get('bridge_vlan_aware', 0)) == 1,
                             'Reviewed trunk must already be VLAN-aware')
            zones = self.api('get', '/cluster/sdn/zones')
            vn = self.api('get', '/cluster/sdn/vnets')
            on_bridge = {z['zone'] for z in zones if z.get('bridge') == c['bridge']}
            for w in c['workspaces']:
                if any(link['ifname'] == w['vnet'] for link in snapshot['links']):
                    boundary.require(any(v['vnet'] == w['vnet'] for v in vn),
                                     'Refusing to adopt an unmanaged host VNet bridge')
                for v in vn:
                    boundary.require(not (v.get('zone') in on_bridge and int(v.get('tag', 0)) == w['vlan'])
                                     or v['vnet'] == w['vnet'], 'VLAN is owned by a different VNet')
            objects = [('/cluster/sdn/zones', 'zone', 'hapi',
                        {'type': 'vlan', 'bridge': c['bridge'], 'nodes': c['node']})]
            objects += [('/cluster/sdn/vnets', 'vnet', w['vnet'],
                         {'zone': 'hapi', 'tag': w['vlan'], 'vlanaware': 0, 'alias': 'hapi:' + w['id']})
                        for w in c['workspaces']]
            for obj in objects:
                self.inspect(*obj)
            stage = 'staging'
            checkpoint('running', snapshot=snapshot_digest)
            changed = False
            for obj in objects:
                changed |= self.ensure(*obj)
            if changed:
                stage = 'applying'
                checkpoint('running', snapshot=snapshot_digest)
                upid = self.api('set', '/cluster/sdn', **{'release-lock': 0})
                boundary.require(isinstance(upid, str) and upid.startswith('UPID:'), 'SDN apply task unavailable')
                deadline = time.monotonic() + 120
                while True:
                    task_node = upid.split(':')[1]
                    status = self.api('get', f'/nodes/{task_node}/tasks/{upid}/status')
                    if status.get('status') == 'stopped':
                        boundary.require(status.get('exitstatus') == 'OK', 'SDN apply failed; inspect pending state')
                        break
                    boundary.require(time.monotonic() < deadline, 'SDN apply timed out; reconcile before retry')
                    time.sleep(1)
            stage = 'sdn-config-applied'
            checkpoint('complete', snapshot=snapshot_digest, network_ready=False)
            return changed
        except Exception:
            checkpoint('failed', network_ready=False)
            raise
        finally:
            self.api('delete', '/cluster/sdn/lock')
            self.token = None


if __name__ == '__main__':
    try:
        boundary.require(len(sys.argv) == 2, 'Supply the reviewed manifest')
        config = boundary.load(sys.argv[1])
        boundary.STATE.mkdir(parents=True, mode=0o700, exist_ok=True)
        print('changed' if SDN(boundary.STATE / 'sdn.json').reconcile(config) else 'unchanged')
    except Exception as error:
        print('HAPI SDN refused: ' + str(error), file=sys.stderr)
        sys.exit(1)
