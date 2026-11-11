---
title: 'GA2 网站放行：员工登录后放行当前公网 IP'
type: 'feature'
ticket: ''
created: '2026-11-06'
status: 'in-review'
baseline_revision: 'd648769efb205388acab0a9054005557b1c4526e'
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

**Problem:** GA2 的 UDP 入口对全网开放，未认证流量也会计费。GA2 只懂来源 IP，无法验证 WireGuard。

**Approach:** 员工登录网站放行当前公网 IPv4，租约 7 天；执行器每分钟把有效租约同步成 GA2 ACL 的 `/32` 规则。本次只建机制，不删除现有全网放行规则。

## Boundaries & Constraints

**Always:**
- 只增删描述正好是 `ga2-lease` 的规则，其他规则一律不碰。
- 网站或腾讯 API 出错时不删规则，下一轮重试。
- 腾讯凭据只放执行器，Worker 不持有。
- 每人最多 2 个 IP，新 IP 挤掉最久没放行或续期的（按 `expires_at`）；重复放行同一 IP 只续期。
- 只有状态副本里 `ga2:true` 且状态为 `ACTIVE`/`NO_EXPIRY` 的员工能放行，也只有他们的租约进入同步。
- IP 明文只存在 `ga2_leases`，这是对“不存 IP 明文”规则的有意例外，租约到期即删。

- 用户 2026-11-07 决定：连接状态改成实时查询。员工打开页面时，Worker 经 Hub 只读接口读 `wireguard_peer_up`；页面开着时每 15 秒刷新一次。状态读取失败只影响这一行显示，不影响页面、放行和 ACL 同步。
- Hub 只读接口只暴露 Portal 的 `/metrics`，用独立令牌保护；Worker 只持有这个只读令牌。

**Never:**
- 不删 `0.0.0.0/0` 规则，不做阈值关停、敲门脚本或流量统计。
- 不把租约到期当成撤销：实测删规则后已有 UDP 流至少 52 秒不断。
- 不装新依赖；TC3 签名只用 Python 标准库。
- `ga2-sync` 和 Worker 都不使用 Portal 管理员令牌，`ga2-sync` 不访问 Portal。执行器的其他流程仍能经 BWS 读到这个令牌。
- 公开仓库不写员工信息或真实 IP。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 放行 | 已登录、有资格、IPv4 | 写入租约，页面显示已放行和到期时间 | 无 |
| 无资格 | 未登录，或无 `ga2`，或状态不符 | 拒绝，不写入 | 401/403 |
| IPv6 | `cf-connecting-ip` 为 IPv6 | 拒绝，提示需要 IPv4 | 400 |
| 第 3 个 IP | 已有 2 个 | 删除最久没放行或续期的，写入新的 | 无 |
| 网络变化 | 当前 IP 不在租约内 | 页面显示“当前网络尚未发起连接。” | 无 |
| 非中国来源 | `request.cf.country` 不是 CN | 仍可放行，提示可能开着代理 | 无 |
| 同步新增/删除 | 租约与现有规则不同 | 只增删差异 | 单条失败时退出非零，下轮重试 |
| 页面打开 | 有资格的员工打开 `/me` | 页面不等 Hub，先显示“正在检查连接状态”，随后更新 | 无 |
| 已连上 | 这位员工在 `wg-users` 上有设备 `wireguard_peer_up` 为 1，有无租约都算 | 页面显示“网络已连接”；当前网络没有租约时隐藏“当前网络尚未发起连接。” | 无 |
| 等待连接 | 有租约，这位员工没有在线设备 | 页面显示“正在等待连接” | 无 |
| 未连接 | 没有租约，也没有在线设备 | 不显示连接状态行，只显示“当前网络尚未发起连接。” | 无 |
| 状态读取失败 | Hub 超时、非 200、指标里没有任何 `wg-users` 行、未配置，或副本没有 `ga2_user` | 页面显示“暂时无法确认连接状态” | 200，`connection: unknown` |
| 状态接口权限 | 未登录，或无资格 | 不访问 Hub，页面保持原样 | 401/403 |
| 页面隐藏 | 标签页不可见 | 暂停刷新，回到页面立刻刷新一次 | 无 |
| 超上限 | 租约 IP 超过 50 个 | 照常删除已结束的规则，不新增 | `GA2_SYNC_TOO_MANY` |
| 锁被占用 | 其他 wsctl 正在运行 | 等几秒后跳过，退出 0 | 记录 skipped |

