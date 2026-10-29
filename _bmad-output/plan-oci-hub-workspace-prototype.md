---
title: 'OCI Hub 平行接入原型'
type: 'feature'
ticket: ''
created: '2026-10-29'
status: 'built'
baseline_revision: '06ef32fddea2c1a51e88e19d0438e03056369383'
route: 'full'
route_source: 'auto'
risk: 'high'
review: 'quick'
review_source: 'pinned'
lenses_ran: ['quick']
review_loop_iteration: 8
context:
  - 'docs/architecture/oci-employee-vpn-hub.md'
  - 'docs/planning/ga2-employee-traffic-quota.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

交付可部署的 OCI Hub 原型代码：管理员按 profile 开户，经 Portal 管理设备，员工沿用公开项目 bootstrap；每用户每月上传＋下载合计 5 GB。代码与隔离验证属于本轮，真实项目创建、安装/部署、用户发信和 Git 发布另按明确目标授权。

## Boundaries & Constraints

**Always:** existing 原请求哈希/入口/VM500 保持；oci-hub 独立资源、BWS 项目、凭据、状态及包。PVE 纯路由，OpenWrt 新聚合回程；实际 ACL 就绪才启动。Portal 唯一写 OCI 接口，VM Spoke 由 Ansible 管；所有状态写入经 OCI 执行器，多原因月恢复，允许轮询超用。

**Never:** 迁移现有用户、读取真实配置/令牌运行测试、整目录发布私有工程、自动升级 provider、改无关 Guacamole 文件。

**已确认决策（2026-10-29，1A/2A/3A）：** Portal 可保存仅新方案设备/VM Spoke 的 WireGuard 私钥副本，BWS 保持恢复权威；OCI 不保存员工 SSH 私钥、existing 凭据或 BWS 令牌。额度为 5,000,000,000 字节，Asia/Shanghai 每月一日重置，5 秒采样；长停采跨月不可拆分增量标待核对，仅暂停受影响账户，不清零或全算新月。保留完整跨层计划。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 行为 | 失败 |
| --- | --- | --- | --- |
| 双方案 | 同邮箱/设备 ID | 各自资源和交付；旧请求哈希不变 | 错 profile 拒绝 |
| 额度 | quota 后 admin_disabled | 次月仅清 quota，仍停用 | API 失败保留待重试动作 |
| 重跑 | 相同 action_id/计数代次 | 不重复开户/累计/赠额 | 账本损坏不按零恢复 |
| 边界 | ACL 未就绪 | 新 VM/OCI 接口不开放 | 现有业务保持 |

</frozen-after-approval>

## Code Map

I=本仓库；P=IaC 主 checkout 的 `remotecc/employee-admin` 独立私有 Git，运行数据位于相邻 `employee-data`；C=公开 `blue126/workspace-onboarding` 独立仓库，基线 `7acfc76ef5b795fa94533b04adfb1b7f3751a0a8`，不使用本机旧 checkout 的 HEAD。

- I:`terraform/modules/proxmox-vm/{main,variables}.tf` 有 protection、无 hook/首次停机输入；旧 `terraform/proxmox/employee-workspace.tf` 绑定 VM500。
- I:`ansible/roles/employee-workspace/tasks/{main,authorization}.yml` 依赖旧网关 derived_keys；`tests/employee-workspace/` 提供离线/mock/netns 模式。
- P:`admin-core.py` 规范化请求参与审批哈希；`bws-store.py` 拒绝未知记录；`onboard-host.py` 整目录同步不可用于 OCI 发布。
- Portal v2.3.1：Basic(username,API token)，`/api/v1`；整对象 GET/PUT，Disabled 删除内核 peer；Addresses 是 Hub /32，AllowedIPs 是客户端路由，RoutingTable=off。

## Tasks & Acceptance

