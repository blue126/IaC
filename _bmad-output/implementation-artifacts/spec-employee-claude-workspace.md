---
title: 员工 Claude Code 工作环境第一阶段
type: feature
created: 2026-10-21
status: done
project_root: /Users/weierfu/.codex/worktrees/employee-claude-architecture/IaC
route: dispatch
review_loop_iteration: 1
baseline_commit: a6bffdfef447fdf54485ca4882dfe1e87b6ae04a
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-employee-claude-workspace/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-employee-claude-workspace/access-and-isolation.md'
  - '{project-root}/_bmad-output/specs/spec-employee-claude-workspace/verification.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

为5–10名员工提供澳洲个人持久VM，用本人Claude订阅开发交付；采用现有IaC，独立架构文档不是前置。

## Boundaries & Constraints

员工拥有sudo，依赖/工具自管，公司提供基础Claude Code；覆盖旧“不承诺root”表述。采用本次已同步的CAP-1至CAP-6及companions。VM外隔离、个人OAuth、VM内授权浏览器、纯终端、停用保盘均保留。终端自建中继不纳入技术杜绝保证。已选择外置受管SSH入口，禁止其内置转发，员工不得绕过入口直接连VM。

用户已选1A／2A：允许正常公网开发连接，VM外拒绝受保护目标，不承诺识别全部自建加密代理；员工在澳洲VM内实际登录并核对账号/认证来源/出口，不新增防sudo替换令牌机制。

本次不授权生产部署、个人凭据启用或提交推送。用户随后明确授权：在本任务独立本地验证Sandbox按现有Kit安装工具链及缺少的OpenSSH/nftables/iproute2，下载验证providers；不连接生产基础设施。现场参数与Q-6凭据/备份许可须在部署及首次登录前解决。

## I/O & Edge-Case Matrix

| 输入/状态 | 预期 |
|---|---|
| 已登记设备、交互或精确SFTP请求 | 仅连接固定本人VM |
| 未登记身份、任意入口命令、客户端指定目标 | 拒绝，不执行客户端字符串 |
| SSH转发/隧道请求、客机修改sshd | 入口仍拒绝；客机改动不能改变映射 |
| 目标hostkey变化、映射缺失 | 拒绝连接，不自动接受新身份 |
| 撤设备/停员工 | 终止受管会话；员工级从VM外停用并保盘 |

</frozen-after-approval>

## Code Map

- `terraform/proxmox/versions.tf`：bpg 0.70.0；`terraform/proxmox/ubuntu-2604.tf`：模块/inventory模式。
- `terraform/proxmox/employee-workspace.tf`：员工专属持久VM resource，固定NIC槽位及prevent_destroy；共享proxmox-vm模块保持原状。
- `ansible/roles/common/tasks/main.yml`：公钥/sudo；`ansible/roles/ubuntu-vm/tasks/main.yml`：SSH验证后收紧认证。
- `tests/ci/fixtures/ansible.cfg`：无生产Vault验证；CI脚本含安装操作。

## Tasks & Acceptance

- [x] `terraform/proxmox/employee-{access,workspace}.tf`：单节点内部网桥/员工、多NIC网关、VM及专属inventory；默认空配置零资源。
- [x] `ansible/roles/employee-access/`：接口/nftables、设备身份到VM固定映射、两段SSH及SFTP分派；禁止入口shell/转发，固定客户端参数/hostkey。
- [x] `ansible/roles/employee-workspace/{defaults,tasks}/main.yml`、`ansible/inventory/group_vars/employee_workspaces.yml`：账号/sudo/公钥/基础CLI。
- [x] `ansible/playbooks/{deploy,disable}-employee-workspace.yml`：Deploy/Verify；撤设备须杀既有会话，停员工须VM外断网/停机并保盘。
- [x] `docs/guides/employee-claude-workspace.md`：配置与实测、旧入口、OAuth；同步已裁决的源契约差异。
- [x] `tests/employee-workspace/`：固定映射、注入/未知命令拒绝、SFTP、网络矩阵与停用保盘的独立预期测试。