</frozen-after-approval>

## Code Map

私有代码在本 worktree 的 `remotecc/`（从主检出私有仓库克隆，分支 `feat/ga2-site-admission`），不动主检出。

- `apply-site/worker.js` -- 路由 `handle`:1934；`authorized`:1140；`readSession`:1375；`statusCopy`:1390；`statusPage`:1802、`bundleCard`:1787；按钮范例 `sessionDownload`:1665；39-458 行是生成内容，不手改
- `apply-site/design/text.json` -- 文案来源，改后运行 `node sync-design.mjs`
- `apply-site/migrations/` -- 下一个是 0015；已应用文件不可改；迁移先于 Worker 部署
- `apply-site/test-worker.mjs` -- `fakeD1`:12 精确匹配 SQL；范例 /me:1658、/admin:981
- `wsctl/wsctl` -- 动作列表:25、写动作列表:47、锁:57-60
- `wsctl/oci-hub-admin.py` -- 分支范例:440、安全错误码正则:597
- `wsctl/hub-requests.py` -- 复用 `site_settings`:71、`call`:38
- `wsctl/hub-publish.py` -- `build` 的状态行
- `wsctl/test-hub-publish.py` -- 本地假站点测试范例
- `ansible/roles/semaphore/files/semaphore-bootstrap.py`（公开 IaC）-- `TEMPLATES`、`SCHEDULES`
- `apply-site/worker.js` 现状：`ga2Status`、`ga2Connection`、`ga2PushStatus`、`ga2Card`、`mePage`、`handle` 里的 `/admin/ga2/status`；外部调用范例和测试注入看 `SITEVERIFY`（`env.SITEVERIFY || fetch`、`AbortSignal.timeout(Number(env.SITEVERIFY_TIMEOUT_MS) || ...)`）；`json()` 已带 `no-store`
- `wsctl/hub-ga2.py` 现状：`portal`、`moment`、`device_keys`、`handshakes`、`push_status`、`run` 里的 `status_error`、`read_leases` 返回的 `emails`
- `ansible/roles/caddy/templates/reverse-proxy.Caddyfile.j2`（公开 IaC）-- 只有一条 `reverse_proxy`，没有可选扩展点
- `ansible/playbooks/configure-oci-hub-portal-public.yml`（公开 IaC）-- 用 `lineinfile` 改 `portal.yaml` 以保留凭据，`Restart scoped Portal after URL change` 是重启 handler；同一 playbook 有 verify play
- `ansible/roles/oci-hub/templates/portal.yaml.j2`、`ansible/roles/oci-hub/defaults/main.yml`、`ansible/inventory/host_vars/oracle-cloud-ubuntu2404.yml`（公开 IaC）

Hub 上已核实的事实（2026-11-07，只读）：
- 指标行形如 `wireguard_peer_up{addresses="...",id="...",interface="wg-users",name="...",user="oci-hub:user:<员工ID>"} 1`。`wg-workspaces` 的 VM peer 带同样的 `user`，所以必须同时过滤 `interface="wg-users"`。`name` 是自由文本，可能含 `}` 和转义引号，解析不能用 `[^}]*`。
- 全部指标约 12 KB。`8787` 上只有 `/metrics` 返回内容，其他路径 404。
- Caddy 是 v2.11.1。下面的路由已用 `caddy adapt` 校验：`handle` 排在顶层 `reverse_proxy` 之前，`basic_auth` 自带 `hash_cache`。
- Portal 判定规则：`IsConnected = IsPingable || 握手不早于 ReKeyTimeoutInterval`，默认 180 秒（v2.3.1 源码）。`statistics.data_collection_interval` 默认 1 分钟。

