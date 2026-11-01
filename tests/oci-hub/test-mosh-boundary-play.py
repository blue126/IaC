#!/usr/bin/env python3
"""Run the actual approved-boundary play against nftables in a disposable netns."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]


def command(*args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=True, **kwargs)


def main():
    if sys.platform != 'linux' or os.geteuid() != 0:
        print('NOT RUN: run as root in the approved Linux validation Sandbox')
        return 77
    ns = 'omb' + uuid.uuid4().hex[:8]
    command('ip', 'netns', 'add', ns)
    try:
        for interface in ('wg-users', 'wg-workspaces'):
            command('ip', '-n', ns, 'link', 'add', interface, 'type', 'veth', 'peer', 'name', 'peer-' + interface[3:])
            command('ip', '-n', ns, 'link', 'set', interface, 'up')
            command('ip', '-n', ns, 'link', 'set', 'peer-' + interface[3:], 'up')
        command('ip', '-n', ns, 'addr', 'add', '10.235.0.1/24', 'dev', 'wg-users')
        command('ip', '-n', ns, 'addr', 'add', '10.234.0.1/24', 'dev', 'wg-workspaces')
        spec = importlib.util.spec_from_file_location('fixtures', Path(__file__).with_name('test-offline.py'))
        fixture = importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory(prefix='oci-mosh-boundary-play-') as temporary:
            base = Path(temporary);policy = base / 'boundary.json';receipt = base / 'receipt.json'
            program = base / 'boundary.py'
            old = copy.deepcopy(fixture.HUB)
            old['device_sources'] = old.pop('ga2_sources')
            policy.write_text(json.dumps(old))
            previous = hashlib.sha256(policy.read_bytes()).hexdigest()
            candidate = copy.deepcopy(old);candidate['generation'] += 1
            candidate['pairs'][0]['mosh_ports'] = [60000, 60009]
            content = json.dumps(candidate, sort_keys=True, indent=2)
            approved = hashlib.sha256(content.encode()).hexdigest()
            plays = (ROOT / 'ansible/playbooks/configure-oci-hub-mosh-boundary.yml').read_text()
            plays = plays.replace('{{ playbook_dir }}/../../scripts/oci-hub/boundary.py', str(ROOT / 'scripts/oci-hub/boundary.py'))
            plays = plays.replace('/etc/oci-hub/boundary.json', str(policy)).replace('/usr/local/lib/oci-hub-boundary.py', str(program))
            parsed = yaml.safe_load(plays)
            for play in parsed:
                play['become'] = False
                for task in play['tasks']:
                    value = task.get('ansible.builtin.command')
                    if isinstance(value, str) and value.startswith(str(program)):
                        task['ansible.builtin.command'] += f' --config {policy} --receipt {receipt}'
            (base / 'play.yml').write_text(yaml.safe_dump(parsed, sort_keys=False))
            (base / 'inventory.yml').write_text('all:\n  children:\n    oci_hub_mosh_gateway:\n      hosts:\n        fixture:\n          ansible_connection: local\n')
            variables = dict(oci_hub_boundary=candidate, oci_hub_boundary_candidate_content=content,
                             oci_hub_boundary_before_sha256=previous, oci_hub_boundary_candidate_sha256=approved)
            (base / 'vars.json').write_text(json.dumps(variables))
            env = dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'tests/ci/fixtures/ansible.cfg'))
            def apply(expected=True):
                argv = ['ip', 'netns', 'exec', ns, 'ansible-playbook', '-i', str(base / 'inventory.yml'), str(base / 'play.yml'), '-e', '@' + str(base / 'vars.json')]
                result = subprocess.run(argv, env=env, capture_output=True, text=True)
                if (result.returncode == 0) != expected:raise AssertionError(result.stdout + result.stderr)
            # Wrong live predecessor must fail before writing config or program.
            policy.write_text(json.dumps(dict(old, generation=99)))
            saved = policy.read_bytes();apply(False)
            assert policy.read_bytes() == saved and not program.exists()
            policy.write_text(json.dumps(old));apply()
            assert policy.read_text() == content
            assert receipt.exists()
            apply()  # A retry after the candidate was saved remains safe.
            assert policy.read_text() == content
            print('PASS: actual Ansible predecessor/candidate guards, exact approved bytes, nft apply/routing verify and recovery rerun in isolated netns')
    finally:
        subprocess.run(['ip', 'netns', 'del', ns], capture_output=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
