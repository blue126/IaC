#!/usr/bin/env python3
"""Check scan boundaries before CI installs the real PyYAML dependency."""

from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch


VALIDATOR = Path(__file__).resolve().parents[2] / "scripts/ci/validate-ansible.sh"
SCANNER = VALIDATOR.read_text().split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]


class AnsibleYamlScanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "ansible"
        self.root.mkdir()
        self.parsed = []

    def write(self, name, content="valid: true\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def scan(self):
        # A parser spy makes this test independent of installed packages.
        # It fails on the collection fixture if the scanner reaches it.
        yaml = ModuleType("yaml")

        def safe_load(stream):
            self.parsed.append(Path(stream.name).relative_to(self.root).as_posix())
            if "!unsafe" in stream.read():
                raise ValueError("unsupported YAML tag")

        yaml.safe_load = safe_load
        with patch.dict(sys.modules, {"yaml": yaml}):
            with patch.object(sys, "argv", ["-", str(self.root)]):
                exec(compile(SCANNER, str(VALIDATOR), "exec"), {})

    def test_skips_downloaded_collection_fixtures(self):
        self.write("playbooks/deploy.yml")
        self.write("collections/ansible_collections/netbox/netbox/tests/fixture.yml",
                   "export_template: !unsafe '{{ example }}'\n")
        self.scan()
        self.assertEqual(self.parsed, ["playbooks/deploy.yml"])

    def test_checks_all_project_yaml_locations(self):
        expected = ["requirements.yml", "roles/example/tasks/main.yml",
                    "playbooks/deploy.yaml", "inventory/hosts.yml",
                    "roles/example/files/collections/example.yaml"]
        for name in expected:
            self.write(name)
        self.write("roles/example/templates/compose.yml.j2", "{{ template }}")
        self.scan()
        self.assertCountEqual(self.parsed, expected)

    def test_keeps_vault_exclusion(self):
        self.write("inventory/group_vars/all/vault.yml", "!unsafe encrypted-fixture\n")
        self.write("inventory/group_vars/all/common.yml")
        self.scan()
        self.assertEqual(self.parsed, ["inventory/group_vars/all/common.yml"])

    def test_project_parser_errors_still_fail_validation(self):
        self.write("roles/example/tasks/main.yml", "value: !unsafe fixture\n")
        with self.assertRaisesRegex(ValueError, "unsupported YAML tag"):
            self.scan()


if __name__ == "__main__":
    unittest.main(verbosity=2)
