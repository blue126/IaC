#!/usr/bin/env python3
"""Check additive installed-helper migration and restrictive worker Hub grants."""
import copy
import importlib.util
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load('prepare_hub_boundary', 'scripts/prepare-hapi-hub-boundary.py')
fixtures = load('oci_boundary_fixtures', 'tests/oci-hub/test-offline.py')
source = (ROOT / 'scripts/oci-hub/boundary.py').read_text()


class HubBoundaryTest(unittest.TestCase):
    def candidate(self):
        text, service = prepare.prepare(source + '\ndef unrelated_feature(): return "retain"\n',
                                        {'cloudflare_tunnel_vmids': [], 'hapi_ingress_grants': []},
                                        '192.168.1.140', [601])
        module = types.ModuleType('prepared_boundary')
        exec(compile(text, '<prepared-boundary>', 'exec'), module.__dict__)
        return module, service

    def test_existing_modes_and_unrelated_features_are_preserved(self):
        module, _ = self.candidate()
        self.assertEqual(module.unrelated_feature(), 'retain')
        for config in [fixtures.PVE, fixtures.HUB]:
            self.assertEqual(module.render(copy.deepcopy(config)), fixtures.b.render(copy.deepcopy(config)))

    def test_only_registered_enabled_worker_can_initiate_the_hub_tls_flow(self):
        module, service = self.candidate()
        config = {**copy.deepcopy(fixtures.PVE), **service}
        rules = module.render(config)
        self.assertIn('ip saddr 10.236.1.2 ip daddr 192.168.1.140/32 tcp dport 9443', rules)
        self.assertIn('ip saddr 192.168.1.140/32 ip daddr 10.236.1.2 tcp sport 9443 ct state established ct direction reply', rules)
        self.assertNotIn('192.168.1.140/32 tcp dport 22', rules)
        config['workspaces'][0]['disabled'] = True
        self.assertNotIn('192.168.1.140/32 tcp dport 9443', module.render(config))
        config['hapi_hub_grants'][0]['vmid'] = 999
        with self.assertRaises(ValueError):
            module.render(config)

    def test_broad_public_metadata_and_worker_network_destinations_fail_closed(self):
        module, service = self.candidate()
        for destination in ['0.0.0.0/0', '1.1.1.1/32', '169.254.169.254/32', '192.168.1.0/24', '10.236.1.2/32']:
            config = {**copy.deepcopy(fixtures.PVE), **copy.deepcopy(service)}
            config['hapi_hub_grants'][0]['destination'] = destination
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                module.render(config)

    def test_duplicate_grants_and_unreviewed_source_context_are_rejected(self):
        module, service = self.candidate()
        config = {**copy.deepcopy(fixtures.PVE), **service}
        config['hapi_hub_grants'].append(copy.deepcopy(config['hapi_hub_grants'][0]))
        with self.assertRaises(ValueError):
            module.render(config)
        for text in [source.replace("c.get('management_access',[])", "c.get('new_management',[])"), source + '\n# hapi_hub_grants\n']:
            with self.assertRaises(ValueError):
                prepare.prepare(text, {}, '192.168.1.140', [601])


if __name__ == '__main__':
    unittest.main(verbosity=2)