**Execution:**
- [x] I:`terraform/modules/proxmox-vm/{main,variables}.tf`,`terraform/proxmox/oci-hub-workspace.tf`,`terraform/oci/oci-hub.tf`：扩展默认兼容的 hook/首次停止创建，独立工作区变量、inventory 和来源限定规则。
- [x] I:`ansible/roles/{oci-hub-pve,oci-hub,oci-hub-spoke}/tasks/main.yml`及各 defaults/templates，`ansible/playbooks/{deploy-oci-hub,deploy-oci-hub-workspace,configure-oci-hub-router}.yml`：Ansible 以 PVE API 管理 SDN（固定 bpg0.70无SDN），部署门控/ACL/Portal及源码白名单 artifact；复用静态 OCI inventory，旧 workspace role 增加缺省 existing 的授权分支。
- [x] P:`services/oci-hub/{portal,ledger,executor}.py`,`test-oci-hub.py`：stdlib 实现完整对象安全更新、标识核对、锁/多原因/幂等动作、采样重建与自然月账。Portal 标准 API 中的 WG 私钥字段仅在必需的受保护请求/数据库中使用；日志、动作记录和诊断不保存原始请求/响应。
- [x] P:`oci-hub-admin.py`,`hub-bws-store.py`,`pack-oci-hub.py`，以及 `onboard.sh`,`onboard-host.py`,`workspace-registry.py`,`generate-device-bundle.py`,`employee-online.py`,`deliver-temp.py`：新增显式后端、独立项目、执行器调用、关联/包/查询；旧核心解析不变。原验证阶段保存源码白名单摘要与差异；后按用户决定纳入独立私有 Git，本地 main 为 `ce10d14`。不复制或提交运行数据。
- [x] C:`schemas/bundle-manifest.schema.json`,`examples/bundle-manifest.example.json`,`scripts/{unix.sh,windows.ps1}`,`tests/test_bootstrap.py`及 AGENTS/README/接入文档：严格新版 native SSH/profile 分派；保留 v1。目标 employee@VM、WG51824/15秒、独立 alias/状态、目标 host/TLS pin；复用 verify-session。
- [x] I:`tests/oci-hub/{prepare-terraform.py,startup.tftest.hcl,test-offline.py,test-network.py,README.md}`及必要 CI 路径分类；P 新测试和白名单 artifact 检查；同步方案技术契约及部署 runbook。

**Acceptance Criteria:**
- Given 合成两用户多设备，when 轮询/重建/跨月/撤销并发，then 月账正确归集，只有目标 profile 被停用，admin/revoked 原因不被月恢复清除。
- Given 错项目/未知接口或 URL-body 标识不符，when 执行动作，then 写前拒绝且输出无秘密；相同请求重复不新增对象。
- Given 无生产凭据的 Terraform mock/网络 namespace，when 新 VM 创建或 ACL 检查失败，then stopped/onboot=false/protection/hook 符合预期且非法路由被拒，旧默认计划不变。
- Given v1 和新版同设备 ID 的合成包，when Unix/Windows check/setup/verify，then 连接参数与 profile 一致、不覆盖旧状态；未知版本/字段拒绝。
- Given 原型源码 artifact，when 构建/评审，then 仅包含白名单代码及校验值，无 settings/令牌/requests/runs/state/bundles；真实 VPN/桌面验收仍明确未执行。

## Implementation Notes — 初期记录（历史）

- C 已核对公开来源为 `https://github.com/blue126/workspace-onboarding`，独立任务 checkout `/private/tmp/oci-hub-client-20261029`，基线固定 `7acfc76ef5b795fa94533b04adfb1b7f3751a0a8`；原 checkout 未修改。
- 2026-10-29 用户明确授权：仅验证 Sandbox `iac-codex-oci-hub-build-direct-v130` 可安装当前 `.sandbox-kit/spec.yaml` 全部工具链和额外 `iproute2 nftables openssh-server wireguard-tools`。不授权宿主/员工 VM 安装、实际部署、生产凭据挂载或新增网络放行。已发起该独立 Sandbox 创建，尚在初始化。
- P 新实现先置于仅源码的临时白名单副本；未读取真实 settings、令牌、请求或运行状态。首轮合成 HTTP/SQLite 测试 7/7 通过。C 原有 32 项测试、增补 v2 合成测试 3/3 通过；Windows 实机与真实 VPN/桌面尚未执行。

