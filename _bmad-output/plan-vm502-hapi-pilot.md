---
title: 'VM502 HAPI 单人试点'
type: feature
ticket: ''
created: '2026-10-29'
status: built
baseline_revision: '06ef32fddea2c1a51e88e19d0438e03056369383'
route: full
route_source: auto
risk: medium
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

## Submission Authorization — 2026-10-30

用户确认 RemoteCC 公开整理文件属于当前工作区后，批准三笔本地提交：通用登录助手修复、HAPI 单人试点、RemoteCC 忽略规则和文档。私有代码/运行数据不进入这些提交。未授权推送、创建 PR 或合并。临时查看入口改为显式 hapi_login_helper tag，默认部署不写该配置。

<frozen-after-approval reason="human-owned intent">

## Intent

在 VM502 试用 HAPI 浏览器本地输入，验证中国侧交互与远端 Claude 会话。批准后部署，真人验收。

## Boundaries & Constraints

- 单人、employee 用户；执行、认证、凭据留在 VM。当前 Claude 未登录，本人先用 workspace-login 登录再测复用。
- 拟用 hapi-test.willfan.me → Cloudflare Named Tunnel/HTTP2 → 127.0.0.1:3006；HAPI 令牌认证，无邮件验证码。域名占用则停止。
- 固定 v0.33.2 官方 Linux x64 baseline 包及发布校验值；systemd 托管 Hub/Runner，HOME=/home/employee。禁用公共 relay、通知、peer tools；默认审批模式。
- 不改 Terraform、员工网关、其他 VM 或 Claude 配置。软件安装、Tunnel/DNS 和令牌写入待明确部署授权；本轮仅计划。

## I/O & Edge-Case Matrix

| 输入/状态 | 输出/失败处理 |
|---|---|
| 无效令牌 | API 401/403，否则关闭入口 |
| 未认证/订阅不兼容 | 停止请求，本人 VM 登录；不换计费方式 |
| 关闭网页 | 任务继续，重开恢复；失败留证 |

</frozen-after-approval>

## Code Map

- terraform/proxmox/employee-workspace.tf：inventory employee-control；不修改。
- ansible/roles/employee-workspace/files/workspace-login.py：--check 不代表认证成功。
- ansible/roles/employee-access/templates/sshd-config.j2：禁止转发，不用员工 ssh -L。
- 实机 x86_64/Claude 2.1.304/Node 22.22.1，HAPI 未安装，内存/磁盘有余量。

## Tasks & Acceptance

**Execution:**
- [x] ansible/playbooks/deploy-employee-hapi.yml：仅 employee-control 的 Deploy/Verify。
- [x] ansible/roles/employee-hapi/tasks/main.yml：校验固定包、安装 HAPI/cloudflared、配置 loopback；BWS 提供试点令牌，0600/no_log。
- [x] 同角色 templates/employee-hapi-{hub,runner,tunnel}.service.j2：三个独立 unit；Runner 受监督前台运行。先管理通道验证，再建专用 Tunnel/DNS。
- [x] docs/guides/employee-hapi-pilot.md：固定检查命令、预期、真人步骤、回滚。

**Acceptance Criteria:**
- Given 中国浏览器，When 输入/退格/中文组词一分钟，Then 无丢字或重复，本人确认跟手；与提交响应延迟分开记录。
- Given 本人 VM 已登录，When HAPI 发起真实请求，Then 成功，进程/凭据/模型出站在 VM；远程模式含 Agent SDK，订阅复用需实测。
- Given 审批请求，When 五分钟后批准，Then 批准前不执行、批准后仅一次。
- Given 已批准的两分钟任务，When 关闭网页三分钟后重开，Then 完成标记和会话记录可恢复。
- Given 入口上线，When 测有效/无效令牌、重跑部署，Then 权限隔离通过且幂等；记录空闲/任务峰值 RSS。

## Implementation Notes

