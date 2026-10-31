#!/usr/bin/env python3
"""Preserve separately owned service grants across complete boundary deployment."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('fixtures',Path(__file__).with_name('test-offline.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

class ServicePolicy(unittest.TestCase):
    def load(self,grants,config=None):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'service-egress.json';p.write_text(json.dumps(grants))
            return f.b.load_service_egress(copy.deepcopy(config or f.PVE),p)
    def test_preserves_all_existing_grants(self):
        c=self.load({'cloudflare_tunnel_vmids':[601],'hapi_ingress_grants':[{'source':'192.168.1.140/32','vmid':601}],'hapi_hub_grants':[{'destination':'192.168.1.140/32','vmid':601}]})
        rendered=f.b.render(c)
        self.assertIn('tcp dport 9443',rendered)
        self.assertIn('tcp dport 7844',rendered)
        self.assertIn('icmp type echo-request accept',rendered)
        self.assertIn('udp dport { 53, 33434-33534 } accept',rendered)
    def test_rejects_unknown_fields_and_foreign_targets(self):
        for grants in ({'unknown':[]},{'cloudflare_tunnel_vmids':[999]},{'hapi_hub_grants':[{'destination':'8.8.8.8/32','vmid':601}]},{'hapi_ingress_grants':[{'source':'0.0.0.0/0','vmid':601}]}):
            with self.subTest(grants=grants), self.assertRaises(ValueError):self.load(grants)
    def test_disabled_workspace_does_not_receive_service_exceptions(self):
        c=copy.deepcopy(f.PVE);c['workspaces'][0]['disabled']=True
        rendered=f.b.render(self.load({'cloudflare_tunnel_vmids':[601],'hapi_ingress_grants':[{'source':'192.168.1.140/32','vmid':601}]},c))
        self.assertNotIn('tcp dport 9443',rendered);self.assertNotIn('tcp dport 7844',rendered)
    def test_absent_file_and_hub_policy_are_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(f.b.load_service_egress(f.PVE,Path(d)/'absent'),f.PVE)
        self.assertEqual(self.load({'unknown':[]},f.HUB),f.HUB)

if __name__=='__main__':unittest.main()
