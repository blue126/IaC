---
title: '申请前验证邮箱（6 位验证码）'
type: 'feature'
ticket: '8'
created: '2026-11-01'
status: 'done'
baseline_revision: '5d2f62d619147d9cedbe075115f8da380b795e3c'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 申请表不验证邮箱，填错的邮箱会让设备包发给别人。

**Approach:** 页面先填邮箱并点"获取验证码"：Worker 校验 Turnstile 并限频后，生成 6 位数字码，只存其 SHA-256，经 Resend REST API 从 `noreply@cc.willfan.me` 发出。提交申请时必须带该邮箱的有效验证码；验证通过即作废，申请记录标 `email_verified=1`。

**Decision:** 用户 2026-11-01 要求申请前验证邮箱并使用免费组件；Resend 免费版，仅发信权限的 Key 已存 Worker secret `RESEND_API_KEY`。验证码请求承担 Turnstile 校验（防止滥发邮件），申请提交保留 3.2 的 Turnstile 与 IP 限频。

## Boundaries & Constraints

**Always:** 验证码 6 位数字，用 `crypto.getRandomValues` 生成；10 分钟过期；每个验证码最多校验 5 次，超过即作废；同一邮箱 60 秒内只发一次（429 `CODE_TOO_SOON`）；同一 IP 每小时最多获取 5 次验证码（429 `CODE_RATE_LIMITED`，复用 rate_limits 表，窗口键加前缀 `code:` 区分）；Turnstile 规则与 3.2 一致（无令牌 absent 照发、令牌无效 403 `CODE_CHALLENGE_FAILED`、校验方错误 unverified 照发）；Resend 调用 5 秒超时，失败 502 `CODE_SEND_FAILED` 且不记录"已发送"；提交申请缺验证码或错误/过期/用尽 → 400 `APPLY_CODE_INVALID`，不写申请、不计 IP 申请次数；验证码与邮箱绑定（小写规范化后比较）；D1 只存验证码哈希；邮件正文中文，含验证码与"10 分钟内有效，如非本人操作请忽略"；发信地址与名称 `远程工作区 <noreply@cc.willfan.me>`。

**Never:** 不存验证码明文；不改管理接口与 `wsctl request`；不引入 npm 依赖；不做登录。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 获取验证码 | POST /api/code {email, turnstile?} | 200 `{sent:true}`；Resend 收到一次请求；D1 存哈希与过期时间 | — |
| 邮箱格式错 | 坏邮箱 | 400 | `APPLY_FIELDS_INVALID` |
| 60 秒内重复获取 | 同邮箱 | 429，不发信 | `CODE_TOO_SOON` |
| IP 超限 | 同 IP 本小时第 6 次 | 429 | `CODE_RATE_LIMITED` |
| Resend 失败 | 非 2xx 或超时 | 502，不算已发送（可立即重试） | `CODE_SEND_FAILED` |
| 正确提交 | 字段 + 正确 code | 201；email_verified=1；验证码作废 | — |
| 验证码复用 | 同 code 再提交 | 400 | `APPLY_CODE_INVALID` |
| 错误码 5 次后 | 第 6 次即使正确 | 400 | `APPLY_CODE_INVALID` |
| 过期 | 10 分钟后 | 400 | `APPLY_CODE_INVALID` |
| 换邮箱 | 用 A 的码提交 B | 400 | `APPLY_CODE_INVALID` |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/apply-site/`（自己的 git）。不 commit、不调用 Cloudflare 或 Resend；部署由主会话完成。

- `worker.js` -- 现有 `page(env)`、`apply()`、`verifyChallenge()`、`windows()`、`sha256Hex()`、`fail()`。新增 `POST /api/code` 处理函数；`apply()` 在 `validate` 后、challenge 前校验 `body.code`（D1 读 `email_codes`，比较哈希、过期、次数；成功后在 3.2 的 batch 里一并删除该验证码并写 `email_verified`）。Resend：`POST https://api.resend.com/emails`，头 `Authorization: Bearer ${env.RESEND_API_KEY}`、`Content-Type: application/json`，体 `{from, to:[email], subject, text, html}`；测试替身经 `env.RESEND`（与 `env.SITEVERIFY` 同样的注入方式）。页面：邮箱下方加"获取验证码"按钮（60 秒倒计时）与 6 位验证码输入框；Turnstile 令牌在获取验证码时使用并 reset，提交时再用新令牌。
- `schema.sql` -- `email_codes(email TEXT PRIMARY KEY, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, sent_at TEXT NOT NULL)`；`applications` 加 `email_verified INTEGER NOT NULL DEFAULT 0`。
- `migrations/0003-email-codes.sql` -- 建 `email_codes`，`ALTER TABLE applications ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0`。
- `test-worker.mjs` -- 假 D1 支持 `email_codes`；覆盖矩阵全部行；现有 apply 测试改为先获取验证码。

