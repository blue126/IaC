# Credential Boundary and Accepted Risk

## Decision

- **Status:** Accepted risk
- **Accepted by:** Project owner
- **Date:** 2026-09-05
- **Behavior baseline:** `e5dd546e965e6878b5edffe093699c81ff1e0dce`
- **Scope:** Existing direct invocation and the existing `Jenkinsfile` post-deployment `Sync to Notion` stage only.

The synchronizer reads repository `.env` configuration, decrypts Ansible Vault when available (or reads Terraform secret data), constructs system/application credential fields, stores them in the project's private Notion workspace, and may print masked prefixes during local dry-run output. It can be run directly and is also invoked by the existing Jenkins post-deployment stage with credentials binding. Notion is a third-party cloud service even though the managed homelab is on a private LAN; the accepted exposure is therefore the private Notion account/workspace, integration token and direct/Jenkins execution or logging path—not merely LAN reachability.

For this personal project, the owner intentionally uses Notion as a private credential GUI and accepts that existing SaaS/account and execution risk. Removing credential fields or the existing Jenkins invocation is **not** a prerequisite for OINK, the repository consistency gate or AI doc-gardening. This decision does not claim the behavior is generally safe, recommend it for shared projects or authorize expanding it.

## Accepted Scope

The accepted risk covers the synchronizer's existing data flow at the behavior baseline:

- direct invocation using local Notion configuration and existing secret sources;
- the `Jenkinsfile` post-deployment stage using Jenkins credentials binding;
- mapping and sending credentials into the owner's private Notion database;
- existing dry-run/status and Jenkins output associated with those invocations.

This contract does not change, test or harden `scripts/sync-to-notion.py` or `Jenkinsfile`. Any additional schedule/trigger, new destination, broader sharing, additional credential source or materially changed output is outside the accepted scope and requires a new decision.

## Existing Controls and Residual Risk

Known controls are the private Notion workspace, Jenkins credentials binding for the existing stage, and Jenkins post-run removal of generated secret files. MFA state, Notion member access, integration-token scope/rotation, cloud exports/backups and local/Jenkins log retention are not verified by this contract and must not be claimed as controls.

Residual risk remains credential disclosure through Notion account/workspace compromise, integration-token misuse, provider storage/export behavior, or direct/Jenkins output. The project owner accepts that residual risk only within the scope above.

## Hard Isolation Boundary

Acceptance ends at the Notion synchronization process. The following components must not import, invoke, inspect, consume or receive the synchronizer, its payloads, its stdout/stderr or any data derived from them:

- `tools/check-doc-claims.py` and its fixtures/report;
- `tools/doc-gardening/`, AI prompts, manifests, model outputs and run records;
- documentation GitHub Actions, their CI artifacts and Draft PR content;
- OINK/Hugo, GitHub Pages, rendered Markdown and `llms.txt`.

Those components must not read `.env`, Ansible Vault values or password files, Terraform `*.tfvars`/state secrets, Notion database content, passwords, API/integration tokens, private keys, credential-bearing connection strings, or masked/truncated/hash-for-display derivatives. A Notion token used by the manual synchronizer is never documentation evidence or inventory data for this automation.

The detector may read only the repository paths declared by the six claims in [claim-registry.md](claim-registry.md). Doc-gardening may consume only its explicit single-document manifest and allowlisted, non-sensitive repository evidence. OINK remains a presentation plane and receives neither synchronization nor model/production credentials.

## Required Automation Evidence

The documentation automation remains acceptable only while deterministic tests demonstrate that:

1. the Phase 1 detector and report run without `.env`, Vault password files, Terraform state/secret files, network access or Notion credentials;
2. doc-gardening manifests, recorded outputs and validators reject secret sentinels without echoing them;
3. documentation CI uses read-only repository permission and contains no Notion, model or production secret path;
4. generated reports/manifests contain only the fields and evidence allowed by their versioned contracts;
5. no documentation workflow imports or invokes `scripts/sync-to-notion.py`.

A failure at this isolation boundary is a hard failure. It must not become `unknown`, be hidden by masking, retry with broader credentials, or be published. This hard failure applies to documentation automation; it does not retroactively revoke the separately accepted manual Notion path.

## Review Triggers

Reassess this accepted risk before any of the following:

- the repository, homelab operations or Notion database become shared with additional people;
- the synchronizer gains an unattended trigger beyond the existing Jenkins post-deployment stage;
- the Notion database, integration or credential fields gain broader access;
- synchronization data is proposed as an AI/runtime oracle or enters an artifact, prompt, report, PR, OINK page or `llms.txt`;
- a Notion account, integration-token, local-log or credential disclosure incident occurs;
- the project moves beyond a personal homelab threat model.
