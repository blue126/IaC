# 首个 Jenkins peer agent 恢复规格

状态：已批准完整 B 范围；2026-10-23 旧基线上的本地实现与验证完成。2026-10-30 向最新主线集成时，只读投影的文件白名单与资源适配尚未更新，回归 98/99 通过；此分支尚不可合并或启用。生产部署、恢复演练及执行移交未验收。

本文件从已批准的 BMad 规格提取意图契约、任务、技术契约与验收要求；删除过程日志，不改变验收范围。原始文件及各轮评审在本地忽略目录 `_bmad-output/` 保留，后续阅读和实施不依赖该目录。

背景见 [CI-only 架构](../architecture/ci-only-execution-architecture.md)。本次保持 GitHub IaC main，仅恢复首个 peer，不包含父目标的 Gitea 权威迁移、全部 Terraform root 迁移等后续能力。

用户批准 pve0 / CT110 / 192.168.1.110、Debian 12、2 vCPU / 2 GiB / 16G；部署前重新核对 IPAM、资源所有权、模板与存储。用户授权本任务本地提交；部署、推送和合并分别另行确认。

实现来源：`245e217f4f2e5fe96ff59143e0c9f446017ce0fc`。操作步骤见 [部署与恢复指南](../guides/jenkins-agent-bootstrap.md)，本地验收和范围取舍见 [交付记录](../reference/jenkins-peer-agent-delivery.md)。

<intent-contract>

## Intent

**Problem:** 首个 peer 尚未部署；运行时、只读凭据边界、作业清理和独立恢复能力尚不足以移交 controller 执行。

**Approach:** 复用 LXC/Ansible/BOM，完成执行、隔离、清理和恢复验证；为全部存续 jobs 建立迁移映射后，将 controller executors 置零。

**用户决定（2026-10-21）：** 沿用 pve0／CT110／192.168.1.110、Debian 12、2 vCPU／2 GiB／16G，部署前复核 IPAM。选择 B：交付真实 IaC 工具链、plan 网络/凭据限制、deploy 串行清理、独立 watchdog 与 controller 执行移交。

## Boundaries & Constraints

**Always:** 非特权 LXC、独立 UID/0700 目录/secret；plan 无 sudo、Docker、部署凭据或 mutation 通道，覆盖 IPv4/IPv6。IaC main 自建 saved plan，Terraform/Ansible scope 分别审批。mutation 串行、清理失败隔离。BOM/Vault 为来源，AD-9 留记录，恢复 gate 使用真实证据。

**Never:** 伪造证据、覆盖冲突资源、虚报 CI-only 完成；提交/安装/部署遵守授权边界。

## I/O & Edge-Case Matrix

| 场景 | 预期行为 | 失败处理 |
|---|---|---|
| 资源冲突、版本错配、secret 缺失 | 拒绝创建/启动 | 保留 controller 执行能力 |
| 非只读 API、跨 UID 或签名/备份证据异常 | 拒绝执行 | 不泄密/不回滚 |
| deploy 并发或清理不完整 | 串行且检查残留 | 隔离 executor |

</intent-contract>

## Tasks & Acceptance

**Execution（按阶段交付，不同时启用新入口）：**

