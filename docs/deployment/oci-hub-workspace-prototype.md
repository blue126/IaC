# OCI Hub 原型部署与恢复契约

这是可审阅的原型代码与部署步骤；源码和合成验证已完成，真实项目创建、部署、员工验收及发信另按批准范围执行。现有入口、VM500、员工身份与原请求解析继续属于 `existing`。设计依据为 [OCI Hub 架构](../architecture/oci-employee-vpn-hub.md)；合成验证入口见 [tests/oci-hub](../../tests/oci-hub/README.md)。

## 配置及所有权

| 内容 | 唯一写入者 |
| --- | --- |
| 新 VM | `oci_hub_workspaces` + 通用 VM module，首次 `started=false`、`onboot=false`、`protection=true` |
| PVE SDN | `oci-hub-pve` 经 `pvesh`；固定 bpg 0.70 不升级、不创建 Terraform SDN 资源 |
| PVE/OCI ACL | `scripts/oci-hub/boundary.py` 的独立 `oci_hub` nft 表；事务替换且不清空其他规则 |
| OCI 两接口及 peer | 固定 WG Portal v2.3.1；不部署两接口的 wg-quick 配置 |
| VM Spoke | `oci-hub-spoke` 的 `wg-quick@wg-workspace` |
| 月账、原因、动作 | OCI 执行器 + SQLite；管理员本机只查询，不回写旧月账快照 |

必须显式核对未占用 VMID、VNet、物理 /30、overlay /32、MAC、模板名、baseline ID、bootstrap snippet、hook datastore/目录以及实际 PVE 节点。模板必须预装经验证 KasmVNC、nginx、`workspace-login` 和 `workspace-browser`；本轮不安装到真实 VM。独立 BWS 项目和机器账号须先创建并批准，机器账号只能访问该新项目。`hub-bws-store.py` 拒绝与 existing 同项目、跨项目授权和未知记录。实际项目 ID、令牌、地址、源清单与叶证书由受保护部署输入提供。

## 部署顺序

1. 在已批准任务 Sandbox 中预检 PVE SDN 全局锁 API、无无关 pending changes、实际 firewall 后端、SDN Apply 对共享网络的重载范围、OpenWrt 聚合回程与 WAN NAT。取得精确部署授权后才执行。
2. 运行 `configure-oci-hub-router.yml` 准备新边界、hook 和 SDN。`oci_hub_sdn_apply_authorized=true` 必须来自明确的 Apply 审阅；`oci_hub_pve_prepare_only=true` 时目标 `oci_hub_prepare_vmid` 仍 disabled。Simple Zone 固定 pve2，Subnet SNAT=0。PVE 保留聚合黑洞路由；OpenWrt 只写 `network.oci_hub` 回程条目，前提为已核验 WAN 转发/NAT。
3. Terraform 创建新 VM 保持停止。PVE 通过 live nft JSON 与配置摘要、VMID、net0 VNet/MAC、disabled 状态校验启动，规则缺失或代次不符拒绝；后续配置把该目标 disabled 改 false 后才经 `qm start` 触发 hook。已运行服务重载使用同一原子规则替换，停止 boundary 单元保留规则。
4. 通过 `deploy-oci-hub.yml` 部署固定校验值的 Portal 二进制及白名单源码 artifact。先加载/校验 ACL，再启动 Portal。明确忽略所有现有接口，禁用 import、自助/默认 peer、自动用户恢复与配置导出；API/界面仅监听 loopback。保护 Portal 数据库、配置、执行器配置与备份，OCI 不接收任一 BWS 令牌或员工 SSH 私钥。
5. 首次账本初始化必须显式 `oci_hub_new_ledger_authorized=true`。执行器另留 `.initialized` 标记；账本丢失/损坏不能重新初始化为零。timer 每 5 秒向同一执行器采样，只采 `wg-users`，不重复计工作区 peer。
6. `deploy-oci-hub-workspace.yml` 只限新 VM 与明确 PVE host；安装该 VM Spoke 配置与来自设备 /32 的 native SSH 公钥。nginx 仅监听该 VM overlay:8443，注入仅本 VM 的受限 Basic 后端凭据，验证 loopback:8444 KasmVNC 的 TLS；浏览器不接收后台凭据。前端只代理 GET/HEAD 静态资源与 WebSocket，显式拒绝 `/api` 和 `/api/`；非 owner 的受限后端凭据不提供管理 API。Host/Origin、原始后端不可外部监听、TLS SAN/host pin、路径/API、XFCE/Firefox 生命周期仍需实际验收。
7. 新对象初始禁用，通过 OCI 执行器登记 profile/代次/用户—设备—VM 映射并回读，再解除本次新建身份的初始原因。旧身份的 admin/revoked/quota 不因重跑解除。生成受保护的本地 v2 候选包，完成独立端到端验收后才允许交付；Temp.sh 上传和邮件分别需要明确交付范围及审批摘要。

