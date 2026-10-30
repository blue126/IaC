#!/usr/bin/env python3
"""Verify only retained PVE quarantine and disabled-hook behavior."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import jinja2
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('boundary',ROOT/'ansible/roles/retired-workspace-boundary/files/boundary.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
class RetiredBoundary(unittest.TestCase):
    def test_policy_only_denies_reserved_guest_ports(self):
        text=(ROOT/'ansible/roles/retired-workspace-boundary/templates/boundary.nft.j2').read_text()
        rendered=jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(text).render(retired_workspace_boundary_vmids=[503])
        self.assertEqual(rendered.count('tap503i0'),3)
        self.assertNotIn('tap500',rendered);self.assertNotIn('masquerade',rendered);self.assertNotIn('wg-',rendered)
    def test_normalization_keeps_policy_but_ignores_ephemeral_counters(self):
        self.assertEqual(b.normalize({'handle':4,'packets':90,'verdict':'drop'}),{'packets':0,'verdict':'drop'})
        self.assertNotEqual(b.normalize({'verdict':'drop'}),b.normalize({'verdict':'accept'}))
    def test_apply_verify_detects_kernel_or_source_drift(self):
        with tempfile.TemporaryDirectory() as d:
            policy=Path(d)/'guard.nft';applied=Path(d)/'applied.json';policy.write_text('scoped quarantine')
            snapshot={'nftables':[{'table':{'family':'bridge','name':'employee_boundary'}}]}
            with patch.object(b,'POLICY',policy),patch.object(b,'APPLIED',applied),patch.object(b,'snapshot',return_value=snapshot),patch.object(b.subprocess,'run') as command:
                b.apply();b.verify();self.assertEqual(command.call_args.args[0],['/usr/sbin/nft','-f',str(policy)])
                with patch.object(b,'snapshot',return_value={'nftables':[]}):
                    with self.assertRaises(RuntimeError):b.verify()
                policy.write_text('changed')
                with self.assertRaises(RuntimeError):b.verify()
    def test_failed_kernel_apply_does_not_commit_a_new_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            policy=Path(d)/'guard.nft';applied=Path(d)/'applied.json';policy.write_text('policy');applied.write_text('previous')
            with patch.object(b,'POLICY',policy),patch.object(b,'APPLIED',applied),patch.object(b.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['nft'])):
                with self.assertRaises(subprocess.CalledProcessError):b.apply()
            self.assertEqual(applied.read_text(),'previous')
    def test_disabled_and_wrong_target_hooks_reject_before_commands(self):
        text=(ROOT/'terraform/proxmox/employee-boundary-hook.py.tftpl').read_text()
        code=text.replace('${vmid}','503').replace('${gateway_tap}','tap500i3').replace('${disabled}','true');context={'__name__':'test_hook'};exec(compile(code,'<retired-hook>','exec'),context)
        for target in ('503','999'):
            with patch.object(context['sys'],'argv',['hook',target,'pre-start']),patch.object(context['subprocess'],'run') as commands:
                with self.assertRaises(RuntimeError):context['main']()
                commands.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