### 首轮实施交接与验证（历史，2026-10-29）

代码任务已实现，等待父任务 diff/矩阵审计与正式 review；未标记真实 H-01～H-16 上线门槛通过。P 额外增加 `hub-onboard.py`、`hub-host.py`、`hub-bundle.py`、`profile-dispatch.py` 和 `test-hub-store-artifact.py`，用于将计划指定集成点串成独立检查点与源码白名单传输。真实 BWS 项目、模板、地址/证书和对应独立 runtime settings 仍须按部署输入预检，未创建或读取真实凭据。

- 最终日志目录：`/private/tmp/oci-hub-validation/`，索引 `summary.json`。原批次 29 个检查全部退出 0，随后仅对最终改动补跑相关私有测试/artifact 与 Spoke lint。
- Terraform：backend-free Proxmox init/validate 和 3 个 mock run 通过（含旧模块默认行为）；独立 OCI init/validate 和 3 个来源规则 mock run 通过。provider 固定 bpg 0.70.0 / OCI 8.3.0。
- Ansible：新角色及相关旧角色变更 lint 通过；3 个新 playbook 使用独立合成 inventory syntax-check 通过；CI shell task 与分类契约通过。nginx 配置由部署时 `nginx -t` 门控，未在真实桌面安装或加载。
- P：仅源码合成副本的 75 项已有相关测试、11 项 OCI Hub HTTP/SQLite/并发/检查点测试、3 项项目/artifact 隔离测试通过。未改旧核心请求解析；私有源码共 18 文件，首次 before hashes、累计差异和最终 after hashes 在 `/private/tmp/oci-hub-private-review/manifest.json`，已核对安装源码一致。
- C：Linux 原生 bootstrap 35 项（4 个 macOS 专用跳过）、verify-session 4 项通过；早先 macOS 原有 32 项及新 v2 3 项分别通过。Windows 仅增补现有 CI 可执行的 v1/v2 合成契约，未在本机执行 Windows/PowerShell；不把它写成 Windows 验收通过。
- namespace 实测：Hub 本人 SSH/HTTPS、跨用户/管理端口/input 拒绝与缺 ACL 拒启；PVE bridge/纯路由保留私有源、伪造源/受保护 OCI 服务/IPv6 拒绝及移除规则后的正对照通过。VLAN 子接口创建被 Sandbox 内核拒绝（`Error: Unknown device type`），明确未执行该场景；没有安装内核模块或扩大网络权限。
- 最终仅源码 artifact：`/private/tmp/oci-hub-source-final.tar.gz`，SHA256 `fc40578eb49efa2de3c5a78ba6127c8f4c6d9e6cf1be01b4a2b93347ed14f0cd`。只含 3 个服务源码与 SHA256 清单，无 settings/令牌/requests/runs/state/bundles。
- 公开独立 checkout：`/private/tmp/oci-hub-client-20261029`，分支 `oci-hub-workspace-prototype`；本 IaC worktree 保持原任务位置。未提交、推送、创建 PR、部署、发包或发信。

## Plan Change Log

### Review 1 修正范围（2026-10-29）

Q2、Q3、Q4 暴露了转发就绪和计数代次生命周期的计划缺口：部署入口需明确启用并验证 IPv4 转发及实际路由；恢复和受管重建需建立可验证的新计数基线，无法确认的间隔进入待核对状态。相关测试须使用与部署一致的入口，覆盖月初恢复和未观察到的重建。其他审核问题一起修复。冻结的用户意图不变；保留既有方案、凭据隔离和已通过验证证据。

用户明确选择保留已有实现并增量修复，覆盖本轮 bad_plan 回退步骤；修复后重新执行相关验证并审核。

### Review 2 修正范围（2026-10-29）

R2-1 补充未知代次跨月缺口的人工核对和解除逻辑，保留原始证据并防止其他未解决缺口被误清；R2-2 要求整批 Portal 对象在账本事务提交及外部写入前完成校验。保留 Review 1 的独立 profile、凭据隔离、单写者和已通过回归；继续用户授权的增量修复。

