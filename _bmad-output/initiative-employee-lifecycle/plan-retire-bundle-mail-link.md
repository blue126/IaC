---
title: 'Retire the mailed one-time device-bundle link (/d/<token>)'
type: 'refactor'
ticket: ''
created: '2026-11-03'
status: 'done'
baseline_revision: 'apply-site 471a2044e70b80ae5c265106a1d6806f23e9066b; employee-admin b2ff6c759fd6dd365d0b2eb5fa5d010298de3a64; IaC 99cad13ad4c8b61f2140706177bccf6a3c256f64'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Onboarding and reissue mails stopped carrying the bundle link (employees download from 「我的工作区」 `/me`), but delivery still mints a public `/d/<token>` link (72 h, 3 downloads, mailed code) that nobody receives, receipts still expire with it, and the handbook, `employee-provision` skill and deployment docs still describe it (PR #232 review-policy-gate flagged the contradiction).

**Approach:** Keep the bundle upload and the signed-in `/me` download; remove the `/d/` page, its code flow and link expiry from the Worker and the oci-hub delivery path; make the executor independent of `url`/`link_url` so it can deploy before the Worker; update every current document to "download after signing in to 「我的工作区」, kept until retirement or replacement".

## Boundaries & Constraints

**Always:** Work in new task worktrees (apply-site and employee-admin main checkouts hold unrelated work; never touch the uncommitted HAPI files). Executor changes must work against both the current and the new Worker. Keep `bundle_downloads` logging for session downloads. Stop before any external write: `wrangler deploy`, `git push ws-executor`, D1 migrations.

**Decisions (2026-11-03, user):** (1) Delete the unused link templates `templates/mosh-hub-trial.html` and `email-template.txt` and their references in `admin-core.py:38` and `remotecc-layout.json`. (2) Add apply-site migration `0013` that drops the `bundle_codes` table, deletes `rate_limits` rows with window `bcode`, and drops `bundles.expires_at`, `bundles.downloads` and `bundles.recipient`; `schema.sql` and the test mock follow. The migration is written and tested here, applied only at deploy.

**Never:** Change the non-oci-hub (retired `existing`/Temp.sh) delivery path. Edit `remotecc/design/text.json` (link-only `TEXT.bundle` strings stay unused). Rewrite dated planning/research records.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Upload | `POST /admin/bundles` with valid bundle | `{token, sha256}`; no `url`, no `expires_at` | unchanged auth/size errors |
| Verify | `GET /admin/bundles/<token>` for a stored bundle | `{sha256, available: true}` | 404 `ADMIN_BUNDLE_NOT_FOUND` when absent |
| Old link | any `GET/POST /d/<token>` or `/d/<token>/code` | 404 like any unknown path | — |
| Session download | signed-in `POST /me/bundles/<device>` | unchanged: zip, logged `via='session'` | unchanged |
| New executor, old Worker | reply still has `url`, status has `downloads` | delivery completes; extra fields ignored | — |
| In-flight receipt | receipt has `link_url` but no `site_token` | token derived from `link_url`; no expiry stop | `UPLOAD_URL_INVALID` if neither parses |
| Long gap before notify | oci-hub receipt older than 72 h | notify proceeds (no `DELIVERY_EXPIRED_REQUEST_REDELIVERY`) | — |

</frozen-after-approval>

## Code Map

apply-site (`worker.js`):
- Remove link-only: `BUNDLE_TTL_MS`, `BUNDLE_MAX_DOWNLOADS`, `BUNDLE_CODE_LIMIT/WINDOW` (:23-27), `countDownload` :1255, `downloadPage` :1348, `GONE_TEXT` :1366, `liveBundle` :1369, `maskEmail` :1376, `bundleCodeHash` :1382, `requestBundleCode` :1389, `readDownloadCode` :1446, `claimBundleCode` :1471, `bundlePage` :1482-1573, `downloadBundle` :1574, `purgeBundles` :1604 (+ cron call :2289), `DOWNLOAD_PATH/CODE_PATH` :1624-1625 and routes :2269-2279, `bundleAvailable` :1247.
- Change: `uploadBundle` :1280-1300 (no TTL/url; INSERT keeps writing NOT NULL `expires_at`/`downloads` placeholders via `putBundle`), `bundleStatus` :1318-1333 (`{sha256, available}`), `putBundle`/`deleteDeviceBundles` :1219-1233 (drop `bundle_codes`/`bcode` deletes only if no rows can exist — keep them, harmless).
- Keep: `sessionDownload` :1933, `deviceBundle` :1925, `getBundle`, `logDownload`, `zipResponse`, `removeBundles`, `randomToken`, `TOKEN_PATTERN`, `TEXT.bundle.buttons.downloading`/`errors.unavailable`.
- `test-worker.mjs`: link sections :1183-1655, :478-481, :2054; mock D1 :132-223 may keep its branches. `schema.sql`: comment `bundles.expires_at/downloads`, `bundle_codes` as legacy.

employee-admin:
- `deliver-temp.py`: `site_upload` :190-199 (accept `token`, ignore `url`, return token), `site_verify` :201-212 (token from `receipt['site_token']` else `link_url`; require sha256 match and `available is True`; drop `downloads == 0`), `publish` :215-257 (oci-hub: store `site_token`, no `expires_at`/expiry stop; non-oci-hub unchanged), `notify` :404 expiry check (oci-hub skip), CLI output :432.
- `oci-hub-admin.py` (HEAD): `REISSUE_PLACEHOLDER_LINK` :236/:271, run-reuse expiry :263, `link_stale`/`REISSUE_LINK_STALE` :315-318, outputs :325 and :573 (`link_url`/`expires_at` → `site_token`). Edit only these lines; the main checkout's uncommitted HAPI lines are elsewhere.
- Tests: `test-temp-delivery.py` (:30-46, :69, :84, :135-164, :239-322), `test-oci-hub.py` (:539-541, :626, :635, :797-803, :836-857), `test-hub-requests.py` :25.
- `docs/admin-handbook.md` :124, :139-147, :252, :262-265, :275-276.

IaC: `.agents/skills/employee-provision/SKILL.md:37`, `references/operations.md:20,24`, `docs/deployment/oci-hub-native-provisioning.md:60`, `docs/architecture/oci-employee-vpn-hub.md:102`.

## Tasks & Acceptance

**Execution:**
- [ ] `remotecc/employee-admin/deliver-temp.py`, `oci-hub-admin.py` + tests -- token-based upload/verify, no link expiry on oci-hub, `site_token` in receipts/outputs, legacy `link_url` receipts still verify -- executor deploys first
- [ ] `remotecc/apply-site/worker.js`, `test-worker.mjs`, `schema.sql`, `migrations/0013-retire-bundle-links.sql` -- remove `/d/` flow, new upload/status shapes, drop link-only D1 objects -- link no longer reachable
- [ ] `remotecc/employee-admin/templates/mosh-hub-trial.html`, `email-template.txt`, `admin-core.py`, `remotecc-layout.json` -- delete unused link templates and their references -- decision 1
- [ ] `remotecc/employee-admin/docs/admin-handbook.md` -- describe session-only download, fix :262 contradiction, add deploy order -- matches code
- [ ] IaC docs and `employee-provision` skill -- same wording; bundle kept until retirement or replacement -- clears the #232 gate finding

**Acceptance Criteria:**
- Given the three worktrees, when their test suites run, then all pass and no test references `/d/`.
- Given the IaC PR, when CI runs, then every check including `review-policy-gate` passes.
- Given current docs (handbook, skill, deployment/architecture docs), when searched for `/d/`, `一次性`, `72`, `下载 3 次`, then no current-behavior statement describes the mailed link.

## Implementation Notes

Worktrees (created for this plan; edit only these, never the main checkouts):
- apply-site: `/private/tmp/rc-retire-link/apply-site` (branch `retire-bundle-links`); `../design` resolves through the sibling link `/private/tmp/rc-retire-link/design`.
- employee-admin: `/private/tmp/rc-retire-link/employee-admin` (branch `retire-bundle-links`).
- IaC: `/private/tmp/iac-retire-bundle-link` (branch `claude/retire-bundle-link`).
Commit nothing; the orchestrator commits after review.

## Plan Change Log

## Review Triage Log

Pass 1 (quick lens): high 0, medium 1, low 3, false 2, maybe-false 0.

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | `putBundle` omits NOT NULL `recipient`/`expires_at`, so uploads fail between `wrangler deploy` and migration 0013 | low | reject | Real but operator-controlled and documented in Design Notes and handbook 6.2a (run no delivery between steps 2 and 3); every order has a window (old Worker reads dropped columns), and avoiding it needs a two-phase deploy, more than a direct fix. |
| 2 | AC 1 "no test references `/d/`" unmet (test-worker.mjs:1245, test-temp-delivery.py:323/331/335) | false | reject | These tests exist to prove the matrix rows "Old link 404", "New executor, old Worker" and "In-flight receipt"; the fix would be editing the plan. |
| 3 | Migration 0013 untested | false | reject | Ran it with sqlite3 on HEAD `schema.sql` plus sample rows: `bundle_codes` gone, `bcode` row gone, other rate row kept, three columns dropped, bundle row kept. |
| 4 | `employee-provision/SKILL.md:43` still says the mail carries "真实链接…SHA256" | medium | patch | Contradicts line 37 and the mail tests (no token, no outer SHA in body); same class as the #232 gate finding. |
| 5 | `oci-hub-native-provisioning.md:56` "上传并下载校验"; :60 "次数限制" ambiguous after the quota removal | low | patch | oci-hub verifies through `GET /admin/bundles/<token>` (deliver-temp.py `site_verify`), no download; :60 now only means HTTP rate limiting. Direct wording fix. |
| 6 | `remotecc-layout.json` entry `email-template.html` removed but symlink/.gitignore line remain | low | reject | Nothing reads `email-template.html` (only `.gitignore`); `runtime-layout.py` only adds links, so the leftover link is inert; removing runtime links is outside this change. |

## Design Notes

Deploy order (reported, not executed): 1) push employee-admin to ws-executor (works with the old Worker); 2) `wrangler deploy` apply-site (new code no longer reads or writes the dropped columns; until step 3, uploads fail on the old NOT NULL columns, so run no delivery in between); 3) apply D1 migration 0013. Old executor + new Worker breaks uploads (it requires `url`).

## Verification

**Commands:**
- `node --test test-worker.mjs` (apply-site worktree, with `../design` linked) -- all pass
- `python3 -m unittest test-temp-delivery test-oci-hub test-hub-requests` (employee-admin worktree) -- all pass
- `rg -n "/d/|link_url|BUNDLE_TTL" <changed files>` -- only legacy-receipt handling remains
