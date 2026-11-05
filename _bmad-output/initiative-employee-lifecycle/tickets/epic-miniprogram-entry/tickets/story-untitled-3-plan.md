---
title: '网站员工登录与我的工作区'
type: 'feature'
ticket: '3'
created: '2026-11-02'
status: 'done'
baseline_revision: '5a36d5a0d3859db70a863c9b00fb12b12edbf492'
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

**Problem:** 员工开通后只能问管理员才知道自己的到期日、流量和登录方式；设备包只能靠邮件链接下载。

**Approach:** 网站加"我的工作区"：员工用邮箱验证码登录，得到 2 小时 HttpOnly 会话，看到自己工作区的状态、到期日（北京时间）、主机名、规格、本月流量、接入设备和登录命令，并能在设备包有效期内直接下载（与邮件链接共用 3 次额度）。数据只来自执行器推送的状态副本（AD-21）：网站新增一个只接受管理令牌的整份替换接口。

**Decision (2026-11-02 用户):** 1) 5.3 只做网站侧（登录、我的工作区页、会话下载、`PUT /admin/status` 接收接口），用测试数据验证；执行器生成并推送副本放到 5.6，"与 wsctl status 一致、续费后推送更新"的验收随之移到 5.6。2) "申请中"由执行器把已拉取、未开户也未驳回的申请写进副本（5.6 实现），网站只按副本显示。3) 只给副本里有的邮箱发登录码；接口对外一律返回同样的 200，不暴露邮箱是否存在，页面提示"如该邮箱已开通，验证码会发到这里"。

**状态副本格式（5.6 按此生成）:** `{generation: int, employees: [{email, state: "ACTIVE"|"PENDING"|"EXPIRED"|"PAUSED"|"NO_EXPIRY", paid_through: ISO8601 带时区 | null, hostname: str | null, spec: {name, cpu, memory_gb, disk_gb} | null, traffic: {used_bytes, limit_bytes} | null, devices: [device_id], updated_at: ISO8601}]}`；email 小写且唯一；PENDING 行其余字段可为 null/空。

## Boundaries & Constraints

**Always:** 会话令牌 32 字节随机，D1 只存其 SHA-256；cookie `__Host-session`，`HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=7200`，服务端以 `expires_at` 为准；登录验证码与申请验证码同规则（6 位、10 分钟、5 次、60 秒、每 IP 每小时 5 次、Turnstile 同 3.2），但与申请验证码分开存放；状态副本是全体员工的整份替换并带单调递增 `generation`，旧 generation 拒绝（409）；页面只显示副本里的字段，不自行推导状态；会话只能看到会话邮箱的数据；会话下载走 POST 并校验 `Origin` 为本站，计数与邮件链接同一行 `downloads`，满 3 次照旧删数据；所有文案来自 text.json（缺的先加进 text.json），样式沿用 5.2；导航加回"我的工作区"。

**Never:** 不在网站存私钥或 VM 访问凭据；不改申请、邮件链接下载、管理接口的既有行为；不 commit、不部署、不改执行器以外的系统（另行授权）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 请求登录码 | POST /api/login/code {email, turnstile?} | 200；邮箱在副本中才发信 | 坏邮箱 400；60 秒内 429 `CODE_TOO_SOON`；IP 超限 429 |
| 登录 | POST /api/login {email, code} | 200 + Set-Cookie；码作废 | 错/过期/用尽 400 `LOGIN_CODE_INVALID` |
| 查看 | GET /me 带有效会话 | 该邮箱的状态页 | 无会话或过期 → 登录页 |
| 退出 | POST /api/logout | 会话删除，cookie 清空 | — |
| 会话下载 | POST /me/bundles/<device> | 200 zip，downloads+1 | 非本人设备/失效 410；无会话 401；Origin 不符 403 |
| 推送副本 | PUT /admin/status {generation, employees:[…]} | 200，整份替换 | 无令牌 401；generation 不大于现值 409；格式错 400 |

</frozen-after-approval>

## Code Map

