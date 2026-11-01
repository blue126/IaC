#!/usr/bin/env python3
"""Real VLAN switches/nftables in disposable namespaces; never touch host links."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import tempfile
import time
import uuid

spec = importlib.util.spec_from_file_location('plan', Path(__file__).with_name('test-network-plan.py'))
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)
net = plan.network
SERVER = '''import socket,sys,threading
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('0.0.0.0',int(sys.argv[1])));s.listen();print('READY',flush=True)
def serve(c):
 try:
  while c.recv(4096): c.sendall(b'OK')
 except OSError: pass
 c.close()
while True:
 c,_=s.accept();threading.Thread(target=serve,args=(c,),daemon=True).start()
'''
CLIENT = '''import socket,sys
s=socket.socket();s.settimeout(0.4)
if len(sys.argv)>3:s.bind((sys.argv[3],0))
try:
 s.connect((sys.argv[1],int(sys.argv[2])));s.sendall(b'hi');assert s.recv(2)==b'OK'
except (OSError,AssertionError):sys.exit(1)
'''


def main():
    expected_unsupported = sys.argv[1:] == ['--run-isolated-netns', '--boundary-only', '--expect-no-bridge-conntrack']
    subset = sys.argv[1:] == ['--run-isolated-netns', '--boundary-only'] or expected_unsupported
    if os.geteuid() != 0 or (sys.argv[1:] != ['--run-isolated-netns'] and not subset) or not os.environ.get('SANDBOX_ID'):
        sys.exit('Run as root in the approved Sandbox with --run-isolated-netns')
    names = {k: 'hapi-test-' + uuid.uuid4().hex[:8] + '-' + k for k in ('pve', 'router', 'alice', 'bob')}
    created, processes = [], []
    passed = 0

    def run(*args, input=None, check=True):
        result = subprocess.run(args, input=input, text=True, capture_output=True)
        if check and result.returncode:
            raise RuntimeError(str(args) + ': ' + result.stderr)
        return result

    def ns(name, *args, **kwargs):
        return run('ip', 'netns', 'exec', names[name], *args, **kwargs)

    def link(left, iface, right, peer):
        ns(left, 'ip', 'link', 'add', iface, 'type', 'veth', 'peer', 'name', 'peer')
        ns(left, 'ip', 'link', 'set', 'peer', 'netns', names[right])
        ns(right, 'ip', 'link', 'set', 'peer', 'name', peer)
        for node, dev in [(left, iface), (right, peer)]:
            ns(node, 'ip', 'link', 'set', dev, 'up')

    def record(label, result):
        nonlocal passed
        if not result:
            raise AssertionError(label)
        passed += 1
        print('PASS ' + label, flush=True)

    def probe(label, source, target, port, allowed, bind=None):
        result = ns(source, sys.executable, '-c', CLIENT, target, str(port), *([bind] if bind else []), check=False)
        record(label, (result.returncode == 0) == allowed)

    def serve(name, port):
        process = subprocess.Popen(['ip', 'netns', 'exec', names[name], sys.executable, '-u', '-c', SERVER, str(port)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(process)
        ready, _, _ = select.select([process.stdout], [], [], 5)
        if not ready or process.stdout.readline().strip() != 'READY':
            raise AssertionError('Positive-control server did not start')

    def packet(label, expected, source_mac=None, source_ip=None, tag=None, arp=False):
        marker = b'HAPI-' + uuid.uuid4().hex.encode()
        listener_code = '''import socket,sys
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));s.bind(('wan.770',0));s.settimeout(0.5)
print('READY',flush=True)
try:
 while True:
  if bytes.fromhex(sys.argv[1]) in s.recv(65535):sys.exit(0)
except TimeoutError:sys.exit(1)
'''
        listener = subprocess.Popen(['ip', 'netns', 'exec', names['router'], sys.executable, '-u', '-c',
                                     listener_code, marker.hex()], stdout=subprocess.PIPE, text=True)
        processes.append(listener)
        assert listener.stdout.readline().strip() == 'READY'
        w = plan.FIXTURE['workspaces'][0]
        mac = bytes.fromhex((source_mac or w['mac']).replace(':', ''))
        gw = bytes.fromhex(w['gateway_mac'].replace(':', ''))
        if arp:
            payload = struct.pack('!HHBBH', 1, 0x800, 6, 4, 2) + mac + socket.inet_aton(source_ip or '10.77.1.2')
            payload += gw + socket.inet_aton('10.77.1.1') + marker
            ethertype = b'\x08\x06'
        else:
            udp = struct.pack('!HHHH', 41000, 41001, len(marker) + 8, 0) + marker
            header = struct.pack('!BBHHHBBH4s4s', 0x45, 0, len(udp) + 20, 1, 0, 64, 17, 0,
                                 socket.inet_aton(source_ip or '10.77.1.2'), socket.inet_aton('1.1.1.1'))
            total = sum(struct.unpack('!10H', header))
            total = (total & 65535) + (total >> 16)
            total = (total & 65535) + (total >> 16)
            payload = header[:10] + struct.pack('!H', ~total & 65535) + header[12:] + udp
            ethertype = b'\x08\x00'
        packet_bytes = gw + mac + (tag or b'') + ethertype + payload
        sender = "import socket,sys;s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW);s.bind(('eth0',0));s.send(bytes.fromhex(sys.argv[1]))"
        ns('alice', sys.executable, '-c', sender, packet_bytes.hex())
        record(label, (listener.wait(timeout=3) == 0) == expected)

    try:
        for key, name in names.items():
            run('ip', 'netns', 'add', name)
            created.append(name)
            ns(key, 'ip', 'link', 'set', 'lo', 'up')
        if not subset:
            ns('pve', 'ip', 'link', 'add', 'vmbr77', 'type', 'bridge', 'vlan_filtering', '1')
            ns('pve', 'ip', 'link', 'set', 'vmbr77', 'up')
            link('pve', 'trunk', 'router', 'wan')
            ns('pve', 'ip', 'link', 'set', 'trunk', 'master', 'vmbr77')
        for w in plan.FIXTURE['workspaces']:
            person, vid = w['id'], str(w['vlan'])
            if not subset:
                ns('pve', 'bridge', 'vlan', 'add', 'dev', 'trunk', 'vid', vid)
                ns('pve', 'bridge', 'vlan', 'add', 'dev', 'vmbr77', 'vid', vid, 'self')
            ns('pve', 'ip', 'link', 'add', w['vnet'], 'type', 'bridge')
            ns('pve', 'ip', 'link', 'set', w['vnet'], 'up')
            if subset:
                link('pve', 'gwport' + vid, 'router', 'wan.' + vid)
                ns('pve', 'ip', 'link', 'set', 'gwport' + vid, 'master', w['vnet'])
                ns('router', 'ip', 'link', 'set', 'wan.' + vid, 'address', w['gateway_mac'])
                ns('router', 'ip', 'addr', 'add', w['gateway'] + '/30', 'dev', 'wan.' + vid)
            else:
                for node, parent in [('pve', 'vmbr77'), ('router', 'wan')]:
                    dev = parent + '.' + vid
                    ns(node, 'ip', 'link', 'add', 'link', parent, 'name', dev, 'type', 'vlan', 'id', vid)
                    if node == 'pve':
                        ns(node, 'ip', 'link', 'set', dev, 'master', w['vnet'])
                    else:
                        ns(node, 'ip', 'link', 'set', dev, 'address', w['gateway_mac'])
                        ns(node, 'ip', 'addr', 'add', w['gateway'] + '/30', 'dev', dev)
                    ns(node, 'ip', 'link', 'set', dev, 'up')
            tap = 'tap' + str(w['vmid']) + 'i0'
            link(person, 'eth0', 'pve', tap)
            ns('pve', 'ip', 'link', 'set', tap, 'master', w['vnet'])
            ns(person, 'ip', 'link', 'set', 'eth0', 'address', w['mac'])
            ns(person, 'ip', 'addr', 'add', w['address'], 'dev', 'eth0')
            ns(person, 'ip', 'route', 'add', 'default', 'via', w['gateway'])
            serve(person, 9443)
            serve(person, 22)
        ns('router', 'sysctl', '-w', 'net.ipv4.ip_forward=1')
        for ip in ['1.1.1.1', '10.90.0.10', '10.90.0.20', '10.90.0.30', '203.0.113.70']:
            ns('router', 'ip', 'addr', 'add', ip + '/32', 'dev', 'lo')
        for port in [18080, 9443, 22]:
            serve('router', port)
        probe('positive-public', 'alice', '1.1.1.1', 18080, True)
        probe('positive-cross-workspace-before-policy', 'alice', '10.77.2.2', 22, True)
        probe('positive-management-before-policy', 'alice', '10.90.0.30', 18080, True)
        packet('positive-tagged-frame-before-policy', True, tag=bytes.fromhex('81000303'))
        c = copy.deepcopy(plan.FIXTURE)
        with tempfile.TemporaryDirectory(prefix='hapi-net-kernel-') as temp:
            net.STATE = Path(temp)
            def executor(*args, input=None):
                return ns('pve', *args, input=input).stdout
            net.run = executor
            if expected_unsupported:
                before = executor('nft', '-j', 'list', 'ruleset')
                try:
                    net.preflight(c)
                    raise AssertionError('Expected the unsupported bridge conntrack check to fail')
                except RuntimeError as error:
                    record('unsupported-bridge-conntrack-denied', 'Protocol error' in str(error))
                record('preflight-left-kernel-rules-unchanged', before == executor('nft', '-j', 'list', 'ruleset'))
                root = Path(temp)
                current = root / 'manifest.json'
                current.write_text(json.dumps(c))
                prior = current.read_bytes()
                candidate = copy.deepcopy(c)
                candidate['workspaces'][0]['enabled'] = False
                (root / 'candidate.json').write_text(json.dumps(candidate))
                plan.stage.boundary.run = executor
                with plan.patch.object(plan.stage.sdn.SDN, 'reconcile') as reconcile:
                    try:
                        plan.stage.deploy(root / 'candidate.json', net.digest(c), root, root / 'stage-state')
                        raise AssertionError('Network stage accepted an unsupported kernel')
                    except RuntimeError as error:
                        record('real-stage-refuses-unsupported-kernel', 'Protocol error' in str(error))
                    record('real-stage-never-reached-sdn-writes', not reconcile.called)
                failed = json.loads((root / 'stage-state/network-operation.json').read_text())
                record('real-stage-preserved-live-manifest-and-recorded-failure',
                       current.read_bytes() == prior and failed['stage'] == 'kernel-preflight' and
                       failed['status'] == 'failed' and not failed['public_entry_ready'])
                print(json.dumps({'passed': passed, 'full_boundary_verified': False,
                                  'blocked': 'Sandbox kernel lacks VLAN and bridge conntrack support'}))
                return
            record('actual-kernel-apply', net.apply(c))
            net.verify(c)
            record('idempotent-kernel-apply', not net.apply(c))
            probe('development-egress', 'alice', '1.1.1.1', 18080, True)
            probe('other-employee-egress', 'bob', '1.1.1.1', 18080, True)
            probe('deny-cross-workspace', 'alice', '10.77.2.2', 22, False)
            probe('deny-management', 'alice', '10.90.0.30', 18080, False)
            probe('deny-gateway-management', 'alice', '10.77.1.1', 22, False)
            probe('deny-protected-public-hairpin', 'alice', '203.0.113.70', 18080, False)
            probe('control-mtls-service', 'router', '10.77.1.2', 9443, True, '10.90.0.10')
            probe('control-cannot-ssh', 'router', '10.77.1.2', 22, False, '10.90.0.10')
            probe('administrator-ssh', 'router', '10.77.1.2', 22, True, '10.90.0.20')
            probe('unknown-source-denied', 'router', '10.77.1.2', 9443, False, '10.90.0.30')
            packet('valid-unicast-packet', True)
            packet('deny-ip-spoofing', False, source_ip='10.90.0.10')
            packet('deny-mac-spoofing', False, source_mac='02:00:00:77:01:99')
            packet('deny-vlan-injection', False, tag=bytes.fromhex('81000303'))
            packet('deny-qinq-injection', False, tag=bytes.fromhex('88a8030381000302'))
            packet('deny-arp-spoofing', False, arp=True, source_ip='10.77.1.1')
            ns('pve', 'nft', 'insert', 'rule', 'bridge', 'hapi_7701', 'guest_out', 'accept')
            try:
                net.verify(c, 7701)
                raise AssertionError('Drift was accepted')
            except ValueError:
                record('kernel-drift-blocks-start-verification', True)
            record('repair-owned-rule-drift', net.apply(c))
            # Disabling one employee must also stop an already established flow.
            code = "import socket,sys;s=socket.create_connection(('1.1.1.1',18080));s.settimeout(.6);s.sendall(b'hi');assert s.recv(2)==b'OK';print('READY',flush=True);sys.stdin.readline();\ntry:\n s.sendall(b'hi');sys.exit(1 if s.recv(2)==b'OK' else 0)\nexcept OSError:sys.exit(0)"
            active = subprocess.Popen(['ip', 'netns', 'exec', names['alice'], sys.executable, '-u', '-c', code],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            processes.append(active)
            assert active.stdout.readline().strip() == 'READY'
            c['workspaces'][0]['enabled'] = False
            net.apply(c)
            active.stdin.write('check\n')
            active.stdin.flush()
            record('disable-cuts-existing-egress', active.wait(timeout=3) == 0)
            probe('disabled-employee-denied', 'alice', '1.1.1.1', 18080, False)
            probe('other-employee-preserved', 'bob', '1.1.1.1', 18080, True)
            net.verify(c)
        print(json.dumps({'passed': passed, 'vlan_filtering_tested': not subset,
                          'vlan_encapsulation_tested': not subset,
                          'scope': 'isolated Linux bridge/nft, not live PVE/router acceptance'}))
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for name in reversed(created):
            run('ip', 'netns', 'delete', name, check=False)


if __name__ == '__main__':
    main()