- 2026-10-29：用户“批准并继续”，开始实现；部署遵循用户原指示“计划确认后再部署”的批准范围，真人认证及体验验收由用户完成。


- 实机已部署 HAPI v0.33.2、cloudflared 2026.10.5；三个 unit active，Hub 仅 127.0.0.1:3006。公网/本机无效认证拒绝、有效 API、Runner、SSE、列表重载通过；Web Push 路由403。
- 专用 Tunnel `02bc199a-2138-4da2-9f39-dc40776de7a2`，DNS record `b0bfbad2bd46fc77fa9bc341a31f6d30`，入口 https://hapi-test.willfan.me；Cloudflare 状态 healthy。未启用 Argo。
- 私有 bws-store.py 增加两条精确 HAPI Secret 白名单、设备解析排除及 runtime Vault 合成；15 项回归通过，原设备凭据 fingerprint 未改变。未安装 SDK。
- 私有目录整目录挂载期间兼容补丁曾恢复成旧版；重建本任务 Sandbox，改为 /tmp 中少量文件副本后，宿主兼容代码保持。未使用其他任务 Sandbox。
- 语法/production lint/文档检查通过。最终重跑：ok=30 changed=0 failed=0。中国 Linux HTTP 三次200，首字节2.030–2.499秒；这不是本地输入或模型响应延迟。
- Cloudflare 1010 曾拦截 Python 默认 UA；显式测试客户端 UA 后公网验证通过，拒绝断言未放宽。服务 cgroup 当前约288 MiB，真实任务峰值待采样。
- 工作流断点仍在 step-03 Matrix Test Audit：无效令牌行通过；HAPI 实际无登录拒绝/订阅复用与关闭网页任务恢复需真人会话补证，未进入最终 review/commit。VM502 Claude 当前未登录；四项真人验收未完成，不能标 built/done。


- 2026-10-29 用户追加修复：更新 VM502 登录助手输出的旧 WireGuard 浏览器地址；隔离 Claude CLI 原始授权 URL，避免被本机浏览器误打开。仅在 VM502 应用，旧流程默认入口兼容其他员工。
- 修复任务：`ansible/roles/employee-workspace/files/workspace-login.py` 将 auth login 的 stdout/stderr 留在权限0600的本次私有运行目录，不在终端转发原始链接/查询串；仅显示可用 VM 查看入口及成功/失败/验证码操作提示，保留交互输入、取消、超时、VM opener 和已登录短路。
- `workspace-browser.py` 根据配置输出正确的访问说明；`employee-hapi` role 定向部署两份助手，保留 VM bind_address，只将 VM502 viewer_url 设为当前管理员临时入口 http://127.0.0.1:16081/vnc.html#autoconnect=1&resize=scale&reconnect=0，明确它依赖当前管理员电脑 SSH 通道，不是员工公网登录入口。不得以此为其他员工永久写 localhost。
- `tests/employee-workspace/test-login.py` 用真实 tmux/PTY + 合成 CLI 验证 stdout/stderr 中原始 OAuth URL 均不出现在用户输出、VM opener 仍收到原链接、取消/失败不泄漏，原有场景继续通过。更新 HAPI guide。
- 热修复部署只复制助手和修改 viewer 配置，使用专用 tag；不重启 HAPI/Runner/个人浏览器，不自动取消当前人类授权会话。已启动的旧助手须用户退出重跑才生效。

- 登录助手热修复已仅部署 VM502；11 项真实 tmux/PTY 合成回归通过（原始 OAuth stdout/stderr 不外泄、日志0600、VM opener 原URL、手工码、取消/失败、两种查看说明）。production lint 20 files/0 failure；部署助手 SHA256 与源码一致，HAPI/Runner/browser MainPID 前后均为30156/30171/39220，未重启个人会话。当前旧进程仍需用户退出重跑以加载新助手。


## User Acceptance — 2026-10-29