## 管理员入口

规范入口位于 IaC 主 checkout 的 `remotecc/employee-admin/onboard.sh`，源码属于独立私有 Git。相邻 `remotecc/employee-data/` 保存实际配置、申请、检查点、设备包和回执，不进入任一源码仓库；旧 `~/Projects/employee-workspace-admin` 只保留兼容链接。临时 IaC worktree 不应复制或另建一份管理员运行数据。

`onboard.sh --profile existing ...` 保留原路径；缺省仍为 existing。`onboard.sh --profile oci-hub plan REQUEST.json` 接受含 `profile=oci-hub` 与 `recipient` 的独立请求，沿用邮箱派生 ID 规则。真实分配通过 `settings.oci_hub.onboarding[employee_id]` 显式提供：workspace Terraform 参数、device_id/recipient、runtime BWS record、public_vars、registration_request、bundle_request。不会猜用 VM502 或任意默认模板。

该配置另提供 `terraform_roster`、inventory、PVE/router 精确 host、bundle 目录、Vault 密码文件路径与独立 BWS 绑定。host 入口仅传白名单源码，使用 `sandbox_name`、`sandbox_admin_root=/tmp/oci-hub-admin-<task>`、`runtime_settings` 指向已批准的独立运行环境；不复制真实 settings 或完整私有工程，不自动挂载凭据或安装工具。

plan 生成已检查的 Terraform 二进制计划和摘要；`apply REQUEST.json SHA256` 逐步执行边界、停机创建、hook 启动、Ansible 配置、Portal 登记、仅新身份启用、验证和包生成。新设备/VM 私钥及呈现凭据从独立 BWS 引用物化到内存/临时加密 Vault；请求、检查点与日志不保存原始 Portal 对象或私钥。注册请求使用 `portal_refs`；BWS 记录保存受保护 `portal_object`，执行器只接收受保护请求。工作区 record 提供该 VM 的 `ansible_vars`；设备 record 包含方案内 SSH/WG 身份、归属和 secrets。中断保留 profile 独立 `runs/oci-hub/<request-digest>`，输入/源代码改变需重新审阅，不能用旧审批恢复。

`online`/`registry`/`verify` 通过 OCI 执行器查询月账、映射和原因；API 失败报告未知。`vpn_counters` 是 VPN 流量观察，`ssh_sessions` 明确未知；不能据此关机。bundle 使用 `devices/oci-hub/<device_id>`、独立 alias 与 `wh-` 隧道，native `employee@VM`，51824/15 秒、目标 SSH pin 与叶证书 SHA256。

### 交付前验收

Ansible 的服务检查只产生 `services_checked`。本地候选包可以先生成；没有独立管理员批准的验收记录时，流程返回 `awaiting_e2e_verification`，上传和通知均被阻止。