### Review 3 修正范围（2026-10-29）

R3-1 对可见重建前的未知尾量执行受影响用户核对门控；R3-2 校验设备及工作区归属同一用户；R3-3 在写入前只读预检 Portal 已有对象冲突，并保留写时复核和安全重试。保留前两轮的账本、隔离和测试结果，按用户授权增量修复。

### Review 4 修正范围（2026-10-29）

R4-1 保留没有原因的手动停用；R4-2 为 Terraform apply 成功后的检查点窗口提供可验证、安全的恢复；R4-3 单个设备异常不能阻止对其他账号执行配额停用。保留之前的隔离、审计和回归证据，按用户授权在隔离副本增量修复。

### Review 5 修正范围（2026-10-29）

R5-1 交付与生成一致地检查设备、用户和工作区的有效状态及归属；R5-2 交付前要求可信的端到端验证证据，服务状态和配置检查不得冒充连接及隔离验收。保留之前修复与测试，继续在隔离副本实施。

## Review Triage Log

### Review 1 — quick（2026-10-29）

计数：high=5，medium=2，low=0，false=0，maybe-false=0。5 项来自 quick，2 项为宿主独立发现并合成复现。现有通过日志和矩阵审计不等同于这些运行路径已正确。

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| Q1 SDN 安装导入 | high | patch | pve-sdn.py 导入 boundary，但 role 安装为 oci-hub-boundary.py；已安装布局没有 boundary 模块，首次准备失败。修正部署/导入契约并补布局测试。 |
| Q2 转发就绪 | high | bad_plan | 两角色/门控均不设置或核验 IPv4 forwarding，netns 测试自行开启，干净网关会无法转发。RoutingTable=off 并不必然丢失 /24 地址的内核直连路由，不能把该部分泛化为必无路由；需核验固定接口地址/实际路由及 forwarding，并用部署相同入口准备测试网络。 |
| Q3 月恢复再暂停 | high | bad_plan | kernel 缺 peer 时重置 rx/tx/generation 但留下旧 stamp；合成 kernel 复现超额→新月恢复→首个100字节被标 accounting_review（reproduction.json）。须记录确认恢复的新代次时间基线。 |
| Q4 未观察的代次重建 | medium | bad_plan | 生产 sample 始终 counter_generations={}；新代次累计已超过旧值时无法凭数值下降检测，可能少计旧基线。增加受管重建和 boot/interface 代次证据，无法确认时记录缺口。 |
| Q5 VM Spoke 更新未生效 | high | patch | 模板写入后始终 state=started，无 notify/重载；新增设备 AllowedIPs 不进内核，旧允许地址/路由仍存。需仅配置改变时受管同步配置及路由，并验新增/删除设备。 |
| H1 新阻断原因未当次生效 | high | patch | reconcile 添加 expired/admin_disabled 后仍使用先前抓取的 row；合成复现账本已有 expired、实际应用 Portal 原因却为空（reproduction-expiry.json）。计算有效原因前重读更新后状态，避免短暂启用。 |
| H2 新包 schema 设备名 | medium | patch | v2 schema 仍强制 ed- 前缀，与用户已决定的无前缀设备名及客户端运行时校验不一致；合成 alice 示例被 jsonschema 拒绝。未发现运行时调用 schema，不将其误报为实际 bootstrap 失败。修正契约并验证无前缀示例。 |

分组保留 Q2、Q3、Q4 为三个独立根因，不因都在生命周期附近而合并。bad_plan 触发回路；低层 patch 随该回路一起修，不丢失。

拟修复范围保持冻结意图；KEEP：现有 profile 请求字节/哈希、独立 BWS/源码白名单、v1/v2 状态隔离及 native SSH、已通过 mock/netns/私有回归、scope 限制及不部署规则。当前全部代码及差异已保存，尚未回退或删除文件。精确回退目标在系统临时目录 `oci-hub-built-review-v2nl_fhb/rollback-targets.json`；用户已明确选择保留现有代码增量修复，覆盖原回退步骤；本轮未回退或删除文件。