- [ ] S1 `terraform/proxmox/jenkins-agent.tf`、`ansible/inventory/host_vars/jenkins-agent.yml`、agent role：恢复资源/inventory；部署前复核 VMID/IPAM/template/storage。保持旧 controller executor 和现有入口，用 AD-9 有记录地引导。
- [ ] S2 `ci/toolchain-bom.yml`、新 `ci/agent-toolchain.lock.json`、agent role：预装校验锁定工具和只读 provider mirror；创建三个 UID/node；节点 secret 写入 Vault，先通过无秘密 smoke/重连与隔离能力验证。JAR 只从 BOM 消费，更新为 `4ae5bbd00b0f79f4453d20fbb6b70dcac4d0a9a4d21d85b18b2c72dd9d117aae`，部署时复核。
- [ ] S3 `ansible/roles/jenkins-plan-gateway/`、`scripts/jenkins/plan-snapshot.py`：实现下述 producer/broker/成对投影契约、当前 Proxmox provider Read 兼容和明确覆盖报告。
- [ ] S4 新 `scripts/jenkins/job-runner.py` 与 agent role unit/socket 模板：实现 root admission、全局锁、非 root transient service、每次 run 的网络/目录生命周期、清理与隔离；修复 Verify 组检查。
- [ ] S5 新 `ansible/roles/jenkins-watchdog/`、`scripts/jenkins/controller-maintenance.py`、controller config gate：实现独立维护、签名备份/证据、CT110 隔离演练与限定恢复。未得到真实证据前，不启用 JCasC 变更。
- [ ] S6 `Jenkinsfile`、新 `Jenkinsfile-plan`、`Jenkinsfile-webhook-router`、新 `ci/agent-jobs.yml`：按映射迁移全部 jobs，去除全局秘密/运行时安装；私有应用仅交付 CI 接入补丁规范，由授权应用所有者应用并回传验证。旧入口在相应新入口验证后才切换。
- [ ] S7 `ansible/roles/jenkins/templates/jenkins.yaml.j2`、defaults、`deploy-jenkins.yml`：区分 bootstrap=2 与 normal=0；通过真实恢复证据、全部作业映射和幂等验证后，单独批准并归零；随后正常 Jenkins plan 对账。
- [ ] S8 `ansible/tests/jenkins-agent/`、`tests/ci/`、新 `docs/guides/jenkins-agent-bootstrap.md`：实现下表反例与验收记录，写 AD-9、凭据版本/owner/回退矩阵和操作步骤。各阶段失败保留上一个已验证入口。

**Acceptance Criteria:**

- Given 已复核位置，when S1 provisioning，then Terraform 变更仅为 CT110/对应 inventory，目标仍为既定 2 vCPU/2GiB/16G。
- Given plan job 与匹配的签名快照，when 用真实锁定 Terraform/provider 预测当前 Proxmox 配置，then 已声明非秘密覆盖域的变更可被发现；脱敏/不支持字段有明确盲区，不能由 partial/失败推出全 root 无变更。缺少当前 provider Read 适配属于未完成，不能以 smoke 替代。
- Given 固定 main SHA，when 经两次独立审批，then apply 使用同一 saved plan；Ansible 使用刷新后的 inventory/scope 摘要；任一 SHA/状态/秘密版本/范围变化均重新计划审批。
- Given 任一身份的并发、abort 或失联，when runner 收尾，then 无残留进程/凭据/可写 workspace；证明失败则后续任务在绑定秘密前被阻断。
- Given 武装维护与同 tuple 的实测备份，when 模拟维护失败，then Jenkins 独立恢复且 Gitea 未被回滚；无有效证据时 controller 变更和归零均被拒绝。
- Given 四个旧 jobs 和新 plan job 均有调度/清理证据，when 获批移交，then controller=0 且正常 plan/deploy、agent 重连、维护和重复运行通过；Router 对缺失下游明确失败不启动业务 mutation。

## 技术契约

### 入口、身份与信任

本次保持当前 GitHub IaC main；不执行父规格长期 Gitea 权威迁移。新手动作业 `IaC-ReadOnly-Plan` 使用受保护 main 的 `Jenkinsfile-plan`，仅授权操作员可 Build；不接受任意 ref、命令、路径、provider 或环境覆盖。入口解析不可变 SHA，输入只允许 `root=proxmox` 与生成的 nonce。PR/外部 payload 不取得生产入口。Jenkins 权限限制 Configure/Credentials，凭据按 job/folder 授权；凭据 domain 的名称不作为访问控制证明。

| 作业 | node / Unix UID（各一 executor） | 凭据与能力 |
|---|---|---|
| IaC-ReadOnly-Plan | iac-plan | 只读 SCM、签名投影视图、受限 broker；无 HCP/Vault/SSH mutation 秘密 |
| IaC-Homelab-Pipeline | iac-deploy | 当前 Proxmox 范围，按 stage 注入 HCP/provider 或批准的 Ansible 凭据 |
| Webhook-Router | agent none | 纯路由，不分配 shell；main、固定下游表；未知/缺失路由拒绝 |
| n8n-rental | iac-apps（第三 UID/JVM） | Gitea 只读 SCM；CT106 发布 SSH、Google clasp 秘密仅对应批准 stage |
| n8n-rental-clasp-validation | iac-apps | 保留原修复 bundle/测试 SHA 语义；不绑定生产发布秘密，先审计测试后执行 |

