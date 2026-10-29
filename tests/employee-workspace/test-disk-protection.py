#!/usr/bin/env python3
"""Replay mock state into offline plans; never use a real backend or credentials."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

root, log = Path(sys.argv[1]), Path(sys.argv[2])
rows = list(map(json.loads, log.read_text().splitlines()))
def test_state(name):
    return next(row['test_state'] for row in rows if row.get('@testrun') == name and 'test_state' in row)

def install_state(snapshot):
    resources = {}
    for raw in snapshot['root_module']['resources']:
        resource = copy.deepcopy(raw)
        if resource['type'] == 'proxmox_virtual_environment_vm' and resource['name'] != 'employee_template':
            resource['values']['template'] = False
        if resource['type'] == 'terraform_data':
            for name in ('input', 'output'):
                value = resource['values'][name]
                resource['values'][name] = {'value': value, 'type': ['object', {key: 'number' if isinstance(item, (int, float)) else 'string' for key, item in value.items()}]}
        if resource['type'] == 'proxmox_virtual_environment_vm' and resource['name'] == 'employee_workspace':
            resource['values']['vga'] = [{'type': 'serial0', 'memory': 16, 'clipboard': ''}]
        key = (resource['type'], resource['name'])
        item = resources.setdefault(key, {'mode': resource['mode'], 'type': resource['type'], 'name': resource['name'], 'provider': 'provider["' + resource['provider_name'] + '"]', 'instances': []})
        item['instances'].append({'index_key': resource['index'], 'schema_version': resource['schema_version'], 'attributes': resource['values'], 'sensitive_attributes': []})
    (root / 'terraform.tfstate').write_text(json.dumps({'version': 4, 'terraform_version': '1.9.8', 'serial': 1, 'lineage': 'employee-offline-test', 'outputs': {}, 'resources': list(resources.values())}))

fixture = json.loads(Path(__file__).with_name('fixture.json').read_text())
base = {'employee_access': {'node': 'pve-test', 'pve_inventory_host': 'pve-test', 'vmid': 500, 'template_id': 9000, 'storage_pool': 'local-zfs', 'uplink_bridge': 'vmbr1', 'uplink_address': fixture['uplink_address'], 'uplink_gateway': fixture['uplink_gateway'], 'uplink_mac': fixture['uplink_mac'], 'dns_server': '1.1.1.1', 'admin_public_keys': []}, 'employee_workspaces': fixture['networks']}
varfile = root / 'protection.tfvars.json'
env = {key: value for key, value in os.environ.items() if not key.startswith(('TF_', 'TFC_', 'PROXMOX_'))}
env.update(TF_CLI_CONFIG_FILE='/dev/null', PROXMOX_VE_ENDPOINT='https://127.0.0.1:1', PROXMOX_VE_API_TOKEN='test@pve!test=00000000-0000-0000-0000-000000000000')
vm = 'proxmox_virtual_environment_vm.employee_workspace["alice"]'
marker = 'terraform_data.employee_retirement["alice"]'
for label, flags in [('unchanged-positive-control', []), ('first-start-preserves-inherited-vga', ['-out=' + str(root / 'first-start.tfplan')]), ('destroy', ['-destroy']), ('forced-replacement', ['-replace=' + vm]), ('vmid-change', []), ('retire-existing-state', []), ('retired-cannot-reactivate', [])]:
    install_state(test_state('retired_workspace_keeps_network_allocation_without_vm' if label == 'retired-cannot-reactivate' else 'allocated'))
    variables = copy.deepcopy(base)
    variables['employee_access']['boundary_ready'] = label == 'first-start-preserves-inherited-vga'
    if label == 'first-start-preserves-inherited-vga':
        for value in variables['employee_workspaces'].values():value.update(start_ready=True, hook_bound=True)
    if label == 'vmid-change':variables['employee_workspaces']['alice']['vmid'] = 601
    if label == 'retire-existing-state':variables['employee_workspaces']['alice'].update(retired=True, disabled=True, start_ready=False, hook_bound=False)
    varfile.write_text(json.dumps(variables))
    result = subprocess.run(['terraform', 'plan', '-no-color', '-input=false', '-refresh=false', '-var-file=' + str(varfile)] + flags, cwd=root, env=env, text=True, capture_output=True)
    (root / (label + '.log')).write_text(result.stdout + result.stderr)
    expected = marker if label == 'retired-cannot-reactivate' else vm
    ok = result.returncode == 0 if label in ('unchanged-positive-control','first-start-preserves-inherited-vga') else result.returncode != 0 and expected in result.stderr and 'lifecycle.prevent_destroy' in result.stderr
    if label == 'retire-existing-state':ok = ok and 'employee_workspace["bob"] has lifecycle.prevent_destroy' not in result.stderr
    if label == 'first-start-preserves-inherited-vga' and result.returncode == 0:
        plan = json.loads(subprocess.check_output(['terraform', 'show', '-json', str(root / 'first-start.tfplan')], cwd=root, env=env, text=True))
        changes = [item for item in plan.get('resource_changes', []) if item['type'] == 'proxmox_virtual_environment_vm' and item['name'] == 'employee_workspace']
        ok = len(changes) == 2
        for item in changes:
            change = item['change'];before, after = change['before'], change['after']
            ok = ok and change['actions'] == ['update'] and after['started'] and after['on_boot']
            ok = ok and len(before['vga']) == len(after['vga']) == 1 and before['vga'][0]['type'] == after['vga'][0]['type'] == 'serial0'
            ok = ok and before['vga'][0]['memory'] == after['vga'][0]['memory']
    print(json.dumps({'case': label, 'protected': ok}), flush=True)
    if not ok:
        print(result.stdout + result.stderr, file=sys.stderr);raise SystemExit(1)
