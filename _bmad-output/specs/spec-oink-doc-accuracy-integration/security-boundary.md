# Notion Synchronization Security Boundary

## Blocking finding

The current `scripts/sync-to-notion.py` reads the repository `.env` for the Notion integration configuration, decrypts Ansible Vault when available (or reads Terraform `secrets.auto.tfvars`), maps system/app credentials and tokens to Notion fields/notes, and prints masked password prefixes in dry-run output. This is incompatible with the Phase 1 boundary: a static documentation detector and OINK presentation plane must never receive secret material.

## Permitted Notion data

The retained inventory sync may send only reviewed non-sensitive metadata:

- resource name;
- address or explicitly approved non-secret endpoint;
- resource classification;
- parent relationship identifier;
- static VM/resource identifier and static port description, where neither embeds credentials or tokens.

`NOTION_TOKEN` may authenticate the direct Notion API request at runtime, but it is never report content, a documentation field, a test expectation, a log value, or a value available to OINK, Hugo, GitHub Pages, the drift detector, or its fixtures.

## Prohibited data

The sync, drift detector, OINK-facing report, tests and logs must not read for publication, retain, emit, mask, truncate, hash for display, or place into Notion properties any of:

- Ansible Vault values or variables resolved from them;
- Terraform `secrets.auto.tfvars` values or Terraform state values;
- passwords, SSH/RDP credentials, application credentials, database credentials, API keys/tokens, integration tokens, connection strings containing credentials, or private keys;
- free-form notes derived from those values.

The Notion integration credential is an authentication implementation detail, not inventory data. No code path may print it or any masked/prefixed derivative.

## Required remediation contract

1. Remove the secret-loading and credential-construction path from the retained synchronization behavior. The synchronizer must build its Notion payload exclusively from an explicit non-sensitive allowlist.
2. Remove or reject credential-bearing Notion property mappings. No alternate `Notes` field may be used as a secret side channel.
3. Preserve a dry-run mode, but make its output a projection of the same allowlisted payload; it must not reveal masked values, prefixes, lengths, hashes intended for comparison, or debug structures containing secret values.
4. Add deterministic tests with synthetic, unique sentinel values and a mocked Notion client. Assert that outbound request objects and captured stdout/stderr exclude every sentinel and its recognizable derivatives, while a representative allowlisted resource is still produced.
5. Keep the documentation drift detector independent of the synchronizer. It reads only the four repository paths in [claim-registry.md](claim-registry.md) and must not import, invoke, or receive outputs from the sync path.

## Acceptance evidence

Implementation is blocked until all of these are demonstrated locally:

- source-level tests prove the payload schema has no credential-bearing properties;
- mocked execution proves sentinel non-disclosure in request payloads and logs;
- the allowlisted inventory record remains valid in normal and dry-run modes;
- the Phase 1 detector and report fixtures pass without `.env`, Vault password file, Terraform secret file, network access, or Notion credentials;
- a search/assertion over generated report/manifest output confirms the test sentinels are absent.

A failure of any security check is a hard failure. It must not be converted into `unknown`, masked away, retried with broader credentials, or bypassed to publish documentation.