## Tasks & Acceptance

**Execution:**
已完成，代码已在工作区（未提交），不要重做：
- [x] `apply-site/migrations/0015-ga2-leases.sql`、`schema.sql` -- 建 `ga2_leases(email, ip, expires_at, created_at)`，主键 `(email, ip)`
- [x] `apply-site/worker.js`、`design/text.json` -- 状态副本接受 `ga2` 布尔值；加 `POST /api/ga2/allow`（校验 Origin）、`/me` 卡片和 `GET /admin/ga2/leases`
- [x] `apply-site/test-worker.mjs` -- 覆盖放行和租约场景
- [x] `wsctl/hub-publish.py`、`wsctl/test-hub-publish.py` -- 按 `settings.ga2.employees` 输出 `ga2:true`
- [x] `wsctl/hub-ga2.py`、`wsctl/test-hub-ga2.py` -- 同步：读租约，TC3 签名调用 ACL 接口，增删差异，写审计
- [x] `wsctl/wsctl`、`wsctl/oci-hub-admin.py` -- 注册写动作 `ga2-sync`，用短锁等待
- [x] `ansible/roles/semaphore/files/semaphore-bootstrap.py`、`templates/config.json.j2` -- `wsctl ga2-sync` 模板、每分钟计划、任务历史上限

本次要做（连接状态从每分钟推送改成实时查询）。私有路径相对 `remotecc/`：

