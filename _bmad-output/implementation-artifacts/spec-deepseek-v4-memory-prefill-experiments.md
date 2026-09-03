---
title: 'DeepSeek V4 Memory and Prefill Experiments'
type: 'feature'
created: '2026-08-15'
status: 'in-review'
review_loop_iteration: 2
baseline_commit: 'a3d766b2d00ece89b79789b4535102d13dec7c59'
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The pinned DeepSeek V4 GGUF service has spare RAM/VRAM while coding-agent prefill remains slow. Candidate automation also overwrites evidence and cannot prove exact control restoration.

**Approach:** Build a constrained experiment path, then test host cache, GPU expert placement, and graph split in order. Each accepted winner becomes the next control; promotion requires correctness, stability, headroom, and material user benefit.

## Boundaries & Constraints

**Always:** Keep `ik_llama.cpp@981e5ea0`, the GGUF, proxy, 128K context, dual GPUs, one backend owner, loopback backend, and CIDR-controlled API fixed. Change one primary variable per candidate. Use a new experiment-ID directory for command, pins, control ID, contract, timings, resources, sanitized logs, and lifecycle result; never store prompts, source, credentials, or headers. Run correctness before performance. Capture failure evidence before restoring control unless OOM, corrupt output, or host instability requires immediate stop.

**Ask First:** Runtime/model pin changes, tensor-regex overrides, context above 128K, another runtime, wider network access, deletion, or ESXi/VMX/PCIe/power changes.

**Never:** Touch unrelated Anki/Caddy changes; accept free-form runtime args; run primary and candidate together; mix cache, expert, graph, context, precision, batch, or NUMA changes; overwrite evidence; promote failed correctness or infer peak safety from idle memory.

## I/O & Edge-Case Matrix

| Scenario | State | Expected behavior | Error handling |
|---|---|---|---|
| Valid candidate | Unique ID; one approved change | Isolated render and complete evidence; exact control restored | Record verdict and final owner |
| Invalid candidate | Missing/unsafe ID or conflicting values | Fail before service change | Report violated invariant |
| Duplicate run | Evidence directory exists | Refuse overwrite | Require new ID |
| Runtime failure | OOM, bad contract, timeout, swap, restart | Skip benchmark and stop qualification | Preserve evidence; restore control |
| Cache workload | A cold/continuation, B cold, return A | Warm-return TTFT, cache/eviction data, cold latency, medians | Mark unavailable fields explicitly |

</frozen-after-approval>

## Code Map

- `ansible/roles/deepseek-v4-ik/{defaults,tasks,templates}` -- validated controls, isolated lifecycle, Compose/proxy ownership.
- `ansible/playbooks/qualify-deepseek-v4-ik.yml` -- explicit prepare, experiment, and read-only verify entry points.
- `ansible/roles/deepseek-v4/files/{benchmark-runner.py,coding-cache-runner.py,resource-sampler.py}` -- performance/cache/resource evidence.
- `ansible/tests/deepseek-v4-ik/` -- valid and rejected render/policy cases.
- `ansible/inventory/host_vars/llm-server.yml` -- final promoted values only.
- `docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md` -- measured comparison and follow-ups.

## Tasks & Acceptance

**Execution:**
- [x] Add strict experiment/control IDs, cache MiB, MoE mode/count, and split mode; reject unsafe combinations and graph without two-GPU preflight.
- [x] Render each candidate in its immutable evidence directory, leaving production Compose untouched; collect manifest, pre/post/peak resources, logs, and restore initial owner/proxy state.
- [x] Make the stable proxy independent of only the production owner so a candidate can pass the full public contract.
- [x] Extend benchmark medians for PP/TTFT/E2E/TG and optional cache fields; add deterministic cache and resource runners with self-tests.
- [x] Fix qualification routing/tags; locally validate baseline/cache/expert/graph renders plus invalid/duplicate cases.
- [x] Run 8/16/32 GiB cache tests (32 only without pressure), `n-cpu-moe=42` then one-layer steps, and topology/P2P plus layer-versus-graph.
- [ ] Promote only the winner, rerun production contract/128K checks, soak one hour, and update the learning note.

**Acceptance Criteria:**
- Every candidate passes the 19-case API contract before benchmarking; afterward the stable owner/API is verified.
- Cache uses at least three comparable samples and promotes the smallest size with about 10% better return-to-A median TTFT, no material cold regression, swap, OOM, or restart.
- Expert moves one layer per run, retains about 2 GiB measured peak VRAM per GPU and TG at least 8 tok/s; promotion needs about 10% benefit and stops at first failed/immaterial step.
- Graph captures topology/P2P first, changes only split mode from the winning control, and needs full correctness plus about 10% benefit.
- The final profile passes 128K correctness and a one-hour soak without sustained swap, OOM, unexpected restart, missing evidence, or control drift.

