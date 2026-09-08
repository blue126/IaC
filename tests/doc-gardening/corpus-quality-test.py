#!/usr/bin/env python3
"""Offline tests for the strict Phase 2A quality corpus evaluator."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = REPOSITORY_ROOT / "tools/doc-gardening"
sys.path.insert(0, str(TOOL_ROOT))
import contract  # noqa: E402


def load_script(name: str) -> Any:
    path = TOOL_ROOT / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVALUATOR = load_script("evaluate-corpus.py")
REVISION = {"base": "a" * 40, "head": "b" * 40}
CONFIGURATION = {
    "model": "claude-opus-5",
    "runtime": "claude-code-action@pinned",
    "schema_sha256": "c" * 64,
}
COMMITTED_CORPUS = REPOSITORY_ROOT / "tests/doc-gardening/corpus/v3"


class CorpusQualityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.results_dir = Path(self.temporary_directory.name)
        phase_one = EVALUATOR._load_phase_one()
        self.claims = list(phase_one.CLAIMS)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def corpus(self, *, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if cases is None:
            cases = []
            for index, claim in enumerate(self.claims):
                cases.append(
                    {
                        "id": f"positive-{index}",
                        "kind": "positive",
                        "document_path": claim.document_path,
                        "revision": REVISION,
                        "result_file": f"positive-{index}.json",
                        "claim_id": claim.claim_id,
                    }
                )
            cases.extend(
                [
                    {
                        "id": "negative-registered",
                        "kind": "negative",
                        "document_path": self.claims[0].document_path,
                        "revision": REVISION,
                        "result_file": "negative-registered.json",
                        "claim_id": None,
                    },
                    {
                        "id": "negative-external",
                        "kind": "negative",
                        "document_path": "docs/deployment/immich-deployment.md",
                        "revision": REVISION,
                        "result_file": "negative-external.json",
                        "claim_id": None,
                    },
                ]
            )
        return {
            "schema_version": 1,
            "kind": "shadow_quality_corpus",
            "configuration": CONFIGURATION,
            "cases": cases,
        }

    def write_case(
        self,
        case: dict[str, Any],
        *,
        candidates: list[dict[str, Any]] | None = None,
        status: str = "completed",
        reason: str = "analysis_completed",
        record_overrides: dict[str, Any] | None = None,
    ) -> None:
        candidates = [] if candidates is None else candidates
        manifest_sha = "d" * 64
        record = {
            "schema_version": 2,
            "kind": "run_record",
            "status": "completed",
            "reason": "shadow_completed",
            "manifest_sha256": manifest_sha,
            "prompt_sha256": "e" * 64,
            "schema_sha256": CONFIGURATION["schema_sha256"],
            "model": CONFIGURATION["model"],
            "runtime": CONFIGURATION["runtime"],
            "output_sha256": "f" * 64,
            "artifact_kind": "claim_candidates",
            "live": True,
        }
        if record_overrides:
            record.update(record_overrides)
        result = {
            "schema_version": 2,
            "kind": "candidate_discovery_result",
            "revision": case["revision"],
            "document_path": case["document_path"],
            "change_type": "M",
            "previous_path": None,
            "status": status,
            "reason": reason,
            "manifest_sha256": manifest_sha,
            "run_record_sha256": contract.sha256_bytes(contract.canonical_json(record)),
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
        result_path = self.results_dir / case["result_file"]
        result_path.write_text(json.dumps(result), encoding="utf-8")
        result_path.with_suffix(".run.json").write_text(json.dumps(record), encoding="utf-8")

    @staticmethod
    def candidate(claim_id: str) -> dict[str, Any]:
        return {
            "id": f"candidate-{claim_id.replace('.', '-')}",
            "classification": "candidate_contradiction",
            "reason": "evidence_conflict",
            "hunk_id": "hunk-1",
            "source": {"span_id": "span-1", "quote": "Changed documentation value."},
            "evidence_refs": [claim_id],
            "edit": None,
        }

    def populate_valid_cases(self, corpus: dict[str, Any]) -> None:
        for case in corpus["cases"]:
            candidates = [self.candidate(case["claim_id"])] if case["kind"] == "positive" else []
            self.write_case(case, candidates=candidates)

    def test_exact_strict_corpus_promotes(self) -> None:
        corpus = self.corpus()
        self.populate_valid_cases(corpus)
        report = EVALUATOR.evaluate(corpus, self.results_dir)
        self.assertTrue(report["promotion_eligible"])
        self.assertEqual(
            report["counters"],
            {
                "evaluable_positives": 6,
                "correct_positives": 6,
                "false_negatives": 0,
                "evaluable_negatives": 2,
                "false_positives": 0,
                "action_failures": 0,
                "output_failures": 0,
                "integrity_failures": 0,
            },
        )

    def test_missing_positive_candidate_is_false_negative(self) -> None:
        corpus = self.corpus()
        self.populate_valid_cases(corpus)
        target = corpus["cases"][0]
        self.write_case(target, candidates=[])
        report = EVALUATOR.evaluate(corpus, self.results_dir)
        self.assertFalse(report["promotion_eligible"])
        self.assertEqual(report["counters"]["false_negatives"], 1)

    def test_wrong_evidence_is_false_negative_and_positive_error(self) -> None:
        corpus = self.corpus()
        self.populate_valid_cases(corpus)
        target = corpus["cases"][0]
        self.write_case(target, candidates=[self.candidate(self.claims[1].claim_id)])
        report = EVALUATOR.evaluate(corpus, self.results_dir)
        self.assertEqual(report["counters"]["false_negatives"], 1)
        self.assertEqual(report["counters"]["false_positives"], 1)

    def test_negative_contradiction_is_false_positive(self) -> None:
        corpus = self.corpus()
        self.populate_valid_cases(corpus)
        target = corpus["cases"][-1]
        self.write_case(target, candidates=[self.candidate(self.claims[0].claim_id)])
        report = EVALUATOR.evaluate(corpus, self.results_dir)
        self.assertEqual(report["counters"]["false_positives"], 1)

    def test_action_failure_is_not_evaluable_but_blocks_promotion(self) -> None:
        corpus = self.corpus()
        self.populate_valid_cases(corpus)
        target = corpus["cases"][0]
        self.write_case(target, status="blocked", reason="action_failed")
        report = EVALUATOR.evaluate(corpus, self.results_dir)
        self.assertEqual(report["counters"]["action_failures"], 1)
        self.assertEqual(report["counters"]["false_negatives"], 0)
        self.assertFalse(report["promotion_eligible"])

    def test_tampered_run_record_is_integrity_failure(self) -> None:
        corpus = self.corpus()
        self.populate_valid_cases(corpus)
        target = corpus["cases"][0]
        record_path = (self.results_dir / target["result_file"]).with_suffix(".run.json")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["model"] = "unexpected"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        report = EVALUATOR.evaluate(corpus, self.results_dir)
        self.assertEqual(report["counters"]["integrity_failures"], 1)

    def test_exact_closed_claim_coverage_is_required(self) -> None:
        corpus = self.corpus()
        corpus["cases"].pop(0)
        with self.assertRaisesRegex(contract.ContractError, "corpus_shape_invalid"):
            EVALUATOR.evaluate(corpus, self.results_dir)

    def test_result_file_cannot_escape_results_directory(self) -> None:
        corpus = self.corpus()
        corpus["cases"][0]["result_file"] = "../outside.json"
        with self.assertRaisesRegex(contract.ContractError, "corpus_case_invalid"):
            EVALUATOR.evaluate(corpus, self.results_dir)

    def test_committed_corpus_v3_matches_its_promotion_report(self) -> None:
        corpus = json.loads((COMMITTED_CORPUS / "corpus.json").read_text(encoding="utf-8"))
        expected = json.loads((COMMITTED_CORPUS / "report.json").read_text(encoding="utf-8"))
        report = EVALUATOR.evaluate(corpus, COMMITTED_CORPUS / "results")
        self.assertTrue(report["promotion_eligible"])
        self.assertEqual(report, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
