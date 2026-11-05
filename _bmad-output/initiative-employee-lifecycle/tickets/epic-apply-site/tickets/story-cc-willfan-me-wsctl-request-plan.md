---
title: 'cc.willfan.me 规格页与申请表上线并可被 wsctl request 拉取'
type: 'feature'
ticket: '1'
created: '2026-11-01'
status: 'done'
baseline_revision: 'fe6c395afc30e749685113889ded2fb822f14252'
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

**Problem:** 员工没有线上入口提交申请，管理员只能手工收集邮箱与姓名。

**Approach:** 在 `cc.willfan.me` 部署一个纯 JavaScript 的 Cloudflare Worker（D1 绑定），提供移动端优先的规格页与申请表，提交写入 D1；提供只接受管理令牌的列表接口；执行器新增 `wsctl request` 拉取未处理申请并落为本地请求文件。

**Decision:** 管理令牌只在执行器生成与保存（BWS `executor/apply-site-admin-token`），Worker 只保存其 SHA-256（普通变量 `ADMIN_TOKEN_SHA256`），令牌本身不经过部署方。Cloudflare 资源由主会话经 MCP 创建（epic Decision 2026-11-01）。

## Boundaries & Constraints

**Always:** 页面文案与小程序一致（标题"远程工作区"、说明"面向内部员工的纯命令行 Linux 工作区，SSH / Mosh 直连，每月含 5GB 双向流量。不提供图形桌面。"、标准型 2 vCPU / 8 GB 内存 / 20 GB 磁盘 / 5 GB/月流量、申请说明 2–4 条，去掉邀请码一条）；字段邮箱（必填，小写规范化）、姓名（必填，≤40 字）、手机号（选填，≤20 字）；接口返回 JSON，错误为 `UPPER_SNAKE` 码；D1 只存申请内容，不存凭据；管理接口 Bearer 令牌经 SHA-256 后常量时间比较，失败 401；`wsctl request` 只在执行器运行；请求文件原子写入、已存在且内容相同则不改；不使用任何前端框架或 npm 依赖。

**Never:** 不做 Turnstile 与限频（3.2）、不做已处理回写与 provision 接入（3.3）、不做设备包（3.4）；不调用家中或 OCI；不改 IaC 仓库。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 打开首页 | GET / | 200 HTML，含规格与表单，视口适配手机 | — |
| 有效提交 | POST /api/apply {email,name,phone?} | 201 `{id}`；D1 新增 status='new' | — |
| 缺字段/格式错 | 无姓名、坏邮箱、超长 | 400，不写 D1 | `APPLY_FIELDS_INVALID` |
| 非 JSON/超大 | body > 4 KB 或非 JSON | 400 | `APPLY_BODY_INVALID` |
| 管理列表 | GET /admin/applications，正确令牌 | 200 `{applications:[…]}` 只含 status='new' | — |
| 无/错令牌 | 无 Authorization 或错误 | 401 | `ADMIN_UNAUTHORIZED` |
| 拉取落地 | `wsctl request` | 每条写 `requests/oci-hub/site-<id>.json`，输出 `{profile,action:'request',pulled:[ids],sources:{site:'ok'}}` | 网站不可达 → `sources.site` 为错误码，非零退出 |
| 重复拉取 | 同一申请已落地 | 文件不变，`pulled` 仍列出 | — |

</frozen-after-approval>

## Code Map

私有代码：`/Users/weierfu/Projects/IaC/remotecc/`（不进公开仓库）。`employee-admin/` 有用户未提交改动：README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py（旧 signup-api 命令行，勿改勿用），不得修改或提交。标 hitl 的任务由主会话执行；不 commit、不 push、不调用 Cloudflare。

- 新 `remotecc/apply-site/`（新建，`git init` 由主会话做，实现只写文件）：
  - `worker.js` -- ES module Worker；`export default { fetch(request, env) }`；纯函数 `handle(request, env, now)` 便于测试；HTML 内联 CSS，`lang="zh-CN"`，无外部资源。
  - `schema.sql` -- `applications(id TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL, phone TEXT, status TEXT NOT NULL DEFAULT 'new', created_at TEXT NOT NULL, processed_at TEXT)` 及 `status` 索引；id 用 `crypto.randomUUID()` 去横线取前 12 位。
  - `test-worker.mjs` -- `node --test`，用内存假 D1（实现 `prepare().bind().run()/all()/first()`）覆盖矩阵中 Worker 各行。
- `employee-admin/hub-requests.py` 新增 -- `pull(settings)`：`settings['apply_site']['base_url']` + 令牌文件 `settings['apply_site']['admin_token_file']`；urllib 请求，超时 15 秒；落地目录 `Path(settings['apply_site']['requests_dir'])`；用 `hub-onboard.save` 原子写。
- `employee-admin/oci-hub-admin.py` -- action choices 加 `request`，调用 `hub-requests.pull`；安全错误码前缀加 `APPLY`、`REQUEST` 已有。
- `employee-admin/wsctl` -- 动作列表与执行器写入守卫加 `request`。
- `employee-admin/wsctl-secrets.py` -- 已支持 `{"key","settings":[dotted]}`，无需改；执行器 settings 加 `apply_site` 块与一条 `executor/apply-site-admin-token` → `apply_site.admin_token_file`（主会话做）。
- 测试：新 `employee-admin/test-hub-requests.py`（本地 `http.server` 假站点，需沙箱外运行）、`test-wsctl.py`。