## Spec Change Log

- 2026-08-15: Implemented immutable experiment evidence, exact live-control validation, typed
  promotion verdicts, fail-closed resource sampling, managed-host recovery, topology identity
  checks, independent soak health/completion scheduling, and localhost valid/rejected fixtures.
- 2026-08-15: Completed cache 8/16/32 GiB, `n-cpu-moe=42`, and topology/P2P evaluation. No
  candidate met the approved promotion gate; graph was ineligible because directional P2P was
  `NS`, so the stable 8 GiB/all-CPU/layer profile remained unchanged.
- 2026-08-15: Final R6 passed exact live drift checks, pre/post 19-case contracts, 126,992-token
  recall, and all resource-stability assertions. The one-hour soak completed but failed the strict
  availability gate because synchronous saving of a 34.1 GiB 127K prompt-cache state blocked one
  health request for 30 seconds. The approved corrective path is now an isolated
  `--ctx-checkpoints` experiment: first an explicit 32-checkpoint candidate control, then 8,
  and 4 only if 8 fails its evidence gate. The final promotion task remains open.
- 2026-08-15: Source inspection proved the 72.15-second transition is synchronous host-RAM
  state serialization and deep copying, not a disk write. At the user's direction, add a
  non-promotional single-repeat checkpoint=8 diagnostic that may reuse the root-owned checksum
  proof recorded after the unchanged GGUF. It preserves contract, resource, watchdog, immutable
  evidence, and exact restoration gates; three repeats and the one-hour soak remain mandatory
  before promotion.
- 2026-08-15: Ran `checkpoint8-diagnostic-20260815-r4`. The 19-case public contract passed and
  exact production restoration plus read-only verification passed. Cache-state save time fell
  from the R6 72.15 seconds at 32 checkpoints to 21.97 seconds at 8, while the measured short
  handoff was 27.58 seconds; one 10-second health probe still timed out and strict recall/handoff
  answers failed, so the candidate was rejected. The first fixture produced only 116,445 prompt
  tokens; both long-context runners now calibrate with the pinned server's read-only `/tokenize`
  endpoint and perform only one real long completion per sample. No checkpoint=4 run or
  production promotion was attempted.
- 2026-08-15: Post-diagnostic review made checkpoint evidence non-inheritable unless exact
  restoration is recorded before watchdog disarm and qualification. A one-repeat diagnostic can
  no longer unlock checkpoint=4; formal intermediate evidence requires three repeats. The full
  route now has a seven-hour watchdog ceiling around a three-hour transition deadline, preserving
  startup and restoration margin without increasing the expected runtime.

## Design Notes

Production Compose is the untouched control. Each candidate uses a separate Compose project in its evidence directory while production is stopped. The stable proxy relays to the exclusive backend on port 8082, permitting the complete 19-case public contract. Cleanup removes only the candidate project and restores the prior owner/proxy state.

## Verification

**Commands:**
- `python3 -m py_compile <runners>; <runner> --self-test` -- deterministic tests pass.
- `ansible-playbook -i 'localhost,' ansible/tests/deepseek-v4-ik/render.yml` -- valid and invalid cases pass.
- `ansible-playbook -i 'llm-server,' ansible/playbooks/qualify-deepseek-v4-ik.yml --syntax-check` -- offline syntax passes.
- `docker compose -f <fixture> config --quiet` -- valid Compose and unchanged boundaries.
- Live Ansible experiments -- record contract, performance, resources, lifecycle, and soak verdicts
  without overwriting failed evidence.

**Observed results:**

- Python syntax/self-tests, playbook syntax, Compose validation and localhost policy/render matrix
  passed; the matrix ended `ok=60 failed=0 rescued=5`, with all rescues expected rejections.
- `ansible-lint` reports only two pre-existing `no-handler` findings in candidate preparation.
- Live cache/expert/topology runs completed with immutable evidence and restored the stable owner.
- `final-baseline-20260815-r6` preserved complete evidence and intentionally failed the final gate
  on the single backend health timeout described above; post-contract remained 19/19 and read-only
  `--tags verify` passed.
- `checkpoint8-diagnostic-20260815-r4` was safely rejected after reducing state-save time by about
  69.5% but retaining one health timeout and failing strict answer checks. It recorded zero swap,
  OOM, and restart; final owner/proxy health and exact control restoration passed.