- [x] `apply-site/migrations/0016-ga2-vpn-status.sql`、`schema.sql` -- 删除这个迁移文件（未提交、未部署）和 `ga2_vpn_status` 表
- [x] `apply-site/worker.js` 删除 -- `GA2_HANDSHAKE_MS`、`GA2_STATUS_STALE_MS`、`ga2PushStatus`、`/admin/ga2/status` 路由、`ga2Connection`，以及 `ga2Leases` 响应里的 `emails`
- [x] `apply-site/worker.js` 状态副本 -- 接受可选字符串 `ga2_user`，必须匹配 `^oci-hub:user:[A-Za-z0-9._-]{1,64}$`，否则整行无效；只在 `ga2` 为 true 时保留
- [x] `apply-site/worker.js` 新接口 `GET /api/ga2/status` -- 无会话 401 `SESSION_REQUIRED`；无资格 403 `GA2_NOT_ELIGIBLE`，这两种都不访问 Hub。否则返回 `{ connection }`，值为 `connected`、`waiting`、`unknown` 或 `null`，判定按矩阵
- [x] `apply-site/worker.js` 读 Hub -- `(env.GA2_METRICS_FETCH || fetch)(env.GA2_METRICS_URL, { headers: { authorization: 'Basic ' + btoa('ga2-site:' + env.GA2_METRICS_TOKEN) }, signal: AbortSignal.timeout(Number(env.GA2_METRICS_TIMEOUT_MS) || 3000) })`。URL 或令牌未配置、请求失败、非 200 都算 `unknown`，不抛错
- [x] `apply-site/worker.js` 解析 -- 逐行处理 `wireguard_peer_up{`，取最后一个 `}` 分开标签和值，标签用能处理 `\"` 的正则解析。只看 `interface="wg-users"`。没有任何 `wg-users` 行算 `unknown`；`user` 等于副本 `ga2_user` 且值为 1 的行存在算在线
- [x] `apply-site/worker.js` `/me` -- 渲染不再读 Hub。`ga2Status` 只返回 `expires_at`、`proxy`。卡片放 `id="ga2-connection"` 的状态行，初始文案“正在检查连接状态”；“当前网络尚未发起连接。”那一行加 `id="ga2-off"`，只在没有租约时渲染
- [x] `apply-site/worker.js` 页面脚本 -- 有状态行时立刻请求 `/api/ga2/status`，之后每 15 秒一次，`document.hidden` 时跳过，`visibilitychange` 回到可见时立刻刷新。`connection` 为 null 时状态行清空；为 `connected` 时隐藏 `ga2-off`，否则显示。401/403 不改页面；网络失败显示“暂时无法确认连接状态”
- [x] `apply-site/design/text.json` -- `status.ga2.connection` 加 `checking`：“正在检查连接状态”，然后运行 `node sync-design.mjs`
- [x] `apply-site/test-worker.mjs` -- 删除 `/admin/ga2/status`、`ga2_vpn_status` 和握手相关测试，`fakeD1` 同步清理；覆盖矩阵新增的每一行，包括 `name` 含 `}`、VM peer 同 `user` 但只在 `wg-workspaces` 在线时不算连上、别人的设备在线不算、Hub 超时
- [x] `wsctl/hub-publish.py`、`wsctl/test-hub-publish.py` -- `ga2:true` 的行同时输出 `ga2_user: 'oci-hub:user:' + 员工 ID`，更新模块文档串里的说明
- [x] `wsctl/hub-ga2.py`、`wsctl/test-hub-ga2.py` -- 删除 `portal`、`moment`、`device_keys`、`handshakes`、`push_status`、`status_error` 和相关测试；`read_leases` 不再要求 `emails`。`ga2-sync` 只读租约、同步 ACL、写审计，不访问 Portal，也不读 `public_metadata_file`。其余行为不变，删掉因此没人用的 import 和常量
- [x] `wsctl/README.md`、`wsctl/docs/admin-handbook.md` -- 删除 `settings.ga2.portal`、`executor/wg-portal-api-token`、`status_error`、`0016`、`PUT /admin/ga2/status`。写清实时查询链路、断开最多约 3 分钟才变、连上约 30 秒内显示。上线步骤写：生成随机令牌，`caddy hash-password --algorithm bcrypt --bcrypt-cost 10` 得到哈希放 IaC Vault 的 `vault_oci_hub_portal_metrics_password_hash`，跑 `configure-oci-hub-portal-public.yml`（会重启 Portal），明文令牌放 Worker Secret `GA2_METRICS_TOKEN`，普通变量 `GA2_METRICS_URL=https://wgportal.willfan.me/ga2-metrics`，再部署站点；同时写轮换方法
- [x] `apply-site/docs/ARCHITECTURE.md`、`apply-site/docs/content/usage/vpn-connection.md`、`apply-site/wrangler.toml` 顶部注释 -- 更新状态来源说明和两个新 Worker 配置项。员工文档只说明现象：连上后约半分钟内显示，断开后最多几分钟才变，多台设备时任一台在线都算
- [x] `ansible/roles/caddy/templates/reverse-proxy.Caddyfile.j2`（公开 IaC）-- 加可选变量 `caddy_reverse_proxy_pre_directives`，定义时缩进放在 `reverse_proxy` 行之前；未定义时渲染结果和现在完全一样
- [x] `ansible/playbooks/configure-oci-hub-portal-public.yml`（公开 IaC）-- 断言 `oci_hub_portal_metrics_password_hash` 非空；用 `lineinfile` 在 `^statistics:` 后写 `  data_collection_interval: {{ oci_hub_portal_data_collection_interval }}`，通知现有重启 handler；给 Portal 站点传下面的路由。verify play 加两项：`8787` 仍只监听 loopback；未带令牌请求 `https://wgportal.willfan.me/ga2-metrics` 返回 401
- [x] `ansible/roles/oci-hub/defaults/main.yml`、`templates/portal.yaml.j2`（公开 IaC）-- 默认 `oci_hub_portal_data_collection_interval: 15s`，模板的 `statistics` 段写入同一项
- [x] `ansible/inventory/host_vars/oracle-cloud-ubuntu2404.yml`（公开 IaC）-- `oci_hub_portal_metrics_password_hash: "{{ vault_oci_hub_portal_metrics_password_hash }}"`。不改 Vault 文件
- [x] `docs/architecture/oci-employee-vpn-hub.md`（公开 IaC）-- 删掉 `remotecc-ops` 持有 Portal 令牌的例外，改写成：网站经 `/ga2-metrics` 只读取指标，令牌不能写，泄露时暴露员工 ID、VPN 地址、设备名和在线时间，不含私钥；`remotecc-ops` 不再访问 Portal