应用补丁仅改 CI 身份、受控 runner、锁和清理，不改发布逻辑。保留 Node22.23.3、clasp2.4.2 的已知兼容基线，补 npm 完整锁及离线依赖。禁止本地 Docker/socket；Google stage 不使用运行时 `npx --yes` 安装。应用代码与 inline bundle 只在所属私有仓库/配置保存，本库记录摘要和接入契约。既有 SCM 身份不自动成为 CT106 发布身份。应用 mutation 与 IaC `deploy-n8n.yml` 共用稳定 `service:n8n-rental` 冲突域。

### 只读数据路径

实际部署策略由 root 管理：CT107 gateway role 消费 `jenkins_plan_gateway_policy` 与 `jenkins_plan_gateway_producer_policy`，写入 `/etc/jenkins-plan-gateway/broker.json` 与 `producer.json`；`ci/proxmox-plan-policy.json` 定义已审核的 broker route/响应 schema 和原生投影约束。CT110 agent role 消费 `jenkins_agent_runner_config` 与 `jenkins_agent_wrapper_trust`，分别写入私有 runner policy 与公开 wrapper trust。策略必须显式绑定真实 alias/node/VMID/storage、固定出口、身份、scope、密钥及证据，秘密通过 Vault 间接提供；不存在可直接启用的通用访问占位配置。缺少这些材料时保持 activation=false、bootstrap=2，完整 B 的身份、只读投影、两次审批、串行清理、隔离及恢复 gate 仍须逐项验收。

CT107 上 root 管理的独立 producer/broker 服务不占 Jenkins executor。producer 专用 HCP 身份只读 `iac-proxmox-lab` state，API 读取 finalized current-state-version；无足够最小权限就拒绝，不自动换 owner/org token。raw state/预签下载 URL/密钥只在 root0700 临时目录；不执行仓库中的 Terraform/provider/script。producer 的 state-read token 不下发 CT110；iac-plan 无任何 HCP token，iac-deploy 的独立部署 token 仅在对应 stage 临时绑定。broker 对 primary cluster/pve2 分别用专用只读 PVE token，响应字段也白名单过滤，避免重新引入秘密；这不是向 peer 发放原 token。

producer 仅处理固定 schema/来源的 Terraform 配置与 state，按同一策略成对变换：移除 cloud backend，生成一次性 local backend；所有 provider 别名改为 broker、禁止 SSH/root password；敏感 map 值在配置输入、state 和 refresh 响应中使用相同确定性哨兵。混合 inventory map 按 key 处理。manifest 列出改写字段及依赖影响；秘密参与 count/name/trigger/output、未知 schema/opaque private/未审计 data 或 provisioner 时拒绝相应预测，不把哨兵造成的相同值当作已验证真实值。不得把投影视图写回 HCP 或用于 apply。

签名 manifest 绑定 root/source SHA、state-version/lineage/serial、TF/provider/schema/lock/policy 摘要、bundle hash、覆盖/盲区、nonce、签发时间与15分钟期限；签名前及结束时重查 current state-version。状态更新则结果 stale。公钥 root 固定；签名私钥不交 job。输出区分 predictive/partial/unpredictable/stale；仅完整覆盖域可报告无变更，partial/unpredictable 不算完整验收。

plan 的实际任务进程只可到固定 broker IP/端口，禁 DNS/公网/直连 PVE:8006/HCP/SSH/本地其他服务，IPv4/IPv6 同时覆盖。broker 限 HTTPS 固定上游、GET 路径/node/VMID/storage/query 白名单，拒绝 CONNECT/任意 URL/重定向与写方法；PVE ACL 再次限制。`query-url-metadata` 默认拒绝：只为受保护配置里的固定镜像 URL/node/参数增加经测试的只读适配，不赋 Sys.Modify。缺适配就失败，不回退 `-refresh=false`、`-target` 或删资源伪装成功。root 预置与 lockfile 匹配的 filesystem mirror；固定 CLI config、`init -lockfile=readonly`，无 direct 安装。

### runner、网络与清理