AC：Given 授权测试环境，When 本人开发/SFTP，Then sudo/工具自主与CAP-1/2/5通过。
AC：Given 正反对照目标，When 测试身份/二层/伪装/IPv6/公网回流，Then 最终CAP-3拒绝矩阵成立。
AC：Given 员工修改客机sshd，When 向受管入口请求转发/其他目标，Then 仍拒绝。
AC：Given VM内真实授权流程，When 登录/替换并核对账号和出口，Then CAP-4按1A/2A验收，不要求防sudo替换；未知不算通过。
AC：Given 已登记设备/员工，When 撤销/停用，Then CAP-6成立且既有业务正常。

## Implementation Notes

- 2026-10-21：用户批准并继续。project_root绑定本任务工作树，源输入副本及草稿为本任务已有未提交文档。主checkout只作协调。外部实网验收待另行授权，不虚构通过。

- 2026-10-21：实现代理已交回两个Terraform入口、两个Ansible角色、部署/停用playbook、指南及测试。已修正Verify默认变量覆盖与disabled/started一致性；报告现有Python环境17项离线测试通过、配置渲染及5脚本AST检查通过，未运行宿主Terraform/Ansible。
- 根代理核对冻结意图SHA256仍为3c0dec5e29a1319b0b514aaeac5d253f6f9f7810dcf19f3245362f78c9663f01，跟踪及未跟踪文件空白检查通过。初步全量差异快照为`/private/tmp/employee-workspace-build-g8o0hwsq.diff`；恢复后须按最终版本重新生成/完整审读，尚未进入Step4评审。
- Step3验证待续：无本任务Sandbox；新建时.sandbox-kit会安装工具链，已向用户请求授权，尚未收到答复。Terraform fmt/validate、Ansible syntax/lint、真实nft/SSH运行与矩阵测试尚未执行，不能标通过。现场CAP/OAuth验收仍另需授权；工作流保持in-progress。

- 2026-10-21：获准Sandbox验证完成：离线20、Terraform mock4及3组计划状态断言、真实SSH/SFTP26、隔离网络35均通过；两playbook syntax、25文件lint、Terraform validate、nft/sshd配置及格式检查通过。日志在iac-employee-claude-verify-direct-v130:/tmp/employee-workspace-verify/。根代理已读原始结果与代码差异，按代码交付范围进入原生评审，未声明现场CAP完成。
- 冻结矩阵对应：固定目标/未知命令/身份/SFTP→ssh-final.jsonl；转发拒绝及宽松客机→同文件，TUN有效配置为no（因无/dev/net/tun，真实-w未实测）；hostkey变化/缺映射→同文件；设备旧SSH/SFTP撤销/他设备保留→同文件；员工禁用既有出网切断→network-final-expanded.jsonl，VM停机/禁自启/断NIC→startup-assertions.jsonl，实际PVE命令/保盘仍属现场验收。
- 已修复全局pve-guests依赖：改本员工VM pre-start hook并默认boundary_ready=false；接口改名前后维护路径经真实网络验证。现场PVE hook执行、WireGuard握手、真实OAuth与CAP-5未执行，部署前按指南验收。

## Spec Change Log

- Iteration 1：三个原生层全部返回后逐项分诊，共13条，BH-8/ECH-1同根因合并。无intent_gap；不改变冻结需求。修正非冻结实现设计，消除已确认的失败路径。
- KEEP：受管双会话/固定目标SFTP、员工sudo及1A/2A、独立L2/nft边界、设备级撤销、无生产凭据测试、20离线/4Terraform/26SSH/35网络的正反对照覆盖和原始日志。用户未授权删除本任务未跟踪文件；按照仓库文件边界保留当前实现，采用原位重新落实设计，未执行技能要求的删除式回退。此为明确流程例外，不声称已回退。
- 实现约束补充：员工NIC必须有持久、唯一、可验证的槽位，按槽位生成设备顺序/接口/tap；新增字母序更早员工不移动现有槽位。持久员工VM要有实际销毁/替换保护，不能只靠bridge保护或操作提醒，验证应覆盖破坏性计划。
- 网关路由默认关闭，只有专属防火墙成功加载才开启；启动/重载失败保持关闭，PVE节点不能因此被改全局routing。Verify要核对实际内核表及其与已应用期望的一致性，不能只检查文件语法/服务active。
- 其余修复：停员工先应用VM外网络拒绝再尝试qm停机；处理WireGuard接口Address变化；所有NIC含uplink MAC一致校验；在修改前no_log校验必需系统私钥及可解析性/唯一性；hook核验base chain挂接；仅放行已允许连接的必要related ICMP错误，并保留新建私网拒绝。
- 测试必须覆盖真实任务路径：使用实际workspace授权渲染及跨play数据的Alice/Bob有效/跳过/异员工/from限制；实际Ansible撤设备和qm失败后的网络撤销；缩小MTU的公网传输；未挂接链/实际表缺失/防火墙加载失败；增员稳定槽位与员工磁盘保护。复用获准Sandbox与已有工具，不访问生产。


