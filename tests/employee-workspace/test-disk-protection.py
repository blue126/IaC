#!/usr/bin/env python3
"""Replay mock state into offline plans and require employee VM destroy protection."""
import json
import os
from pathlib import Path
import subprocess
import sys

root, log = Path(sys.argv[1]), Path(sys.argv[2])
state = next(row['test_state'] for row in map(json.loads, log.read_text().splitlines()) if row.get('@testrun') == 'allocated' and 'test_state' in row)
resources = {}
for resource in state['root_module']['resources']:
    if resource['type'] == 'proxmox_virtual_environment_vm':
        resource['values']['template'] = False
    if resource['type'] == 'terraform_data':
        for name in ('input', 'output'):
            resource['values'][name] = {'value': resource['values'][name], 'type': ['object', {key: 'number' if isinstance(value, (int, float)) else 'string' for key, value in resource['values'][name].items()}]}
    key = (resource['type'], resource['name'])
    item = resources.setdefault(key, {'mode': resource['mode'], 'type': resource['type'], 'name': resource['name'], 'provider': 'provider["' + resource['provider_name'] + '"]', 'instances': []})
    item['instances'].append({'index_key': resource['index'], 'schema_version': resource['schema_version'], 'attributes': resource['values'], 'sensitive_attributes': []})
(root / 'terraform.tfstate').write_text(json.dumps({'version': 4, 'terraform_version': '1.9.8', 'serial': 1, 'lineage': 'employee-offline-test', 'outputs': {}, 'resources': list(resources.values())}))
fixture = json.loads(Path(__file__).with_name('fixture.json').read_text())
variables = {'employee_access': {'node': 'pve-test', 'pve_inventory_host': 'pve-test', 'vmid': 500, 'template_id': 9000, 'storage_pool': 'local-zfs', 'uplink_bridge': 'vmbr1', 'uplink_address': fixture['uplink_address'], 'uplink_gateway': fixture['uplink_gateway'], 'uplink_mac': fixture['uplink_mac'], 'dns_server': '1.1.1.1', 'admin_public_keys': []}, 'employee_workspaces': fixture['networks']}
varfile = root / 'protection.tfvars.json'
varfile.write_text(json.dumps(variables))
env = {key: value for key, value in os.environ.items() if not key.startswith(('TF_', 'TFC_', 'PROXMOX_'))}
env.update(TF_CLI_CONFIG_FILE='/dev/null', PROXMOX_VE_ENDPOINT='https://127.0.0.1:1', PROXMOX_VE_API_TOKEN='test@pve!test=00000000-0000-0000-0000-000000000000')
for label, flags in [('unchanged-positive-control', []), ('destroy', ['-destroy']), ('forced-replacement', ['-replace=proxmox_virtual_environment_vm.employee_workspace["alice"]']), ('vmid-change', [])]:
    if label == 'vmid-change':
        variables['employee_workspaces']['alice']['vmid'] = 601
        varfile.write_text(json.dumps(variables))
    result = subprocess.run(['terraform', 'plan', '-no-color', '-input=false', '-refresh=false', '-var-file=' + str(varfile)] + flags, cwd=root, env=env, text=True, capture_output=True)
    (root / (label + '.log')).write_text(result.stdout + result.stderr)
    ok = result.returncode == 0 if label == 'unchanged-positive-control' else result.returncode != 0 and 'proxmox_virtual_environment_vm.employee_workspace["alice"]' in result.stderr and 'lifecycle.prevent_destroy' in result.stderr
    print(json.dumps({'case': label, 'protected': ok}), flush=True)
    if not ok:
        print(result.stdout + result.stderr, file=sys.stderr)
        raise SystemExit(1)