Caddy 路由（`caddy_reverse_proxy_pre_directives` 的内容）：

```caddyfile
handle /ga2-metrics {
    basic_auth {
        ga2-site {{ oci_hub_portal_metrics_password_hash }}
    }
    rewrite * /metrics
    reverse_proxy 127.0.0.1:8787
}
```

**Acceptance Criteria:**
- Given 已有非租约规则，when 同步运行，then 这些规则完全不变。
- Given 租约过期，when 下次同步，then 对应规则被删除，D1 里没有这个 IP。
- Given 配置里没有 `ga2` 段，when 运行 `ga2-sync`，then 明确报错退出，其他 wsctl 动作不受影响。

## Implementation Notes

私有仓库基线：`086ad47d7f0c7ebf3b08924befac5c94e2b4a15d`。

## Plan Change Log

- 2026-11-06：用户追加连接状态（按钮方案的页面反馈），放进 `ga2-sync`。握手按设备计算，所以“VPN 已连上”表示这位员工的某台设备已连上，不一定是当前打开页面的设备。
- 2026-11-06：用户决定握手状态改走 WG Portal REST API。Portal 配了 `api_admin_only: true`，令牌有写权限，用户接受这个权限范围；代码只发 GET。

- 2026-11-06（评审后）：评审发现 `GET /peer/by-interface/wg-users` 返回的 peer 对象含 `PrivateKey`。改为从 `query` 取设备公钥，所以每分钟多一次到 OCI 的 SSH；握手时间仍走 Portal API。避免的问题：全部设备私钥每分钟传到执行器。KEEP：只发 GET，VM peer 不算入。
- 2026-11-06（评审后）：同步改为先删后增，审计去掉 IP 哈希。

- 2026-11-06（用户追问后）：设备公钥其实已在执行器本地，改读 `public_metadata_file`，去掉每分钟一次的 SSH。