- Iteration 1修复后证据：root已核对round1原始日志，offline20、SSH34、network49、runtime9、Terraform mock7及3组计划状态断言、正常plan正向对照与destroy/forced-replacement/VMID-change拒绝、28文件lint、两playbook syntax、systemd单元静态解析均通过。代码与冻结矩阵的授权目标、错误身份/命令、转发、hostkey/缺映射、实际Ansible撤销和外部网络停用路径已对照。真实PVE/systemd/WG握手/OAuth及现场CAP限制仍保留，不以shim或mock冒充现场结果。
- 上轮BH-1..10/ECH-1..2/VG-1均有对应实现与测试：稳定槽位/自保护VM、先阻断再停机、WG地址同步、全NIC MAC检查、私钥前置校验、base-chain挂接检查、related ICMP、实际内核摘要、加载失败关闭routing，以及实际授权/撤销任务路径。共享模块已恢复，未留下无调用扩展。当前进入按原生loopback要求的再评审，不额外添加review层。

## Review Triage Log

| ID | Verdict | Evidence | Route |
|---|---|---|---|
| BH-1 | high | NIC/interface/tap取index(sort(employee IDs))；在alice/bob前加入aaron会实际重排既有端口，跨Terraform/Ansible分阶段变更会破坏既有连接。 | bad_spec |
| BH-2 | high | disable.yml在qm set/status/stop之后才执行拒绝网络；命令失败即中止，旧公网流仍可达。 | patch |
| BH-3 | high | prevent_destroy仅保护网关/bridge；员工模块VM仍可在VMID等变化时replacement，桥不变时不会阻止删除员工磁盘。 | bad_spec |
| BH-4 | medium | wg-quick strip移除Address，wg syncconf不设置接口地址；现有接口的地址变更不会实际应用，sshd/规则却已引用新值。 | patch |
| BH-5 | medium | validate-inputs.py的MAC集合未纳入uplink_mac，调用方也未传该值；可生成重复MAC匹配的netplan。 | patch |
| BH-6 | medium | 部署直到device.yml copy私钥时才发现缺Vault项或后续ssh-keygen解析失败，此前已修改边界/账户/授权；预检缺失。 | patch |
| BH-7 | high | hook只匹配rule.chain和drop表达式，不检验base chain的type/hook/priority；同名未挂接普通链可通过。 | patch |
| BH-8 | medium | forward在related前丢弃私网来源ICMP；output仅允许往VM的TCP22，丢弃网关本地产生的PMTU错误，较小MTU路径可挂起。 | patch; grouped ECH-1 |
| BH-9 | medium | Verify只查磁盘nft语法及oneshot active；实际表被删除或漂移时仍可通过，需要实际内核策略证据。 | bad_spec |
| BH-10 | medium | SSH测试手工撤销文件和pkill，网络测试直接重载规则，未执行Ansible撤销/停用任务，不能发现实际顺序及中途失败。 | patch |
| ECH-1 | medium | 与BH-8同一ICMP/PMTU规则顺序及output缺例外问题，跟踪规则确认，不把每个合法related错误当新建私网访问。 | patch; grouped BH-8 |
| ECH-2 | high | sysctl持久ip_forward=1与firewall服务加载成功没有依赖；重启时nft失败后网络/转发仍可开启，员工VM到维护网等路径可能失去网关阻断。 | bad_spec |
| VG-1 | medium | 预验证缺口：SSH测试手写无from限制的root授权，未用实际workspace任务/跨play注册数据；把来源gateway误改ip仍能测试通过但实际登录全部失败。 | patch |



