#!/usr/bin/env python3
"""Build a backend-free OCI ingress root for mock-provider plans only."""
from pathlib import Path
import shutil
import tempfile

root = Path(__file__).resolve().parents[2]
fixture = Path(tempfile.mkdtemp(prefix='oci-mosh-ingress-'))
(fixture / 'tests').mkdir()
shutil.copy2(root / 'terraform/oci/oci-hub.tf', fixture / 'oci-hub.tf')
shutil.copy2(Path(__file__).with_name('ingress.tftest.hcl'), fixture / 'tests/ingress.tftest.hcl')
(fixture / 'versions.tf').write_text('''terraform {
  required_providers {
    oci = { source = "oracle/oci", version = "8.3.0" }
  }
}
variable "tenancy_ocid" { type = string }
''')
print(fixture)
