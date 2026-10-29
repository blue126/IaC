#!/usr/bin/env python3
"""Prepare only source and pinned providers; never copy credentials or state."""
from pathlib import Path
import shutil
import tempfile

root=Path(__file__).resolve().parents[2]
fixture=Path(tempfile.mkdtemp(prefix='oci-hub-terraform-'))
(fixture/'proxmox/tests').mkdir(parents=True)
shutil.copytree(root/'terraform/modules/proxmox-vm',fixture/'modules/proxmox-vm',ignore=shutil.ignore_patterns('.terraform','*.tfstate*','*.tfvars*'))
shutil.copy2(root/'terraform/proxmox/oci-hub-workspace.tf',fixture/'proxmox/oci-hub-workspace.tf')
shutil.copy2(Path(__file__).with_name('startup.tftest.hcl'),fixture/'proxmox/tests/startup.tftest.hcl')
(fixture/'proxmox/versions.tf').write_text('''terraform {
  required_providers {
    proxmox = { source = "bpg/proxmox", version = "0.70.0" }
    ansible = { source = "ansible/ansible", version = "~> 1.3.0" }
  }
}
provider "proxmox" { alias = "pve2" }
variable "employee_workspaces" {
  type = map(any)
  default = {}
}
''')
# Expose module values in this synthetic root only, for create-time assertions.
p=fixture/'modules/proxmox-vm/outputs.tf'
p.write_text(p.read_text()+'''\noutput "startup_contract" {
  value = {
    started = proxmox_virtual_environment_vm.vm.started
    on_boot = proxmox_virtual_environment_vm.vm.on_boot
    protection = proxmox_virtual_environment_vm.vm.protection
    hook = proxmox_virtual_environment_vm.vm.hook_script_file_id
  }
}
''')
print(fixture/'proxmox')