用户明确确认：“我感觉效果不错，可以认为验收成功。”本次 VM502 HAPI 单人试点的整体用户验收通过。只记录用户实际给出的整体体验结论；没有逐项计时记录的五分钟审批、三分钟关页恢复及任务峰值，不伪填为已测量通过，也不撤销用户的验收决定。

已观察到本人登录后真实 Claude Opus5.5 回复。该轮原始 result.modelUsage 上报 contextWindow=1000000；界面200k来自 HAPI v0.33.2 converter的首轮估计（assistant usage.context_window=200000），非该轮实际模型窗口。未改第三方二进制。范围保持 VM502；用户已明确本会话不处理 Mosh。

代码审查、Git 提交/推送状态独立于上述用户验收。尚未获得本地提交、推送或PR授权。


- 用户批准正式管理员脚本恢复与临时副本清理后，完整检查发现正式代码原已通过 AUXILIARY_KEYS/PREFIXES 排除 HAPI 服务记录；“完全不认识 HAPI 记录、会阻断开户”的先前推断不准确。实际缺失是 HAPI 专用 runtime Vault 合成。现已在正式 bws-store.py 补充 compose-vault --include-hapi；默认开户不读取/注入 HAPI 令牌，保留既有兼容及其他任务修改。
- 正式私有代码20项回归通过；真实只读 BWS 验证及 HAPI Vault合成通过，输出加密且0600，员工密钥指纹未改变。验证记录及前后源码保存在私有 archive/hapi-bws-formal-20261029-bdb23419；已清理本次旧BWS助手副本、一次性补丁及验证副本，Sandbox恢复停止状态。未删除正式BWS记录、访问令牌交付文件、VM服务或个人登录态。并行README的项目级技能说明已保留。

## Plan Change Log

## Review Triage Log

### 2026-10-29 Quick review

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| verify.yml 多 unit 的 is-active 可漏检 Runner | medium | patch | systemctl 对多个 unit 为任一个 active 即成功；当前任务不检查每行，API 的机器列表不能保证进程此刻存活。改为逐 unit 检查。 |
| verify.yml loopback 断言在 fail-closed block 外 | medium | patch | 监听地址断言失败会在到达后续 rescue 前退出，Tunnel 维持运行；将已有服务/监听检查纳入同一关闭入口保护。 |


### Review resolution

两项 medium/patch 均已修复：逐个检查 Hub/Runner，服务与 loopback 断言纳入 fail-closed block。单文件 production lint、隔离正常/Hub停止/Runner停止/公网监听四种场景通过；实机 --tags verify 为 ok=11 changed=0 failed=0。无未解决的本次代码发现，未新增延期事项。用户整体接受的单人试点已 built；本地提交仍待 AGENTS.md 要求的独立授权。

## Design Notes

中风险：新增远程执行入口。真人负责体感、登录和审批；Agent 负责协议/状态证据。Cloudflare 不保证降低 RTT；中国 Linux 192.168.8.1 只测 HTTP。

> 🧠 **From Hindsight memory (员工本地 IDE 连接本人 VM 与本地交互试点)** — HAPI 四项行为尚待验收；与本轮目标交叉核对。

来源：[安装](https://hapi.run/docs/guide/installation)、[部署](https://hapi.run/docs/guide/deployment)、[集成](https://hapi.run/docs/guide/agents)、[版本](https://github.com/tiann/hapi/releases/tag/v0.33.2)。

## Verification

任务 Sandbox：iac-codex-vm502-hapi-pilot-direct-v130。
- ansible-playbook playbooks/deploy-employee-hapi.yml --syntax-check；生产 ansible-lint：通过。
- --tags verify：三个 unit active、3006 仅 loopback、认证/SSE/会话恢复通过。
- 回滚先关专用入口，再停 unit、撤销试点令牌并移除专属资源；保留报告、本人 .claude/工作文件，核对 SSH/workspace-login 正常。
