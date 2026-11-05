---
title: '设备包经一次性链接下载'
type: 'feature'
ticket: '4'
created: '2026-11-01'
status: 'done'
baseline_revision: 'b89041e31c26647ad1d30abbadefb6d22f8ca169'
route: 'full'
route_source: 'auto'
risk: 'high'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 设备包经 Temp.sh 交付：第三方网盘、三天有效、下载次数不限，私钥暴露时间过长。

**Approach:** oci-hub 的交付把设备包上传到 `cc.willfan.me`（存 D1 BLOB），得到一次性链接 `https://cc.willfan.me/d/<token>`：GET 显示下载页（需点按钮），POST 下载文件；24 小时内最多 3 次，下载满或过期后删除包内容。执行器用管理接口核对上传的 SHA-256（不消耗下载次数），邮件沿用现有 Microsoft 邮件通道，内容改为 24 小时 / 3 次。

**Decision:** 2026-11-01 设备包存 D1（epic Decision）；用户要求推进到 epic 3 结束。

## Boundaries & Constraints

**Always:** Worker 内设备包存取封装为 `putBundle/getBundle/deleteBundle` 三个函数（日后换 R2 只改这里）；上传接口 `POST /admin/bundles?device=<id>&recipient=<email>`，body 为 zip 原始字节（≤ 64 KB，否则 413 `ADMIN_BUNDLE_TOO_LARGE`），返回 `{token, url, expires_at, sha256}`；token 为 32 位十六进制随机值，D1 只存其 SHA-256；同一 device 上传新包时删除该 device 的旧包（旧链接立即失效）；`GET /admin/bundles/<token>` 返回 `{sha256, downloads, expires_at}` 不计次；`GET /d/<token>` 有效则返回中文下载页（含剩余次数与到期时间，按钮以 POST 提交），无效返回"链接已失效，请联系管理员重新发送" 410；`POST /d/<token>` 有效则计次并返回 `application/zip`（`Content-Disposition: attachment; filename="device-bundle.zip"`），第 3 次下载后删除包内容；过期或已用尽 410 `BUNDLE_GONE`；计次用条件 UPDATE + RETURNING，并发不超 3 次；Worker 增加 cron（每小时）删除过期包；执行器端：`deliver-temp.publish` 在 `profile='oci-hub'` 时改走网站（新 provider `apply-site`），收据 `expires_at` 为 24 小时，核对用 admin GET 比对 SHA-256，不再下载；`settings['apply_site']` 提供 base_url 与令牌（与 3.1 相同，https、不跟随重定向、UA `wsctl/1`）；邮件模板 `templates/onboarding.html` 有效期一行改为"24 小时内有效、最多下载 3 次，下载满或过期后链接失效；需要重新发送请联系管理员"；其他内容不变。

