---
title: '申请表 Turnstile 校验与 IP 限频'
type: 'feature'
ticket: '2'
created: '2026-11-01'
status: 'done'
baseline_revision: '09db4f5'
route: 'full'
route_source: 'auto'
risk: 'low'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `cc.willfan.me` 的申请接口已公开，任何人可无限提交。

**Approach:** 页面嵌入 Turnstile 小组件，提交时带上令牌；Worker 先向 siteverify 校验，再按来源 IP 限频（每小时 3 次、每天 10 次，D1 计数）。按 AD-13，Turnstile 无法加载（页面拿不到令牌）时仍接受提交但只靠限频，并在申请记录里标明 `challenge='absent'`。

## Boundaries & Constraints

**Always:** 令牌存在但校验失败 → 403 `APPLY_CHALLENGE_FAILED`，不计数、不写申请；siteverify 本身不可达 → 视同 absent（只靠限频）并标 `challenge='unverified'`；校验通过标 `challenge='passed'`；限频只统计成功写入的申请，超限 429 `APPLY_RATE_LIMITED`；IP 取 `CF-Connecting-IP`，D1 只存其 SHA-256；计数窗口按 UTC 小时与 UTC 日；每次写入时顺手删除两天前的计数行；`TURNSTILE_SECRET` 为 secret 绑定，`TURNSTILE_SITEKEY` 为普通变量；页面在 Turnstile 脚本加载失败时仍可提交。

**Never:** 不做邮箱验证码、不做登录；不改管理接口与 `wsctl request`；不引入 npm 依赖。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 校验通过 | 有效令牌 | 201，challenge='passed' | — |
| 校验失败 | 无效令牌 | 403，不写不计数 | `APPLY_CHALLENGE_FAILED` |
| 无令牌 | 字段 `turnstile` 缺失 | 201，challenge='absent' | — |
| siteverify 不可达 | fetch 抛错或非 200 | 201，challenge='unverified' | — |
| 每小时第 4 次 | 同 IP 本小时已 3 条 | 429，不写 | `APPLY_RATE_LIMITED` |
| 每天第 11 次 | 同 IP 当天已 10 条（跨小时） | 429 | `APPLY_RATE_LIMITED` |
| 不同 IP | — | 各自计数 | — |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/apply-site/`（自己的 git）。不 commit、不调用 Cloudflare；部署由主会话经 MCP 完成。

- `worker.js` -- 现有 `apply()`、`validate()`、`PAGE`；在 `validate` 之后、INSERT 之前加 challenge 与限频；页面加 `<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer>` 与 `<div class="cf-turnstile" data-sitekey="${TURNSTILE_SITEKEY}">`（页面改为按 env 生成），提交体带 `turnstile`（取 `cf-turnstile-response` 隐藏域，无则省略）。siteverify：POST `https://challenges.cloudflare.com/turnstile/v0/siteverify`，表单字段 `secret`、`response`、`remoteip`，读 `success`。
- `schema.sql` -- 加 `ALTER TABLE applications ADD COLUMN challenge TEXT;`（另起迁移文件 `migrations/0002-challenge-rate.sql`，含 `rate_limits(ip_hash TEXT, window TEXT, count INTEGER, PRIMARY KEY(ip_hash, window))`），`schema.sql` 同步为最终形态。
- `test-worker.mjs` -- 假 D1 需支持新表；`fetch` 用注入的 `env.SITEVERIFY`（测试替身）或全局 `fetch` 打桩；覆盖矩阵全部行。

## Tasks & Acceptance

**Execution:**
- [x] `worker.js`、`schema.sql`、`migrations/0002-challenge-rate.sql`、`test-worker.mjs` -- 实现与测试
- [x] 部署（hitl，主会话）-- MCP 建 Turnstile 小组件（域名 cc.willfan.me，managed）、执行迁移、上传 Worker（新增 TURNSTILE_SECRET、TURNSTILE_SITEKEY）
- [x] 实测（hitl）-- 无效令牌 403；同 IP 连续第 4 次 429；页面显示 Turnstile 小组件

**Acceptance Criteria:**
- Given 部署完成，when 用无效 Turnstile 令牌提交，then 403 且 D1 无新增。
- Given 同一 IP 本小时已提交 3 条，when 再提交，then 429。

## Implementation Notes

- 顺序：`validate` → challenge（失败即 403）→ 限频检查（读 `rate_limits`）→ 一个 D1 `batch`（事务）里写申请、两个计数 upsert、删除 `window < 两天前的 UTC 日` 的旧行。
- `window` 取值：小时 `YYYY-MM-DDTHH`、日 `YYYY-MM-DD`；SQLite 中未加引号的 `window` 列名已用 sqlite3 实测可用。
- `turnstile` 为 `undefined/null` → absent；非字符串或空串 → 403；`TURNSTILE_SECRET` 未配置 → unverified；siteverify 返回 200 但非 JSON → unverified。
- `TURNSTILE_SITEKEY` 未配置时页面不渲染脚本与小组件；sitekey 做 HTML 属性转义；每次提交后 `turnstile.reset()`（令牌一次性）。
- 评审修正：`success:false` 且 `error-codes` 全为服务端错误（invalid-input-secret / missing-input-secret / internal-error）→ unverified，其余（含空列表）→ 403；siteverify 请求带 `AbortSignal.timeout(5000)`，超时视同 unverified（测试通过 `env.SITEVERIFY_TIMEOUT_MS` 缩短）。
- 已知限制：检查与写入之间非原子，同 IP 并发请求可能略超限额（低风险，接受）。

- 2026-11-01 部署：提交 5d2f62d；Turnstile 小组件 sitekey 0x4AAAAAAFu2s5RMOR1xBOkQ（managed，cc.willfan.me），密钥经 MCP 直写 Worker secret TURNSTILE_SECRET（未经本会话输出）；D1 执行 ALTER challenge 一次 + rate_limits；上传 Worker（源码 8201a8df…1f64，keep_bindings secret_text，新增 TURNSTILE_SITEKEY）；关闭 workers.dev 与 previews。
- 2026-11-01 实测：页面含 Turnstile 脚本与小组件；无效令牌 403 且 D1 无新增；无令牌连续提交 201×3 后第 4 次 429，记录 challenge='absent'；rate_limits 小时与日计数均为 3；workers.dev 返回 404。D1 中另有用户自测申请 338ead3560cc。测试申请 7497c58ac666、c999da7daf42、51644325843d、0090f4d75eff 待 3.3 dismiss。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 1 / low 2 / rejected 2
  - medium, patch — siteverify 返回服务端错误码（密钥错误、内部错误）也被当作访客失败 403：改为 unverified。
  - low, patch — siteverify 无超时：5 秒超时，超时视为 unverified。
  - low, patch（部署处理）— 缺 CF-Connecting-IP 时所有请求共用一个计数桶：部署时关闭 workers.dev 路由，只经自定义域名访问（该头恒在）。
  - rejected — 迁移中 ALTER 不可重放：只由主会话执行一次并记录于此；新库只用 schema.sql。
  - rejected — AC 依赖部署实测。

## Verification

**Commands:**
- `cd remotecc/apply-site && node --test test-worker.mjs` -- expected: 全部通过
