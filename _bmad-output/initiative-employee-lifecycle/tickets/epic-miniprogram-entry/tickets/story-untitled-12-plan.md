---
title: '执行器生成状态副本并推送到网站'
type: 'feature'
ticket: '12'
created: '2026-11-02'
status: 'done'
baseline_revision: '71b8aed5883ec0985aa97d47b389a99afaf5b7f2'
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

**Problem:** 网站"我的工作区"（5.3）只显示执行器推送的状态副本，但执行器还不会生成和推送它，员工登录不了也看不到状态。

**Approach:** employee-admin 新增一个模块，用便宜的数据源（catalog、到期规则、一次 OCI `query`、Terraform roster、本地申请文件）为全体员工生成 5.3 计划规定格式的副本，经现有 apply-site 管理客户端 `PUT /admin/status` 整份推送。新命令 `wsctl publish-status` 供 Semaphore 每小时调用；开户、续费、到期初始化、退役、拉取/驳回申请之后也各推一次。推送失败只记录，不让原命令失败。

**Decision (2026-11-02 用户):** 1) 新增第六种状态 `DISABLED`（"已停用"，"工作区已被停用，请联系管理员"）：lifecycle `disabled` 且原因不是当前周期 `quota_exhausted` 时使用；网站 text.json、副本校验与页面同步支持。2) 规格档位：执行器 settings 里放一张"核数/内存/磁盘 → 档位名"的对照表，档位为经济型、标准型、性能型（当前 `2/8192/50G → 标准型`），定制型由管理员单独开通；对不上的传 `name: null`。第一期网站不向员工展示任何档位名：首页规格条去掉"标准型"标签，"我的工作区"规格行只显示数字；副本格式里 `spec.name` 改为可为 null。3) 磁盘实际为 50 GB：text.json 的规格行与规格条、设计画布中的 20 GB 改为 50 GB。4) 流量按十进制 GB 显示（与账本 `QUOTA=5_000_000_000` 一致）。

## Boundaries & Constraints

**Always:** 副本格式严格按 5.3 计划（email 小写唯一；ACTIVE/EXPIRED/PAUSED 必须有 paid_through）；`generation` 取推送时刻的 Unix 毫秒（单调、无需本地状态，wsctl 全局锁保证不并发）；本月流量按 OCI 账本当前周期（`Asia/Shanghai` 的 `YYYY-MM`）的 rx+tx，上限 `QUOTA + bonus`（ledger.py 的 `QUOTA=5_000_000_000`）；主机名取员工实际 hostname（当前为 `oci-hub-<id>`，5.10 改名后随之变化）；"申请中"= 已拉取、无 `processed_at`、且邮箱不在 catalog 的申请；不做 wg/PVE 的 SSH 观测；推送失败返回 `{'error': CODE}` 的形式，与 `hub-expiry.push_result` 一致；新错误码前缀加入 oci-hub-admin 的安全码白名单。

**Never:** 不修改用户未提交的文件（README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py）；副本里不放私钥、令牌、VPN 地址、设备包；不 commit、不部署、不建 Semaphore 模板（主会话另行授权）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 正常员工 | lifecycle active，本月未超额 | ACTIVE，paid_through、hostname、spec、traffic、devices | — |
| 流量超额 | 设备原因含 `quota_exhausted:<当前周期>` | PAUSED | — |
| 其他停用 | lifecycle disabled，原因非当前周期超额（admin_disabled、revoked 等） | DISABLED | — |
| 规格对不上 | roster 数字不在对照表 | `spec.name` 为 null，数字照传 | — |
| 已到期 / 可退役 | lifecycle expired 或 retirable | EXPIRED | — |
| 不设到期 | `no_expiry` | NO_EXPIRY，paid_through 可为 null | — |
| 申请中 | 未处理申请文件，邮箱不在 catalog | PENDING，其余字段 null/空 | 同邮箱多份只出一行 |
| 网站不可用 | PUT 超时或非 2xx | `publish-status` 非零退出；开户/续费等照常完成并记录错误 | `STATUS_PUBLISH_*` |
| 旧 generation | 网站返回 409 | 记录为错误，不重试 | `STATUS_PUBLISH_STALE` |

</frozen-after-approval>

## Code Map