## Tasks & Acceptance

**Execution:**
- [x] `remotecc/apply-site/worker.js`、`schema.sql`、`test-worker.mjs` -- Worker 与测试
- [x] `employee-admin/hub-requests.py`、`oci-hub-admin.py`、`wsctl`、`test-hub-requests.py`、`test-wsctl.py` -- 拉取入口与测试
- [x] 部署（hitl，主会话）-- 执行器生成令牌并写 BWS，取其 SHA-256；MCP 建 D1 `apply-site`、执行 schema、上传 Worker（D1 绑定 + `ADMIN_TOKEN_SHA256`）、绑定自定义域名 `cc.willfan.me`；执行器 settings 加 `apply_site`
- [x] 实测（hitl）-- 手机提交一条测试申请 → 执行器 `wsctl request` 落地；无令牌管理接口 401；用户国内网络打开页面

**Acceptance Criteria:**
- Given 部署完成，when 手机浏览器提交申请，then 执行器 `wsctl request` 输出包含其 id，且 `requests/oci-hub/site-<id>.json` 内邮箱为小写。
- Given 公网，when 无令牌访问 `/admin/applications`，then 401。

## Implementation Notes

- 请求文件内容：`{profile:'oci-hub', source:'site', application_id, email(小写), name, created_at[, phone]}`；手机号为空时不写该键。执行器对远端返回再次校验（id 必须 12 位十六进制、邮箱格式、长度），任一条无效则整批不写，`sources.site=REQUEST_SITE_RESPONSE_INVALID`。
- `sources.site` 错误码：`REQUEST_SITE_UNREACHABLE`、`REQUEST_SITE_UNAUTHORIZED`、`REQUEST_SITE_HTTP_ERROR`、`REQUEST_SITE_RESPONSE_INVALID`、`REQUEST_SITE_TOKEN_UNAVAILABLE`、`REQUEST_SITE_SETTINGS_MISSING`；非 ok 时先打印结果再以该码非零退出（同 expiry 模式）。
- 评审修正：`base_url` 必须 `https://`（否则 `REQUEST_SITE_URL_INVALID`，令牌不发出）；拉取不跟随重定向（3xx → `REQUEST_SITE_HTTP_ERROR`）；pull 内任何异常都映射为 `REQUEST_SITE_*` 码，结果总会打印；执行器拒绝 >254 字邮箱。Worker 的 D1 错误返回 500 `APPLY_STORAGE_FAILED` / `ADMIN_STORAGE_FAILED`，Content-Length 超限在读取前拒绝。
- 执行器 settings `apply_site` 块需含 `base_url`、`admin_token_file`、`requests_dir`（指向 `.../requests/oci-hub`）。
- Worker 未配置 `ADMIN_TOKEN_SHA256` 或格式非 64 位十六进制时管理接口一律 401；未知路径 404 `NOT_FOUND`，方法不符 405 `METHOD_NOT_ALLOWED`。
- 沙箱内无法绑定本地端口：`test-hub-requests.py` 与 `test-wsctl.py` 的 ssh-agent 用例须在沙箱外运行。

- 2026-11-01 部署：BWS `executor/apply-site-admin-token`（用户授权写入）；D1 `apply-site`（a0825fea-10fa-49ed-91a1-a907ca9c0fa4）；Worker `apply-site`（源码 SHA-256 38cf5248…2ed8，绑定 DB 与 ADMIN_TOKEN_SHA256）；自定义域名 cc.willfan.me；执行器 settings 加 apply_site 与 BWS 映射（备份 settings.json.pre-apply-site）。提交 apply-site 09db4f5、employee-admin 37124d7、7c82435（Cloudflare 浏览器完整性检查拒绝 Python-urllib UA，error 1010，改发 `wsctl/1` UA）。
- 2026-11-01 实测：页面 200；无令牌 /admin/applications 401；curl 模拟手机提交 201（id 7497c58ac666），坏字段 400；执行器 `wsctl request` 落地 site-7497c58ac666.json，邮箱已小写。Chrome 扩展未连接，未做真机浏览器；国内网络实测按用户要求暂缓。测试申请待 3.3 dismiss。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 1 / low 6 / rejected 0
  - medium, patch — 拉取跟随 3xx 重定向会把 Bearer 令牌带到别的主机，且接受非 https：禁止重定向、要求 https。
  - low, patch — 拉取失败时错误文本或异常绕过结果输出：统一映射为 REQUEST_SITE_* 码。
  - low, patch — 执行器未复核邮箱长度：>254 拒绝。
  - low, patch — D1 失败返回平台 500 页：包装为 JSON 错误码。
  - low, patch — 读完整个 body 才检查大小：先看 Content-Length。
  - low, patch — 标准型卡片缺小程序的描述一行：补上。
  - low, patch — 字段错误提示未提手机号：改文案。

## Verification

**Commands:**
- `cd remotecc/apply-site && node --test test-worker.mjs` -- expected: 全部通过
- `cd remotecc/employee-admin && for t in test-hub-requests.py test-wsctl.py; do python3 $t || exit 1; done` -- expected: OK（沙箱外运行）