## Tasks & Acceptance

**Execution:**
- [x] `worker.js`、`schema.sql`、`migrations/0003-email-codes.sql`、`test-worker.mjs` -- 实现与测试
- [x] 部署（hitl，主会话）-- 用户在 Resend 添加并验证域名 `cc.willfan.me`（DNS 记录经 Cloudflare 添加）；执行 0003 迁移；上传 Worker（keep_bindings 保留 TURNSTILE_SECRET 与 RESEND_API_KEY）
- [x] 实测（hitl）-- 向管理员邮箱获取验证码，确认收到并能提交；错误码与复用被拒

**Acceptance Criteria:**
- Given 部署完成，when 在页面获取验证码，then 邮箱在 1 分钟内收到 6 位验证码，填入后提交成功，记录 `email_verified=1`。
- Given 已用过的验证码，when 再次提交，then 400 `APPLY_CODE_INVALID`。

## Implementation Notes

- 校验顺序：`/api/code` 为 body → 邮箱 → Turnstile → 清理旧 `code:` 窗口与过期验证码 → 原子占用 IP 名额（`DO UPDATE … WHERE count < 5 RETURNING`）→ 原子占用邮箱名额（upsert `WHERE sent_at <= now-60s RETURNING`，失败则释放 IP 名额并返回 `retry_after`）→ Resend；发送失败时释放 IP 名额并删除本次写入的验证码。发送后不再写 D1。`/api/apply` 为 body → 字段 → 验证码 → Turnstile → IP 限频 → batch（申请 `email_verified=1` + 删除验证码 + 计数）。
- 尝试次数用 `UPDATE … SET attempts = attempts + 1 WHERE email=? AND attempts<5 AND expires_at>? RETURNING code_hash` 原子扣减，正确与错误都计一次，并发请求无法超过 5 次；码正确但随后 Turnstile 403 或 IP 429 时验证码保留（已扣一次）。
- 哈希为 `SHA-256(email + ':' + code)`。名额在发信前占用，并发请求无法同时通过 60 秒与每小时 5 次限制。新码在发信前就覆盖旧码，发送失败时旧码也已失效（用户本就在重新获取）。
- 已知竞态：两个并发提交使用同一正确验证码时都可能在 batch 删除前通过校验，产生两条同邮箱申请；影响仅为重复申请，未处理。

- 2026-11-01 部署：提交 f08b7fc；Resend 域名 cc.willfan.me 由用户添加（DKIM/SPF/退信 MX 生效），用户授权后加 `_dmarc.willfan.me TXT "v=DMARC1; p=none"`；D1 建 email_codes、加 email_verified；Worker 源码 250986c4…556b，keep_bindings 保留 TURNSTILE_SECRET、RESEND_API_KEY。
- 2026-11-01 实测：无码提交 400；获取验证码 200，60 秒内再取 429（retry_after 60）；错码 400；用户收到验证码（进了 Gmail 垃圾箱），正确码提交 201（55b6abea1076，email_verified=1），复用 400；email_codes 已清空。待办：送达率（垃圾箱）需观察。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 1 / low 3
  - medium, patch — 获取验证码"先读限额、再等 Resend、后写入"，并发请求可绕过 60 秒与每小时 5 次限制、各发一封真实邮件：发信前原子预占，失败回滚，补并发测试。
  - low, patch — "发信成功但 D1 写入失败"路径无测试：补测试。
  - low, patch — "正确验证码在 403/429 后保留并扣一次"无测试：补断言。
  - low, patch — CODE_TOO_SOON 时页面总是倒数 60 秒：服务端返回剩余秒数。

## Verification

**Commands:**
- `cd remotecc/apply-site && node --test test-worker.mjs` -- expected: 全部通过