### Iteration 1 再评审分诊

| ID | Verdict | Evidence | Route |
|---|---|---|---|
| R1-BH-1 | high | disable先include PVE任务；其失败会在网关阻断之前结束，独立可用的网关未尝试拒绝。 | patch |
| R1-BH-2 | medium | WG文件写入后同步失败，重跑template unchanged不会通知handler，运行peer仍旧；正常deploy同路径。 | patch; grouped R1-ECH-2 |
| R1-BH-3 | medium | firewall unit与可能已启用且flush ruleset的标准nftables.service同在network-pre前但无彼此顺序；该支持配置下员工表可后被清空。不是声称现场已出现。 | patch |
| R1-BH-4 | medium | hook核验base chain/drop但不调用已有完整策略verify；在fallback前插accept仍能通过has_port_drop。可复用已存在的应用摘要控制。 | patch |
| R1-BH-5 | medium | disk_size用开头数字直接作为GiB，1T/100M未拒绝且被错误解释。保留现有字段，限定并校验明确G格式即可。 | patch |
| R1-BH-6 | medium | 公钥仅文本regex，AAAAhostAlice可过而不是有效Ed25519 wire blob；失败在修改后才体现。 | patch |
| R1-BH-7 | medium | 持久VM可改address/gateway/MAC，但Cloud-Init不会可靠重配运行客机；现有terraform_data仅冻结slot。复用分配记录冻结这些创建时网络值。 | patch |
| R1-BH-8 | high | Cloud-Init公钥忽略后续变化，角色只管employee账户，admin_public_keys无持续消费者，旧管理员key不会被撤销。 | patch |
| R1-BH-9 | medium | 子串检查允许allowusers ubuntu unwanted-user通过，实际用户集合未约束。 | patch |
| R1-BH-10 | medium | boundary入口直接修改PVE，绕过网络结构校验；首次流程在full deploy之前使用它。需不依赖未生成hostkey的网络校验。 | patch |
| R1-ECH-1 | medium | 网关file写入后reload失败会留routing=0；重跑停用不再触发reload，其他员工持续中断。 | patch |
| R1-ECH-2 | medium | 与R1-BH-2同一changed-only通知缺陷；每次协调实际WG状态而非仅文件变化。 | patch; grouped R1-BH-2 |
| R1-ECH-3 | medium | 成功revoke删除mapping后，正常deploy仍无条件写disabled mapping；Verify要求不存在，产生错误失败。 | patch |
| R1-VG-1 | medium | 预验证Regression gap：SSH夹具手工发布mapping/入口公钥，未执行device.yml及assignment变化kill；ip→gateway或遗漏mapping.changed不会被现有测试发现。 | patch |

以上均为已演示路径的局部修正，使用现有输入/内部工具，不新增用户能力或改变冻结意图；按patch接回同一实施代理，不触发新的bad_spec loopback。所有原始条目均保留，只有WG重复项合并根因。

## Design Notes

内部bridge无物理端口及宿主IP；规则按入接口隔离。provider会应用节点网络变更，部署前核对未应用配置和管理恢复路径，不接管现有桥。地址/节点/VMID等为部署输入，停用不可通过删除roster实现。

首轮按WireGuard候选准备自建接入，正式入口依实测；不把候选写成已部署。受管入口ForceCommand固定映射，禁内置转发；内层禁escape/用户配置/代理/复用，严格hostkey。SFTP走精确子系统分支，不解释任意客户端命令，不记录终端正文。

OAuth保留VM浏览器要求；Browsh+headless Firefox仅为纯终端候选，需先验证兼容性，再由员工实测。不得从文档推定授权成功或擅自改图形入口。

## Verification

在获准Sandbox使用已有工具执行fmt、无后端validate、隔离inventory的syntax/lint及离线测试；无授权不安装。实网CAP验收另获准执行，沿用本次已同步的verification.md；静态检查不替代现场证据。


## Final Verification and Patch Resolution

