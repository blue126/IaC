#!/usr/bin/env python3
"""Fixture tests for the deterministic documentation claim checker."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPOSITORY_ROOT / "tools/check-doc-claims.py"
MODULE_SPEC = importlib.util.spec_from_file_location("check_doc_claims", CHECKER_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = CHECKER
MODULE_SPEC.loader.exec_module(CHECKER)


NETBOX_DOCUMENT = """# Netbox

#### Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `netbox_image` | `"netboxcommunity/netbox:v4.1.11"` | Image |
| `netbox_port` | `8080` | Port |
"""

LLM_DOCUMENT = """# LLM Server

### `defaults/main.yml` — 关键变量

```yaml
llm_server_engine_version: "f7923739"
llm_server_webui_port: 3000
```
"""

NETBOX_DEFAULTS = """---
netbox_port: 8080
netbox_image: "netboxcommunity/netbox:v4.1.11"
"""

LLM_DEFAULTS = """---
llm_server_engine_version: "f7923739"
llm_server_webui_port: 3000
"""


class Fixture:
    def __init__(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.write("docs/deployment/netbox-deployment.md", NETBOX_DOCUMENT)
        self.write("docs/deployment/llm-server-deployment.md", LLM_DOCUMENT)
        self.write("ansible/roles/netbox/defaults/main.yml", NETBOX_DEFAULTS)
        self.write("ansible/roles/llm-server/defaults/main.yml", LLM_DEFAULTS)

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def read(self, relative_path: str) -> str:
        return (self.root / relative_path).read_text(encoding="utf-8")

    def replace(self, relative_path: str, old: str, new: str) -> None:
        self.write(relative_path, self.read(relative_path).replace(old, new))

    def close(self) -> None:
        self.temporary_directory.cleanup()


class DocClaimsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Fixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def claim(self, claim_id: str) -> dict[str, object]:
        report = CHECKER.build_report(self.fixture.root)
        return next(claim for claim in report["claims"] if claim["id"] == claim_id)

    def assert_reason(self, claim_id: str, status: str, reason: str) -> None:
        claim = self.claim(claim_id)
        self.assertEqual(claim["status"], status)
        self.assertEqual(claim["reason"], reason)

    def test_repository_fixture_has_four_verified_claims(self) -> None:
        report = CHECKER.build_report(REPOSITORY_ROOT)
        self.assertEqual(report["schema_version"], 1)
        self.assertRegex(report["revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(
            [claim["id"] for claim in report["claims"]],
            [claim.claim_id for claim in CHECKER.CLAIMS],
        )
        self.assertEqual([claim["status"] for claim in report["claims"]], ["verified"] * 4)
        for claim in report["claims"]:
            self.assertRegex(claim["document"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(claim["oracle"]["sha256"], r"^[0-9a-f]{64}$")

    def test_changed_markdown_scalar_is_contradiction(self) -> None:
        self.fixture.replace("docs/deployment/netbox-deployment.md", "`8080`", "`8081`")
        claim = self.claim("service.netbox.port")
        self.assertEqual(claim["status"], "contradiction")
        self.assertEqual(claim["reason"], "value_mismatch")
        self.assertEqual(claim["document"]["locator"], "Configuration Variables::netbox_port")

    def test_changed_oracle_scalar_is_contradiction(self) -> None:
        self.fixture.replace("ansible/roles/netbox/defaults/main.yml", "netbox_port: 8080", "netbox_port: 8081")
        claim = self.claim("service.netbox.port")
        self.assertEqual(claim["status"], "contradiction")
        self.assertEqual(claim["reason"], "value_mismatch")
        self.assertEqual(claim["oracle"]["path"], "ansible/roles/netbox/defaults/main.yml")
        self.assertEqual(claim["oracle"]["key"], "netbox_port")

    def test_type_mismatch_is_contradiction(self) -> None:
        self.fixture.replace("docs/deployment/netbox-deployment.md", "`8080`", '`"8080"`')
        self.assert_reason("service.netbox.port", "contradiction", "type_mismatch")

    def test_pathological_integer_is_indeterminate_without_crashing(self) -> None:
        huge_integer = "9" * 5000
        self.fixture.replace("docs/deployment/netbox-deployment.md", "`8080`", f"`{huge_integer}`")
        self.fixture.replace("ansible/roles/netbox/defaults/main.yml", "netbox_port: 8080", f"netbox_port: {huge_integer}")
        self.assert_reason("service.netbox.port", "indeterminate", "locator_non_scalar")

    def test_unsupported_implicit_yaml_scalars_fail_closed(self) -> None:
        for raw_value in ("yes", "OFF", "0x10", "0o10", "0b10", "0123", "1e3", "1.0e3", ".inf"):
            with self.subTest(raw_value=raw_value):
                parsed, value = CHECKER._parse_scalar(raw_value)
                self.assertFalse(parsed)
                self.assertIsNone(value)

        self.fixture.replace("docs/deployment/netbox-deployment.md", "`8080`", "`yes`")
        self.fixture.replace("ansible/roles/netbox/defaults/main.yml", "netbox_port: 8080", "netbox_port: yes")
        self.assert_reason("service.netbox.port", "indeterminate", "locator_non_scalar")

    def test_changed_string_claim_does_not_echo_secret_sentinel(self) -> None:
        sentinel = "SECRET_SENTINEL_DO_NOT_ECHO"
        self.fixture.replace(
            "docs/deployment/netbox-deployment.md",
            '"netboxcommunity/netbox:v4.1.11"',
            f'"{sentinel}"',
        )
        claim = self.claim("service.netbox.image")
        self.assertEqual(claim["status"], "contradiction")
        self.assertNotIn(sentinel, json.dumps(claim))
        self.assertEqual(claim["document"]["value"], {"type": "string", "redacted": True})

    def test_missing_sources_are_indeterminate(self) -> None:
        (self.fixture.root / "docs/deployment/netbox-deployment.md").unlink()
        self.assert_reason("service.netbox.port", "indeterminate", "document_source_missing")
        self.fixture.write("docs/deployment/netbox-deployment.md", NETBOX_DOCUMENT)
        (self.fixture.root / "ansible/roles/netbox/defaults/main.yml").unlink()
        self.assert_reason("service.netbox.port", "indeterminate", "oracle_source_missing")

    def test_missing_locator_is_indeterminate(self) -> None:
        self.fixture.replace("docs/deployment/netbox-deployment.md", "Configuration Variables", "Other Variables")
        self.assert_reason("service.netbox.port", "indeterminate", "locator_missing")

    def test_duplicate_locator_is_indeterminate(self) -> None:
        self.fixture.write(
            "docs/deployment/netbox-deployment.md",
            NETBOX_DOCUMENT + "\n#### Configuration Variables\n\n| Variable | Default |\n|---|---|\n| `netbox_port` | `8080` |\n",
        )
        self.assert_reason("service.netbox.port", "indeterminate", "locator_multiple")

    def test_table_locator_uses_headers_and_optional_outer_pipes(self) -> None:
        self.fixture.write(
            "docs/deployment/netbox-deployment.md",
            """# Netbox

   #### Configuration Variables