### Review 1 增量修复交接

- Q1：按实际安装布局导入 boundary；新增安装文件名布局的导入与 SDN 调用回归。
- Q2：ACL 原子应用成功后才启用并核验 forwarding；持久化 sysctl；路由门控检查真实地址、直连路由与 route-get 接口；PVE hook/部署核验和 OCI 执行器启用前使用此门控。namespace 测试从 forwarding=0 出发，使用部署相同 apply 入口准备，额外证明关闭 forwarding 后就绪检查失败。
- Q3：确认缺失→恢复时提交带当前时间的零基线（包括旧计数为零）；超额→跨月→恢复→100 字节回归验证不误标 accounting_review、不重复计历史用量。
- Q4：生产采样不再发送空代次证据，记录 boot/ifindex/Portal invocation；增加持锁受管 rebuild 和原始未知连续性 gap。普通连续采样不误停；明确接口重建按新代次首累计计量；Portal 上下文变化/上下文缺失且新累计高于旧值时不虚假推断 reset 或连续，暂停待核对。单一写入口拒绝远端自报 counters。对于同接口内无任何可观察信号的外部重建，技术上仍不能检测，已在 runbook 明确风险及禁止绕过写入者的边界，不将其计作检测通过。
- Q5：Spoke 模板变化 notify handler 并在验证前 flush；实际 Ansible task/handler 图配合合成 systemctl，验证新增/删除设备更新内核/路由模型，无变化不重启。Sandbox 内核拒绝真实 WireGuard 接口创建（`Attribute failed policy validation`），该场景未冒称实网通过。
- H1：添加外部 expired/admin_disabled 后重读最新 identity，再算 effective reasons；两个当次停用回归通过。
- H2：仅修正 v2 schema 的无前缀设备 ID 契约，并用 jsonschema 验证 alice 与三个示例；v1 契约及原请求解析保持。

私有写回仅 `services/oci-hub/{ledger,executor}.py` 和 `test-oci-hub.py` 三个文件，写前校对原 after hashes、写后读回核验成功；审查差异及 before 快照为 `/private/tmp/oci-hub-review1-evidence/manifest.json`，未触碰其他私有文件。精确最终测试日志将在 `/private/tmp/oci-hub-review1-validation/` 交接，真实凭据/部署/Windows/VLAN 约束保持。

### Review 2 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R2-1 跨月缺口无法恢复 | high | bad_plan | 生产 counter_evidence 对超过 10 秒的采样先判 unknown，sample 优先保存 counter_continuity_unknown；resolve_gap 却只接收 cross_month_review。需保留不确定代次证据，支持安全核对及恢复。 |
| R2-2 非法注册提前提交 | high | bad_plan | execute 在 Portal 对象验证之前结束账本事务，错误对象会留下 identities、prepared action 与 generation；同 action ID 的修正请求因摘要冲突无法重试。需在提交及外部写入前完成可回滚的批次预验证。 |

沿用用户明确授权的保留实现并增量修复，两个独立根因修复后重新验证与审核。

### Review 3 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R3-1 重建尾量未触发核对 | high | bad_plan | reset 会记录 counter_rebuild_tail_unknown，但未设置 accounting_review，也未纳入人工缺口解决，无法保证遗漏量不被忽视。 |
| R3-2 工作区归属缺失校验 | high | bad_plan | register 只检查用户和工作区存在，未核对 workspace.user_id 等于 device.user_id，可能跨员工关联。 |
| R3-3 Portal 存量冲突迟发现 | high | bad_plan | Portal.ensure 在事务提交后逐项 GET/POST 检查冲突，后项冲突时已落本地状态且前项可能已写 Portal；需先完整只读校验，写入时仍处理竞态及可重试失败。 |

