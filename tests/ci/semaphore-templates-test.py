#!/usr/bin/env python3
"""Contract for the manually run wsctl templates; reads the definitions offline."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "ansible/roles/semaphore/files/semaphore-bootstrap.py"


def load_bootstrap():
    # exec instead of import so the check leaves no bytecode cache in the role.
    namespace = {"__name__": "semaphore_bootstrap"}
    source = BOOTSTRAP.read_text(encoding="utf-8")
    exec(compile(source, str(BOOTSTRAP), "exec"), namespace)
    return namespace


class Templates(unittest.TestCase):
    def setUp(self):
        self.bootstrap = load_bootstrap()

    def template(self, name):
        arguments, survey, override, description = self.bootstrap["TEMPLATES"][name]
        self.assertTrue(description)
        return arguments, [field["name"] for field in survey], override

    def test_renew_is_manual_and_takes_the_employee_and_months(self):
        arguments, fields, override = self.template("wsctl renew")
        self.assertEqual(arguments, ["renew"])
        self.assertEqual(fields, ["WSCTL_EMPLOYEE", "WSCTL_MONTHS"])
        self.assertFalse(override)
        self.assertNotIn("wsctl renew", self.bootstrap["SCHEDULES"])

    def test_retire_is_manual_and_keeps_the_approval_field(self):
        arguments, fields, override = self.template("wsctl retire")
        self.assertEqual(arguments, ["retire"])
        self.assertEqual(fields, ["WSCTL_EMPLOYEE", "WSCTL_APPROVE"])
        self.assertFalse(override)
        self.assertNotIn("wsctl retire", self.bootstrap["SCHEDULES"])


if __name__ == "__main__":
    unittest.main()