- 2026-11-06（用户决定）：有资格人数为 0 就是没人有资格，删除 `GA2_SYNC_EMPTY_COPY` 和矩阵的“名单异常”行。租约还在 D1，名单恢复后下一轮规则自动加回。
- 2026-11-06（用户决定）：Semaphore 设 `max_tasks_per_template` 为 5000。
- 2026-11-07（用户决定，重新协商了冻结区）：连接状态从“`ga2-sync` 每分钟推送握手”改成“Worker 实时读 Hub 只读接口”。原因：登录后要马上看到状态，一分钟延迟影响体验；Portal 本身有 `wireguard_peer_up`，不用自己判断握手时间。避免的问题：执行器持有能读私钥的 Portal 管理员令牌、`ga2_vpn_status` 这张中转表、推送时刻和页面时刻的比较。KEEP：ACL 同步全部行为不变；页面不被 Hub 拖慢；状态失败不影响放行。
- 2026-11-11（本地功能测试后，用户决定，重新协商了冻结区）：第 3 个 IP 挤掉的从“最早创建的”改成“最久没放行或续期的”（按 `expires_at` 排序，不改表结构）。原因：续期不改创建时间，员工天天续期的家里 IP 会被很少用的旧 IP 留下而挤掉。页面去掉“VPN”字样：标题“网络连接”，有租约“连接已发起，北京时间 … 到期。”，无租约“当前网络尚未发起连接。”，在线“网络已连接”。按钮仍是“连接当前网络”。KEEP：两个 IP 上限、只续期、文档地址不变。
- 2026-11-11（codebuddy 评审后，用户决定，重新协商了冻结区）：租约 IP 超过 50 个时照常删除已结束的规则，只跳过新增，原来是整轮不改。原因：异常时过期规则会一直放行。规则归属从“描述以 `ga2-lease` 开头”改成“描述正好是 `ga2-lease`”，避免误删 `ga2-lease-xxx` 这样的手工规则。`/admin/ga2/leases` 的注释写清楚：员工失去资格时规则下一轮就删，D1 里的记录留到到期。评审另报的代理出口、提前删规则属于既定设计；员工 ID 格式、`statistics:` 缺失两条不成立或只在理论上存在。
- 2026-11-11（用户决定）：`ga2-sync` 不再每分钟列出整个 BWS 项目（含全部设备私钥）。settings 的 `bws_materialize.actions` 列出动作需要的记录，这些记录带 BWS `id`，`wsctl-secrets.py` 逐条 `bws secret get`，并校验返回的 key。其他动作不变。代价：每分钟 3 次请求。
- 2026-11-11（rebase 到 main 时）：main 已删除 `configure-oci-hub-portal-public.yml`，Portal 公网配置并入 `oci-hub` role 和 `deploy-oci-hub.yml`。改动随之迁移：采集间隔由 role 默认值写进 `portal.yaml.j2`，不再用 `lineinfile`；`/ga2-metrics` 路由放进 role 的 Caddy 任务，Vault 没有哈希时不加路由（不再断言失败，dry run 不受阻）；两项 verify 移到 `deploy-oci-hub.yml`。下面任务列表和验证里提到的旧 playbook 是当时的记录。

## Review Triage Log

第 1 轮（quick），high 1、medium 3、low 2、待用户决定 2：

| 判定 | 去向 | 发现 | 证据与处理 |
|---|---|---|---|
| high | patch | `/peer/by-interface` 把设备私钥带到执行器 | Hub swagger 的 `models.Peer` 含 `PrivateKey`、`PresharedKey`；已改，测试断言只请求 `/metrics/by-user/` |
| medium | patch | 新增持续失败会挡住所有删除 | 原 `run` 先增后删，已改为先删后增并加测试 |
| medium | patch | 审计里无盐 IP 哈希和邮箱同行，可还原 | IPv4 空间可穷举，已删除全部 `ip_sha256` |
| medium | 待用户决定 | `eligible==0` 的合法清零也会报 `GA2_SYNC_EMPTY_COPY` | 冻结矩阵要求不删，手册写自动删除，两者冲突 |
| low | patch | 架构文档写“只读指标” | 令牌实际能读写 Portal 全部内容，已改文档 |
| low | patch | 手册没写 `bws_materialize` 的回退步骤 | `set_path` 对缺失的 `ga2` 会抛错，已补一行 |
| low | 待用户决定 | 连接状态按推送时刻判定，偏离矩阵字面 | 推送中断时最多 8 分钟误报已连上；按页面时刻比较估算有 9% 误报 |
| medium | 待用户决定 | 每分钟任务没有 Semaphore 历史上限 | `config.json.j2` 没配置；`max_tasks_per_template` 可用，但对所有模板生效 |

第 2 轮（quick，实时查询改动），medium 3、low 3：

