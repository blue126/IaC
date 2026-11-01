#!/usr/bin/env python3
"""Check the repository helper's restrictive worker Hub grants."""
import copy
import importlib.util
from pathlib import Path
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
# Hub egress support now lives in the repository helper, so every deploy keeps it.
helper = load('repository_boundary', 'scripts/oci-hub/boundary.py')
SERVICE = {'cloudflare_tunnel_vmids': [], 'hapi_ingress_grants': [],
           'hapi_hub_grants': [{'vmid': 601, 'destination': '192.168.1.140/32'}]}


class HubBoundaryTest(unittest.TestCase):
    def candidate(self):
        return helper, copy.deepcopy(SERVICE)

    def test_policies_without_hub_grants_render_no_hub_flow(self):
        for config in [fixtures.PVE, fixtures.HUB]:
            self.assertNotIn('tcp dport 9443', helper.render(copy.deepcopy(config)))

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
        # The in-place migration refuses a helper that already carries the support.
        with self.assertRaisesRegex(ValueError, 'already contains Hub egress support'):
            prepare.prepare(source, {}, '192.168.1.140', [601])


if __name__ == '__main__':
    unittest.main(verbosity=2)
