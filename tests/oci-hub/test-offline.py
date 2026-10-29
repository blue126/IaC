#!/usr/bin/env python3
"""Synthetic boundary validation and live-policy fail-closed tests."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('boundary',ROOT/'scripts/oci-hub/boundary.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

PVE={'profile':'oci-hub','kind':'pve','node':'pve2','generation':1,'aggregate':'10.236.0.0/16','endpoint':'203.0.113.9','uplink':'eth0','protected':['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','203.0.113.0/24'],'development_destinations':['0.0.0.0/0'],'dns_servers':[], 'management_access':[], 'workspaces':[{'vmid':601,'vnet':'ohalice','subnet':'10.236.1.0/30','address':'10.236.1.2','gateway':'10.236.1.1','mac':'02:00:00:00:01:02','disabled':False}]}
HUB={'profile':'oci-hub','kind':'hub','generation':1,'interfaces':{'wg-users':'10.235.0.1/24','wg-workspaces':'10.234.0.1/24'},'ga2_sources':['192.0.2.2/32'],'workspace_sources':['198.51.100.2/32'],'pairs':[{'device':'10.235.0.2','workspace':'10.234.0.2'},{'device':'10.235.0.3','workspace':'10.234.0.3'}]}


class Boundary(unittest.TestCase):
    def test_invalid_scope_and_overlap_rejected(self):
        c=copy.deepcopy(PVE);c['profile']='existing'
        with self.assertRaises(ValueError):b.render(c)
        c=copy.deepcopy(PVE);c['workspaces'].append({**c['workspaces'][0],'vmid':602,'vnet':'ohbob'})
        with self.assertRaises(ValueError):b.render(c)
        c=copy.deepcopy(PVE);c['workspaces'][0]['vnet']='vmbr0'
        with self.assertRaises(ValueError):b.render(c)
    def test_missing_or_changed_live_policy_denies_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'policy.json').write_text(json.dumps(PVE))
            (p/'receipt.json').write_text(json.dumps({'policy':b.digest(PVE),'rules':b.digest(['expected'])}))
            with patch('sys.argv',['boundary','verify','--config',str(p/'policy.json'),'--receipt',str(p/'receipt.json')]),patch.object(b,'live',return_value=['tampered']):
                with self.assertRaises(ValueError):b.main()
    def test_hook_checks_live_policy_vmid_bridge_and_disable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);config=copy.deepcopy(PVE)
            policy=p/'policy.json';receipt=p/'receipt.json'
            policy.write_text(json.dumps(config));receipt.write_text(json.dumps({'policy':b.digest(config),'rules':b.digest(['expected'])}))
            arguments=['boundary','hook','601','pre-start','--config',str(policy),'--receipt',str(receipt)]
            with patch('sys.argv',arguments),patch.object(b,'live',return_value=['expected']),patch.object(b,'verify_forwarding'),patch.object(b,'verify_routing'),patch.object(b,'run',return_value='net0: virtio=02:00:00:00:01:02,bridge=ohalice\n'):
                b.main()
            with patch('sys.argv',arguments),patch.object(b,'live',return_value=['expected']),patch.object(b,'verify_forwarding'),patch.object(b,'verify_routing'),patch.object(b,'run',return_value='net0: virtio=02:00:00:00:01:02,bridge=vmbr0\n'):
                with self.assertRaises(ValueError):b.main()
            config['workspaces'][0]['disabled']=True
            policy.write_text(json.dumps(config));receipt.write_text(json.dumps({'policy':b.digest(config),'rules':b.digest(['expected'])}))
            with patch('sys.argv',arguments),patch.object(b,'live',return_value=['expected']),patch.object(b,'verify_forwarding'),patch.object(b,'verify_routing'):
                with self.assertRaises(ValueError):b.main()

    def test_installed_sdn_layout_loads_its_deployed_boundary_module(self):
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            shutil.copy2(ROOT/'scripts/oci-hub/boundary.py',p/'oci-hub-boundary.py')
            shutil.copy2(ROOT/'scripts/oci-hub/pve-sdn.py',p/'oci-hub-pve-sdn.py')
            spec=importlib.util.spec_from_file_location('installed_sdn',p/'oci-hub-pve-sdn.py')
            installed=importlib.util.module_from_spec(spec);spec.loader.exec_module(installed)
            self.assertEqual(installed.validate(copy.deepcopy(PVE))['profile'],'oci-hub')
            with patch.object(installed,'api',side_effect=[[],None]) as api:
                self.assertTrue(installed.ensure('/cluster/sdn/vnets','vnet','ohalice',{'zone':'ocihub'}))
                self.assertEqual(api.call_args.args,('create','/cluster/sdn/vnets'))

    def test_forwarding_and_actual_routes_are_required_for_readiness(self):
        with patch.object(b,'run',return_value='0'):
            with self.assertRaises(ValueError):b.verify_forwarding()
        def kernel(*args):
            if args[3:5]==('address','show'):
                address=HUB['interfaces'][args[-1]]
                host,prefix=address.split('/')
                return json.dumps([{'addr_info':[{'local':host,'prefixlen':int(prefix)}]}])
            if 'exact' in args:
                network=args[-1];interface='wg-users' if network=='10.235.0.0/24' else 'wg-workspaces'
                return json.dumps([{'dst':network,'dev':interface}])
            return json.dumps([{'dev':'wg-users' if args[-1].startswith('10.235.') else 'wg-workspaces'}])
        with patch.object(b,'run',side_effect=kernel):b.verify_routing(HUB)
        def wrong_route(*args):
            if 'exact' in args:return '[]'
            return kernel(*args)
        with patch.object(b,'run',side_effect=wrong_route):
            with self.assertRaises(ValueError):b.verify_routing(HUB)

    def test_management_grants_require_exact_remote_source_and_known_target(self):
        for entry in ({'source':'192.0.2.0/24','vmid':601},{'source':'0.0.0.0/0','vmid':601},{'source':'192.0.2.40/32','vmid':999},{'source':'10.236.1.2/32','vmid':601}):
            config=copy.deepcopy(PVE);config['management_access']=[entry]
            with self.assertRaises(ValueError):b.render(config)
        config=copy.deepcopy(PVE);config['management_access']=[{'source':'192.0.2.40/32','vmid':601}]
        self.assertIn('tcp dport 22',b.render(config));self.assertIn('ct direction reply',b.render(config))
        self.assertNotIn('tcp dport 22',b.render(PVE))
    def test_controller_preflight_refuses_missing_target_grant(self):
        import io
        argv=['boundary','render','--config','-','--require-management-vmid','601']
        with patch('sys.argv',argv),patch('sys.stdin',io.StringIO(json.dumps(PVE))):
            with self.assertRaisesRegex(ValueError,'management source missing'):b.main()
        config=copy.deepcopy(PVE);config['management_access']=[{'source':'192.0.2.40/32','vmid':601}]
        with patch('sys.argv',argv),patch('sys.stdin',io.StringIO(json.dumps(config))),patch('sys.stdout',io.StringIO()) as output:
            b.main();self.assertIn('tcp dport 22',output.getvalue())

    def test_render_scopes_no_global_flush_or_nat(self):
        for config in (PVE,HUB):
            rendered=b.render(config)
            self.assertNotIn('flush ruleset',rendered)
            self.assertNotIn('masquerade',rendered)
            self.assertIn('hook input',rendered);self.assertIn('hook forward',rendered)
    def test_kernel_json_ignores_counters_but_not_rules(self):
        a={'rule':{'handle':12,'expr':[{'counter':{'packets':0,'bytes':0}},{'drop':None}]}}
        changed=copy.deepcopy(a);changed['rule']['handle']=13;changed['rule']['expr'][0]['counter']['packets']=100
        self.assertEqual(b.canonical(a),b.canonical(changed))
        changed['rule']['expr'][1]={'accept':None}
        self.assertNotEqual(b.canonical(a),b.canonical(changed))


if __name__=='__main__':unittest.main()