选 root daemon 启动每次任务的 transient `.service`，不让 agent 委派 cgroup。Unix socket 用 SO_PEERCRED 校验身份；只接受 CT107 受信控制服务按固定 job/profile 表与实际构建元数据签发的 admission（job/build/SHA/nonce/UID/scope/期限），不让 job 自报授权范围；root 固定 User/路径/unit 属性，不接受调用方 root 命令或任意 systemd 参数。agent 保留 NoNewPrivileges/ProtectControlGroups；job 使用 Type=exec/RemainAfterExit=yes、`Delegate=no`、KillMode=control-group、PrivateTmp/PrivateIPC/ProtectProc=invisible 和只读工具链；主进程退出后由 monitor 显式 stop，不提前 collect 丢失状态。受保护 CI wrapper 在 remoting 上只做 admission/传输/状态查询，仓库脚本、测试和任意用户代码只能在 job unit 内执行。LXC 的 nesting/cgroup2/namespace/加固必须实测有效，失败不静默删除加固或改特权。

root runner 在任何 stage 绑定秘密前取得 CT110 全局 flock，三个身份合计只运行一个 job；mutation 额外记录排序后的 root/服务冲突域并覆盖 plan→apply→inventory→Ansible→Verify。每次 run 独立0700 HOME/TMPDIR/工作目录和网络 namespace：remoting JVM 只连 controller，任务不继承它的 controller 通道。deploy/apps 按批准 scope 开放明确目标/端口与受限解析/HTTPS 出口；plan 无 DNS，所有身份禁 Docker、宿主/D-Bus socket及其他身份目录。Unix socket ACL/mount 隐藏与 loopback 隔离单独验收，不能依赖 skuid 一项规则。

收尾顺序固定：停止 job unit→TERM/超时 KILL→核验 cgroup 与 run namespace 无活进程→撤销网络/绑定→清除本 run 的 plan/state/tfvars/backend、Ansible/npm临时文件、SSH/Vault/Google绑定文件与 checkout→检查残留→释放锁。abort、controller断开、daemon重启均走同一路径。root 持久目录 `/var/lib/jenkins-agent-control/` 保存 run registry 与 quarantine，阻断后续 admission，同时停止受影响 agent；尽可能标 node offline。daemon/系统重启先重建锁与核对遗留 unit、挂载、run-dir，再启动 agent/接单，不能因 flock 或 `/run` 消失自动放行。管理员通过固定 verify-and-release 操作确认无进程/秘密/目录后解除，不接受流水线自行清标记。

### 独立维护与恢复

CT110 root maintenance/watchdog 独立于所有 agent unit；受信 root/PVE 管理员属于信任边界，root-only controller 备份含 master.key/credentials，不宣称能抵御此管理员。维护命令只接受签名 bundle ID/固定模式，无任意 shell。CT107 使用专用 jenkins-recovery 身份，其唯一 sudo 能力是无任意参数的 root-owned helper；对应 SSH key 仅供 CT110 root，限制来源、forced-command、无 PTY/SFTP/转发。helper 仅能 quiet/drain、停 Jenkins、导出/替换其 home 与列明的 service config、启动/健康检查；独立验签 target/nonce/期限/备份摘要/一次性授权，拒绝跨根链接、特殊文件及任意路径。不接触 Gitea/整 CT；core/Java 必须与备份匹配，不匹配拒绝，本项不包含任意 core/Java 升级恢复。签名私钥 root-only，公钥及 key ID 版本化；轮换须重新签发/演练，旧 key 撤销后旧证据失效。

维护流程：独立编排器取得 control-plane 锁→quietDown/等待构建结束→停止 Jenkins 并确认无写进程→生成 home/service config 备份以及 core/plugins/Java tuple 与 hashes→保持生产 Jenkins 停止，在 CT110 演练该备份→验证成功后签发证据、武装并执行本次变更，最后启动服务。首次 baseline 的停服/演练记入获批 AD-9 引导；后续由正常独立维护入口执行。演练期间 Jenkins 不接受新写入，Gitea 继续独立运行；候选副本不向生产回写。计划须包含约10分钟演练停服窗口；超时/失败恢复原 Jenkins，gate保持关闭。若备份后生产重新写入，下一动作必须重新捕获并演练，不沿用旧证据回滚新数据。

演练落点固定 CT110：drain 并停三个 agent，禁止普通作业；副本专用 UID/0700、隔离 mount/network namespace（仅 loopback，无 veth/生产路由），禁止任务/触发器/agent接入。原备份 hash 先验证，启动所需的副本执行抑制 overlay 明确记录，验证原配置可解析、核心/插件加载与离线健康检查。保留单份已验证备份及一份待验证候选，不清理其他任务数据。

