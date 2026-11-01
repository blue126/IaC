#!/usr/bin/env python3
"""Copy only employee resources into a fresh backend-free fixture."""
from pathlib import Path
import shutil
import tempfile

root = Path(__file__).resolve().parents[2]
fixture = Path(tempfile.mkdtemp(prefix='employee-terraform-'))
(fixture / 'proxmox/tests').mkdir(parents=True)
for name in ['employee-access.tf', 'employee-workspace.tf', 'employee-template.tf', 'employee-boundary-hook.py.tftpl']:
    shutil.copy2(root / 'terraform/proxmox' / name, fixture / 'proxmox' / name)
(fixture / 'proxmox/provider.tf').write_text('provider "proxmox" {\n  alias = "pve2"\n}\n')
(fixture / 'proxmox/hub-ownership-fixture.tf').write_text('variable "oci_hub_workspaces" {\n type = map(any)\n default = {}\n}\n')
for test in Path(__file__).parent.glob('*.tftest.hcl'):
    shutil.copy2(test, fixture / 'proxmox/tests' / test.name)
(fixture / 'proxmox/versions.tf').write_text('''terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
      version = "0.70.0"
    }
    ansible = {
      source = "ansible/ansible"
      version = "~> 1.3.0"
    }
  }
}
''')
print(fixture / 'proxmox')