| 判定 | 去向 | 发现 | 证据与处理 |
|---|---|---|---|
| medium | 待用户决定 | `ga2-sync` 走通用物化，每分钟把整个 BWS 项目读进内存，并加载 SSH 私钥 | `wsctl-secrets.py` 的 `bws secret list` 取回全部 `value`，`wsctl` 无差别加载 agent。机制已有，`enforce` 每 5 分钟也这样；本次把频率提到每分钟。收窄要新增配置，计划没定 |
| medium | patch | 架构文档和手册写 `remotecc-ops` 不持有 Portal 令牌 | 开户流程经 BWS 读 `OCI_HUB_PORTAL_ADMIN_V1`，这句话不成立。改成 `ga2-sync` 和 Worker 不使用 |
| medium | patch | 手册写到期或停用后下一轮删规则 | `ga2Leases` 只看状态副本，`hub-enforce.py` 不推送，定时 `publish-status` 每小时一次。写明最长约一小时 |
| low | patch | 部署文档没写新路由、采集间隔、Portal 重启和 Vault 前置 | `docs/deployment/oci-hub-native-provisioning.md` 把这个 playbook 列为日常维护入口 |
| low | patch | `ARCHITECTURE.md` 写“按设备计算” | 页面逻辑是任一设备在线就算，手册也写按员工算 |
| low | reject | `ga2Leases` 不走 `statusCopy`，判定来源不同 | 只在 `retire` 且推送失败时出现，规则最多多留到下一次推送；此时 WireGuard peer 已删。修复要给每分钟的读取加逐行查询 |

## Design Notes

“网络已连接”按员工计算，不按设备：员工有多台设备时，任一台在线都算，不一定是正在看页面的这台。连上后最慢约 30 秒显示（Portal 采集 15 秒，页面刷新 15 秒）；断开后要等握手超时，最多约 3 分钟。这个超时来自 Portal 的 `ReKeyTimeoutInterval`，不改。

状态行和租约是两件事：租约说的是当前网络能不能建立新连接，状态行说的是这位员工有没有设备在线。所以已连上时不显示“当前网络尚未发起连接。”，否则保留全网规则期间员工会看到自相矛盾的两句话。

租约过滤放在 `GET /admin/ga2/leases`：退役、到期、停用的员工不再出现在状态副本的有效状态里，下一次 `publish-status` 之后规则自动删除，不用改 `hub-retire.py`。`retire`、`renew` 会立即推送；自然到期和 `enforce` 造成的停用要等每小时第 15 分的定时推送，最长约一小时。退役员工的 IP 明文最多留到租约到期。

员工看到的是“连接”，不是“加速”：在这一步之前，他的 WireGuard 根本不通。按钮固定为“连接当前网络”，首次使用和断线重连用同一个按钮；可以连接时显示到期时间，按钮变成“延长 7 天”。提示写“换了网络或连接不上时，回到这里点一下，约 1 分钟后自动恢复”。不做关闭按钮。页面和员工文档不出现“VPN”字样。

## Verification

**Commands:**
- `cd remotecc/apply-site && node --test test-worker.mjs` -- expected: 全部通过
- `python3 remotecc/wsctl/test-hub-ga2.py && python3 remotecc/wsctl/test-hub-publish.py && python3 remotecc/wsctl/test-wsctl.py` -- expected: 全部通过
- `python3 -m py_compile ansible/roles/semaphore/files/semaphore-bootstrap.py` -- expected: 无输出
- `cd remotecc/apply-site && node sync-design.mjs --check` -- expected: 通过
- `python3 remotecc/wsctl/test-hub-site.py` -- expected: 全部通过
- `cd ansible && /Users/weierfu/Projects/IaC/.venv/bin/ansible-playbook playbooks/configure-oci-hub-portal-public.yml --syntax-check --vault-password-file /Users/weierfu/Projects/IaC/ansible/.vault_pass` -- expected: 通过。这个 worktree 没有 `.venv`，不要安装，只用这个已有环境
- `git grep -n "ga2_vpn_status\|handshake_at\|wg-portal-api-token"` 在 `remotecc/` 里 -- expected: 没有 GA2 相关结果（文件未跟踪时改用 `grep -rn`）

**Manual checks (if no CLI):**
- 上线不在本计划内，需单独授权：CAM 子账号、BWS 密钥、IaC Vault 哈希、Hub Caddy 和 Portal 配置、Worker Secret、设置、部署站点、Semaphore 同步。本次不访问 Hub，不改 Vault，不部署。