资源准入：正常态三个 remoting JVM 各 Xmx96MiB/MemoryMax256MiB；单 job MemoryMax640MiB，root监督预算128MiB，保留384MiB，实测 OOM/超限不得归零。演练前 MemAvailable≥1792MiB；仅起一个副本，Xmx768MiB、MemoryHigh1280MiB/Max1536MiB、SwapMax0、10分钟超时。磁盘剩余必须覆盖候选 archive A＋展开 H＋缺少 runtime R＋max(512MiB,0.25H)＋2GiB安全余量（旧验证备份已占用不能扣除），并检查 inode；常态每次启动也检查2GiB余量。监测越界停止任务并隔离。数字是预算，未测峰值不视为通过；失败保持 gate 关闭，扩大资源需另行决定。

watchdog 仅在签名 maintenance ID、备份 hash、旧/新 tuple（core/plugins/Java/config）、授权记录、演练证据与30分钟期限匹配时武装。普通网络抖动不回滚；明确进入变更阶段后，超时/健康失败还须由限定 SSH status 确认目标服务失败，才通过 helper 恢复。SSH/网络整体不可达时保留诊断并报告失败，不猜测性恢复。过期未开始则拒绝；已开始超时则恢复已验证旧 tuple，结果持久记录后解除。证据含实际命令退出/启动健康/隔离检查、时间、版本与 hashes；gate 读取并验签真实文件，布尔或非空 ID 不能替代证据。

归零后 agent 更新也由 root maintenance 先排空、提交异步维护并等待当前作业退出后执行，验证重连才重启接单；普通 role handler 不得在自身作业中重启运行它的服务。controller 变更同样脱离正在运行的 pipeline；AD-9 仅用于首次引导/明确灾难恢复，不成为日常绕过方式。

## Verification

代码验证使用本任务独立 Sandbox，TF fmt/`init -backend=false`/validate 与现有 CI fixture syntax/lint；所需包未安装时列明再申请，不在 host 安装。PR/本地代码验证只用假上游、合成秘密与临时目录；以下 live 项目另在获批部署/演练中完成，不将未运行写成通过。

| 验证输入/故障 | 必须观测的结果 |
|---|---|
| VMID/IPAM冲突、错误版本/缺 secret、namespace不生效 | preflight拒绝，未创建/未切换入口 |
| 跨 UID 文件/proc环境/IPC/socket；plan IPv6/直连/DNS/loopback | 拒绝且不输出秘密；broker非法路径/方法/CONNECT/重定向返回拒绝，假上游写计数0 |
| state秘密map/嵌套输出、未知private/schema、过期nonce/状态更新 | 秘密金丝雀不在bundle/log；unknown拒绝、stale失效，不报告全root无变更 |
| 固定provider读取含download probe；已知非秘密配置变更 | 覆盖报告可追溯；缺适配失败；真实预测发现变化，不能仅验证在线 |
| 不同job并发、双fork/setsid/改环境、abort/daemon重启 | 仅一个任务获锁；全cgroup被回收，残留模拟导致隔离且下一任务在绑定秘密前拒绝 |
| changed SHA/plan/state/credential版本/inventory scope | 审批失效，未执行apply/Ansible；成功路径不replan后apply |
| 篡改签名/备份、错误tuple/过期/资源不足/普通断网 | 不武装/不变更；仅武装且进入维护后的故障可触发已演练恢复 |
| 故意失败维护、agent自更新、第二次Ansible运行 | Jenkins同tuple恢复/Gitea不变；异步更新后重连；重复运行无意外变化 |
| 四旧job＋新plan、缺失Router下游、normal executors | 各自node/凭据/清理有证据；缺路由失败且无mutation；满足全部gate才0 |


技术依据：[HCP state read API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-versions)、[provider mirror](https://developer.hashicorp.com/terraform/cli/config/config-file#provider-installation)、[systemd252 namespace](https://www.freedesktop.org/software/systemd/man/252/systemd.exec.html)、[cgroup kill](https://www.freedesktop.org/software/systemd/man/252/systemd.kill.html)。实际 LXC 效力仍须验证。
