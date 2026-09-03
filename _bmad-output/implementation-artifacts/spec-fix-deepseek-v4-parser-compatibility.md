---
title: 'Fix DeepSeek V4 reasoning parser compatibility'
type: 'bugfix'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
baseline_commit: '00524b140ca8a63219073bf75c54ebc599fade06'
context:
  - '/workspaces/IaC/AGENTS.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The production ik_llama OpenAI endpoint can return hidden `<think>` text in `message.content` when a caller sends `thinking_budget_tokens: 0`. `--reasoning-format deepseek` is already enabled and does not correct this, so Open WebUI can display internal reasoning instead of the requested final answer. The model also has no trusted source for the current date, so it guesses dates incorrectly.

**Approach:** Place a local, dependency-free OpenAI compatibility proxy in front of the candidate. It preserves the existing WebUI URL, normalizes only zero-thinking synchronous and SSE responses by dropping leaked thought content, and injects a short trusted current-date system context using a configured IANA timezone.

## Boundaries & Constraints

**Always:** Keep the model runtime dual-GPU and private; maintain the current host-gateway API URL (`host.docker.internal:8081/v1`); preserve OpenAI response fields, tool calls, SSE framing, exactly one `[DONE]`, and unmodified behavior when `thinking_budget_tokens` is absent or nonzero; inject only trusted date/time context with the configured IANA timezone (`America/Los_Angeles` default); use pinned/no-new-image dependencies; add deterministic offline and live regression coverage.

**Ask First:** Changing model/runtime engine, model weights, GPU topology, public/LAN exposure, Open WebUI database schema, or deleting any additional artifact.

**Never:** Strip content from requests other than explicit `thinking_budget_tokens: 0`; invent `reasoning_content` when thought output was disabled; apply a lossy transformation when a terminating `</think>` marker has not been received; trust model-generated dates over the injected clock context; route traffic through a third-party or public proxy.

The proxy is an adaptation boundary, not a second model server. It must use timeouts compatible with the current long inference requests, stream upstream data rather than buffering an entire completion, and never log prompts, responses, authorization material, or the WebUI database. It may emit concise operational metadata such as method, path, upstream status, and whether normalization was activated. The model backend continues to own generation, GPU allocation, model identity, and tool-call production.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Sync suppression | JSON chat request with `thinking_budget_tokens: 0`; upstream has `<think>…</think>OK` | Client receives final `OK`; no think marker or thought text | If no closing marker, leave response unchanged |
| Chunked SSE suppression | Same request; marker is split across SSE deltas | Suppress deltas until the marker completes, forward subsequent content/tool calls and one `[DONE]` | Preserve legal non-content delta and SSE framing |
| Normal passthrough | Budget omitted/nonzero, tool request, malformed upstream payload | Byte/semantic behavior is unchanged except normal proxy transport | Return upstream status/body; log safe diagnostic only |
| Trusted date | Any valid chat request; configured timezone | Upstream receives a non-user system message containing the current ISO date, weekday and timezone | If JSON cannot be parsed, forward request unchanged |

The proxy treats a JSON body as eligible only after it successfully parses the request and finds the numeric value zero for `thinking_budget_tokens`. A malformed client request is sent to the upstream unchanged rather than rejected by a proxy-specific parser. Valid chat request messages receive one leading system context calculated per request from the configured timezone; user-supplied system instructions remain in their original order after it. For eligible non-streaming responses, it drops everything before the first `</think>` marker, whether or not the upstream retained its matching opening marker; content without a terminator remains unchanged. For eligible SSE, it retains per-choice content until the closing marker is observed, then passes all remaining deltas as emitted by the backend; if a terminator never arrives it replays the retained content unchanged at completion. Tool-call deltas, role metadata, usage events, error events, and `[DONE]` are protocol data rather than reasoning text and must not be dropped.

</frozen-after-approval>

## Code Map

- `ansible/roles/deepseek-v4-ik/templates/docker-compose.yml.j2` -- candidate endpoint exposure and proxy-side routing boundary.
- `ansible/roles/deepseek-v4-ik/templates/deepseek-v4-ik.service.j2` -- service ownership and startup ordering.
- `ansible/roles/deepseek-v4-ik/tasks/production.yml` -- production render, readiness and Open WebUI migration sequence.
- `ansible/roles/deepseek-v4/files/contract-runner.py` -- live API contract evidence.

## Tasks & Acceptance

**Execution:**