- `remotecc/apply-site/worker.js` -- 复用 `requestCode`/`checkCode` 的验证码与限频逻辑（需泛化出用途前缀或独立表）、`authorized()`（管理令牌）、`liveBundle`/`countDownload`/`downloadBundle`（计数与删数据）、`shell()`/`styles()`/`tags()`（5.2 页面外壳）、`fill()`/`js()`。新增路由 `/me`、`/api/login/code`、`/api/login`、`/api/logout`、`/me/bundles/<device>`、`PUT /admin/status`。
- `remotecc/apply-site/schema.sql` + `migrations/0007-sessions-status.sql` -- `login_codes`、`sessions(token_hash PK, email, expires_at)`、`status_copies(email PK, employee_id, data JSON, generation)` 与 `status_meta(generation)`。小时 cron 顺带清理过期会话。
- `remotecc/apply-site/test-worker.mjs` -- 假 D1 扩展新表；覆盖矩阵全部行。
- `remotecc/design/text.json` -- `status.*` 已有大部分文案；登录页、未开通、错误码文案需补。改后 `node sync-design.mjs`。
- `remotecc/design/canvas/project/{WebStatus,Status}.dc.html` -- 页面布局依据（只读）。
- 执行器侧（5.6 使用，本 story 不改）：`remotecc/employee-admin/hub-status.py:view()`（每员工 `lifecycle`、`paid_through`、`hostname`、`devices`、`usage`、`workspace_block_reasons` 含 `quota_exhausted`）、`hub-requests.py:call()/admin_request()`（只允许 GET/POST/DELETE，需加 PUT；UA `wsctl/1`）、`hub-expiry.py:push` 的触发点（provision/renew/expiry/retire）。规格在 `terraform/proxmox/oci-hub-workspaces.auto.tfvars.json`。employee-admin 有用户未提交改动（README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py），不得修改或提交。

## Tasks & Acceptance

**Execution:**
- [x] `remotecc/design/text.json` -- 补登录页（标题、说明、"如该邮箱已开通…"提示、按钮）、未登录/未找到副本、会话过期、错误码 `LOGIN_CODE_INVALID` 等文案；`status.states` 已有五种状态；运行 `node sync-design.mjs` -- 文案单一来源
- [x] `remotecc/apply-site/migrations/0007-sessions-status.sql` + `schema.sql` -- 新表（见 Code Map） -- D1 结构
- [x] `remotecc/apply-site/worker.js` -- `PUT /admin/status`（校验格式、generation 单调、事务内整份替换）；登录码与登录接口；会话读取（cookie → hash → 未过期）；`GET /me`（有会话→按副本渲染 WebStatus/Status 设计：状态行、到期日北京时间与剩余天数、主机名、规格、本月流量、接入设备、`mosh <hostname>`、该邮箱各设备的有效设备包卡片、联系管理员；无会话→登录页）；`POST /api/logout`；`POST /me/bundles/<device>`（Origin 校验，复用计数与删数据逻辑）；导航加回"我的工作区"；cron 清理过期会话与登录码 -- 网站侧全部功能
- [x] `remotecc/apply-site/test-worker.mjs` -- 覆盖矩阵每一行；另测：他人邮箱看不到状态、2 小时后会话失效、会话下载与邮件链接合计不超过 3 次、cookie 属性、五种状态各自的显示 -- 行为证明
- [x] `_bmad-output/.../tickets/tickets.toml` -- 不改（主会话已把移交的验收写进 5.6）

**Acceptance Criteria:**
- Given 推送了含测试员工的副本，when 该员工用邮箱验证码登录，then 看到副本中的状态、到期日与设备包，且 cookie 为 HttpOnly/Secure/SameSite=Lax、2 小时有效。
- Given 两个员工的副本，when A 登录，then 页面与接口都拿不到 B 的任何字段。
- Given 某设备包已经邮件链接下载 2 次，when 员工在"我的工作区"再下载 1 次，then 成功且之后两条路径都显示已失效。
- Given 未开通的邮箱，when 请求登录码，then 返回与已开通邮箱相同的 200，且不发信。

## Implementation Notes

- `status_copies` 不含 `employee_id`：冻结的副本格式里没有这个字段，表为 `(email PK, data, generation)`。`status_meta` 多一列 `push_id`：upsert 只在 generation 更大时成功，其余语句都以 push_id 为门，旧推送或并发中落败的推送不改任何数据，返回 409 `ADMIN_STATUS_STALE`。
- `PUT /admin/status` 请求体上限 1 MiB、最多 1000 名员工、每人最多 20 台设备；只保存副本格式里的字段，多余字段丢弃；email 必须已是小写。
- 登录码复用 `requestCode`/`checkCode`（按用途参数化表名与限频窗口）：`login_codes` 表，IP 计数窗口 `login:YYYY-MM-DDTHH`，与申请码互不占用额度。副本外的邮箱也照常预留限频与码行，只是不发信，60 秒与 IP 限制的表现完全一致。Turnstile 只在请求登录码时校验（与 `/api/code` 相同）。
- 会话下载按副本中该邮箱的 `devices` 判定归属，不比对 bundle 的 `recipient`。
- 流量按 2^30 字节显示为 GB，保留 1 位小数。

