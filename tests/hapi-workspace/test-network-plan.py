#!/usr/bin/env python3
"""Exercise collision rejection, exact NIC gates and SDN failure/retry contracts."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'ansible/roles/hapi-network/files'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, FILES / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


network = module('network', 'hapi-network.py')
sdn = module('sdn', 'hapi-sdn.py')
allocation = module('allocation', 'hapi-preflight.py')
stage = module('stage', 'hapi-network-stage.py')
FIXTURE = json.loads(Path(__file__).with_name('network-fixture.json').read_text())


class FakePVE(sdn.SDN):
    def __init__(self, state):
        super().__init__(state)
        self.rows = {'/cluster/sdn/zones': [], '/cluster/sdn/vnets': []}
        self.writes = []
        self.fail_create = False
        self.pending = False
        self.live = {'guests': [], 'links': [{'ifindex': 1, 'ifname': 'vmbr77'}]}

    def snapshot(self, c):
        return copy.deepcopy(self.live)

    def api(self, method, path, **fields):
        if path == '/cluster/sdn/lock':
            if method == 'create':
                if self.pending:
                    raise ValueError('unrelated pending change')
                return 'fixture-token'
            self.writes.append(('unlock', path))
            return None
        if method == 'get':
            if '/network/' in path:
                return {'type': 'bridge', 'bridge_vlan_aware': 1, 'active': 1}
            if '/tasks/' in path:
                return {'status': 'stopped', 'exitstatus': 'OK'}
            if path in self.rows:
                return copy.deepcopy(self.rows[path])
            collection, identifier = path.rsplit('/', 1)
            key = 'zone' if collection.endswith('zones') else 'vnet'
            return copy.deepcopy(next(row for row in self.rows[collection] if row[key] == identifier))
        self.writes.append((method, path))
        if method == 'create':
            self.rows[path].append(copy.deepcopy(fields))
            if self.fail_create:
                self.fail_create = False
                raise OSError('response lost after create')
        if method == 'set':
            return 'UPID:fixture-pve:0:0:0:reloadnetworkall::root@pam:'


class NetworkPlanTest(unittest.TestCase):
    def setUp(self):
        self.c = copy.deepcopy(FIXTURE)

    def test_allocation_collisions_and_protected_identity_subnets(self):
        network.validate(self.c)
        for field in ('vmid', 'vnet', 'vlan', 'mac', 'address'):
            c = copy.deepcopy(self.c)
            c['workspaces'][1][field] = c['workspaces'][0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                network.validate(c)
        self.c['control_address'] = '10.77.1.1'
        with self.assertRaises(ValueError):
            network.validate(self.c)

    def test_reserved_vm_and_noncanonical_inputs(self):
        for update in ({'vmid': 502}, {'enabled': 'false'}, {'vlan': 1},
                       {'gateway': '10.77.1.2'}, {'mac': 'ff:ff:ff:ff:ff:ff'},
                       {'vnet': 'vmbr0;id'}, {'address': '8.8.8.8/30'}):
            c = copy.deepcopy(self.c)
            c['workspaces'][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                network.validate(c)

    def test_gate_rejects_additional_nics_trunks_and_unmanaged_qemu(self):
        w = self.c['workspaces'][0]
        config = {'name': 'hapi-alice', 'onboot': 0,
                  'hookscript': 'local:snippets/hapi-network-hook.py',
                  'net0': 'virtio=' + w['mac'].upper() + ',bridge=haalice',
                  'ipconfig0': 'ip=' + w['address'] + ',gw=' + w['gateway']}
        network.binding(self.c, w, config)
        network.binding(self.c, w, config | {'ipconfig0': 'gw=' + w['gateway'] + ',ip=' + w['address']})
        for update in ({'net1': 'virtio=00:00:00:00:00:01,bridge=vmbr0'},
                       {'net0': config['net0'] + ',trunks=771'},
                       {'net0': config['net0'] + ',tag=771'},
                       {'net0': config['net0'] + ',firewall=1'},
                       {'args': '-netdev user'}, {'onboot': 1},
                       {'name': 'unrelated'}, {'hostpci0': '0000:01:00.0'},
                       {'ipconfig0': 'ip=dhcp'}, {'hookscript': 'unknown'}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                network.binding(self.c, w, config | update)

    def test_sdn_idempotence_and_ownership(self):
        with tempfile.TemporaryDirectory() as temp:
            api = FakePVE(Path(temp) / 'state.json')
            self.assertTrue(api.reconcile(self.c))
            self.assertFalse(api.reconcile(self.c))
            api.rows['/cluster/sdn/vnets'][0]['tag'] = 999
            with self.assertRaises(ValueError):
                api.reconcile(self.c)
            other = FakePVE(Path(temp) / 'unowned.json')
            other.rows = copy.deepcopy(api.rows)
            with self.assertRaises(ValueError):
                other.reconcile(self.c)

    def test_sdn_pending_changes_block_all_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            api = FakePVE(Path(temp) / 'state.json')
            api.pending = True
            with self.assertRaises(ValueError):
                api.reconcile(self.c)
            self.assertEqual(api.writes, [])

    def test_lost_api_response_preserves_allocation_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            api = FakePVE(Path(temp) / 'state.json')
            api.fail_create = True
            with self.assertRaises(OSError):
                api.reconcile(self.c)
            self.assertEqual(api.writes[-1][0], 'unlock')
            # A real PVE pending configuration blocks retry until inspected.
            api.pending = True
            with self.assertRaises(ValueError):
                api.reconcile(self.c)
            api.pending = False
            self.assertTrue(api.reconcile(self.c))
            self.assertEqual(len(api.rows['/cluster/sdn/zones']), 1)
            self.assertEqual(len(api.rows['/cluster/sdn/vnets']), 2)

    def test_live_collisions_block_sdn_writes_and_checkpoint_failure(self):
        cases = [
            {'node': 'other-node', 'vmid': 7701, 'type': 'qemu', 'config': {}},
            {'node': 'fixture-pve', 'vmid': 8801, 'type': 'qemu', 'config': {'name': 'hapi-alice'}},
            {'node': 'other-node', 'vmid': 8801, 'type': 'qemu',
             'config': {'net0': 'virtio=02:00:00:77:01:02,bridge=vmbr0'}},
            {'node': 'other-node', 'vmid': 8801, 'type': 'lxc',
             'config': {'net0': 'name=eth0,hwaddr=02:00:00:77:01:99,ip=10.77.1.3/24'}},
            {'node': 'fixture-pve', 'vmid': 8801, 'type': 'qemu',
             'config': {'net0': 'virtio=02:00:00:77:01:99,bridge=vmbr77,trunks=760-780'}},
            {'node': 'fixture-pve', 'vmid': 8801, 'type': 'qemu',
             'config': {'net0': 'virtio=02:00:00:77:01:99,bridge=haalice'}}]
        for guest in cases:
            with self.subTest(guest=guest), tempfile.TemporaryDirectory() as temp:
                api = FakePVE(Path(temp) / 'state.json')
                api.live['guests'] = [guest]
                with self.assertRaises(ValueError):
                    api.reconcile(self.c)
                self.assertEqual(api.writes, [('unlock', '/cluster/sdn/lock')])
                checkpoint = json.loads((Path(temp) / 'sdn-operation.json').read_text())
                self.assertEqual((checkpoint['stage'], checkpoint['status']), ('preflight', 'failed'))
                self.assertFalse(checkpoint['network_ready'])

    def test_host_addresses_and_native_vlan_conflicts_are_rejected(self):
        snapshot = {'guests': [], 'links': [{'ifindex': 1, 'ifname': 'vmbr77'}]}
        allocation.check(self.c, snapshot)
        for link in [
            {'ifindex': 2, 'ifname': 'vmbr99', 'addr_info': [{'family': 'inet', 'local': '10.77.1.1'}]},
            {'ifindex': 2, 'ifname': 'unmanaged770', 'link_index': 1,
             'linkinfo': {'info_kind': 'vlan', 'info_data': {'id': 770}}}]:
            with self.subTest(link=link), self.assertRaises(ValueError):
                allocation.check(self.c, {'guests': [], 'links': snapshot['links'] + [link]})

    def test_completed_sdn_checkpoint_does_not_claim_network_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            api = FakePVE(Path(temp) / 'state.json')
            api.reconcile(self.c)
            state = json.loads((Path(temp) / 'sdn-operation.json').read_text())
            self.assertEqual((state['stage'], state['status']), ('sdn-config-applied', 'complete'))
            self.assertEqual(state['manifest'], network.digest(self.c))
            self.assertFalse(state['network_ready'])

    def test_unowned_vnet_is_rejected_before_creating_the_zone(self):
        with tempfile.TemporaryDirectory() as temp:
            api = FakePVE(Path(temp) / 'state.json')
            api.rows['/cluster/sdn/vnets'] = [{'vnet': 'haalice', 'zone': 'hapi', 'tag': 770}]
            with self.assertRaises(ValueError):
                api.reconcile(self.c)
            self.assertEqual(api.writes, [('unlock', '/cluster/sdn/lock')])

    def test_collection_minimizes_credential_fields(self):
        def api(method, path, **fields):
            self.assertEqual(method, 'get')
            if path == '/cluster/resources':
                return [{'node': 'fixture-pve', 'vmid': 8801, 'type': 'qemu'}]
            return {'name': 'unrelated', 'cipassword': 'SECRET-SENTINEL',
                    'sshkeys': 'SECRET-SENTINEL', 'args': '-secret SECRET-SENTINEL',
                    'net0': 'virtio=02:00:00:88:01:01,bridge=vmbr0'}
        with patch.object(allocation.boundary, 'run', return_value='[]'):
            snapshot = allocation.collect(self.c, api)
        self.assertNotIn('SECRET-SENTINEL', json.dumps(snapshot))
        self.assertIs(snapshot['guests'][0]['config']['args'], True)

    def test_failed_network_stages_preserve_active_manifest(self):
        for failed in ('preflight', 'sdn', 'apply', 'verify'):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temp:
                root, state = Path(temp), Path(temp) / 'state'
                old = json.dumps(self.c).encode()
                (root / 'manifest.json').write_bytes(old)
                candidate = copy.deepcopy(self.c)
                candidate['workspaces'][0]['enabled'] = False
                (root / 'candidate.json').write_text(json.dumps(candidate))
                with patch.object(stage.os, 'geteuid', return_value=0), \
                     patch.object(stage.boundary, 'preflight') as preflight, \
                     patch.object(stage.sdn.SDN, 'reconcile', return_value=True) as reconcile, \
                     patch.object(stage.boundary, 'apply', return_value=True) as apply, \
                     patch.object(stage.boundary, 'verify') as verify:
                    target = {'preflight': preflight, 'sdn': reconcile, 'apply': apply, 'verify': verify}[failed]
                    target.side_effect = ValueError('synthetic failure')
                    with self.assertRaises(ValueError):
                        stage.deploy(root / 'candidate.json', network.digest(self.c), root, state)
                    if failed == 'preflight':
                        reconcile.assert_not_called()
                    if failed in ('preflight', 'sdn'):
                        apply.assert_not_called()
                self.assertEqual((root / 'manifest.json').read_bytes(), old)
                checkpoint = json.loads((state / 'network-operation.json').read_text())
                self.assertEqual(checkpoint['status'], 'failed')
                self.assertFalse(checkpoint['public_entry_ready'])

    def test_stage_rechecks_existing_allocations_before_any_network_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'manifest.json').write_text(json.dumps(self.c))
            candidate = copy.deepcopy(self.c)
            candidate['workspaces'][0]['vmid'] = 8801
            (root / 'candidate.json').write_text(json.dumps(candidate))
            with patch.object(stage.os, 'geteuid', return_value=0), patch.object(stage.boundary, 'preflight') as preflight:
                with self.assertRaises(ValueError):
                    stage.deploy(root / 'candidate.json', network.digest(self.c), root, root / 'state')
                preflight.assert_not_called()

    def test_stale_enabled_snapshot_cannot_overwrite_another_deployment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            changed = copy.deepcopy(self.c)
            changed['workspaces'][0]['enabled'] = False
            (root / 'manifest.json').write_text(json.dumps(changed))
            stale = copy.deepcopy(self.c)
            stale['workspaces'][1]['enabled'] = False
            (root / 'candidate.json').write_text(json.dumps(stale))
            with patch.object(stage.os, 'geteuid', return_value=0), patch.object(stage.boundary, 'preflight') as preflight:
                with self.assertRaisesRegex(ValueError, 'Stale manifest baseline'):
                    stage.deploy(root / 'candidate.json', network.digest(self.c), root, root / 'state')
                preflight.assert_not_called()
            self.assertEqual(json.loads((root / 'manifest.json').read_text()), changed)

    def test_retry_after_success_does_not_require_a_new_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            changed = copy.deepcopy(self.c)
            changed['workspaces'][0]['enabled'] = False
            for name in ('manifest.json', 'candidate.json'):
                (root / name).write_text(json.dumps(changed))
            with patch.object(stage.os, 'geteuid', return_value=0), \
                 patch.object(stage.boundary, 'preflight'), \
                 patch.object(stage.sdn.SDN, 'reconcile', return_value=False), \
                 patch.object(stage.boundary, 'apply', return_value=False), patch.object(stage.boundary, 'verify'):
                self.assertFalse(stage.deploy(root / 'candidate.json', network.digest(self.c), root, root / 'state'))

    def test_existing_access_bridge_requires_trusted_peer_mac_and_ports(self):
        c = json.loads(Path(__file__).with_name('access-bridge-fixture.json').read_text())
        network.validate(c)
        for mutate in ('employee-uplink', 'wrong-gateway', 'duplicate-ip'):
            bad = copy.deepcopy(c)
            if mutate == 'employee-uplink':
                bad['trusted_peers'][0]['ports'] = ['tap7702i0']
            elif mutate == 'wrong-gateway':
                bad['trusted_peers'][0]['mac'] = '02:00:00:77:00:99'
            else:
                bad['workspaces'][1]['address'] = bad['workspaces'][0]['address']
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                network.validate(bad)

    def test_access_bridge_reads_live_allocations_without_sdn_writes(self):
        c = json.loads(Path(__file__).with_name('access-bridge-fixture.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            api = FakePVE(Path(temp) / 'state.json')
            api.live['guests'] = [{'node': 'fixture-pve', 'vmid': 8801, 'type': 'qemu',
                                  'config': {'net0': 'virtio=02:00:00:88:01:01,bridge=vmbr77',
                                             'ipconfig0': 'ip=192.168.77.99/24,gw=192.168.77.1'}}]
            self.assertFalse(api.reconcile(c))
            self.assertEqual(api.writes, [])
            api.live['guests'][0]['config']['ipconfig0'] = 'ip=192.168.77.2/24,gw=192.168.77.1'
            with self.assertRaises(ValueError):
                api.reconcile(c)

    def test_gate_binding_requires_stopped_exact_network_and_no_unknown_hook(self):
        w = self.c['workspaces'][0]
        config = {'name': 'hapi-alice', 'onboot': 0, 'digest': 'fixture-digest',
                  'net0': 'virtio=' + w['mac'] + ',bridge=haalice',
                  'ipconfig0': 'ip=' + w['address'] + ',gw=' + w['gateway']}
        for update, state, allowed in [({}, 'stopped', True), ({}, 'running', False),
                                        ({'hookscript': 'foreign:snippets/unknown.py'}, 'stopped', False),
                                        ({'net0': 'virtio=' + w['mac'] + ',bridge=vmbr0'}, 'stopped', False)]:
            calls = []
            def run(*args, input=None):
                if args[1] == 'set':
                    calls.append(args)
                    return 'null'
                if args[2].endswith('/qemu'):
                    return '[{"vmid":7701}]'
                if args[2].endswith('/config'):
                    return json.dumps(config | update)
                return json.dumps({'status': state})
            with self.subTest(update=update, state=state), patch.object(network, 'run', side_effect=run):
                if allowed:
                    self.assertTrue(network.bind_hooks(self.c))
                    self.assertEqual(len(calls), 1)
                    self.assertIn('fixture-digest', calls[0])
                else:
                    with self.assertRaises(ValueError):
                        network.bind_hooks(self.c)
                    self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