Description | Default | Variable
--- | --- | ---
Port | 8080 | `netbox_port`
Image | "netboxcommunity/netbox:v4.1.11" | `netbox_image`
""",
        )
        report = CHECKER.build_report(self.fixture.root)
        self.assertEqual([claim["status"] for claim in report["claims"][:2]], ["verified", "verified"])

    def test_table_locator_ignores_fenced_fake_rows(self) -> None:
        self.fixture.write(
            "docs/deployment/netbox-deployment.md",
            """# Netbox

#### Configuration Variables

````markdown
| Variable | Default |
|---|---|
| `netbox_port` | `9999` |
```
| `netbox_port` | `9998` |
````

| Variable | Default |
|---|---|
| `netbox_port` | `8080` |
| `netbox_image` | `"netboxcommunity/netbox:v4.1.11"` |
""",
        )
        self.assertEqual(self.claim("service.netbox.port")["status"], "verified")

    def test_missing_oracle_key_is_indeterminate(self) -> None:
        self.fixture.replace("ansible/roles/netbox/defaults/main.yml", "netbox_port: 8080\n", "")
        self.assert_reason("service.netbox.port", "indeterminate", "oracle_key_missing")

    def test_duplicate_oracle_key_is_indeterminate(self) -> None:
        self.fixture.write("ansible/roles/netbox/defaults/main.yml", NETBOX_DEFAULTS + "netbox_port: 8080\n")
        self.assert_reason("service.netbox.port", "indeterminate", "oracle_key_duplicate")

    def test_non_scalar_oracle_is_indeterminate(self) -> None:
        self.fixture.replace("ansible/roles/netbox/defaults/main.yml", "netbox_port: 8080", "netbox_port:\n  value: 8080")
        self.assert_reason("service.netbox.port", "indeterminate", "oracle_non_scalar")

    def test_fenced_yaml_locator_is_section_scoped_and_unique(self) -> None:
        self.fixture.write(
            "docs/deployment/llm-server-deployment.md",
            """# LLM Server

```yaml
llm_server_webui_port: 9999
```

### `defaults/main.yml` — 关键变量

```yaml
llm_server_engine_version: "f7923739"
llm_server_webui_port: 3000
llm_server_webui_port: 3000
```
""",
        )
        self.assert_reason("service.llm-server.webui-port", "indeterminate", "locator_multiple")

    def test_heading_and_fenced_yaml_markdown_variants(self) -> None:
        for opener, inner_non_closer, closer in (
            ("~~~~yaml", "~~~", "~~~~"),
            ("````yaml", "~~~", "````"),
        ):
            with self.subTest(opener=opener):
                self.fixture.write(
                    "docs/deployment/llm-server-deployment.md",
                    f"""# LLM Server

   ### `defaults/main.yml` — 关键变量

{opener}
llm_server_engine_version: "f7923739"
{inner_non_closer}
llm_server_webui_port: 3000
{closer}
""",
                )
                report = CHECKER.build_report(self.fixture.root)
                self.assertEqual([claim["status"] for claim in report["claims"][2:]], ["verified", "verified"])

    def test_source_symlink_cannot_escape_repository_root(self) -> None:
        sentinel = "OUTSIDE_SECRET_SENTINEL"
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_document = Path(outside.name) / "netbox.md"
        outside_document.write_text(NETBOX_DOCUMENT + sentinel, encoding="utf-8")
        document = self.fixture.root / "docs/deployment/netbox-deployment.md"
        document.unlink()
        document.symlink_to(outside_document)

        report = CHECKER.build_report(self.fixture.root)
        claim = next(item for item in report["claims"] if item["id"] == "service.netbox.port")
        self.assertEqual(claim["status"], "indeterminate")
        self.assertEqual(claim["reason"], "document_source_outside_root")
        self.assertIsNone(claim["document"]["sha256"])
        self.assertNotIn(sentinel, json.dumps(report))

    def test_report_write_is_atomic_when_replace_fails(self) -> None:
        output = self.fixture.root / "report.json"
        output.write_text("old-complete-report\n", encoding="utf-8")
        with mock.patch.object(CHECKER.os, "replace", side_effect=OSError("replace failed")):
            self.assertFalse(CHECKER._write_report(output, CHECKER.build_report(self.fixture.root)))
        self.assertEqual(output.read_text(encoding="utf-8"), "old-complete-report\n")
        self.assertEqual(list(output.parent.glob(".report.json.*.tmp")), [])

    def test_workflow_runs_on_every_pull_request_with_read_only_permissions(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github/workflows/doc-accuracy.yml").read_text(encoding="utf-8")
        trigger_block = workflow.split("permissions:", 1)[0]
        self.assertIn("  pull_request:\n", trigger_block)
        self.assertNotIn("paths:", trigger_block)
        self.assertNotIn("push:", trigger_block)
        self.assertNotIn("workflow_dispatch:", trigger_block)
        self.assertNotIn("secrets:", workflow)
        self.assertNotIn("environment:", workflow)
        self.assertEqual(workflow.count("contents: read"), 2)
        self.assertGreaterEqual(workflow.count("if: always()"), 2)

    def test_report_schema_is_stable_and_does_not_echo_unrelated_input(self) -> None:
        sentinel = "SECRET_SENTINEL_DO_NOT_ECHO"
        self.fixture.write(
            "ansible/roles/netbox/defaults/main.yml",
            NETBOX_DEFAULTS + f'unrelated_password: "{sentinel}"\n',
        )
        first = json.dumps(CHECKER.build_report(self.fixture.root), ensure_ascii=False)
        second = json.dumps(CHECKER.build_report(self.fixture.root), ensure_ascii=False)
        self.assertEqual(first, second)
        self.assertNotIn(sentinel, first)
        self.assertNotIn(str(self.fixture.root), first)
        self.assertEqual(set(json.loads(first)), {"schema_version", "revision", "claims"})

    def test_cli_exit_codes_and_failure_report_are_deterministic(self) -> None:
        output = self.fixture.root / "report.json"
        success = subprocess.run(
            [sys.executable, str(CHECKER_PATH), "--root", str(self.fixture.root), "--output", str(output)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(success.returncode, 0)
        self.assertTrue(output.is_file())
        self.assertNotIn(str(self.fixture.root), output.read_text(encoding="utf-8"))

        self.fixture.replace("docs/deployment/netbox-deployment.md", "`8080`", "`8081`")
        failure = subprocess.run(
            [sys.executable, str(CHECKER_PATH), "--root", str(self.fixture.root), "--output", str(output)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(failure.returncode, 1)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertIn("contradiction", [claim["status"] for claim in report["claims"]])
        self.assertNotIn(str(self.fixture.root), failure.stdout + failure.stderr + json.dumps(report))


if __name__ == "__main__":
    unittest.main(verbosity=2)