### Review 4 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R4-1 无原因停用被解除 | high | bad_plan | disabled 且 DisabledReason 为空时，空集合被视为受管原因，未登记管理员停用；账本原因为空时 reconcile 将启用 peer。 |
| R4-2 apply 检查点窗口 | high | bad_plan | Terraform apply 后先写 roster 再写 provisioned 标记；中断后旧 plan 可能 stale，或 roster 哈希已变导致无法继续。需要能核实实际状态的恢复，不盲目重放或扩大批准范围。 |
| R4-3 单个故障阻断其他用户配额 | high | bad_plan | reconcile 顺序处理并在第一处异常退出；前面的 peer 错误可让后续超额用户持续未停用。应隔离失败并继续处理其他 peer，最终报告错误。 |

### Review 5 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R5-1 交付未检查父级停用 | high | bad_plan | eligible 仅检查设备行；用户或工作区被暂停时现有 bundle 仍能通过交付检查，需检查关联父级与归属。 |
| R5-2 验证阶段缺端到端 | high | bad_plan | verified 仅运行 Ansible verify tag，而该 play 仅检查服务 active 与 sshd 配置语法；不能证明接入、身份、pin 与跨用户隔离，不得当完整验收允许交付。 |

### Review 6 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R6-1 交付包内容未绑定验收 | high | bad_plan | oci-hub-admin 的 deliver 仅从 ZIP 提取 manifest 和 known_hosts 进行验收匹配，deliver-temp.load_bound 依据包自带 checksum 建立交付身份；验收记录没有绑定完整 ZIP 或私钥材料。保留 manifest/pin 而替换密钥并重算自带校验和，可交付无法使用的包。需把验收证据绑定具体不可变 bundle 摘要，并在上传及通知前重新核对同一摘要。 |

第六次 bad_plan 循环已超过 bmad-build 上限 5；用户随后明确授权继续修复，覆盖本次循环上限，沿用保留代码增量修复。R5 副本及测试证据仍在临时目录，尚未写回真实私有工程；尚未提交、部署或交付。

### Review 7 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R7-1 existing 交付可绕过 OCI 门控 | high | bad_plan | deliver-temp.load_bound 的默认 existing 分支没有检查内层 manifest profile，可向其传入未验收 OCI 包并上传/发信。须从同一包快照检查 profile，错 profile 在写前拒绝。 |
| R7-2 开户审批未固定注册内容 | high | bad_plan | approval_payload 仅固定 allocation 内的 registration_request 路径，apply 之后重读且没有限定 register 与本次归属，替换为其他账户 reason 动作仍使用原审批。须计划时限定动作/归属并固定注册与bundle公共请求的内容快照及摘要，apply 在外部写前拒绝变化。 |

沿用用户授权的增量修复和超出循环限制后继续审核；不部署或交付。

### Review 8 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R8-1 PVE 拒绝管理配置连接 | high | bad_plan | PVE forward 对进入 vnet 的流量只接受已建立回包；Terraform 将物理IP设为Ansible地址，而开户在边界启用之后才连接，管理员首次TCP22会被drop。须显式限定批准管理来源及目标VM的SSH和精确回程，保留跨用户、其他端口、主动私网连接和反欺骗拒绝。 |

继续用户已授权的增量修复；用真实namespace管理TCP连接验证部署路径，不把自行放行的测试当作部署配置已就绪。

### Review 9 — quick（2026-10-29）

| ID | verdict | route | 证据与处理 |
| --- | --- | --- | --- |
| R9-1 损坏账本隔离循环提前退出 | high | patch | executor 账本初始化失败路径逐peer隔离未捕获单项错误；前项缺失/归属冲突/API失败时后续员工仍可接入且无法记账。逐项尝试并汇总失败，保留profile和接口约束。 |
| R9-2 Windows 实际profile根未检查链接 | high | patch | windows.ps1 检查原StateRoot后才追加oci-hub子目录；子目录为junction时可沿链接写私钥/ACL。保留原根检查并校验实际profile根，补Windows合成回归。 |

两项均在已证明的现有状态上做直接修正，无新增公开接口；按patch处理并复验，不回退代码。

两项已完成最小修复，经原reviewer只读复核确认无残留；相关回归通过。本轮审核确认的问题全部处理，无代码问题延期。

## Final Verification and Handoff

