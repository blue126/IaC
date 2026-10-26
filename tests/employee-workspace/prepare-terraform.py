#!/usr/bin/env python3
"""Copy only employee resources into a fresh backend-free fixture."""
from pathlib import Path
import shutil
import tempfile
import re

root = Path(__file__).resolve().parents[2]
fixture = Path(tempfile.mkdtemp(prefix='employee-terraform-'))
(fixture / 'proxmox/tests').mkdir(parents=True)
for name in ['employee-access.tf', 'employee-workspace.tf', 'employee-template.tf', 'employee-boundary-hook.py.tftpl']:
    shutil.copy2(root / 'terraform/proxmox' / name, fixture / 'proxmox' / name)
access_file = fixture / 'proxmox/employee-access.tf'
access_text = access_file.read_text()
access_text = re.sub(r'provider \"proxmox\" \{.*?\n\}\n', 'provider \"proxmox\" {\n  alias = \"employee\"\n}\n', access_text, count=1, flags=re.S)
access_file.write_text(access_text)
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