- [x] `ansible/roles/deepseek-v4-ik/files/openai-compat-proxy.py` -- implement stdlib reverse proxy plus narrowly scoped sync/SSE zero-thinking normalization and self-tests.
- [x] `ansible/roles/deepseek-v4-ik/templates/*` and `tasks/production.yml` -- deploy the proxy with a private candidate backend, health checks, bounded logs, and stable WebUI endpoint.
- [x] `ansible/roles/deepseek-v4/files/contract-runner.py` -- add the live zero-thinking exact-answer regression to the existing evidence suite.
- [x] `ansible/tests/deepseek-v4/*` -- render and policy tests for private routing plus proxy self-test execution.

Deployment changes must be idempotent: a rerun updates proxy code/configuration and restarts only the owning service. Candidate and proxy are a single logical deployment; health readiness must prove both that the proxy answers and that it can reach the candidate. The candidate’s direct port must not remain usable from the Open WebUI container after the switch. Existing `open-webui` data is not recreated or reseeded for this fix, because its saved endpoint is already the stable frontend URL.

**Acceptance Criteria:**

- Given a zero-thinking exact-answer request, when sent through the production-facing endpoint, then the final answer is returned without `<think>` or leaked reasoning.
- Given SSE thought text split across multiple deltas, when the terminator arrives, then only post-terminator content is forwarded and the stream has exactly one `[DONE]`.
- Given a nonzero/absent thinking budget or a tool call, when proxied, then its content and protocol fields remain unchanged.
- Given a valid chat request, when the proxy forwards it, then the model receives the current date and weekday from the configured trusted timezone rather than needing to guess.
- Given the rendered production configuration, when validated locally and deployed, then Open WebUI reaches the model through its existing endpoint and the full contract suite passes.

## Spec Change Log

## Design Notes

The proxy remains local and keeps port 8081 as the stable frontend. The candidate moves behind it to an internal-only port, so Open WebUI needs no connection migration and the existing database remains authoritative. The normalizer is deliberately stateful for SSE but only activates after the explicit zero-thinking request flag. This is necessary because the upstream may omit the `<think>` opening marker; buffering ends at the first `</think>`, while a missing terminator is safer as passthrough than accidental answer loss. Date context is built from the host clock with Python `zoneinfo`, using `America/Los_Angeles` for this Roseville homelab unless deployment configuration explicitly selects another IANA timezone.

This also makes the regression independently testable without a GPU: the proxy self-test feeds representative completion JSON and SSE frames directly into normalization functions. The live case remains essential because it proves the actual backend still reaches the intended request path and that Open WebUI’s route has not bypassed the compatibility boundary. If the upstream changes its reasoning envelope in the future, tests should fail closed rather than silently broadening the cleanup rule.

## Verification

**Commands:**

- `python3 ansible/roles/deepseek-v4-ik/files/openai-compat-proxy.py --self-test` -- expected: sync, split-SSE, passthrough and malformed cases pass.
- `cd ansible && ansible-playbook -i 'llm-server,' playbooks/deploy-deepseek-v4-ik.yml --syntax-check` -- expected: valid Ansible syntax.
- `python3 ansible/tests/deepseek-v4/policy-test.py` -- expected: private routing and pinning policy passes.
- Live contract runner with the production-facing endpoint -- expected: zero-thinking regression and existing contract cases pass.

## Suggested Review Order

**Compatibility boundary**

- Narrowly adapts only the broken reasoning envelope and trusted clock context.
  [`openai-compat-proxy.py:37`](../../ansible/roles/deepseek-v4-ik/files/openai-compat-proxy.py#L37)

- Handles sync, split and multi-line SSE without losing tool events.
  [`openai-compat-proxy.py:97`](../../ansible/roles/deepseek-v4-ik/files/openai-compat-proxy.py#L97)

- Constrains request framing, response encoding and proxy resource exposure.
  [`openai-compat-proxy.py:195`](../../ansible/roles/deepseek-v4-ik/files/openai-compat-proxy.py#L195)

**Production ownership and evidence**

- Keeps 8081 stable while the candidate backend becomes loopback-only on 8082.
  [`production.yml:41`](../../ansible/roles/deepseek-v4-ik/tasks/production.yml#L41)

- Runs the full compatibility suite on the user-facing proxy endpoint.
  [`production.yml:110`](../../ansible/roles/deepseek-v4-ik/tasks/production.yml#L110)

- Adds zero-thinking and trusted-date assertions to live evidence.
  [`contract-runner.py:224`](../../ansible/roles/deepseek-v4/files/contract-runner.py#L224)

**Regression checks**

- Proves the endpoint boundary and configured trusted timezone render correctly.
  [`render.yml:40`](../../ansible/tests/deepseek-v4-ik/render.yml#L40)

- Enforces proxy presence and runs its deterministic offline self-test.
  [`policy-test.py:126`](../../ansible/tests/deepseek-v4/policy-test.py#L126)