- 2026-11-02 复核：审查补丁后 110/110 通过；以 node:sqlite 作 D1 替身渲染 /me（ACTIVE、PAUSED、未登录），深色 1280 与浅色 390 截图核对，布局与 WebStatus/Status 设计一致。未提交、未部署、未执行迁移 0007。

- 2026-11-02 部署（用户授权）：线上 D1 执行迁移 0007（新增 login_codes、sessions、status_copies、status_meta）；`wrangler deploy` 版本 6fc0ce98-92d7-4bf7-b896-0cd3d3c6a93e（含 5.3 与 5.12 网站部分，apply-site 96ed579）。绑定、cron、域名、workers.dev 关闭均不变；冒烟：/、/apply、/me 200，字体 200，无令牌 PUT /admin/status 401，坏邮箱登录码 400，首页显示 50 GB 且无档位名。执行器侧（employee-admin 7e0e7ee）未推送：执行器运行目录被直接覆盖为用户的 desktop-update 分支 fe8a146，按用户选择 B 等其合入 main 后再推。

- 2026-11-02 线上验收：用户以 control 员工邮箱在 cc.willfan.me/me 用邮箱验证码登录成功，页面显示副本中的状态（长期有效）、主机名、规格（2 vCPU · 8 GB · 50 GB）、本月流量、接入设备、登录命令与有效设备包（剩余 3/3、有效期北京时间）。登录命令目前显示 `mosh oci-hub-control`，在 5.10 之前并不能直接使用。

## Plan Change Log

## Review Triage Log

### Pass 1 (quick) — high 0 / medium 2 / low 4 / false 1 / maybe-false 1 / rejected 1

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | 登录码：已开通邮箱要等 Resend 返回，响应时间暴露邮箱是否存在 | medium | patch | `requestCode` 对未知邮箱在插入后立即 200，已知邮箱等 `purpose.send`；与 Decision 3 冲突。登录码发信改为 `ctx.waitUntil` 后台发送，两种邮箱同样立即 200 |
| 2 | 登录码：发信失败只对已开通邮箱返回 502 | medium | patch | 与 #1 同根因，一并修复：登录码路径不再因发信失败返回 502 |
| 3 | PAUSED 等非 EXPIRED 状态仍显示"前可正常连接" | medium | patch | `statusPage` 对所有非 EXPIRED 显示 `expiry_detail`，属自行推导；只在 ACTIVE 显示，其他状态仅显示到期日期 |
| 4 | EXPIRED 无日期渲染"已于 — 结束"，且 `—` 写死 | low | patch | `statusRow` 允许 EXPIRED 的 paid_through 为 null；校验要求 ACTIVE/EXPIRED/PAUSED 必须有 paid_through |
| 5 | 规格、流量、登录命令里的 vCPU/GB/mosh 等写死 | low | patch | 违反"所有文案来自 text.json"；加模板到 text.json |
| 6 | /me 500 页借用 bundle 的错误文案 | low | reject | 文案通用（"服务暂时不可用"），无实际危害，修改需新增条目与分支 |
| 7 | 推送批量语句可能超过 D1 每次调用的查询上限 | maybe-false | defer | 当前员工 8 人，远低于免费版 50 条；需查 D1 文档确认 batch 内语句是否单独计数与账户套餐 |
| 8 | 假 D1 无法证明推送的 push_id 门控在真实 SQLite 上成立 | false | reject | 用 node:sqlite 按迁移 0007 原样执行四次推送：同 generation 与更旧推送均不改数据并判为 409，更大 generation 整份替换 |
| 9 | 未开通邮箱拿到码也能建立会话 | low | patch | `login` 不核对副本；登录时邮箱不在副本按 `LOGIN_CODE_INVALID` 处理 |

## Verification

**Commands:**
- `node sync-design.mjs --check` -- expected: 无差异
- `node --test test-worker.mjs` -- expected: fail 0
