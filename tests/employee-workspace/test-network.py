#!/usr/bin/env python3
"""Exercise rendered nft policy in disposable, disconnected Linux namespaces.

Requires explicit --run-isolated-netns, root, iproute2, nftables and Python/Jinja2.
Never attaches to a host interface or contacts a real target.
"""
import copy
import importlib.util
import json
import os
import select
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time
import tempfile
import uuid

spec = importlib.util.spec_from_file_location('offline', Path(__file__).with_name('test-offline.py'))
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)

SERVER = """
import socket,threading
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('0.0.0.0',int(__import__('sys').argv[1])));s.listen()
def echo(c):
    try:
        while c.recv(64): c.sendall(b'OK')
    except OSError: pass
    finally: c.close()
while True:
    c,_=s.accept();threading.Thread(target=echo,args=(c,),daemon=True).start()
"""
CLIENT = """
import socket,sys
s=socket.socket(socket.AF_INET6 if ':' in sys.argv[1] else socket.AF_INET);s.settimeout(1)
try:
    if len(sys.argv)>3: s.bind((sys.argv[3],0))
    s.connect((sys.argv[1],int(sys.argv[2])));s.sendall(b'hi')
    assert s.recv(2)==b'OK'
except (OSError,AssertionError): sys.exit(1)
"""