本节为最终结果，前述首轮交接及各轮修复记录为历史。用户授权保留代码增量修复，并在超出原审核次数限制后继续；冻结意图与首轮审核版本一致。

- 私有管理员工程已精确写回9个变化文件，19个相关源码的读回哈希均与审核版本一致。源码写前快照：`/private/tmp/oci-hub-final-install-before/`；写回收据：`/private/tmp/oci-hub-final-installed.json`。未复制真实settings、凭据、运行状态或设备包。
- 最终Sandbox回归：私有管理员65/65、existing交付12/12、项目/artifact隔离3/3；客户端38项通过（6项平台专用跳过）、会话验证4/4。已核对测试副本与安装源码哈希相同。
- IaC：offline 9/9、最新PVE角色lint和3个新playbook合成inventory语法检查通过；真实namespace管理TCP22及原有正反隔离测试通过。Terraform此前6个mock run与backend-free validate已通过，此后未修改Terraform。
- 最后两个review发现已获独立复核确认修正；最终差异：`/private/tmp/oci-hub-final-review/all.diff`。验证索引：`/private/tmp/oci-hub-final-verification.json`。
- 最终仅源码artifact：`/private/tmp/oci-hub-final-source.tar.gz`，SHA256 `a7a7c2eba74946c7b369ef7529761810838d99477eda4cfe0e601ad79e236780`，仅含三个服务源码与SHA256清单。
- 未执行Windows/macOS平台专用用例、VLAN内核探针，以及真实Portal/PVE/OCI/OpenWrt部署和员工VPN/桌面验收。缺真实端到端批准记录时，程序保留待验收状态并禁止交付。
- 交付位置：管理员源码已纳入独立私有仓库 main `ce10d14`；公开客户端 OCI Hub 兼容提交为 `1615014bf07074787b130e85569b03200cccc234`（本地提交，未发布）。本计划与 IaC Hub 原型按用户批准单独整理提交；真实部署和员工验收仍未执行。

## 当前源码与历史证据（2026-10-30）

管理员源码权威为主 checkout 的 `remotecc/employee-admin` 独立私有 Git；`employee-data` 只存运行资料且不进 Git。原路径是兼容链接，原“源码无 Git”与环境初始化记录仅描述当时阶段，不作为当前操作指引。后续维护复用已登记管理员入口，不重新同步旧快照覆盖私有 main。

历史验证段中的 `/private/tmp` 路径是当次留证，不是部署输入或其他机器上的文件位置。可复现的 IaC 检查以 `tests/oci-hub/README.md` 为准；私有源码测试在不含真实配置或凭据的合成副本运行。未执行的 Windows/macOS、VLAN 和真实网络/桌面验收继续如实保留。

## Design Notes

完整计划约 2300 tokens（估算，新增决策后略增），超过建议 1600；用户已选择保留，实施按任务与 Code Map 定位，不反复读取无关上下文。

BWS/地址/模板等真实值由显式部署输入和 preflight 校验；单元夹具使用合成值。新模板必须匹配经验证 OS/基线，不能暗用 VM502 或默认模板名。首版直连备用关闭。私有测试在源码白名单副本先生成合成 settings，再导入模块。多项目修改分别留证，提交/推送不包含在批准实现中。

## Verification

- 独立 Sandbox：Terraform `fmt/validate/test` 使用临时 backend-free root＋mock；Ansible lint/syntax 使用 `tests/ci/fixtures/ansible.cfg` 和独立合成 inventory；不启动部署流水线。
- P 合成副本：现有相关 unittest＋`test-oci-hub.py`；本地 HTTP fixture 验 Basic/整对象 PUT/401/500/重试，临时 SQLite 验月账。
- C：`python3 tests/test_bootstrap.py -v`；现有 Windows 合成 CI 覆盖新旧包；Linux 隔离 netns 验 routed input/forward 正负对照。
- 不自动安装缺失依赖或放宽 Sandbox 网络；环境限制如实报告，不能把 mock 通过算真实 PVE/WireGuard/KasmVNC 验收。