**Never:** 不改 `profile='existing'`（旧方案，3.6 退役）；不做 reissue 命令（3.5）；不加包密码；不改审批/确认流程的语义（审批摘要可因收据字段变化而变化）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 上传 | 管理令牌 + zip | 200，返回 token/url；D1 存哈希化 token | 超大 413；无令牌 401 |
| 新包替换 | 同 device 再上传 | 旧 token 立即 410 | — |
| 下载页 | GET /d/<token> | 200 HTML，含按钮（POST） | 无效 410 |
| 下载 1–3 次 | POST /d/<token> | 200 zip，downloads+1 | — |
| 第 4 次 | POST | 410；第 3 次后 BLOB 已删除 | `BUNDLE_GONE` |
| 过期 | 24 小时后 | 410；cron 删除 | `BUNDLE_GONE` |
| 并发 | 同时 5 个 POST，剩 3 次 | 恰好 3 个 200 | — |
| 执行器发布 | deliver（oci-hub） | 收据 provider=apply-site、link_url 为 /d/<token>、expires_at=+24h；SHA 核对不计次 | SHA 不符 `DOWNLOAD_CHECKSUM_MISMATCH` |
| 邮件 | notify | 邮件含新链接与 24 小时 / 3 次说明 | — |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/apply-site/`（自己的 git）与 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py，不得修改或提交）。不 commit、不 push、不调用 Cloudflare；部署与真实发信由主会话完成。

- `apply-site/worker.js` -- 现有 `authorized()`、`fail()`、`json()`、`sha256Hex()`、路由 `handle()`；`export default` 增加 `scheduled(event, env)`。`schema.sql` + 新 `migrations/0005-bundles.sql`：`bundles(token_hash TEXT PRIMARY KEY, device_id TEXT NOT NULL, recipient TEXT NOT NULL, sha256 TEXT NOT NULL, data BLOB, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, downloads INTEGER NOT NULL DEFAULT 0)` 及 `device_id` 索引。
- `employee-admin/deliver-temp.py:119` `load_bound()`（identity 的 `provider`）、`:167` `publish()`（上传与核对）——oci-hub 分支改走网站；`'existing'` 分支保持 temp.sh 不动。`http()`（:33）只服务 temp.sh；网站请求复用 `hub-requests.py` 的 opener 约定（可在 hub-requests 里加 `admin_request(settings, method, path, body, content_type)` 并在此调用）。`publish` 需要 settings：调用方 `oci-hub-admin.py` 交付分支（:416 附近 `deliver`）已持有 settings，按需传入。
- `employee-admin/templates/onboarding.html:5` -- 有效期一行。`hub-onboard.py:101` 把 `templates/onboarding.html` 计入源码哈希，已覆盖。
- 测试：`apply-site/test-worker.mjs`（假 D1 支持 bundles、BLOB）；`employee-admin/test-temp-delivery.py`（oci-hub 发布改测网站路径，假站点或打桩 `admin_request`）。

## Tasks & Acceptance

**Execution:**
- [x] `apply-site/worker.js`、`schema.sql`、`migrations/0005-bundles.sql`、`test-worker.mjs` -- 上传、下载页、计次下载、替换、过期清理
- [x] `employee-admin/deliver-temp.py`、`hub-requests.py`、`oci-hub-admin.py`、`templates/onboarding.html`、`test-temp-delivery.py` -- 执行器改走网站
- [x] 部署（hitl，主会话）-- 迁移、上传 Worker（含 cron 触发器）、push employee-admin
- [x] 实测（hitl）-- 对 `control` 生成设备包并交付到管理员邮箱：链接打开是下载页；POST 3 次成功、第 4 次 410；admin GET 显示 downloads=3 且内容已删

**Acceptance Criteria:**
- Given 交付给 control，when 打开邮件链接，then 看到下载页而非直接下载；点按钮得到的 zip SHA-256 与邮件中一致。
- Given 已下载 3 次，when 再次下载，then 410 且 D1 中 data 为空。

## Implementation Notes

- 2026-11-01 部署：apply-site c673678（源码 c50a9cc1…703a，经 D1 导入接口上传 gzip 源码后在 Cloudflare 侧解压、核哈希、上传，避免手抄）；迁移 bundles、bundle_codes；cron `0 * * * *`；employee-admin adf5e66 推到执行器。
- 2026-11-01 实测（control → fanweiblue@gmail.com）：upload 计划与执行 → provider apply-site、phase verified、link /d/c33beb63…、到期 2026-11-04；下载页显示 f***@gmail.com 与发送按钮；无码 POST 403；通知邮件已发（两步 curl --fail 命令正确）；验证码过期两次（10 分钟，未计次）；第 4 个码 246174 下载 200，zip SHA-256 = 99bd3449…8c9c 与邮件一致，内含 3 个文件；同码复用 403；剩余 2 次。本地下载副本已删除。"3 次后 410 / 内容清空"由单元测试覆盖（该链接验证码发送额度仅剩 1 次）。

## Plan Change Log

- 2026-11-01 用户决定（冻结段之外的意图变更，经用户确认）：① 链接有效期由 24 小时改为 3 天，次数仍 3 次；② 下载前增加邮箱验证码（方案 A）：`POST /d/<token>/code` 把 6 位码发到该包的 recipient（页面打码显示邮箱），`POST /d/<token>` 需带正确 `code`（表单或 JSON），码 10 分钟有效、最多试 5 次、单次使用，同一 token 60 秒内只发一次；Agent 流程为先请求验证码、员工把码告诉 Agent。邮件模板说明同步。

## Review Triage Log

- Pass 2 (quick，下载验证码变更): high 1 / medium 1 / low 5
  - high, patch — 下载验证码请求无总量与 IP 限制，泄露链接可在 72 小时内猜约 2 万次并轰炸收件人：每个包最多发 5 个码，并共用每 IP 每小时上限。
  - medium, patch — OCI Hub 试用邮件模板仍是一步下载，现在必然 403：同步为两步。
  - low, patch — 发码失败回滚会删掉仍有效的旧码：恢复旧行。
  - low, patch — 下载页原生表单出错显示裸 JSON、剩余次数不刷新：改 fetch。
  - low, patch — curl 未加 --fail：补上。
  - low, patch — 过时注释与测试名：更正。

- Pass 1 (quick): high 0 / medium 2 / low 4 / rejected 2
  - medium, patch — 核对只比 SHA-256，续跑时可能对已用尽/已清空的包发出死链接：同时要求 available 且 downloads==0。
  - medium, patch — 交付逻辑依赖 hub-requests.py 但它不在审批源码哈希里：加入。
  - low, patch — 清理与 available 绕过存取封装：收进边界。
  - low, patch — 第 3 次下载后的删除是可吞错的单独调用：并入计次 UPDATE。
  - low, patch — 明确拒绝的上传留下 uploading 收据：删除后再报错。
  - low, patch — 假站点上传分支不校验令牌：补校验与 401 测试。
  - rejected — 旧 temp.sh 收据在新 provider 下 fail-closed（DELIVERY_IDENTITY_CHANGED）：安全行为，需新 run_dir 重新交付；写进 3.6 文档。
  - rejected（部署处理）— cron 触发器不在仓库：部署时经 API 设置 `0 * * * *` 并记录于此。

## Verification

**Commands:**
- `cd remotecc/apply-site && node --test test-worker.mjs` -- expected: 全部通过
- `cd remotecc/employee-admin && for t in test-temp-delivery.py test-hub-requests.py test-oci-hub.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: OK（沙箱外运行）