2026-10-21：同一实施代理完成patch后，根代理独立复跑全部相关检查，日志保存在 `iac-employee-claude-verify-direct-v130:/tmp/employee-workspace-verify-parent-final/`。逐条核对JSON预期/实际及退出码：离线24、runtime18、真实SSH/SFTP48、真实隔离网络58、Terraform mock17、3组启动状态和4个磁盘保护计划正反对照均通过。两个playbook syntax、全部新增角色与playbook的31文件lint（0failure/0warning）、Terraform fmt/validate、两份nft规则语法、sshd有效配置、两份systemd unit静态解析、Python AST及新文件空白检查通过。

| 本轮条目 | 最终实现与验证证据 |
|---|---|
| R1-BH-1 | 网关先拒绝再调用PVE；network.jsonl中PVE失败后员工拒绝、其他员工可用。 |
| R1-BH-2 / R1-ECH-2 | deploy/disable每次执行共享WG同步；runtime.jsonl覆盖首次失败后文件不变仍同步peer及Address。WG传输采用替身，未声称实际握手。 |
| R1-BH-3 | firewall排在nftables.service之后；模板及systemd静态检查通过，实际boot仍属现场验证。 |
| R1-BH-4 | pre-start hook调用完整已应用策略verify；network.jsonl验证保留fallback drop但前插accept时仍拒绝启动。 |
| R1-BH-5 | 磁盘容量仅接受正整数G；Terraform拒绝错误单位，正常配置可计划。 |
| R1-BH-6 | 解析SSH公钥wire结构/类型及WG编码；offline.log覆盖无效公钥，测试夹具改用有效公钥。 |
| R1-BH-7 | 持久分配记录冻结地址、网关、MAC、bridge等创建时网络值；terraform-tests.jsonl拒绝既有分配变更。 |
| R1-BH-8 | Terraform把管理员公钥传给两个Ansible消费者，角色持续替换授权；SSH实测旧key失效、新key登录。 |
| R1-BH-9 | AllowUsers比较完整有效集合；runtime覆盖多用户、相似前缀、通配符及多行。 |
| R1-BH-10 | deploy/boundary/disable共用前置结构校验；runtime实际boundary入口验证无hostkey可初始化、无效拓扑在修改前失败，Terraform拒绝可判定子网冲突。 |
| R1-ECH-1 | 停用每次重载网关；network覆盖首次加载失败routing=0，配置不变重跑仍恢复其他员工且继续拒绝停用员工。 |
| R1-ECH-3 | inactive设备复用revoke；SSH验证停用后再次正常部署不恢复映射、凭据或登录，Bob保持可用。 |
| R1-VG-1 | SSH夹具执行实际device.yml；验证Alice/Bob目标、归属变更终止旧会话、其他设备保持及新目标正确。 |

冻结矩阵逐项对应：本人固定目标/SFTP、未知身份或命令、内置TCP/StreamLocal转发、客机放宽转发、hostkey变化及缺映射→ssh.jsonl；设备撤销与旧SSH/SFTP失效→同文件；员工外部断网及其他员工保留→network.jsonl；停机/禁止自启/断NIC计划→startup.jsonl；销毁/替换保护→disk.jsonl。`ssh -w`因Sandbox无/dev/net/tun未实测，仅有效配置确认permittunnel=no；agent/X11有效配置均关闭，不冒充全通道现场实测。

父侧首个静态检查在Sandbox重启后因/run/sshd不存在而中止；只补该临时运行目录并继续未完成检查，未改业务实现，最终全部通过。初始失败保留在会话工具输出，最终日志不含被误算为通过的失败。

所有评审条目已处理，无延期条目；按原生patch路线直接进入Step5，未自动增加第三轮评审。完成状态限定已授权代码交付及隔离验证；真实PVE hook/停机保盘、systemd boot、WireGuard握手、中国网络并发、VM内个人OAuth和现场CAP仍须部署阶段验收。

Step5要求创建本地commit，但仓库明确要求提交单独授权，冻结边界也未授权提交推送。已完成所有可审阅产物，保留未提交工作树；本地commit等待用户授权，未push/PR/部署。冻结段SHA256保持 `46b1adf6de795ba31483164e1c6edaa5c0d7df7ac055ade41cefb9fabbe08e9c`。


2026-10-21：用户明确授权“你可以继续创建提交”。继续Step5，仅创建包含本任务代码、测试和文档的本地提交；推送、PR及部署仍未授权。提交前核对工作树与最终验证快照一致（56文件），没有新增实现改动，不重复已通过检查。