私有仓库 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`（main，HEAD 71b8aed）。

- 新增 `hub-publish.py` -- `build(base, settings, now)` 生成副本；`publish(base, settings)` 推送；`publish_result(...)` 包装不抛异常。复用：`hub-terminal.catalog` (:24，文件不存在时照 hub-expiry.py:33 的方式判断)、`hub-terminal.root_roster` (:18，roster `oci_hub_workspaces[<id>]` 的 `cores`、`memory` MiB、`disk_size` 如 `"50G"`)、`hub-status.paid_through` (:16) 与 `lifecycle` (:25)、`oci-hub-admin.remote(settings,'query')` (:21，`report['usage']` 行 `{user_id:'oci-hub:user:<id>', period, rx, tx, bonus}`，`report['identities']` 的 `reasons`；`quota_exhausted:<period>` 只出现在设备 identity 上)、`hub-requests.site_settings` (:70) 与 `call(..., method='PUT', body=...)` (:37)、`hub-requests.read_application` (:111) 读 `requests_dir` 下的 `site-*.json`。
- `oci-hub-admin.py` -- argparse `choices` (:389) 加 `publish-status` 分支；安全码正则 (:597) 加 `STATUS_`；在 renew (:440-450 调用处)、apply/writeback (:513-523)、request pull 与 dismiss 之后调用 `publish_result`。
- `hub-terminal.py:537`（开户写首个 paid_through 后）、`hub-expiry.py:93/116`（renew、initialize）、`hub-retire.py:277-278`（退役）-- 在现有 `push_result` 旁边追加 `publish_result`，结果写入同一运行记录。
- `wsctl` -- usage 列表 (:10)、允许动作 (:23)、写操作清单 (:33) 加 `publish-status`。
- 测试：新增 `test-hub-publish.py`，仿照 `test-hub-expiry.py` 的 `Push`（patch `load` + 假 report/catalog）与 `test-hub-requests.py` 的 `SiteCase`（本地 HTTPS 假站点，加 `do_PUT`）；`test-wsctl.py` 加分发用例。
- 网站侧（`/Users/weierfu/Projects/IaC/remotecc/apply-site/`）：`worker.js:1738` 流量改为除以 1e9；`:1561` 副本校验允许 `spec.name` 为 null、状态集合加 `DISABLED`；`:610` 首页规格条去掉档位标签；`:1790` 规格行不显示名称（`status.spec_value` 去掉 `{name}`）；测试相应更新。
- 设计源（`/Users/weierfu/Projects/IaC/remotecc/design/`）：`text.json` 加 `status.states.DISABLED`，`spec.rows` 磁盘与 `spec.bar` 改 50 GB，`status.spec_value` 去掉名称；`canvas/project/{Spec,Web,WebStatus,Status}.dc.html` 的 20 GB 改 50 GB、去掉档位标签；改后在 apply-site 运行 `node sync-design.mjs`。`tokens.json` 的 `status` 加 `DISABLED`（取 warn 配色）。

## Tasks & Acceptance

**Execution:**
- [x] `remotecc/employee-admin/hub-publish.py` -- 新模块：build / publish / publish_result；settings 读 `oci_hub.spec_tiers`（缺省时内置当前 `2/8192/50G → 标准型`）-- 生成与推送
- [x] `remotecc/employee-admin/oci-hub-admin.py`、`wsctl`、`hub-terminal.py`、`hub-expiry.py`、`hub-retire.py` -- 新命令与各触发点（见 Code Map）-- 接入
- [x] `remotecc/employee-admin/test-hub-publish.py`、`test-wsctl.py` -- 覆盖矩阵每一行、推送失败不影响触发命令、PUT 请求体格式 -- 行为证明
- [x] `remotecc/design/text.json`、`tokens.json`、`canvas/project/*.dc.html` -- DISABLED、50 GB、去掉档位名 -- 设计源
- [x] `remotecc/apply-site/worker.js`、`test-worker.mjs` -- DISABLED、spec.name 可空且不显示、十进制 GB、首页去档位标签；运行 sync -- 网站配合

**Acceptance Criteria:**
- Given 测试 catalog 含 ACTIVE、超额、停用、到期、不设到期各一名员工及一份未处理申请，when 运行 build，then 生成的副本逐项符合矩阵，且能被 5.3 的 `PUT /admin/status` 校验接受（同一份 JSON 喂给 apply-site 测试）。
- Given 网站返回 500 或超时，when 运行 `wsctl renew`，then 续费成功写入，运行结果里带 `STATUS_PUBLISH_*` 错误。
- Given 页面渲染，when 查看首页与"我的工作区"，then 不出现任何档位名，磁盘显示 50 GB，流量 5,000,000,000 字节显示为 "5 GB"。

## Implementation Notes

- 基线：employee-admin 71b8aed5883ec0985aa97d47b389a99afaf5b7f2（含用户未提交改动，不得触碰）；apply-site af20f71；design 852ae27。

- 2026-11-02 部署（用户授权）：线上 D1 执行迁移 0007（新增 login_codes、sessions、status_copies、status_meta）；`wrangler deploy` 版本 6fc0ce98-92d7-4bf7-b896-0cd3d3c6a93e（含 5.3 与 5.12 网站部分，apply-site 96ed579）。绑定、cron、域名、workers.dev 关闭均不变；冒烟：/、/apply、/me 200，字体 200，无令牌 PUT /admin/status 401，坏邮箱登录码 400，首页显示 50 GB 且无档位名。执行器侧（employee-admin 7e0e7ee）未推送：执行器运行目录被直接覆盖为用户的 desktop-update 分支 fe8a146，按用户选择 B 等其合入 main 后再推。

- 2026-11-02 执行器：5.12 以 cherry-pick 叠在用户 desktop-update fe8a146 之上为 8268f91（解决 wsctl、oci-hub-admin.py 动作列表冲突），推送 ws-executor main 并经发布 hook 部署。用户授权后运行 `wsctl publish-status`：generation 1793592638481，推送 6 名员工（5 ACTIVE、1 NO_EXPIRY），pilot 与 pilot509 因共享管理员邮箱被跳过；D1 中副本字段齐全。Semaphore 每小时模板在 IaC 分支 claude/semaphore-publish-status（6b36010）本地提交，待推送开 PR。

- 2026-11-02 定时：IaC PR #219 合并（de62b75），推到执行器 /srv/iac，deploy-ws-executor 先 --check 再执行；Semaphore 出现模板 `wsctl publish-status`，cron `15 * * * *`。未在线上验证续费后的更新与"申请中"（当前无未处理申请）。

## Plan Change Log

- 2026-11-02 实现：renew 与 expiry --initialize 的发布放在 `hub-expiry.renew/initialize`（与 push_result 并列），oci-hub-admin 的 renew 分支不再另推，避免重复。oci-hub-admin 在 `apply`（不论有无 writeback）、`request` 拉取/驳回之后各推一次。
- 2026-11-02 实现：409 识别需要 `hub-requests.HTTP_CODES` 增加 `(409,'ADMIN_STATUS_STALE') → REQUEST_SITE_STALE`，再映射为 `STATUS_PUBLISH_STALE`。
- 2026-11-02 实现：同一邮箱多名员工时按 employee_id 排序只发第一名，其余记入 `skipped`（`email_shared`）；paid_through 无效的员工跳过（`paid_through_invalid`），不阻断整份推送。PAUSED 仅当全部停用原因都是当前周期 `quota_exhausted`；混有其他原因为 DISABLED。未设 paid_through 且无 no_expiry 的员工不会到期，发 NO_EXPIRY（停用时发 DISABLED），因为网站要求 ACTIVE/PAUSED 带日期。
- 2026-11-02 实现：网站侧 `spec` 必须带 `name` 键，值可为 null。`text.json` 的 `spec.name` 保留但不再渲染；`canvas/project/Main.dc.html` 组件页里的"标准型"卡片未改（不在计划列出的页面内）。

## Review Triage Log

### Pass 1 (quick) — high 0 / medium 2 / low 4 / false 1 / maybe-false 0; rejected 3

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | 无 paid_through 且被停用的员工使 `state()` KeyError，整份推送失败 | medium | patch | `{'ACTIVE':'NO_EXPIRY','PAUSED':'DISABLED'}[name]` 没有 `DISABLED` 键（hub-publish.py:56）；`build` 只捕获 ValueError。补上 `DISABLED→DISABLED` 并加测试 |
| 2 | 非规范 paid_through 原样发出，网站整份拒绝 | low | patch | `state` 返回 `row['paid_through']` 原串；改为发 `stamp.isoformat()`，与网站 `±HH:MM` 格式一致 |
| 3 | 退役员工若有未标记处理的申请文件，会重新显示"申请中" | medium | patch | 以 `--email` 开户的员工其申请文件从不标记 processed；退役删 catalog 后即符合 PENDING 定义。退役时把该邮箱未处理的申请本地标记为已处理（outcome `retired`），不改网站 |
| 4 | 开户推两次（hub-terminal 与 oci-hub-admin apply） | low | patch | 两次 OCI query 与两次 PUT，站点不可用时两次 15 秒超时；删去 oci-hub-admin.py:534 的重复推送 |
| 5 | `request` 拉取失败后仍推送 | low | patch | oci-hub-admin.py:474 在检查 `sources.site` 之前推送；站点不通时跳过推送 |
| 6 | `publish_result` 透传非 STATUS_ 错误码 | low | reject | 命令仍非零退出且码可读；改名会丢信息 |
| 7 | 验收 2 经 `admin.main(['renew'])` 而非 `wsctl renew` 测试 | low | reject | wsctl 对 renew 是透传，test-wsctl 已覆盖分发；行为已证明 |
| 8 | 审查 diff 缺少集成文件 | false | reject | 暂存脚本的问题（BSD sed），审查者已直接核对工作区 diff，结论已覆盖 |

## Verification

**Commands:**
- `python3 -m unittest test-hub-publish.py test-hub-expiry.py test-hub-requests.py test-wsctl.py` -- expected: 全部通过
- `node --test test-worker.mjs`（apply-site） -- expected: fail 0
