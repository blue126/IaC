#!/usr/bin/env python3
"""Copy only employee resources into a fresh backend-free fixture."""
from pathlib import Path
import shutil
import tempfile

root = Path(__file__).resolve().parents[2]
fixture = Path(tempfile.mkdtemp(prefix='employee-terraform-'))
(fixture / 'proxmox/tests').mkdir(parents=True)
for name in ['employee-access.tf', 'employee-workspace.tf', 'employee-boundary-hook.py.tftpl']:
    shutil.copy2(root / 'terraform/proxmox' / name, fixture / 'proxmox' / name)
shutil.copy2(Path(__file__).with_name('startup.tftest.hcl'), fixture / 'proxmox/tests/startup.tftest.hcl')
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
