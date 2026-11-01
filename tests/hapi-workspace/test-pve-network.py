#!/usr/bin/env python3
"""Exercise only the two explicitly allocated HAPI test VMs on real pve2."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import select
import shlex
import socket
import struct
import subprocess
import sys
import time
import uuid

SERVER = '''import socket,threading
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('0.0.0.0',9443));s.listen()
def serve(c):
 try:
  while True:
   data=c.recv(4096)
   if not data:break
   c.sendall(data)
 except OSError:pass
 c.close()
while True:
 c,_=s.accept();threading.Thread(target=serve,args=(c,),daemon=True).start()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--run-real-pve', action='store_true')
    args = parser.parse_args()
    if not args.run_real_pve or not os.environ.get('SANDBOX_ID'):
        sys.exit('Use the authorized task Sandbox and --run-real-pve')
    root = args.runtime
    c = json.loads((root / 'manifest.json').read_text())
    assert c['node'] == 'pve2' and c['attachment'] == 'access-bridge'
    assert {(w['id'], w['vmid']) for w in c['workspaces']} == {('test-alice', 9101), ('test-bob', 9102)}
    known = root / 'known-hosts'
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
           '-o', 'UserKnownHostsFile=' + str(known), '-o', 'ConnectTimeout=8', 'root@192.168.1.52']
    results, started_servers = [], []
    report = {'scope': 'real-pve-two-vm-access-bridge', 'vlan_verified': False, 'public_entry_ready': False}

    def pve(*argv, check=True):
        return subprocess.run(ssh + [shlex.join(argv)], capture_output=True, text=True, check=check)

    def guest(vmid, *argv):
        result = json.loads(pve('qm', 'guest', 'exec', str(vmid), '--', *argv).stdout)
        if result.get('exitcode') != 0:
            raise RuntimeError('Guest command failed: ' + result.get('err-data', '')[:300])
        return result.get('out-data', '')

    def record(case, actual, expected=True):
        results.append({'case': case, 'actual': actual, 'expected': expected})
        print(('PASS ' if actual == expected else 'FAIL ') + case, flush=True)
        if actual != expected:
            raise AssertionError(case)

    def probe(vmid, address, port, allowed):
        code = 'import socket,json\ntry:\n s=socket.create_connection((' + repr(address) + ',' + str(port) + '),timeout=1);s.close();print("true")\nexcept OSError:print("false")'
        record(f'{vmid}-tcp-{address}:{port}', json.loads(guest(vmid, 'python3', '-c', code)), allowed)

    def frame(w, interface, label, *, source_mac=None, source_ip=None, tag=b'', arp=False, ipv6=False, destination='1.1.1.1', expected=False):
        marker = b'HAPI-TEST-' + uuid.uuid4().hex.encode()
        capture = '''import socket,sys,time
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));s.bind((sys.argv[1],0));s.settimeout(3)
marker=bytes.fromhex(sys.argv[2]);deadline=time.monotonic()+3;print('READY',flush=True)
try:
 while time.monotonic()<deadline:
  s.settimeout(max(.01,deadline-time.monotonic()))
  if marker in s.recv(65535):sys.exit(0)
except TimeoutError:sys.exit(1)
sys.exit(1)
'''
        listener = subprocess.Popen(ssh + [shlex.join(['python3', '-u', '-c', capture, c['trusted_peers'][0]['ports'][0], marker.hex()])],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready, _, _ = select.select([listener.stdout], [], [], 10)
            assert ready and listener.stdout.readline().strip() == 'READY', 'Physical-uplink capture unavailable'
            mac = bytes.fromhex((source_mac or w['mac']).replace(':', ''))
            gateway = bytes.fromhex(w['gateway_mac'].replace(':', ''))
            source = source_ip or str(ipaddress.ip_interface(w['address']).ip)
            if arp:
                payload = struct.pack('!HHBBH', 1, 0x800, 6, 4, 2) + mac + socket.inet_aton(source)
                payload += gateway + socket.inet_aton(w['gateway']) + marker
                ethertype = b'\x08\x06'
            elif ipv6:
                payload = struct.pack('!IHBB16s16s', 6 << 28, len(marker), 59, 64,
                                      socket.inet_pton(socket.AF_INET6, 'fd77::2'), socket.inet_pton(socket.AF_INET6, 'fd77::1')) + marker
                ethertype = b'\x86\xdd'
            else:
                udp = struct.pack('!HHHH', 41000, 41001, len(marker) + 8, 0) + marker
                header = struct.pack('!BBHHHBBH4s4s', 0x45, 0, len(udp) + 20, 1, 0, 64, 17, 0,
                                     socket.inet_aton(source), socket.inet_aton(destination))
                total = sum(struct.unpack('!10H', header))
                total = (total & 65535) + (total >> 16)
                total = (total & 65535) + (total >> 16)
                payload = header[:10] + struct.pack('!H', ~total & 65535) + header[12:] + udp
                ethertype = b'\x08\x00'
            raw = gateway + mac + tag + ethertype + payload
            sender = 'import socket,sys;s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW);s.bind((sys.argv[1],0));s.send(bytes.fromhex(sys.argv[2]))'
            guest(w['vmid'], 'python3', '-c', sender, interface, raw.hex())
            record(label, listener.wait(timeout=8) == 0, expected)
        finally:
            if listener.poll() is None:
                listener.terminate()
                listener.wait(timeout=5)

    try:
        for w in c['workspaces']:
            config = json.loads(pve('pvesh', 'get', f'/nodes/pve2/qemu/{w["vmid"]}/config', '--output-format', 'json').stdout)
            assert config['name'] == 'hapi-' + w['id'] and 'hapi-network-test' in config.get('tags', '')
            pve('python3', '/usr/local/lib/hapi-network.py', 'hook', '--vmid', str(w['vmid']))
            status = json.loads(pve('pvesh', 'get', f'/nodes/pve2/qemu/{w["vmid"]}/status/current', '--output-format', 'json').stdout)
            if status['status'] == 'stopped':
                pve('qm', 'start', str(w['vmid']))
            deadline = time.monotonic() + 300
            while pve('qm', 'guest', 'cmd', str(w['vmid']), 'ping', check=False).returncode:
                if time.monotonic() > deadline:
                    raise TimeoutError('Guest agent/bootstrap not ready for ' + str(w['vmid']))
                time.sleep(3)
            record(str(w['vmid']) + '-cloud-init', 'done' in guest(w['vmid'], 'cloud-init', 'status', '--wait'))
            record(str(w['vmid']) + '-sudo-root', guest(w['vmid'], 'sudo', '-u', 'ubuntu', 'sudo', '-n', 'id', '-u').strip() == '0')
            key = guest(w['vmid'], 'cat', '/etc/ssh/ssh_host_ed25519_key.pub').strip()
            assert key.startswith('ssh-ed25519 ') and len(key.split()) >= 2
            with known.open('a') as stream:
                stream.write(str(ipaddress.ip_interface(w['address']).ip) + ' ' + ' '.join(key.split()[:2]) + '\n')
            admin_ssh = ssh[:-1] + ['ubuntu@' + str(ipaddress.ip_interface(w['address']).ip), 'true']
            record(str(w['vmid']) + '-approved-admin-ssh', subprocess.run(admin_ssh, capture_output=True).returncode == 0)
            guest(w['vmid'], 'python3', '-c', 'import subprocess;subprocess.run(["nft","flush","ruleset"],check=True)')
            record(str(w['vmid']) + '-public-egress', 'true' in guest(w['vmid'], 'python3', '-c', 'import socket;socket.create_connection(("1.1.1.1",443),timeout=4).close();print("true")'))
            record(str(w['vmid']) + '-dns', bool(guest(w['vmid'], 'python3', '-c', 'import socket;print(socket.getaddrinfo("example.com",443))').strip()))
            guest(w['vmid'], 'systemd-run', '--unit=hapi-network-test-peer', '--collect', '--property=RuntimeMaxSec=1800', '/usr/bin/python3', '-u', '-c', SERVER)
            started_servers.append(w['vmid'])
            probe(w['vmid'], '127.0.0.1', 9443, True)
            probe(w['vmid'], '192.168.1.52', 22, False)
            probe(w['vmid'], '192.168.1.52', 8006, False)
            probe(w['vmid'], w['gateway'], 22, False)
        alice, bob = c['workspaces']
        for w in c['workspaces']:
            probe(500, str(ipaddress.ip_interface(w['address']).ip), 9443, True)
        for w, other in [(alice, bob), (bob, alice)]:
            ip = str(ipaddress.ip_interface(other['address']).ip)
            dev = json.loads(guest(w['vmid'], 'ip', '-j', 'link', 'show'))
            interface = next(link['ifname'] for link in dev if link.get('address') == w['mac'])
            guest(w['vmid'], 'ip', 'neigh', 'replace', ip, 'lladdr', other['mac'], 'nud', 'permanent', 'dev', interface)
            try:
                probe(w['vmid'], ip, 22, False)
                probe(w['vmid'], ip, 9443, False)
            finally:
                guest(w['vmid'], 'ip', 'neigh', 'del', ip, 'dev', interface)
        dev = json.loads(guest(alice['vmid'], 'ip', '-j', 'link', 'show'))
        interface = next(link['ifname'] for link in dev if link.get('address') == alice['mac'])
        frame(alice, interface, 'valid-frame-observed-on-real-uplink', expected=True)
        frame(alice, interface, 'spoofed-ip-blocked-before-uplink', source_ip=str(ipaddress.ip_interface(bob['address']).ip))
        frame(alice, interface, 'spoofed-gateway-mac-blocked-before-uplink', source_mac=alice['gateway_mac'])
        frame(alice, interface, 'vlan-injection-blocked-before-uplink', tag=bytes.fromhex('81000064'))
        frame(alice, interface, 'qinq-injection-blocked-before-uplink', tag=bytes.fromhex('88a8006481000065'))
        frame(alice, interface, 'arp-poisoning-blocked-before-uplink', source_ip=alice['gateway'], arp=True)
        frame(alice, interface, 'ipv6-blocked-before-uplink', ipv6=True)
        frame(alice, interface, 'protected-wan-blocked-before-uplink', destination=str(ipaddress.ip_network(c['protected_networks'][0]).network_address))
        fdb = json.loads(pve('bridge', '-j', 'fdb', 'show', 'br', c['bridge']).stdout)
        record('spoofing-did-not-move-gateway-fdb-to-employee-port',
               not any(row.get('mac') == alice['gateway_mac'] and row.get('ifname') == 'tap9101i0' for row in fdb))
        for w in c['workspaces']:
            record(str(w['vmid']) + '-egress-after-attacks', 'true' in guest(w['vmid'], 'python3', '-c', 'import socket;socket.create_connection(("1.1.1.1",443),timeout=4).close();print("true")'))
        pve('python3', '/usr/local/lib/hapi-network.py', 'verify')
        report['traffic_passed'] = True
    finally:
        for vmid in started_servers:
            try:
                guest(vmid, 'systemctl', 'stop', 'hapi-network-test-peer.service')
            except Exception:
                pass
        report['results'] = results
        report['passed'] = sum(r['actual'] == r['expected'] for r in results)
        (root / 'network-test-results.json').write_text(json.dumps(report, indent=2) + '\n')
        (root / 'network-test-results.json').chmod(0o600)
        print(json.dumps({'passed': report['passed'], 'traffic_passed': report.get('traffic_passed', False), 'public_entry_ready': False}), flush=True)


if __name__ == '__main__':
    main()