管理员在受保护配置 `oci_hub.e2e_verification[device_id]` 中登记验收记录路径、批准的记录 SHA256 和决定编号。记录绑定实际设备、用户、工作区、映射代次、网络策略、SSH/TLS pin，以及完整内层包和外层交付包的 SHA256；有效期最多一小时。验收须覆盖经 Hub 的 SSH、主机身份、TLS、桌面 WSS 和跨用户/管理/横向访问隔离，附受保护的原始检查证据。客户端自报结果或 Ansible 服务状态不能代替此记录。

上传及发信前重新检查真实关联的设备、用户和工作区状态。验收与发送使用同一份不可变包数据；包内私钥被替换、外层说明变更或证据过期，都必须重新验收，重算包自带校验和不能替代批准的摘要。

### 中断恢复

计划阶段固定本次注册和候选包公共请求的内容与文件摘要，并纳入审批；注册只允许本次员工、设备和工作区的登记动作。apply 写入前核对输入未变，后续使用批准的快照；不能通过替换请求文件将原批准用于其他员工或停用动作。BWS 物化后的归属仍需核对，私钥不进入检查点。

Terraform apply 前持久化操作意图；恢复时只读核对已批准的目标资源、state lineage/serial、无关资源和 roster。无法证明一致时停止并要求核对，不重放旧计划。Portal 注册先进行整批归属和已有对象冲突预检，写入时继续复核；外部服务部分失败保留 prepared 动作供同 ID 安全重试，不假定跨系统事务原子性。

管理员无原因地停用 peer 也保留为 `admin_disabled`。单个 peer 查询或停用失败会被汇总报告，其余 peer 继续处理，避免一个故障阻止其他超额用户断开。

## 记账、暂停与恢复

每用户每自然月 5,000,000,000 字节，Asia/Shanghai；5 秒轮询接受超用。设备汇总 RX+TX，计数回退或代次重建保留历史累计，新代次首值计入。SQLite 原因集合为权威，Portal DisabledReason 只是摘要；月切换只移除 quota。action_id+摘要保证增额、注册和其他动作重放不重复；API 未确认保留 prepared 动作供同 ID 重试。

长停采跨月的增量保留原始前后样本为 `cross_month_review`，只暂停对应用户。`resolve_gap` 需提供 gap_id 及各月份 RX/TX 分配，合计必须精确等于待核定增量；不会自动全算新月或清零。撤销是永久原因，月恢复不清。损坏账本使用受保护的 public mapping 快照只隔离本方案已登记员工 peer，保留原库等待修复；不能把数据库错误当无人在线或新用户。

## 上线及撤回

上线前实测 Portal 完整 API/重启与计数代次、PVE hook/重启/SDN Apply、OpenWrt 纯路由回程/WAN NAT、KasmVNC TLS/WSS/Origin/API、VM sudo 下跨用户/管理/IPv6/VLAN 隔离、Windows v2、真实中国网络及 GA2 预算/紧急停用。合成 tests 不替代这些门槛。

撤回仅停止本方案入口、Portal/配额服务和精确登记的新 VM；保存月账及凭据。不要 flush 全局 nftables、回滚其他 SDN pending changes、关闭 VM500 或删除任一 existing 身份。真实基础设施删除、BWS 变更、邮件、提交/推送继续逐目标授权。

## Review 1 修正后的就绪与计数代次

`boundary.py apply` 先原子加载本方案 ACL，再启用并读回 `net.ipv4.ip_forward=1`。两角色持久化该 sysctl。`verify --routing` 还检查接口的实际 IPv4 地址/前缀、main 表直连路由，以及目标地址实际使用的接口。Hub 的 boundary 配置现在必须显式提供 `interfaces`，只允许 `wg-users` 与 `wg-workspaces` 两个名称；地址是已核验部署输入，不由 peer 推导。Portal 首次启动只要求 ACL/forwarding 就绪，执行器在每次启用 peer 前再要求完整路由就绪；PVE SDN Apply 后及 pre-start hook 同样要求完整就绪。`RoutingTable=off` 不等于内核没有地址派生的直连路由，以实际核验为准。