def main():
    if sys.argv[1:] != ['--run-isolated-netns'] or os.geteuid() != 0:
        raise SystemExit('Use root in the authorized Sandbox with --run-isolated-netns')
    for executable in ('ip', 'nft', 'sysctl'):
        if not shutil.which(executable):
            raise SystemExit('Missing installed tool: ' + executable)
    prefix = 'employee-test-' + uuid.uuid4().hex[:8]
    names = {key: prefix + '-' + key for key in ('pve', 'gw', 'alice', 'bob', 'wan', 'device', 'public')}
    created, processes, results = [], [], []

    def run(*args, input=None, check=True):
        return subprocess.run(args, input=input, text=True, capture_output=True, check=check)

    def ns(name, *args, **kwargs):
        return run('ip', 'netns', 'exec', names[name], *args, **kwargs)

    def link(left, left_if, right, right_if):
        # Names exist only inside the task namespaces.
        ns(left, 'ip', 'link', 'add', left_if, 'type', 'veth', 'peer', 'name', 'peer')
        ns(left, 'ip', 'link', 'set', 'peer', 'netns', names[right])
        ns(right, 'ip', 'link', 'set', 'peer', 'name', right_if)
        ns(left, 'ip', 'link', 'set', left_if, 'up')
        ns(right, 'ip', 'link', 'set', right_if, 'up')

    def address(name, interface, cidr):
        ns(name, 'ip', 'address', 'add', cidr, 'dev', interface, *(['nodad'] if ':' in cidr else []))

    def server(name, port, ipv6=False):
        code = SERVER.replace("socket.socket()", "socket.socket(socket.AF_INET6)").replace("0.0.0.0", "::") if ipv6 else SERVER
        processes.append(subprocess.Popen(['ip', 'netns', 'exec', names[name], sys.executable, '-u', '-c', code, str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE))

    def probe(label, source, target, port, expected, bind=None):
        args = [sys.executable, '-c', CLIENT, target, str(port)] + ([bind] if bind else [])
        actual = ns(source, *args, check=False).returncode == 0
        results.append({'case': label, 'expected': expected, 'actual': actual})
        print(json.dumps(results[-1]), flush=True)
        if actual != expected:
            raise AssertionError(label)


    def packet_probe(label, expected, spoof=False, vlan=False):
        marker = ('EMPLOYEE-PACKET-' + uuid.uuid4().hex).encode()
        receiver = """
import socket,sys,time
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3))
s.bind(('emp0',0));s.settimeout(0.8)
marker=bytes.fromhex(sys.argv[1]);print('READY',flush=True)
try:
    while True:
        if marker in s.recv(65535): sys.exit(0)
except TimeoutError: sys.exit(1)
"""
        listener = subprocess.Popen(['ip','netns','exec',names['gw'],sys.executable,'-u','-c',receiver,marker.hex()],stdout=subprocess.PIPE,text=True)
        processes.append(listener)
        assert listener.stdout.readline().strip() == 'READY'
        source = '10.231.99.2' if spoof else '10.231.1.2'
        udp = struct.pack('!HHHH', 41000, 41001, 8 + len(marker), 0) + marker
        header = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(udp), 1, 0, 64, 17, 0, socket.inet_aton(source), socket.inet_aton('10.231.1.1'))
        words = struct.unpack('!10H', header)
        checksum = sum(words)
        checksum = (checksum & 0xffff) + (checksum >> 16)
        checksum = (checksum & 0xffff) + (checksum >> 16)
        header = header[:10] + struct.pack('!H', (~checksum) & 0xffff) + header[12:]
        ethernet = bytes.fromhex('020000000101020000000102')
        ethernet += bytes.fromhex('810000640800') if vlan else bytes.fromhex('0800')
        sender = "import socket,sys;s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW);s.bind(('eth0',0));s.send(bytes.fromhex(sys.argv[1]))"
        ns('alice',sys.executable,'-c',sender,(ethernet + header + udp).hex())
        actual = listener.wait(timeout=3) == 0
        results.append({'case':label,'expected':expected,'actual':actual})
        print(json.dumps(results[-1]),flush=True)
        if actual != expected:
            raise AssertionError(label)

    def record(label, passed):
        results.append({'case': label, 'expected': True, 'actual': bool(passed)})
        print(json.dumps(results[-1]), flush=True)
        if not passed:
            raise AssertionError(label)

    def transfer(label, target):
        client = "import socket,hashlib,sys;s=socket.create_connection((sys.argv[1],18082),timeout=8);data=b'x'*131072;s.sendall(data);s.shutdown(socket.SHUT_WR);assert s.recv(64).decode()==hashlib.sha256(data).hexdigest()"
        result = ns('alice', sys.executable, '-c', client, target, check=False)
        record(label, result.returncode == 0)

    def firewall_checks(config):
        with tempfile.TemporaryDirectory(prefix='employee-firewall-kernel-') as temp:
            base = Path(temp)
            policy = base / 'policy.nft'
            applied = base / 'applied.json'
            controller = offline.ROLE / 'files/employee-firewall.py'
            prefix_code = f"import importlib.util,pathlib;spec=importlib.util.spec_from_file_location('fw',{str(controller)!r});m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.POLICY=pathlib.Path({str(policy)!r});m.APPLIED=pathlib.Path({str(applied)!r});"
            policy.write_text(offline.render('nftables.conf.j2', config))
            ns('gw', sys.executable, '-c', prefix_code + 'm.apply(True);m.verify(True)')
            record('actual-kernel-policy-verifies', True)
            ns('gw', 'nft', 'add', 'rule', 'inet', 'employee_access', 'input', 'counter', 'drop')
            record('actual-kernel-policy-drift-denied', ns('gw', sys.executable, '-c', prefix_code + 'm.verify(True)', check=False).returncode != 0)
            ns('gw', sys.executable, '-c', prefix_code + 'm.apply(True)')
            ns('gw', 'nft', 'delete', 'table', 'inet', 'employee_access')
            record('missing-kernel-policy-denied', ns('gw', sys.executable, '-c', prefix_code + 'm.verify(True)', check=False).returncode != 0)
            policy.write_text('INVALID NFT POLICY')
            record('failed-firewall-load-fails', ns('gw', sys.executable, '-c', prefix_code + 'm.apply(True)', check=False).returncode != 0)
            record('failed-firewall-load-disables-routing', ns('gw', 'sysctl', '-n', 'net.ipv4.ip_forward').stdout.strip() == '0')
            probe('failed-firewall-no-unfiltered-egress', 'alice', '1.1.1.1', 18080, False)
            policy.write_text(offline.render('nftables.conf.j2', config))
            ns('gw', sys.executable, '-c', prefix_code + 'm.apply(True);m.verify(True)')
            probe('recovered-firewall-egress', 'alice', '1.1.1.1', 18080, True)
            policy.write_text(offline.render('pve-nftables.conf.j2', config))
            prior = ns('pve', 'sysctl', '-n', 'net.ipv4.ip_forward').stdout
            ns('pve', sys.executable, '-c', prefix_code + 'm.apply(False);m.verify(False)')
            record('pve-firewall-preserves-host-routing', ns('pve', 'sysctl', '-n', 'net.ipv4.ip_forward').stdout == prior)
            hook = (offline.ROOT / 'terraform/proxmox/employee-boundary-hook.py.tftpl').read_text().replace('${vmid}', '501').replace('${gateway_tap}', 'tap500i1').replace('${disabled}', 'false')
            hook_module = base / 'hook.py'
            hook_module.write_text(hook)
            hook_check = f"import runpy,json,subprocess;m=runpy.run_path({str(hook_module)!r});rules=json.loads(subprocess.check_output(['nft','-j','list','table','bridge','employee_boundary']));assert m['has_port_drop'](rules,'forward','tap501i0','iifname')"
            record('hook-accepts-real-attached-chain', ns('pve', sys.executable, '-c', hook_check, check=False).returncode == 0)
            controller_wrapper = base / 'verify.py'
            controller_wrapper.write_text(prefix_code + 'm.verify(False)')
            service_stub = base / 'systemctl'
            service_stub.write_text('#!/bin/bash\nexit 0\n')
            service_stub.chmod(0o755)
            hook_module.write_text(hook.replace('/usr/bin/systemctl', str(service_stub)).replace('/usr/local/lib/employee-firewall.py', str(controller_wrapper)))
            record('hook-main-valid-policy-passes', ns('pve', sys.executable, str(hook_module), '501', 'pre-start', check=False).returncode == 0)
            ns('pve', 'nft', 'insert', 'rule', 'bridge', 'employee_boundary', 'forward', 'iifname', 'tap501i0', 'accept')
            record('fallback-drop-remains-after-injected-accept', ns('pve', sys.executable, '-c', hook_check, check=False).returncode == 0)
            record('hook-main-rejects-accept-before-fallback-drop', ns('pve', sys.executable, str(hook_module), '501', 'pre-start', check=False).returncode != 0)
            ns('pve', sys.executable, '-c', prefix_code + 'm.apply(False)')
            ns('pve', 'nft', 'delete', 'table', 'bridge', 'employee_boundary')
            detached = offline.render('pve-nftables.conf.j2', config)
            for chain in ('input', 'forward', 'output'):
                detached = detached.replace('type filter hook ' + chain + ' priority -200; policy accept;', '')
            ns('pve', 'nft', '-f', '-', input=detached)
            record('hook-denies-real-unattached-chain', ns('pve', sys.executable, '-c', hook_check, check=False).returncode != 0)
            ns('pve', 'nft', '-f', '-', input=offline.render('pve-nftables.conf.j2', config))

    def policies(config):
        ns('gw', 'nft', '-f', '-', input=offline.render('nftables.conf.j2', config))
        ns('pve', 'nft', '-f', '-', input=offline.render('pve-nftables.conf.j2', config))

    try:
        for key, name in names.items():
            run('ip', 'netns', 'add', name)
            created.append(name)
            ns(key, 'ip', 'link', 'set', 'lo', 'up')
        for person, net in offline.FIXTURE['networks'].items():
            ns('pve', 'ip', 'link', 'add', net['bridge'], 'type', 'bridge')
            ns('pve', 'ip', 'link', 'set', net['bridge'], 'up')
            guest_tap, gateway_tap = f"tap{net['vmid']}i0", f"tap500i{net['gateway_nic']}"
            link(person, 'eth0', 'pve', guest_tap)
            link('gw', net['interface'], 'pve', gateway_tap)
            for tap in (guest_tap, gateway_tap):
                ns('pve', 'ip', 'link', 'set', tap, 'master', net['bridge'])
            ns(person, 'ip', 'link', 'set', 'eth0', 'address', net['mac_address'])
            ns('gw', 'ip', 'link', 'set', net['interface'], 'address', net['gateway_mac'])
            address(person, 'eth0', net['address'])
            address('gw', net['interface'], net['gateway_address'])
            ns(person, 'ip', 'route', 'add', 'default', 'via', net['gateway'])
            server(person, 22)
        address('alice', 'eth0', 'fd00:231:1::2/64')
        address('gw', 'emp0', 'fd00:231:1::1/64')
        server('gw', 18081, ipv6=True)
        link('gw', 'employee-uplink', 'wan', 'eth0')
        address('gw', 'employee-uplink', '192.168.50.2/24')
        address('wan', 'eth0', '192.168.50.1/24')
        address('wan', 'eth0', '192.168.50.10/24')
        ns('gw', 'ip', 'route', 'add', 'default', 'via', '192.168.50.1')
        ns('wan', 'ip', 'route', 'add', '10.231.0.0/16', 'via', '192.168.50.2')
        for target in ('1.1.1.1', '203.0.113.5', '198.51.100.20', '100.64.0.5'):
            address('wan', 'lo', target + '/32')
        link('wan', 'transit', 'public', 'eth0')
        address('wan', 'transit', '192.0.2.1/30')
        address('public', 'eth0', '192.0.2.2/30')
        address('public', 'lo', '8.8.8.8/32')
        ns('wan', 'ip', 'route', 'add', '8.8.8.8/32', 'via', '192.0.2.2')
        ns('public', 'ip', 'route', 'add', 'default', 'via', '192.0.2.1')
        ns('wan', 'sysctl', '-w', 'net.ipv4.ip_forward=1')
        transfer_server = """
import socket,hashlib,threading
s=socket.socket();s.bind(('0.0.0.0',18082));s.listen()
def serve(c):
 h=hashlib.sha256()
 while True:
  data=c.recv(65536)
  if not data: break
  h.update(data)
 c.sendall(h.hexdigest().encode());c.close()
while True:
 c,_=s.accept();threading.Thread(target=serve,args=(c,),daemon=True).start()
"""
        for node in ('wan', 'public'):
            processes.append(subprocess.Popen(['ip','netns','exec',names[node],sys.executable,'-c',transfer_server], stderr=subprocess.PIPE))
        link('gw', 'wg-employee', 'device', 'eth0')
        address('gw', 'wg-employee', '10.230.0.1/24')
        address('device', 'eth0', '10.230.0.2/24')
        ns('device', 'ip', 'route', 'add', 'default', 'via', '10.230.0.1')
        ns('gw', 'sysctl', '-w', 'net.ipv4.ip_forward=1')
        # A live PVE bridge-local target verifies the input-hook denial.
        address('pve', 'vmbr501', '10.231.1.4/32')
        ns('pve', 'ip', 'route', 'add', '10.231.1.2/32', 'dev', 'vmbr501')
        ns('alice', 'ip', 'route', 'add', '10.231.1.4/32', 'dev', 'eth0')
        for name, port in [('wan', 18080), ('gw', 18080), ('gw', 22), ('pve', 18080)]:
            server(name, port)
        time.sleep(0.3)
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('A positive-control server failed to start')
        # Management-side controls prove protected targets really are listening.
        for target in ('203.0.113.5', '198.51.100.20', '100.64.0.5'):
            probe('positive-' + target, 'wan', target, 18080, True)
        probe('pve-before-policy', 'alice', '10.231.1.4', 18080, True)
        probe('host-output-before-policy', 'pve', '10.231.1.2', 22, True)
        probe('ipv6-before-policy', 'alice', 'fd00:231:1::1', 18081, True)
        packet_probe('vlan-before-policy', True, vlan=True)
        config = copy.deepcopy(offline.FIXTURE)
        policies(config)
        probe('ipv6-blocked', 'alice', 'fd00:231:1::1', 18081, False)
        packet_probe('valid-source-reaches-gateway-port', True)
        packet_probe('spoofed-source-ip', False, spoof=True)
        packet_probe('vlan-blocked', False, vlan=True)
        probe('public-development', 'alice', '1.1.1.1', 18080, True)
        ns('gw', 'ip', 'link', 'set', 'employee-uplink', 'mtu', '600')
        transfer('local-gateway-pmtu-large-transfer', '1.1.1.1')
        ns('gw', 'ip', 'link', 'set', 'employee-uplink', 'mtu', '1500')
        ns('wan', 'ip', 'link', 'set', 'transit', 'mtu', '600')
        transfer('private-router-related-pmtu-large-transfer', '8.8.8.8')
        firewall_checks(config)
        probe('other-workspace', 'alice', '10.231.2.2', 22, False)
        probe('gateway-management', 'alice', '10.231.1.1', 18080, False)
        probe('pve-local', 'alice', '10.231.1.4', 18080, False)
        probe('pve-host-output', 'pve', '10.231.1.2', 22, False)
        ns('gw', 'ip', 'link', 'set', 'employee-uplink', 'name', 'ens18')
        probe('maintenance-before-rename', 'wan', '192.168.50.2', 22, True, '192.168.50.10')
        probe('other-source-before-rename', 'wan', '192.168.50.2', 22, False, '192.168.50.1')
        ns('gw', 'ip', 'link', 'set', 'ens18', 'name', 'employee-uplink')
        probe('maintenance-after-rename', 'wan', '192.168.50.2', 22, True, '192.168.50.10')
        for target in ('192.168.50.1', '203.0.113.5', '198.51.100.20', '100.64.0.5'):
            probe('protected-' + target, 'alice', target, 18080, False)
        probe('device-user-service', 'device', '10.230.0.1', 22, True)
        probe('device-management', 'device', '10.230.0.1', 18080, False)
        probe('device-direct-vm', 'device', '10.231.1.2', 22, False)
        probe('maintenance-source', 'wan', '10.231.1.2', 22, True, '192.168.50.10')
        probe('nonmaintenance-source', 'wan', '10.231.1.2', 22, False, '192.168.50.1')
        probe('gateway-second-leg', 'gw', '10.231.1.2', 22, True)
        ns('alice', 'ip', 'link', 'set', 'eth0', 'address', '02:00:00:00:01:99')
        probe('spoofed-mac', 'alice', '1.1.1.1', 18080, False)
        ns('alice', 'ip', 'link', 'set', 'eth0', 'address', config['networks']['alice']['mac_address'])
        ns('gw', 'ip', 'neigh', 'flush', 'dev', 'emp0')
        probe('restored-mac', 'alice', '1.1.1.1', 18080, True)
        keepalive_code = """
import socket,sys
s=socket.create_connection(('1.1.1.1',18080),timeout=2)
s.sendall(b'hi');assert s.recv(2)==b'OK';print('READY',flush=True)
command=sys.stdin.readline()
if command.strip()=='reload':
    s.sendall(b'hi');assert s.recv(2)==b'OK';print('ALIVE',flush=True)
    sys.stdin.readline()
try:
    s.sendall(b'hi')
    if s.recv(2)==b'OK': sys.exit(1)
except OSError: pass
sys.exit(0)
"""
        keepalive = subprocess.Popen(['ip','netns','exec',names['alice'],sys.executable,'-u','-c',keepalive_code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        processes.append(keepalive)
        ready, _, _ = select.select([keepalive.stdout], [], [], 5)
        if not ready or keepalive.stdout.readline().strip() != 'READY':
            raise AssertionError('Existing egress connection positive control failed')
        config['networks']['alice']['disabled'] = True
        task_spec = importlib.util.spec_from_file_location('ansible_network_fixture', Path(__file__).with_name('ansible-network-fixture.py'))
        task_fixture = importlib.util.module_from_spec(task_spec)
        task_spec.loader.exec_module(task_fixture)
        def after_reload():
            keepalive.stdin.write('reload\n')
            keepalive.stdin.flush()
            ready, _, _ = select.select([keepalive.stdout], [], [], 5)
            record('actual-unchanged-firewall-reload-preserves-existing-connection', bool(ready) and keepalive.stdout.readline().strip() == 'ALIVE')
        def after_pve_failure():
            probe('pve-failure-still-blocks-employee-at-gateway', 'alice', '1.1.1.1', 18080, False)
            probe('pve-failure-preserves-other-employee', 'bob', '1.1.1.1', 18080, True)
        def after_gateway_failure():
            record('gateway-reload-failure-keeps-routing-closed', ns('gw', 'sysctl', '-n', 'net.ipv4.ip_forward').stdout.strip() == '0')
        def after_retry():
            probe('unchanged-file-retry-preserves-employee-denial', 'alice', '1.1.1.1', 18080, False)
            probe('unchanged-file-retry-restores-other-employee', 'bob', '1.1.1.1', 18080, True)
            record('unchanged-file-retry-restores-routing', ns('gw', 'sysctl', '-n', 'net.ipv4.ip_forward').stdout.strip() == '1')
        task_fixture.disable(Path(__file__).resolve().parents[2], names, config, after_reload, after_pve_failure, after_gateway_failure, after_retry)


        record('actual-ansible-disable-reached-qm-failure', True)

        keepalive.stdin.write('check\n')
        keepalive.stdin.flush()
        denied = keepalive.wait(timeout=4) == 0
        results.append({'case':'disabled-existing-egress','expected':True,'actual':denied})
        print(json.dumps(results[-1]),flush=True)
        if not denied:
            raise AssertionError('Disabled employee retained existing egress')
        probe('disabled-employee-egress', 'alice', '1.1.1.1', 18080, False)
        probe('disabled-second-leg', 'gw', '10.231.1.2', 22, False)
        probe('other-employee-remains', 'bob', '1.1.1.1', 18080, True)
        print(json.dumps({'passed': len(results), 'scope': 'isolated nft IPv4/IPv6/L2 network; no live CAP, SSH auth, WireGuard handshake or OAuth claim'}))
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for name in reversed(created):
            run('ip', 'netns', 'delete', name, check=False)


if __name__ == '__main__':
    main()
