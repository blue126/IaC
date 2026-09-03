#!/usr/bin/env python3
"""Offline regression tests for the Phase 2 document gardening controller."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = REPOSITORY_ROOT / "tools/doc-gardening"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(TOOL_ROOT))
import contract  # noqa: E402


def load_script(name: str) -> Any:
    path = TOOL_ROOT / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_script("validate-contract.py")
EVALUATOR = load_script("evaluate.py")


def load_phase_one() -> Any:
    path = REPOSITORY_ROOT / "tools/check-doc-claims.py"
    spec = importlib.util.spec_from_file_location("check_doc_claims", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves field types through sys.modules, so the module has
    # to be registered before its body runs.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PHASE_ONE = load_phase_one()


def phase_one_required_paths() -> set[str]:
    """Every repository path the current Phase 1 claim set reads."""
    required: set[str] = set()
    for claim in PHASE_ONE.CLAIMS:
        required.add(claim.document_path)
        required.add(claim.oracle_path)
    return required


NETBOX_DOCUMENT = """# Netbox

#### Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `netbox_image` | `"netboxcommunity/netbox:v4.1.11"` | Image |
| `netbox_port` | `8080` | Port |

{note}
"""
# The second seeded service mirrors the Phase 1 claim set, which covers
# netbox and qwen3-tts. It carried llm-server until that role was retired.
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


# The Phase 1 checker runs over this fixture and must find every claim it
# knows about, so these files mirror its claim set. When main adds, renames or
# retires a claim, this mapping has to move with it.
SEEDED_FILES = {
    "docs/deployment/netbox-deployment.md": NETBOX_DOCUMENT,
    "docs/designs/qwen3-tts-openai-api-integration.md": QWEN_DOCUMENT,
    "ansible/roles/netbox/defaults/main.yml": NETBOX_DEFAULTS,
    "ansible/roles/qwen3-tts/defaults/main.yml": QWEN_DEFAULTS,
    # Out of scope by prefix, and in the repository, so the scope allowlist is
    # the only thing that can reject it.
    "docs/learningnotes/2026-01-01-example.md": "# Note\n",
}
PHASE_ONE_HINT = (
    "The doc-gardening fixture must seed every document and oracle in "
    "tools/check-doc-claims.py CLAIMS. Update SEEDED_FILES (and the document "
    "constants above it) to match the current claim set."
)


def assert_fixture_covers_phase_one() -> None:
    missing = phase_one_required_paths() - set(SEEDED_FILES)
    if missing:
        raise AssertionError(
            f"{PHASE_ONE_HINT} Missing: {sorted(missing)}"
        )


class GitFixture:
    def __init__(self, base_note: str = "Initial note.", head_note: str = "Updated note.") -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        assert_fixture_covers_phase_one()
        for relative_path, content in SEEDED_FILES.items():
            self.write(relative_path, content.format(note=base_note))
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()
        self.write("docs/deployment/netbox-deployment.md", NETBOX_DOCUMENT.format(note=head_note))
        self.git("add", "docs/deployment/netbox-deployment.md")
        self.git("commit", "-qm", "head")
        self.head = self.git("rev-parse", "HEAD").stdout.strip()
        self.evidence_report = self.root / "phase-1-report.json"
        report = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "tools/check-doc-claims.py"),
                "--root",
                str(self.root),
                "--output",
                str(self.evidence_report),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if report.returncode != 0:
            raise AssertionError(
                f"{PHASE_ONE_HINT}\n{report.stdout}{report.stderr}"
            )

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        # Host git config must not reach the fixture: commit.gpgsign, hooks
        # and templates would otherwise decide whether these commits succeed.
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

    def build(
        self, *extra: str, documents: list[str] | None = None
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        output = self.root / "manifest.json"
        selected = ["docs/deployment/netbox-deployment.md"] if documents is None else documents
        command = [
            sys.executable,
            str(TOOL_ROOT / "build-candidate.py"),
            "--root",
            str(self.root),
        ]
        for document in selected:
            command += ["--document", document]
        command += [
            "--base",
            self.base,
            "--head",
            self.head,
            "--evidence-report",
            str(self.evidence_report),
            "--evidence-id",
            "service.netbox.port",
            "--output",
            str(output),
            *extra,
        ]
        return subprocess.run(command, check=False, capture_output=True, text=True), output

    def close(self) -> None:
        self.temporary_directory.cleanup()


class DocGardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = GitFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def assert_blocked_without(self, result: subprocess.CompletedProcess[str], sentinel: str) -> None:
        self.assertEqual(result.returncode, 2)
        self.assertIn("blocked", result.stderr)
        self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_fixture_seeds_every_document_and_oracle_phase_one_reads(self) -> None:
        # Phase 1's claim set is the outside world for this suite. When it
        # moves, this fails by name instead of every test dying in setUp.
        self.assertEqual(phase_one_required_paths() - set(SEEDED_FILES), set(), PHASE_ONE_HINT)

    def test_manifest_packages_one_document_hunks_spans_and_selected_evidence(self) -> None:
        sentinel = "UNRELATED_ENVIRONMENT_SENTINEL"
        self.fixture.write("unrelated.txt", sentinel)
        os.environ[sentinel] = sentinel
        self.addCleanup(os.environ.pop, sentinel, None)
        result, output = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(output.read_text(encoding="utf-8"))
        VALIDATOR.validate_manifest_structure(manifest)
        VALIDATOR.validate_manifest_repository(manifest, self.fixture.root)
        self.assertEqual(manifest["document"]["path"], "docs/deployment/netbox-deployment.md")
        self.assertEqual(manifest["revision"], {"base": self.fixture.base, "head": self.fixture.head})
        self.assertEqual([item["id"] for item in manifest["evidence"]], ["service.netbox.port"])
        self.assertGreaterEqual(len(manifest["hunks"]), 1)
        self.assertGreaterEqual(len(manifest["spans"]), 1)
        self.assertNotIn(sentinel, json.dumps(manifest))

    def test_manifest_rejects_fake_evidence_reference(self) -> None:
        output = self.fixture.root / "fake.json"
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "build-candidate.py"),
                "--root",
                str(self.fixture.root),
                "--document",
                "docs/deployment/netbox-deployment.md",
                "--base",
                self.fixture.base,
                "--head",
                self.fixture.head,
                "--evidence-report",
                str(self.fixture.evidence_report),
                "--evidence-id",
                "fabricated.evidence.id",
                "--output",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assert_blocked_without(result, "fabricated evidence payload")
        self.assertFalse(output.exists())

    def test_manifest_rejects_out_of_scope_or_multiple_document_argument(self) -> None:
        # A Markdown file that exists in the fixture repository and is out of
        # scope only by prefix, so the allowlist is what must reject it.
        result, _ = self.fixture.build(
            documents=["docs/learningnotes/2026-01-01-example.md"]
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("document_path_out_of_scope", result.stderr)
        # Non-Markdown is rejected by the same code for the suffix rule.
        result, _ = self.fixture.build(
            documents=["ansible/roles/netbox/defaults/main.yml"]
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("document_path_out_of_scope", result.stderr)
        # Both documents exist and are in scope, so only the one-document
        # invariant can reject this.
        result, output = self.fixture.build(
            documents=[
                "docs/deployment/netbox-deployment.md",
                "docs/designs/qwen3-tts-openai-api-integration.md",
            ]
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("document_multiple", result.stderr)
        self.assertFalse(output.exists())

    def test_secret_sentinel_blocks_packaging_without_echo(self) -> None:
        sentinel = "SECRET_SENTINEL_DO_NOT_ECHO"
        replacement = GitFixture(head_note=sentinel)
        self.fixture.close()
        self.fixture = replacement
        result, output = self.fixture.build()
        self.assert_blocked_without(result, sentinel)
        self.assertFalse(output.exists())

    def test_secret_removed_between_base_and_head_still_blocks_packaging(self) -> None:
        # The head document is clean; the secret survives only as a removed
        # line inside the hunk text that would be handed to the model.
        sentinel = "SECRET_SENTINEL_DO_NOT_ECHO"
        replacement = GitFixture(base_note=sentinel)
        self.fixture.close()
        self.fixture = replacement
        result, output = self.fixture.build()
        self.assert_blocked_without(result, sentinel)
        self.assertFalse(output.exists())

    def test_dirty_or_stale_document_blocks_validation(self) -> None:
        result, output = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.fixture.write(
            "docs/deployment/netbox-deployment.md",
            NETBOX_DOCUMENT.format(note="Changed after packaging."),
        )
        manifest = VALIDATOR.validate_manifest_structure(json.loads(output.read_text(encoding="utf-8")))
        with self.assertRaisesRegex(contract.ContractError, "manifest_working_file_stale"):
            VALIDATOR.validate_manifest_repository(manifest, self.fixture.root)

    def test_stale_sha_and_hallucinated_quote_fail_closed(self) -> None:
        manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        stale = copy.deepcopy(manifest)
        stale["document"]["head_sha256"] = "f" * 64
        stale["manifest_sha256"] = contract.payload_hash(stale, "manifest_sha256")
        with self.assertRaisesRegex(contract.ContractError, "manifest_evidence_sha_mismatch"):
            VALIDATOR.validate_manifest_structure(stale)
        artifact = json.loads((FIXTURES / "valid-candidate.json").read_text(encoding="utf-8"))
        artifact["candidates"][0]["source"]["quote"] = "hallucinated"
        with self.assertRaisesRegex(contract.ContractError, "candidate_quote_mismatch"):
            VALIDATOR.validate_artifact(artifact, manifest)

    def test_valid_candidate_unknown_and_exact_edit_contract(self) -> None:
        manifest = VALIDATOR.validate_manifest_structure(
            json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        )
        for filename in ("valid-candidate.json", "unknown.json", "prompt-injection.json"):
            with self.subTest(filename=filename):
                artifact = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
                VALIDATOR.validate_artifact(artifact, manifest)
        unknown_edit = json.loads((FIXTURES / "unknown-with-edit.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(contract.ContractError, "candidate_unknown_has_edit"):
            VALIDATOR.validate_artifact(unknown_edit, manifest)

    def test_hostile_schema_extra_fake_ref_and_secret_output_fail_closed(self) -> None:
        manifest = VALIDATOR.validate_manifest_structure(
            json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        )
        for filename in ("schema-extra.json", "fake-ref.json", "multi-doc.json", "secret-sentinel.json"):
            with self.subTest(filename=filename):
                artifact = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
                with self.assertRaises(contract.ContractError):
                    VALIDATOR.validate_artifact(artifact, manifest)

    def _recorded_artifact(self, manifest: dict[str, Any]) -> dict[str, Any]:
        span = manifest["spans"][0]
        return {
            "schema_version": 1,
            "kind": "claim_candidates",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidates": [
                {
                    "id": "candidate-replay",
                    "classification": "unknown",
                    "reason": "ambiguous_source",
                    "hunk_id": span["hunk_id"],
                    "source": {"span_id": span["id"], "quote": span["quote"]},
                    "evidence_refs": [],
                    "edit": None,
                }
            ],
        }

    def test_recorded_replay_writes_valid_artifact_and_provenance(self) -> None:
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded = self.fixture.root / "recorded.json"
        recorded.write_text(json.dumps(self._recorded_artifact(manifest)), encoding="utf-8")
        artifact_path = self.fixture.root / "artifact.json"
        record_path = self.fixture.root / "run-record.json"
        replay = subprocess.run(
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
        self.assertEqual(replay.returncode, 0, replay.stderr)
        artifact = VALIDATOR.validate_artifact(json.loads(artifact_path.read_text()), manifest)
        record = VALIDATOR.validate_run_record(json.loads(record_path.read_text()), manifest, artifact)
        self.assertEqual(record["status"], "unknown")
        self.assertEqual(record["reason"], "recorded_replay")
        self.assertEqual(record["model"], "recorded")
        self.assertEqual(record["runtime"], "offline")
        self.assertFalse(record["live"])
        for key in ("prompt_sha256", "schema_sha256", "output_sha256"):
            self.assertRegex(record[key], r"^[0-9a-f]{64}$")

    def test_recorded_proposal_replay_validates_exact_find_replace(self) -> None:
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        span = manifest["spans"][0]
        candidate = {
            "schema_version": 1,
            "kind": "claim_candidates",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidates": [{
                "id": "candidate-proposal",
                "classification": "possibly_stale",
                "reason": "possibly_outdated",
                "hunk_id": span["hunk_id"],
                "source": {"span_id": span["id"], "quote": span["quote"]},
                "evidence_refs": [manifest["evidence"][0]["id"]],
                "edit": None,
            }],
        }
        proposal = {
            "schema_version": 1,
            "kind": "edit_proposal",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidate_id": "candidate-proposal",
            "hunk_id": span["hunk_id"],
            "source": {"span_id": span["id"], "quote": span["quote"]},
            "evidence_refs": [manifest["evidence"][0]["id"]],
            "edit": {"find": span["quote"], "replace": "Replacement note."},
        }
        candidate_path = self.fixture.root / "candidate.json"
        recorded_path = self.fixture.root / "recorded-proposal.json"
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        recorded_path.write_text(json.dumps(proposal), encoding="utf-8")
        artifact_path = self.fixture.root / "proposal.json"
        record_path = self.fixture.root / "proposal-run.json"
        replay = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "run-analysis.py"),
                "--root",
                str(self.fixture.root),
                "--manifest",
                str(manifest_path),
                "--mode",
                "propose",
                "--candidate-artifact",
                str(candidate_path),
                "--recorded-output",
                str(recorded_path),
                "--output-artifact",
                str(artifact_path),
                "--run-record",
                str(record_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(replay.returncode, 0, replay.stderr)
        artifact = VALIDATOR.validate_artifact(json.loads(artifact_path.read_text()), manifest)
        self.assertEqual(artifact["kind"], "edit_proposal")
        record = VALIDATOR.validate_run_record(json.loads(record_path.read_text()), manifest, artifact)
        self.assertEqual(record["artifact_kind"], "edit_proposal")

    def test_non_string_enum_blocks_with_a_run_record(self) -> None:
        # `value in SET` raises TypeError for an unhashable value. That escapes
        # the ContractError contract, so the run used to abort with a traceback
        # and leave no audit record at all.
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        span = manifest["spans"][0]
        hostile = {
            "schema_version": 1,
            "kind": "claim_candidates",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidates": [{
                "id": "candidate-hostile",
                "classification": ["candidate_contradiction"],
                "reason": "evidence_conflict",
                "hunk_id": span["hunk_id"],
                "source": {"span_id": span["id"], "quote": span["quote"]},
                "evidence_refs": [manifest["evidence"][0]["id"]],
                "edit": None,
            }],
        }
        recorded_path = self.fixture.root / "hostile-enum.json"
        recorded_path.write_text(json.dumps(hostile), encoding="utf-8")
        artifact_path = self.fixture.root / "hostile-artifact.json"
        record_path = self.fixture.root / "hostile-run.json"
        replay = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "run-analysis.py"),
                "--root", str(self.fixture.root),
                "--manifest", str(manifest_path),
                "--recorded-output", str(recorded_path),
                "--output-artifact", str(artifact_path),
                "--run-record", str(record_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(replay.returncode, 2, replay.stderr)
        self.assertIn("candidate_classification_invalid", replay.stderr)
        self.assertNotIn("Traceback", replay.stderr)
        self.assertFalse(artifact_path.exists())
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "blocked")
        # The unhashable value must also block the validator directly.
        with self.assertRaisesRegex(contract.ContractError, "candidate_classification_invalid"):
            VALIDATOR.validate_artifact(hostile, manifest)

    def test_propose_mode_rejects_a_candidate_artifact(self) -> None:
        # The generic validator accepts either kind; the mode does not.
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        span = manifest["spans"][0]
        candidate = {
            "schema_version": 1,
            "kind": "claim_candidates",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidates": [{
                "id": "candidate-proposal",
                "classification": "possibly_stale",
                "reason": "possibly_outdated",
                "hunk_id": span["hunk_id"],
                "source": {"span_id": span["id"], "quote": span["quote"]},
                "evidence_refs": [manifest["evidence"][0]["id"]],
                "edit": None,
            }],
        }
        candidate_path = self.fixture.root / "propose-candidate.json"
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        artifact_path = self.fixture.root / "wrong-kind.json"
        record_path = self.fixture.root / "wrong-kind-run.json"
        replay = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "run-analysis.py"),
                "--root", str(self.fixture.root),
                "--manifest", str(manifest_path),
                "--mode", "propose",
                "--candidate-artifact", str(candidate_path),
                # A structurally valid claim_candidates fed to propose mode.
                "--recorded-output", str(candidate_path),
                "--output-artifact", str(artifact_path),
                "--run-record", str(record_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(replay.returncode, 2, replay.stderr)
        self.assertIn("artifact_kind_unexpected", replay.stderr)
        self.assertFalse(artifact_path.exists())

    def test_proposal_must_bind_exactly_to_selected_candidate(self) -> None:
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        alternate_span = copy.deepcopy(manifest["spans"][0])
        alternate_span["id"] = "span-alternate"
        manifest["spans"].append(alternate_span)
        alternate_evidence = copy.deepcopy(manifest["evidence"][0])
        alternate_evidence["id"] = "service.netbox.image"
        manifest["evidence"].append(alternate_evidence)
        manifest["manifest_sha256"] = contract.payload_hash(manifest, "manifest_sha256")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        VALIDATOR.validate_manifest_repository(
            VALIDATOR.validate_manifest_structure(manifest), self.fixture.root
        )

        span = manifest["spans"][0]
        candidate = {
            "schema_version": 1,
            "kind": "claim_candidates",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidates": [{
                "id": "candidate-bound",
                "classification": "possibly_stale",
                "reason": "possibly_outdated",
                "hunk_id": span["hunk_id"],
                "source": {"span_id": span["id"], "quote": span["quote"]},
                "evidence_refs": [manifest["evidence"][0]["id"]],
                "edit": None,
            }],
        }
        candidate_path = self.fixture.root / "bound-candidate.json"
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        proposal = {
            "schema_version": 1,
            "kind": "edit_proposal",
            "manifest_sha256": manifest["manifest_sha256"],
            "document_path": manifest["document"]["path"],
            "revision": manifest["revision"],
            "candidate_id": "candidate-bound",
            "hunk_id": span["hunk_id"],
            "source": {"span_id": span["id"], "quote": span["quote"]},
            "evidence_refs": [manifest["evidence"][0]["id"]],
            "edit": {"find": span["quote"], "replace": "Replacement note."},
        }
        variants = {
            "candidate-id": {"candidate_id": "candidate-other"},
            "source": {
                "source": {
                    "span_id": alternate_span["id"],
                    "quote": alternate_span["quote"],
                }
            },
            "evidence-ref": {"evidence_refs": [alternate_evidence["id"]]},
        }
        for name, mutation in variants.items():
            with self.subTest(name=name):
                shifted = copy.deepcopy(proposal)
                shifted.update(mutation)
                recorded_path = self.fixture.root / f"shifted-{name}.json"
                artifact_path = self.fixture.root / f"shifted-{name}-artifact.json"
                record_path = self.fixture.root / f"shifted-{name}-run.json"
                recorded_path.write_text(json.dumps(shifted), encoding="utf-8")
                replay = subprocess.run(
                    [
                        sys.executable,
                        str(TOOL_ROOT / "run-analysis.py"),
                        "--root",
                        str(self.fixture.root),
                        "--manifest",
                        str(manifest_path),
                        "--mode",
                        "propose",
                        "--candidate-artifact",
                        str(candidate_path),
                        "--recorded-output",
                        str(recorded_path),
                        "--output-artifact",
                        str(artifact_path),
                        "--run-record",
                        str(record_path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(replay.returncode, 2)
                self.assertIn("proposal_candidate_binding_mismatch", replay.stderr)
                self.assertFalse(artifact_path.exists())
                record = json.loads(record_path.read_text(encoding="utf-8"))
                self.assertEqual(record["status"], "blocked")
                self.assertEqual(record["reason"], "validation_failed")

    def test_malformed_refusal_becomes_blocked_record_without_artifact(self) -> None:
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact_path = self.fixture.root / "refused-artifact.json"
        record_path = self.fixture.root / "refused-run.json"
        replay = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "run-analysis.py"),
                "--root",
                str(self.fixture.root),
                "--manifest",
                str(manifest_path),
                "--recorded-output",
                str(FIXTURES / "refusal.txt"),
                "--output-artifact",
                str(artifact_path),
                "--run-record",
                str(record_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(replay.returncode, 2)
        self.assertFalse(artifact_path.exists())
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(record["reason"], "validation_failed")
        self.assertRegex(record["output_sha256"], r"^[0-9a-f]{64}$")

    def test_live_mode_requires_explicit_confirmation_before_codex_execution(self) -> None:
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        record_path = self.fixture.root / "live-blocked.json"
        live = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "run-analysis.py"),
                "--root",
                str(self.fixture.root),
                "--manifest",
                str(manifest_path),
                "--live",
                "--output-artifact",
                str(self.fixture.root / "never-written.json"),
                "--run-record",
                str(record_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(live.returncode, 2)
        self.assertIn("live_confirmation_required", live.stderr)
        self.assertEqual(json.loads(record_path.read_text())["status"], "blocked")

    def test_runner_records_stale_manifest_as_blocked(self) -> None:
        result, manifest_path = self.fixture.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded_path = self.fixture.root / "stale-recorded.json"
        recorded_path.write_text(json.dumps(self._recorded_artifact(manifest)), encoding="utf-8")
        self.fixture.write(
            "docs/deployment/netbox-deployment.md",
            NETBOX_DOCUMENT.format(note="Changed after packaging."),
        )
        record_path = self.fixture.root / "stale-run.json"
        replay = subprocess.run(
            [
                sys.executable,
                str(TOOL_ROOT / "run-analysis.py"),
                "--root",
                str(self.fixture.root),
                "--manifest",
                str(manifest_path),
                "--recorded-output",
                str(recorded_path),
                "--output-artifact",
                str(self.fixture.root / "stale-artifact.json"),
                "--run-record",
                str(record_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(replay.returncode, 2)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "blocked")
        self.assertEqual(record["reason"], "stale_input")

    def test_offline_evaluator_gates_match_golden_metrics(self) -> None:
        report = EVALUATOR.evaluate(FIXTURES)
        self.assertEqual(report["matched"], report["cases"])
        self.assertEqual(report["false_proposals"], 0)
        self.assertEqual(report["security_leakage"], 0)
        self.assertGreaterEqual(report["cases"], 10)

    def test_schemas_are_exact_key_and_enum_constrained(self) -> None:
        for schema_path in sorted((TOOL_ROOT / "schemas").glob("*.json")):
            with self.subTest(schema=schema_path.name):
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertFalse(schema["additionalProperties"])
        candidates = json.loads(
            (TOOL_ROOT / "schemas/claim-candidates-v1.json").read_text(encoding="utf-8")
        )
        candidate_properties = candidates["properties"]["candidates"]["items"]["properties"]
        classification = candidate_properties["classification"]["enum"]
        self.assertEqual(classification, ["candidate_contradiction", "possibly_stale", "unknown"])
        self.assertNotIn("verified", classification)
        self.assertNotIn("document_drift", classification)
        # The schema constrains the model and contract.py constrains the
        # validator. They are two copies of one contract, so they must agree.
        self.assertEqual(set(classification), contract.CLASSIFICATIONS)
        self.assertEqual(
            set(candidate_properties["reason"]["enum"]), contract.CANDIDATE_REASONS
        )
        record = json.loads(
            (TOOL_ROOT / "schemas/run-record-v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(record["properties"]["status"]["enum"]), contract.RUN_STATUSES)
        self.assertEqual(set(record["properties"]["reason"]["enum"]), contract.RUN_REASONS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
