# Shadow quality corpus v3 — provenance note

`corpus.json`, `report.json`, and `results/*.json` are a recorded Phase 2A
shadow run. The offline test suite replays them; it never regenerates them.

During the documentation directory restructure the recorded `document_path`
values were rewritten (`docs/deployment/...` → `docs/guides/...`) so that
`contract.safe_document_path` accepts them under the updated
`ALLOWED_DOCUMENT_PREFIXES`.

The `manifest_sha256` values were deliberately **not** recomputed. They hash the
original analysis manifest, which is not retained here, and the evaluator only
compares `result["manifest_sha256"]` with the matching `*.run.json` record — it
never re-derives that hash from a manifest. The recorded hashes therefore remain
the original values and no longer correspond to the rewritten document paths.
Regenerating the corpus requires a live model run.
