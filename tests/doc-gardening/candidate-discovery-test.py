#!/usr/bin/env python3
"""Offline Phase 2A Shadow candidate-discovery tests."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = REPOSITORY_ROOT / "tools/doc-gardening"
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/doc-candidate-discovery.yml"
sys.path.insert(0, str(TOOL_ROOT))
import contract  # noqa: E402


def load_script(name: str) -> Any:
    path = TOOL_ROOT / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTROLLER = load_script("scan-changed-docs.py")
VALIDATOR = load_script("validate-contract.py")

NETBOX_DOCUMENT = """# Netbox

#### Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `netbox_image` | `\"netboxcommunity/netbox:v4.1.11\"` | Image |
| `netbox_port` | `8080` | Port |

{note}
"""
QWEN_DOCUMENT = """# Qwen3-TTS

### 关键配置值

```yaml
qwen3_tts_vllm_image: "vllm/vllm-omni:v0.28.0"
qwen3_tts_gpu_ordinal: 1
qwen3_tts_port: 8100
qwen3_tts_min_free_vram_mib: 512
```
"""
NETBOX_DEFAULTS = """---
netbox_port: 8080
netbox_image: "netboxcommunity/netbox:v4.1.11"
"""
QWEN_DEFAULTS = """---
qwen3_tts_gpu_ordinal: 1
qwen3_tts_min_free_vram_mib: 512
qwen3_tts_port: 8100
qwen3_tts_vllm_image: vllm/vllm-omni:v0.28.0
"""
RUNTIME_PATHS = (
    "tools/check-doc-claims.py",
    "tools/doc-gardening/contract.py",
    "tools/doc-gardening/build-candidate.py",
    "tools/doc-gardening/validate-contract.py",
    "tools/doc-gardening/scan-changed-docs.py",
    "tools/doc-gardening/prompts/analyze-v2.md",
    "tools/doc-gardening/schemas/claim-candidates-v2.json",
)


class GitFixture:
    def __init__(self, *, runtime_in_base: bool = True) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.write(
            "docs/deployment/netbox-deployment.md",
            NETBOX_DOCUMENT.format(note="Initial note."),
        )
        self.write("docs/designs/qwen3-tts-openai-api-integration.md", QWEN_DOCUMENT)
        self.write("ansible/roles/netbox/defaults/main.yml", NETBOX_DEFAULTS)
        self.write("ansible/roles/qwen3-tts/defaults/main.yml", QWEN_DEFAULTS)
        for index in range(8):
            self.write(
                f"docs/deployment/service-{index}.md",
                f"# Service {index}\n\nBase value {index}.\n",
            )
        if runtime_in_base:
            self.copy_runtime()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        if not runtime_in_base:
            self.copy_runtime()

    def copy_runtime(self) -> None:
        for relative_path in RUNTIME_PATHS:
            source = REPOSITORY_ROOT / relative_path
            destination = self.root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def remove(self, relative_path: str) -> None:
        (self.root / relative_path).unlink()

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        environment["GIT_CONFIG_SYSTEM"] = os.devnull
        result = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        return result

    def commit_head(self, message: str = "head") -> str:
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        self.head = self.git("rev-parse", "HEAD").stdout.strip()
        return self.head

    def prepare(self) -> tuple[Path, dict[str, Any], dict[str, Any]]:
        output = self.root / "candidate-output"
        preparation_path = output / "preparation.json"
        matrix_path = output / "matrix.json"
        CONTROLLER.prepare(
            self.root,
            self.base,
            self.head,
            output,
            preparation_path,
            matrix_path,
            output / "bootstrap-report.json",
        )
        return (
            output,
            json.loads(preparation_path.read_text(encoding="utf-8")),
            json.loads(matrix_path.read_text(encoding="utf-8")),
        )

    def close(self) -> None:
        self.temporary_directory.cleanup()


class CandidateDiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def _manifest_for_item(self, output: Path, item: dict[str, Any]) -> dict[str, Any]:
        return json.loads(
            (output / item["manifest_file"]).read_text(encoding="utf-8")
        )

    def _artifact(
        self,
        manifest: dict[str, Any],
        *,
        classification: str = "unknown",
        reason: str = "missing_evidence",
        evidence_refs: list[str] | None = None,
        edit: Any = None,
    ) -> dict[str, Any]:
        span = manifest["spans"][0]
        return {
            "schema_version": 2,
            "kind": "claim_candidates",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidates": [
                {
                    "id": "candidate-shadow",
                    "classification": classification,
                    "reason": reason,
                    "hunk_id": span["hunk_id"],
                    "source": {"span_id": span["id"], "quote": span["quote"]},
                    "evidence_refs": evidence_refs or [],
                    "edit": edit,
                }
            ],
        }

    def test_modified_document_builds_one_v2_manifest_and_trusted_base_validates(self) -> None:
        self.fixture.write(
            "docs/deployment/netbox-deployment.md",
            NETBOX_DOCUMENT.format(note="Updated note."),
        )
        self.fixture.commit_head()
        output, preparation, matrix = self.fixture.prepare()
        selected = [item for item in preparation["items"] if item["status"] == "selected"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(matrix["include"]), 1)
        manifest = self._manifest_for_item(output, selected[0])
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["document"]["change_type"], "M")
        self.assertRegex(manifest["document"]["base_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            [item["id"] for item in manifest["evidence"]],
            ["service.netbox.image", "service.netbox.port"],
        )

        self.fixture.git("checkout", "-q", self.fixture.base)
        validated = output / "validated.json"
        prompt = output / "prompt.md"
        CONTROLLER.verify_manifest(
            self.fixture.root,
            output / selected[0]["manifest_file"],
            self.fixture.base,
            self.fixture.head,
            validated,
            prompt,
        )
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertEqual(prompt_text.count("UNTRUSTED_MANIFEST_JSON:"), 1)
        self.assertTrue(
            prompt_text.endswith(contract.canonical_json(manifest).decode("utf-8") + "\n")
        )

    def test_nonempty_added_document_has_null_base_and_empty_evidence(self) -> None:
        path = "docs/designs/new-service.md"
        self.fixture.write(path, "# New service\n\nA new claim.\n")
        self.fixture.commit_head()
        output, preparation, matrix = self.fixture.prepare()
        self.assertEqual(len(matrix["include"]), 1)
        item = next(item for item in preparation["items"] if item["document_path"] == path)
        manifest = self._manifest_for_item(output, item)
        self.assertEqual(manifest["document"]["change_type"], "A")
        self.assertIsNone(manifest["document"]["base_sha256"])
        self.assertEqual(manifest["evidence"], [])
        self.assertGreaterEqual(len(manifest["hunks"]), 1)
        self.assertGreaterEqual(len(manifest["spans"]), 1)

    def test_deleted_renamed_and_empty_added_are_explicit_zero_call_outcomes(self) -> None:
        self.fixture.remove("docs/deployment/service-0.md")
        self.fixture.git(
            "mv",
            "docs/deployment/service-1.md",
            "docs/deployment/service-renamed.md",
        )
        self.fixture.write("docs/designs/empty.md", "")
        self.fixture.commit_head()
        _, preparation, matrix = self.fixture.prepare()
        dispositions = {
            (item["change_type"], item["reason"])
            for item in preparation["items"]
        }
        self.assertEqual(
            dispositions,
            {("D", "deleted"), ("R", "renamed"), ("A", "empty_added")},
        )
        self.assertEqual(matrix["include"], [])
        self.assertTrue(all(item["status"] == "no_analysis" for item in preparation["items"]))

    def test_no_evidence_allows_only_unknown_missing_evidence_without_edit(self) -> None:
        path = "docs/deployment/service-0.md"
        self.fixture.write(path, "# Service 0\n\nChanged unsupported claim.\n")
        self.fixture.commit_head()
        output, preparation, _ = self.fixture.prepare()
        item = next(item for item in preparation["items"] if item["status"] == "selected")
        manifest_path = output / item["manifest_file"]
        manifest = self._manifest_for_item(output, item)
        self.assertEqual(manifest["evidence"], [])
        valid = self._artifact(manifest)
        VALIDATOR.validate_artifact(valid, manifest)
        for mutation in (
            {"classification": "possibly_stale", "reason": "possibly_outdated"},
            {"classification": "unknown", "reason": "ambiguous_source"},
            {"classification": "unknown", "reason": "missing_evidence", "edit": {"find": "x", "replace": "y"}},
        ):
            with self.subTest(mutation=mutation):
                hostile = self._artifact(manifest, **mutation)
                with self.assertRaises(contract.ContractError):
                    VALIDATOR.validate_artifact(hostile, manifest)

        self.fixture.git("checkout", "-q", self.fixture.base)
        structured = output / "structured.json"
        structured.write_text(json.dumps(valid), encoding="utf-8")
        prompt_path = output / "shadow-prompt.md"
        CONTROLLER.verify_manifest(
            self.fixture.root,
            manifest_path,
            self.fixture.base,
            self.fixture.head,
            output / "validated-before-finalize.json",
            prompt_path,
        )
        schema_path = TOOL_ROOT / "schemas/claim-candidates-v2.json"
        result_path = output / "results" / f"{item['id']}.json"
        run_record_path = output / "results" / f"{item['id']}.run.json"
        result = CONTROLLER.finalize(
            self.fixture.root,
            manifest_path,
            structured,
            "success",
            self.fixture.base,
            self.fixture.head,
            prompt_path,
            schema_path,
            "claude-opus-5",
            "claude-code-action@test",
            run_record_path,
            result_path,
        )
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "missing_evidence")
        self.assertEqual(result["candidate_count"], 1)
        run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
        self.assertEqual(
            result["run_record_sha256"],
            contract.sha256_bytes(contract.canonical_json(run_record)),
        )
        VALIDATOR.validate_run_record(run_record, manifest, valid)
        retained_records = output / "retained-run-records"
        report = CONTROLLER.aggregate(
            self.fixture.root,
            output / "preparation.json",
            output / "results",
            output / "report.json",
            retained_records,
        )
        self.assertEqual(report["summary"]["unknown"], 1)
        self.assertEqual(report["results"][0]["run_record_sha256"], result["run_record_sha256"])
        self.assertEqual(
            json.loads((retained_records / f"{item['id']}.json").read_text()),
            run_record,
        )

        failed_record_path = output / "results" / "action-failed.run.json"
        failed = CONTROLLER.finalize(
            self.fixture.root,
            manifest_path,
            None,
            "failure",
            self.fixture.base,
            self.fixture.head,
            prompt_path,
            schema_path,
            "claude-opus-5",
            "claude-code-action@test",
            failed_record_path,
            output / "results" / "action-failed.json",
        )
        self.assertEqual(failed["status"], "blocked")
        self.assertEqual(failed["reason"], "action_failed")
        self.assertEqual(failed["candidate_count"], 0)
        VALIDATOR.validate_run_record(
            json.loads(failed_record_path.read_text(encoding="utf-8")),
            manifest,
            None,
        )

    def test_budget_selects_first_five_stable_paths(self) -> None:
        for index in range(7):
            self.fixture.write(
                f"docs/deployment/service-{index}.md",
                f"# Service {index}\n\nChanged value {index}.\n",
            )
        self.fixture.commit_head()
        _, preparation, matrix = self.fixture.prepare()
        selected_paths = [
            item["document_path"]
            for item in preparation["items"]
            if item["status"] == "selected"
        ]
        self.assertEqual(
            selected_paths,
            [f"docs/deployment/service-{index}.md" for index in range(5)],
        )
        self.assertEqual(len(matrix["include"]), 5)
        exhausted = [
            item for item in preparation["items"] if item["reason"] == "budget_exhausted"
        ]
        self.assertEqual(
            [item["document_path"] for item in exhausted],
            ["docs/deployment/service-5.md", "docs/deployment/service-6.md"],
        )

    def test_no_match_and_bootstrap_produce_audited_zero_call_reports(self) -> None:
        self.fixture.write("README.md", "# Changed outside scope\n")
        self.fixture.commit_head()
        output, preparation, matrix = self.fixture.prepare()
        self.assertEqual(preparation["items"], [])
        self.assertEqual(matrix["include"], [])
        report = json.loads((output / "bootstrap-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["documents"], 0)
        self.assertEqual(report["summary"]["selected"], 0)

        bootstrap = GitFixture(runtime_in_base=False)
        self.fixture.close()
        self.fixture = bootstrap
        self.fixture.write(
            "docs/deployment/service-0.md",
            "# Service 0\n\nBootstrap change.\n",
        )
        self.fixture.commit_head()
        _, preparation, matrix = self.fixture.prepare()
        self.assertEqual(matrix["include"], [])
        self.assertEqual(preparation["items"][0]["reason"], "runtime_not_bootstrapped")
        self.assertEqual(preparation["items"][0]["status"], "no_analysis")

    def test_tampered_manifest_and_missing_action_result_aggregate_as_blocked(self) -> None:
        path = "docs/deployment/service-0.md"
        self.fixture.write(path, "# Service 0\n\nChanged value.\n")
        self.fixture.commit_head()
        output, preparation, _ = self.fixture.prepare()
        item = next(item for item in preparation["items"] if item["status"] == "selected")
        manifest_path = output / item["manifest_file"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["hunks"][0]["text"] += "invented\n"
        manifest["hunks"][0]["sha256"] = contract.sha256_bytes(
            manifest["hunks"][0]["text"].encode("utf-8")
        )
        manifest["manifest_sha256"] = contract.payload_hash(manifest, "manifest_sha256")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.fixture.git("checkout", "-q", self.fixture.base)
        with self.assertRaisesRegex(contract.ContractError, "manifest_diff_stale"):
            CONTROLLER.verify_manifest(
                self.fixture.root,
                manifest_path,
                self.fixture.base,
                self.fixture.head,
                output / "never.json",
            )
        report = CONTROLLER.aggregate(
            self.fixture.root,
            output / "preparation.json",
            output / "missing-results",
            output / "report.json",
        )
        self.assertEqual(report["summary"]["blocked"], 1)
        self.assertEqual(report["results"][0]["reason"], "stale_input")
        self.assertEqual(report["results"][0]["candidate_count"], 0)

    def test_secret_input_blocks_without_manifest_or_candidate(self) -> None:
        sentinel = "SECRET_SENTINEL_DO_NOT_RETAIN"
        self.fixture.write(
            "docs/deployment/service-0.md",
            f"# Service 0\n\n{sentinel}\n",
        )
        self.fixture.commit_head()
        output, preparation, matrix = self.fixture.prepare()
        self.assertEqual(matrix["include"], [])
        item = preparation["items"][0]
        self.assertEqual(item["status"], "blocked")
        self.assertEqual(item["reason"], "unsafe_input")
        self.assertEqual(list((output / "manifests").glob(f"{item['id']}*.json")), [])
        report_text = (output / "bootstrap-report.json").read_text(encoding="utf-8")
        self.assertNotIn(sentinel, report_text)

    def test_candidate_limit_and_shadow_edit_are_rejected(self) -> None:
        path = "docs/deployment/service-0.md"
        self.fixture.write(path, "# Service 0\n\nChanged value.\n")
        self.fixture.commit_head()
        output, preparation, _ = self.fixture.prepare()
        item = next(item for item in preparation["items"] if item["status"] == "selected")
        manifest = self._manifest_for_item(output, item)
        artifact = self._artifact(manifest)
        artifact["candidates"] = [
            {**copy.deepcopy(artifact["candidates"][0]), "id": f"candidate-{index}"}
            for index in range(21)
        ]
        with self.assertRaisesRegex(contract.ContractError, "artifact_candidates_invalid"):
            VALIDATOR.validate_artifact(artifact, manifest)
        edited = self._artifact(
            manifest,
            edit={"find": manifest["spans"][0]["quote"], "replace": "replacement"},
        )
        with self.assertRaisesRegex(contract.ContractError, "candidate_shadow_has_edit"):
            VALIDATOR.validate_artifact(edited, manifest)

    def test_v2_recorded_runner_validates_fake_model_output_without_live_ai(self) -> None:
        path = "docs/deployment/service-0.md"
        self.fixture.write(path, "# Service 0\n\nChanged value.\n")
        self.fixture.commit_head()
        output, preparation, _ = self.fixture.prepare()
        item = next(item for item in preparation["items"] if item["status"] == "selected")
        manifest_path = output / item["manifest_file"]
        manifest = self._manifest_for_item(output, item)
        recorded = output / "recorded.json"
        recorded.write_text(json.dumps(self._artifact(manifest)), encoding="utf-8")
        artifact_path = output / "artifact.json"
        record_path = output / "run-record.json"
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "run-analysis.py"),
                "--root",
                str(self.fixture.root),
                "--manifest",
                str(manifest_path),
                "--recorded-output",
                str(recorded),
                "--output-artifact",
                str(artifact_path),
                "--run-record",
                str(record_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["schema_version"], 2)
        self.assertEqual(record["reason"], "recorded_replay")
        self.assertFalse(record["live"])
        VALIDATOR.validate_run_record(record, manifest, json.loads(artifact_path.read_text()))

    def test_workflow_is_read_only_bounded_base_only_and_non_target(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertIn("DRAFT:", workflow)
        self.assertIn("HEAD_REPOSITORY:", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertEqual(workflow.count("CLAUDE_CODE_OAUTH_TOKEN"), 1)
        self.assertIn("--model claude-opus-5", workflow)
        self.assertIn("--max-turns 1", workflow)
        self.assertIn('--disallowedTools "*"', workflow)
        self.assertIn("--json-schema", workflow)
        schema = json.loads((TOOL_ROOT / "schemas/claim-candidates-v2.json").read_text())
        # Claude Code's --json-schema validator rejects draft 2020-12.
        self.assertEqual(schema["$schema"], "http://json-schema.org/draft-07/schema#")
        self.assertIn("max-parallel: 1", workflow)
        self.assertIn("timeout-minutes: 5", workflow)
        self.assertIn("retention-days: 14", workflow)
        self.assertIn("verify-manifest", workflow)
        self.assertIn("--run-record", workflow)
        self.assertIn(".run.json", workflow)
        self.assertIn("candidate-report/run-records", workflow)
        self.assertNotIn("execution_file", workflow)
        analyze = workflow.split("\n  analyze:\n", 1)[1].split("\n  aggregate:\n", 1)[0]
        self.assertIn("ref: ${{ needs.prepare.outputs.base }}", analyze)
        self.assertNotIn("ref: ${{ needs.prepare.outputs.head }}", analyze)
        self.assertNotIn("git checkout", analyze)
        self.assertNotIn("git commit", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("gh pr", workflow)
        self.assertNotIn("create comment", workflow.lower())

    def test_workflow_reads_runtime_bootstrapped_without_jq_exit_status(self) -> None:
        # jq -e exits 1 when the output is false, so reading this boolean with
        # it under `bash -e` fails the step on every not-yet-bootstrapped PR.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("jq -r '.runtime_bootstrapped'", workflow)
        self.assertNotIn("jq -er '.runtime_bootstrapped'", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