VM Spoke 只有配置模板发生变化才通知受管 `wg-quick` 服务重启，在核验前 flush handler。该生命周期同时应用 AllowedIPs 和 Linux 路由；未变化的重跑不重启。安装后的 SDN 辅助程序按实际部署文件名装载相邻 boundary 模块。

执行器是唯一受支持的 OCI 写入口：日常管理员操作、采样和受管 `rebuild` 都经同一个持锁入口，写 API 凭据仅置于 OCI 受限配置；管理员工程不直接调用 Portal。外部请求不能提交自报 counters 的 sample 动作，采样必须读取 OCI 本机内核。受管 rebuild 先取最终样本，停用并确认 peer 已从内核移除，再提交带当前时间的新零基线，然后按最新全部原因决定是否恢复。跨月恢复同样更新确认恢复的基线时间，不能保留旧月 stamp。

采样记录 boot ID、接口 ifindex 和 Portal systemd InvocationID。明确 boot/接口代次变化时保留旧月账、补记新代次首个累计值，旧代次的未知尾量形成阻断缺口并暂停受影响账户，人工核定时不重复计入已记账的新累计。Portal invocation 改变、上下文缺失或较长采样缺口不能证明计数是连续还是已重建，保存原始前后样本为 `counter_continuity_unknown`，暂停对应账户，不自动推算其用量。管理员核查原始样本后，通过 `adjudicate_gap` 提供 gap ID、证据 SHA256、人工决定编号和各月份 RX/TX 分配；系统记录核定，且任何未解决的阻断缺口都会继续暂停该用户。`resolve_gap` 仅处理能确定合计的 `cross_month_review`，不得将未知连续性伪装成可精确拆分的增量。

普通同上下文的连续采样按单写者运行契约计算增量，不会每次误暂停。但 WireGuard transfer 不提供 peer 创建代次：**同一 boot/ifindex/Portal invocation 内完全未观察到的外部删除重建，且新计数已超过旧值，无法由这些采样证明或检测。** 代码不声称解决这一不可观测场景。禁止绕过执行器操作新方案 peer；人工面板/内核维护必须先停用相应接入，并通过受管 rebuild/恢复流程重新建立基线。事后发现绕过操作时，先显式停用受影响账户并保留原始账本待核对；不能仅凭“未发现变化”宣布账目精确。

## R8：批准的 PVE 转发管理通道

本轮只支持管理控制端经 PVE 的明确 `uplink` 转发到指定工作区物理 IP；不支持在 PVE 本机发起工作区 SSH。PVE 的 vnet input 仍全部拒绝，没有新增通用 established input 例外。

PVE boundary 的可选 `management_access` 是逐来源、逐 VM 的批准清单：

```yaml
management_access:
  - source: 192.0.2.40/32
    vmid: 601
```

示例地址仅用于合成验证。真实部署填 PVE 在 uplink 看到的控制端源 IPv4 `/32`，VMID 必须属于本方案 `workspaces`。多控制端分别列 `/32`，不接受整个 LAN、默认路由、工作区聚合段内的来源或未分配 VMID。只放该来源→该 VM 的 TCP 22 原始方向，以及该 VM→该来源、TCP 源端口 22、conntrack established/reply 的回包。所有管理来源同时加入 VM 出站保护，开发公网规则不能放行 VM 主动访问这些管理端。反欺骗检查先于例外，其他来源/端口/工作区仍拒绝。

`render` 未提供此清单时安全生成无管理入口的规则。实际 PVE 部署角色在任何 PVE 配置写入前，使用控制端同一份 `boundary.py render --config - --require-management-vmid <本次VMID>` 通过 stdin 校验策略；缺少本次目标的批准来源即失败，不等到工作区 SSH 超时后才发现。没有自动扩大来源或改走网关/VM500 的回退。

namespace 回归使用真实 TCP 22 与 8443 监听器验证批准来源及已建立回程、非管理员、错误端口/目标、跨工作区、VM 主动到管理端、PVE 本机和无 grant 场景。该 TCP 路径测试不代替真实管理员 SSH key/host pin 或端到端验收。
