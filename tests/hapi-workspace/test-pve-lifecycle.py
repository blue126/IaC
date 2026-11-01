#!/usr/bin/env python3
"""Validate disable, pre-start refusal, repair and idempotence on VM9101/9102."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('network', ROOT / 'ansible/roles/hapi-network/files/hapi-network.py')
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--run-real-pve', action='store_true')
    args = parser.parse_args()
    assert args.run_real_pve and os.environ.get('SANDBOX_ID'), 'Use the authorized task Sandbox'
    root = args.runtime
    original = network.load(root / 'manifest.json')
    assert {(w['id'], w['vmid']) for w in original['workspaces']} == {('test-alice', 9101), ('test-bob', 9102)}
    common = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
              '-o', 'UserKnownHostsFile=' + str(root / 'known-hosts'), '-o', 'ConnectTimeout=8']
    results = []
    phase = 'baseline'
    active = None
    complete = False

    def pve(*argv, check=True):
        return subprocess.run(common + ['root@192.168.1.52', shlex.join(argv)], text=True, capture_output=True, check=check)

    def status(vmid):
        return json.loads(pve('pvesh', 'get', f'/nodes/pve2/qemu/{vmid}/status/current', '--output-format', 'json').stdout)

    def live():
        return json.loads(pve('cat', '/etc/hapi-network/manifest.json').stdout)

    def record(label, passed):
        results.append({'case': label, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + label, flush=True)
        assert passed, label

    def deploy(candidate, expected):
        inventory = json.loads((root / 'inventory.json').read_text())
        host = inventory['all']['children']['hapi_pve']['hosts']['pve2']
        host['hapi_network_manifest'] = candidate
        host['hapi_network_expected_manifest_sha256'] = network.digest(expected)
        path = root / ('lifecycle-' + phase + '-inventory.json')
        path.write_text(json.dumps(inventory))
        path.chmod(0o600)
        env = os.environ | {'ANSIBLE_CONFIG': str(ROOT / 'tests/ci/fixtures/ansible.cfg'),
                            'ANSIBLE_ROLES_PATH': str(ROOT / 'ansible/roles'), 'ANSIBLE_NOCOLOR': '1'}
        command = ['ansible-playbook', '-i', str(path), str(ROOT / 'ansible/playbooks/deploy-hapi-network.yml')]
        result = subprocess.run(command, text=True, capture_output=True, env=env)
        log = root / ('lifecycle-' + phase + '-ansible.log')
        log.write_text(result.stdout + result.stderr)
        log.chmod(0o600)
        assert result.returncode == 0, 'Network role failed; inspect ' + str(log)
        return result.stdout

    def guest_public(vmid):
        code = 'import socket;socket.create_connection(("1.1.1.1",443),timeout=4).close();print("OK")'
        result = json.loads(pve('qm', 'guest', 'exec', str(vmid), '--', 'python3', '-c', code).stdout)
        return result.get('exitcode') == 0 and result.get('out-data', '').strip() == 'OK'

    def wait_ssh():
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            result = subprocess.run(common + ['ubuntu@192.168.1.148', 'true'], capture_output=True)
            if result.returncode == 0:
                return True
            time.sleep(2)
        return False

    try:
        assert live() == original
        for w in original['workspaces']:
            config = json.loads(pve('pvesh', 'get', f'/nodes/pve2/qemu/{w["vmid"]}/config', '--output-format', 'json').stdout)
            assert config['name'] == 'hapi-' + w['id'] and 'hapi-network-test' in config.get('tags', '')
            assert status(w['vmid'])['status'] == 'running'
        bob_pid = status(9102)['pid']
        bob_receipt = pve('sha256sum', '/var/lib/hapi-network/9102.json').stdout
        active = subprocess.Popen(common + ['ubuntu@192.168.1.148', 'cat'], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        active.stdin.write('before-disable\n'); active.stdin.flush()
        ready, _, _ = select.select([active.stdout], [], [], 8)
        record('existing-stream-positive-control', bool(ready) and active.stdout.readline() == 'before-disable\n')
        disabled = copy.deepcopy(original)
        disabled['workspaces'][0]['enabled'] = False
        phase = 'disable'
        deploy(disabled, original)
        active.stdin.write('after-disable\n'); active.stdin.flush()
        ready, _, _ = select.select([active.stdout], [], [], 2)
        record('disabled-existing-stream-stops-delivery', not ready or active.stdout.readline() != 'after-disable\n')
        record('other-employee-egress-preserved', guest_public(9102))
        record('other-employee-rule-receipt-unchanged', bob_receipt == pve('sha256sum', '/var/lib/hapi-network/9102.json').stdout)
        pve('qm', 'shutdown', '9101', '--timeout', '30')
        denied = pve('qm', 'start', '9101', check=False)
        record('disabled-workspace-start-refused', denied.returncode != 0 and
               'Workspace is disabled' in denied.stdout + denied.stderr and status(9101)['status'] == 'stopped')
        phase = 'reenable-stopped'
        deploy(original, disabled)
        pve('nft', 'add', 'rule', 'bridge', 'hapi_9101', 'guest_out', 'counter', 'drop')
        denied = pve('qm', 'start', '9101', check=False)
        record('kernel-rule-drift-start-refused', denied.returncode != 0 and
               'Firewall missing or changed' in denied.stdout + denied.stderr and status(9101)['status'] == 'stopped')
        phase = 'repair-drift'
        deploy(original, original)
        pve('python3', '/usr/local/lib/hapi-network.py', 'verify')
        pve('qm', 'start', '9101')
        record('repaired-workspace-start-and-admin-access', wait_ssh())
        record('repaired-workspace-public-egress', guest_public(9101))
        record('other-employee-never-restarted', status(9102)['pid'] == bob_pid)
        phase = 'idempotence'
        output = deploy(original, original)
        record('unchanged-ansible-rerun-has-zero-changes', bool(re.search(r'pve2\s*:.*changed=0\s+.*failed=0', output)))
        record('final-live-allocation-unchanged', live() == original)
        complete = True
    finally:
        if active and active.poll() is None:
            active.terminate()
            try:
                active.wait(timeout=5)
            except subprocess.TimeoutExpired:
                active.kill(); active.wait()
        current = live()
        if current != original or not complete:
            phase = 'failure-recovery'
            deploy(original, current)
        report = {'scope': 'real-pve-two-vm-lifecycle', 'results': results,
                  'passed': sum(r['passed'] for r in results), 'lifecycle_passed': complete,
                  'public_entry_ready': False}
        (root / 'lifecycle-test-results.json').write_text(json.dumps(report, indent=2) + '\n')
        (root / 'lifecycle-test-results.json').chmod(0o600)
        print(json.dumps({'passed': report['passed'], 'public_entry_ready': False}), flush=True)


if __name__ == '__main__':
    main()
