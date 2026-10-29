# 首个 Jenkins peer 的部署与恢复

当前集成阻塞（2026-10-30）：最新主线的员工网络/启动脚本等资源及文件闭包尚未纳入只读投影适配。`test_current_native_closure` 报 `native source closure changed`；不得只刷新哈希或删除该回归来放行。本指南的实际部署步骤须等兼容性修复及完整 B 验收材料齐备后执行。

批准范围见[恢复规格](../planning/jenkins-peer-agent-recovery.md)，最终评审、范围取舍和本地验证见[交付记录](../reference/jenkins-peer-agent-delivery.md)。

本实现恢复 pve0 的非特权 CT110（192.168.1.110、Debian12、2vCPU、2GiB、16G），保留 controller 的 bootstrap=2。代码默认关闭 agent/gateway/watchdog 激活、所有新 job 和 normal=0；既有 controller 的 role 跳过历史安装分支，只有签名 gate 后才管理配置。历史首次 controller 安装需要独立 bootstrap 标志且目标尚不存在；上线、约10分钟停服演练及最终归零分别需要批准。生产 IPAM、凭据和恢复证据没有由本次代码验证生成。

## 交付与信任边界

`ci/toolchain-bom.yml` 固定 Java25、Terraform1.14.4、Ansible2.19.12 与 agent.jar；`agent-toolchain.lock.json` 补齐 Python/npm 哈希，provider 与 collections 分别继续消费原 lockfile、requirements.yml。`prepare-toolchain.py` 只准备公开离线工件，不安装；`toolchain.py` 在获准部署的 CT110 上校验后安装。缺 wheel 或包哈希时拒绝，不能临时下载或转成未审核源码构建。

CT107 的 root admission/producer/broker 不占 executor。admission 通过固定 Groovy 查询实际 Jenkins build、SCMRevisionAction 与 InputSubmittedAction，仅签发固定 job/profile/scope；root-owned bare source 的 origin 必须等于 profile 的 `scm_url`，只刷新固定 main，运行中的实际 script SHA256 还须等于该 main 文件；只有 `iac-approvers` 的实际 input 可签对应 digest。remoting mTLS 身份只能请求 admission，peer root mTLS 身份才可传输 bundle、续租和取得阶段绑定。两个身份的证书 CN 分别为 `iac-peer-remoting`、`iac-peer-root`；来源固定 CT110。签名私钥、HMAC key 与原始 HCP/PVE token 均留在 root 目录。

CT110 三个 remoting JVM 分别使用 iac-plan/iac-deploy/iac-apps、Xmx96MiB、MemoryMax256MiB。root runner 和 watchdog 共用 128MiB slice，单 job 上限640MiB。root 在任何凭据绑定前取得全局 flock，创建独立 HOME/TMPDIR/workspace、network namespace 和非 root transient service。任务先实测 namespace、跨 UID proc、Unix socket 与 loopback 隔离，再请求阶段绑定。没有委派 cgroup，没有 Docker/socket，没有调用方任意 systemd 参数。部署任务的受限名称解析使用 root 固定 hosts，plan 只允许 broker IP/9443；inet 默认 drop 同时覆盖 IPv4/IPv6。

当前 Proxmox 投影只接受受保护 main 中已审核的31文件闭包。更新合法配置后运行 `python3 scripts/jenkins/update-projection-policy.py` 并审核 diff，验证时用 `--check`。保留 native HCL/local modules，移除 cloud/backend/SSH/root password，按 key 改写 inventory 混合 map。受支持 Read 路由与响应字段在 `ci/proxmox-plan-policy.json`；列表再按 alias/node/VMID、模板和 file ID 筛选。bpg0.70会剥离 endpoint 的路径，因此用无秘密的投影 token ID 选择 primary/pve2，真实上游 token 不离开 broker。download probe 只为固定 HTTPS 镜像做校验 TLS 的 HEAD，不调用需要 Sys.Modify 的 PVE probe。

部署策略由 root 明确提供：CT107 gateway role 的 `jenkins_plan_gateway_policy` / `jenkins_plan_gateway_producer_policy` 写入 `/etc/jenkins-plan-gateway/broker.json` / `producer.json`，前者采用上述 `ci/proxmox-plan-policy.json` 的 broker route/响应约束；CT110 agent role 的 `jenkins_agent_runner_config` / `jenkins_agent_wrapper_trust` 写入 `/etc/jenkins-agent/runner.json` / `/opt/jenkins-agent/control/trust.json`。这些输入必须绑定核对后的 alias/node/VMID/storage、固定出口、三 UID/profile/scope、可信密钥和真实证据，凭据经 Vault 间接绑定；仓库不提供可直接启用的通用访问占位配置。未完成策略与完整 B 验收前，保持 activation=false、bootstrap=2；不得省略签名准入、两次审批、串行清理与隔离、独立 watchdog/recovery 或证据 gate。

覆盖状态保持 `partial`：密码、description、VM args、SSH keys、raw lxc 配置等为明确盲区。未知 data/schema/private、嵌套/敏感输出、secret 进入名称/数量/输出时拒绝 bundle；仅接受 SDK schema_version 与 download_file 的已审计数字缓存。manifest 绑定 SHA、state-version/lineage/serial、schema/lock/policy、bundle、nonce 和15分钟期限。签名前与任务结束后都重查 finalized current state；stale 不能成功。不能把 partial 的零变化写成全 root 无变化。

## 分阶段操作

1. **资源准入**：获准部署后，在 CT107 root 以专用只读 PVE/NetBox 身份运行 `peer-preflight.py --policy <root policy> --output <root report>`。核对 VMID110、IPAM无占用、精确 Debian 模板、vmdata rootdir 支持及空间。任一冲突保留旧入口，禁止 import/覆盖解决冲突。已存在受管 peer 的后续配置更新不复用“新分配”报告；必须核对已有 state/资源所有权。
2. **AD-9引导**：先从健康 controller 的 Web UI/executor 创建 CT110/对应 inventory；代码预期 Terraform diff 只有这两个新对象。记录操作者、批准ID、命令、目标、原因和真实结果。首次 node 建立可用明确 AD-9 操作创建三个 exclusive、各一 executor 的节点；从 controller 获取真实 remoting secret 后写入唯一 Vault 文件，消费者为 host_vars 中的三个 `vault_jenkins_agent_*_secret`。不生成假 secret。
3. **离线工具链与节点**：在已授权的隔离 Sandbox 运行 `prepare-toolchain.py --destination <fresh task dir>`，复制至 CT110 `/var/lib/jenkins-agent-kit` 并核对 root 所有权。部署 agent role 的 `jenkins_agent_install_authorized=true` 只在此次安装授权下设置。预先提供 root-owned runner/trust policy、控制服务 CA/证书与公钥；先安装、后单独激活。`jenkins_agent_activate=false` 保持到这些材料齐全。JAR 从 BOM 消费，部署时重新核对 controller 返回的 SHA256。
4. **producer/broker**：部署 CT107 `jenkins-plan-gateway` role，填写实际 workspace ID、专用最小 state-read 权限、primary/pve2 各自只读 token、可信 CA、完整 alias/node/VMID/模板/file 白名单。专用 HCP 身份存在多余 mutation 权限或权限结构未知时拒绝；不能替换 owner/org token。原始 state/下载 URL 不进入 peer。先完成真实锁定 provider 的当前 root 预测及盲区记录，才启用 plan job。
5. **admission/runner**：按 `ci/agent-jobs.yml` 部署固定映射，root policy 的 profiles 默认 disabled。每个 profile 固定 user、executable、scope、targets、hosts 与 timeout；每次 admission 绑定实际 build/SHA、bundle 和 Vault 凭据版本及 root HMAC 输入摘要。IaC/plan/应用执行 profile 的 executable 固定为 `job-entry.py`，它先执行边界 probe，再分派到 IaC `transaction.py`、plan `plan-task.py` 或经过摘要审核的私有应用包装器；应用包装器仅由授权所有者依接入契约交付。缺证书、秘密、审核输入或内核能力时拒绝启动。工作 unit 的异常退出、失联、OOM、残留分别实测。 对 standalone `CpsScmFlowDefinition` 轻量 SCM job，root profile 必须提供 `standalone_entry: {sha: <审核的40位commit>, script_sha256: <该commit入口文件SHA256>}`；此 SHA 只标识已审核的入口脚本版本。helper 核对实际 `build.execution.script`、固定 SCM URL、main branch、script path；admission 验证 root 记录对应的 Git 脚本，再刷新固定 main，要求该 main 的入口脚本字节也一致，随后签名冻结该 main 的实际执行 SHA、bundle 与来源记录。普通文件变更可正常准入；入口变更须重新审核 root 记录。没有 SCMRevisionAction 时，签名明确记录 `jenkins_fetch_sha: null`，不宣称知道 Jenkins 原始轻量 fetch 的 commit；运行中 lease 使用已签名的执行 SHA，不重新解析 main。
6. **独立恢复 baseline**：准备固定 core/Java 的 WAR，部署 `jenkins-watchdog`，将 CT107 `jenkins-recovery` 身份限定为来源 CT110、forced command、无 PTY/SFTP/转发、唯一 argument-fixed sudo helper。签名授权后调用 `watchdog.py capture-and-drill --bundle <root signed bundle>`。它取 control-plane/global 锁、停止三个 agent，quiet/drain/停止 Jenkins，导出 home/service config，CT110 仅 loopback 启动副本。原配置先解析，再记录抑制 jobs/triggers/agents 的 overlay；匹配 core/plugins/Java 并校验内存1792MiB、磁盘 A+H+R+max(512MiB,0.25H)+2GiB 和 inode。Gitea 独立运行，禁止整 CT 回滚。失败/超时启动原 Jenkins且 gate 不开；成功后保持 Jenkins 停止、签发证据并武装独立 watchdog，不能先恢复生产写入再沿用备份。
7. **计划维护**：gate 在 CT107 读取真实签名证据、备份 hash、tuple、实际命令/隔离/健康文件和 CT110 armed attestation。调用 `watchdog.py begin` 后才变更；root startup fence 保持 Jenkins quiet。complete 必须观测 approved new tuple 与健康，先持久提交恢复决定、恢复 agent，再解除 quiet；配置 gate 的授权只可消费一次。若意外恢复生产写入，旧备份不再可自动回滚，必须重新捕获和演练。普通断网不回滚；明确进入维护、超时/健康失败且限定 SSH status 确认服务失败时才恢复已演练旧 tuple。SSH整体不可达只记诊断。证据/授权30分钟过期、签名/tuple不符均拒绝。
8. **作业迁移与归零**：新增的 `Jenkinsfile-peer`、`Jenkinsfile-plan` 与 `Jenkinsfile-webhook-router-peer` 仅在各自 staged run 通过后切换在线 SCM，分支固定 main。基线 `Jenkinsfile` 与 `Jenkinsfile-webhook-router` 保持原字节；在获准 staged 验证后，单独修改在线 job 的 SCM script path 指向 peer 文件。Router agent none；未知平台或缺失下游直接失败。私有应用所有者依 `jenkins-private-app-ci-contract.md` 回传两个作业的实际验证。全部四旧 job+新 plan 的调度/凭据/清理、两次 Ansible、OOM预算、重连、正常 plan/deploy 和故意失败恢复全部齐全后，再单独批准 normal=0。归零后用正常 Jenkins plan 对账。

IaC deploy 从同一 main SHA 自建 saved plan。Terraform input `TF-<manifest digest>` 审批后只 apply 该文件；SHA、state-version、lineage/serial、lock、凭据版本/输入摘要变化要求重计划。刷新 inventory 后校验 host/IP/playbook/tag/variables source 属于已锁 scope，再通过独立 `ANSIBLE-<scope digest>` input。controller 自身维护不在普通 transaction 中执行。agent 更新需要明确的 control-plane:jenkins-agent scope；role 仅暂存配置，当前作业退出后由独立 root 维护器重启。部分暂存失败会留下 incomplete/quarantine，修复完整配置后才可 verify-and-release。

## 清理与故障处置

固定顺序为 stop job unit、TERM/超时 KILL、核验 cgroup/netns无活进程、撤销网络、清除本 run 所有文件与 checkout、残留检查、释放锁。profile 外的文件不可清理。cleanup 无法证明成功则持久写 `/var/lib/jenkins-agent-control/quarantine.json` 并停三个 agent；之后 admission 在任何秘密绑定前拒绝。daemon 重启先重建 registry/检查遗留 unit/netns，不凭 `/run` 或 flock 消失放行。

备份保留一份已验证版本和一份候选；新候选通过后仅回收 registry 指向的旧受管备份/副本，不扫描清理其他任务目录。失败候选保留，签名 `discard-candidate` 按精确 backup ID/hash 回收后才可重试。

管理员查明原因后调用 `job-runner.py verify-and-release`；它重新清理 registry、检查 unit、netns、workspace 后才解除。流水线没有释放隔离的接口。agent role 只写 `agent-update-pending`，独立 watchdog 获锁、等当前 job 退出、重启并确认三个 node 重连后恢复接单，避免自重启正在运行它的作业。

## 凭据与回退矩阵

| 身份/材料 | 来源与owner | 消费者/范围 | 版本、轮换、回退 |
| --- | --- | --- | --- |
| Jenkins控制API | Vault；CI管理员 | 仅CT107 root admission/recovery；固定scriptText元数据与维护API | 管理员能力留在root边界，不下发agent；轮换后重查所有消费者 |
| 三 node remoting secret | 唯一 Ansible Vault；CI管理员 | 各自 root/group0440；仅 controller agent连接 | 待部署登记真实版本；重连验证后撤旧，失败保留旧入口 |
| HCP state-read | Vault；IaC owner | CT107 root producer，只有iac-proxmox-lab read | 部署前核实最小权限；不发CT110；轮换使快照重新签发 |
| HCP/provider deploy | Vault；IaC owner | peer root按Terraform stage绑定iac-deploy | 版本+keyed digest绑定manifest；变化重新计划审批，root-only SCM材料可放root_only_credentials并同样绑定 |
| Ansible SSH/Vault | Vault；各服务owner | 刷新scope批准后临时绑定iac-deploy | scope/版本变化审批失效；保留上一验证入口 |
| CT106 SSH/Google | 私有应用owner的Vault消费者 | iac-apps对应批准stage；validation无此材料 | 应用owner回传版本/消费者/撤旧/兼容回退；SCM身份不继承此能力 |
| producer/admission/recovery签名key | Vault、root-only；CI管理员 | root控制服务；公钥版本化 | key ID变更后重新签发/演练；撤销旧公钥使旧证据无效 |
| mTLS root/remoting、恢复SSH | Vault；CI管理员 | root-only或对应remoting组；来源/forced command限定 | 分别轮换；核实所有消费者再撤旧，不能复用部署身份 |

root source 的 SCM 只读密钥/known_hosts 也由 Vault 供应，固定在 root-owned bare Git 配置；它不复用 CT106 发布密钥。

待部署记录每项真实 owner、版本ID、消费者、更新顺序、重叠窗口、验证与撤旧/回退兼容版本。本库不写秘密值；空的待验证项阻止相应入口和 controller=0。

## 本地验证与上线记录

代码验证专用 Sandbox：`iac-codex-jenkins-peer-recovery-direct-v130`。它是 linux_arm64，Kit Terraform1.14.9 / Ansible-core2.20.10；另外在任务临时路径校验官方 Terraform1.14.4，SHA256 `dcbc9d4b9fcd47e76ae194d5d569bfbf9f15bf1c59ca692aff6d2a92eb8e8994`。这不替代 CT110 linux_amd64、Java25/Ansible2.19.12 的部署兼容与峰值实测。

生产验收尚未执行：IPAM/provision、真实 secrets、namespace/cgroup内核能力、五 job 调度、应用补丁、停服/恢复、重连/二次幂等与归零。AD-9 的实际记录留在获批部署时补入，未执行不能写通过。

## 修订后的控制服务约束

runner 在回复 start 前写入 used/run registry，status 可以立即返回 starting。同一身份至多保留四条未成帧连接，读请求一秒期限；状态/abort 不等待 controller 审批 RPC。所有 job report 都以 nofollow、nonblocking、普通文件、UID 和 64KiB 限制读取，部分 JSON 暂视为未准备好。entry 使用 root 在 unit 启动前刚续签的 lease，绑定原 admission 的 job/build/SHA/UID/scope/bundle，旧准入时间不能替代当前时间。

admission 每连接 TLS 握手和读请求限三秒，最多16个 worker；每个 registry 读改写在同一个持久锁内。审批重复调用返回原有效授权，不丢其他 stage。每个 bundle 上限256MiB、最多8个未结束 run；完成通知或原固定执行期限到期后删除本 nonce 的 archive、projection 与 snapshot。准备阶段也先登记900秒期限，以便服务重启回收。小型终态审计最多1000条/七天；源 Git、凭据目录和其他任务不在回收范围内。断线后 peer 清理会通知 complete；若通知失败，controller 的定期回收仍按原期限执行。

部署前先验证完整 TLS 链、私钥配对、client/server 用途、server 的固定 .107 IP、remoting/root 证书 CN 及精确三身份证书集合、root binding basename，以及单行单条且与私钥相配的 recovery 公钥。broker 的 `jenkins_plan_gateway_tls_certificate`、`jenkins_plan_gateway_tls_key`、`jenkins_plan_gateway_tls_ca` 均须为明确绝对路径，对应内容由 Vault-backed secret_files 提供；admission policy 的 certificate/private_key/peer_ca 同样预检。空值、错误 UID 名或多行 authorized key 在写秘密前失败。

agent 的 `jenkins_agent_root_certificates` 还须包含有效的公开 `broker-ca.pem`，安装到 `/etc/jenkins-agent/control/broker-ca.pem`。root runner 只为 plan 将该 CA 复制到只读 control 文件；`plan-task.py` 为 Terraform 显式设置 `SSL_CERT_FILE=/job/control/broker-ca.pem`，使干净 Debian 上的 provider 能验证内部 broker。该文件不含客户端私钥，也不依赖调用者的 CA 环境变量或全局信任库修改。

controller tuple 包含根配置 XML、jobs/nodes/users 的 config.xml、凭据/加密材料、真实 `JENKINS_HOME/casc`、启动 Groovy 和 service overrides；排除 queue、node monitor 和 build XML。恢复 fence 是受管维护状态，不进入应用配置摘要。备份 promotion 先持久提交新 verified 引用再回收旧受管目录；中断后 helper 在控制面锁内重入回收。HOME/service 替换失败会撤回已完成的移动。export 只接受当前停服 tuple 的受管 candidate，或显式 allow_verified 的 verified，且 nonce 只能消费一次。

JCasC 重复 Ansible 先只读比较所需核心版本、受管 plugin SHA、渲染后的配置字节和目录/文件权限。完全相同时短路，不消费旧 gate；任何新写入仍必须通过新的单次签名授权。normal=0 的 gate policy 必须填写 `migration_inputs`，精确覆盖五 job 的当前获准 build/source SHA；运行 job 还绑定 UID、scope、credential_versions 和 profile_sha256，Router 绑定脚本摘要且必须 SUCCESS。cleanup 需要五个固定字段严格为 true；一份包含三类事实的 receipt 可同时引用。

peer IaC 入口保留10次构建、ANSI/时间戳和可读阶段摘要。变更分类由 controller 对固定 commit 的 Git 对象生成并签名；删除保留，已删除 playbook 不执行，broad/unmatched 需要 root 审核的 explicit_scope。controller 和未经批准的 agent 范围在任何工具调用前拒绝。可选 Notion 同步默认关闭；开启时 admission profile 与 wrapper trust 的 notion 配置必须相同，固定 destination=https://api.notion.com、database_id 和 integration:notion scope，将目的地/范围纳入 Ansible 审批摘要。root 只在该审批之后的 notion stage 临时绑定 notion-token/notion-database-id，网络仍使用明确 peers/hosts；同步执行在 job unit 内，失败保留既有非阻断结果语义。无需运行时安装依赖。

本地安全套件通过现有 `scripts/ci/validate-repository.sh` Python 分支执行；角色的合成 shell/TLS/rescue/no-op fixture 由现有 Ansible 验证入口执行。另行在任务 Sandbox 运行真实集成：

```bash
python3 tests/ci/jenkins-peer-provider-test.py --terraform /tmp/jenkins-peer-terraform-1.14.4/terraform --mirror /tmp/jenkins-peer-schema/.terraform/providers
python3 tests/ci/jenkins-inventory-scope-test.py --terraform /tmp/jenkins-peer-terraform-1.14.4/terraform --mirror /tmp/jenkins-peer-schema/.terraform/providers
```

这些使用假上游、合成 Vault 和临时文件；真实 Jenkins、CT110 内核隔离、amd64 离线安装与恢复演练仍须独立授权及实测。

remoting unit 额外要求 root 管理的 `/run/jenkins-agent-remoting-ready`；runner 启停先清该标记，只有 reconcile 后没有 quarantine/incomplete/pending/maintenance fence 才恢复。watchdog 仅在获准的重连阶段设置该标记。角色先完成 staging 再首次启动 runner；已有 runner 的变更只排异步维护，pending 本身阻断下一 admission。初次安装不为尚未运行的旧 runtime 排更新。

恢复目录替换从解包前就持久登记 restore journal。helper 在控制面锁内先重建未提交的 HOME/service 移动；已提交且启动/健康/tuple 通过的恢复先记录完成 receipt，再仅回收精确 previous/staging。进程在任何一次 rename 或持久提交后被终止都可重入；同一完成恢复仅在仍 quiet 且匹配旧 tuple 时幂等返回，恢复写入后拒绝重放。

## 父级复验后的阶段与隔离修复（2026-10-22）

`jenkins_agent_activate=false` 的 Verify 保留三 UID/0700 目录和 privilege boundary 检查，另验证 root 所有的 unit/JAR 已安装且权限正确、三个 remoting 无运行进程、runner/service socket 不活动、remoting-ready 不存在。刚写入 unit、尚未 daemon-reload 的 not-found 状态只有在磁盘安装文件通过检查且不接单时接受。activate=true 才断言三个服务 active/User 正确；Verify 不启动服务，也不使用 skip-tags。实际 Ansible Verify 夹具覆盖 staged、active、尚未 reload，以及运行中 agent、监听 socket、ready 残留和缺 JAR 等拒绝情况。

admission 的 global registry 锁只用于原子占用最多8个 run 名额、读取和提交记录；git fetch、source archive、projection、签名准备等在锁外执行。已存在 run 使用各自 nonce flock，保证同 nonce 审批读改写原子，同时让其他 nonce 的 lease 独立前进。accept 主循环只提交单个 GC worker；GC 尝试非阻塞 global 锁，忙时等待下一次周期。阻塞假 source 准备时，另一 run 的真实签名 lease/status 在一秒内返回，配额仍保持原上限；重复审批与过期回收反例仍通过。

同 UID 的 remoting/job 即使有私有 mount 和 hidepid=2，也可通过 `/proc/<pid>/root` 绕回另一进程的根，复制文件到本 run 外。因此 transient unit 增加 `PrivateUsers=yes`。按 [systemd252 的 PrivateUsers 语义](https://www.freedesktop.org/software/systemd/man/252/systemd.exec.html#PrivateUsers=)，由 root 创建独立 user namespace，再保持 unit UID/GID 自映射；三个现有 Unix 身份保持不变。job probe 必须确认 user/net/ipc/mnt namespace 均不同，并拒绝读写 remoting 的 proc-root 非秘密金丝雀。root 随后以同 UID、原 user namespace 的受控 helper 验证反向 job proc-root 读写也被拒绝，前后确认两个 PID 与两份金丝雀真实存活。hidepid 产生的 ENOENT 仅在这些 root 存活检查下视为拒绝；其他异常失败并隔离，任何阶段秘密都在双向检查通过之后绑定。金丝雀使用相同的有界、nofollow、nonblocking 文件读取，cleanup 只回收本 nonce 的精确 probe 文件。

在指定 Sandbox 显式执行下面的真实内核反例，使用现有 sudo/unshare 和临时合成文件：

```bash
python3 tests/ci/jenkins-proc-root-test.py
```

控制组保持 root:root/000/只读 mask、hidepid=2、NoNewPrivileges=1、CapEff=0，仍能双向 proc-root 读写且留下合成残留；先由 root 创建 userns、映射 0→0 与原非 root UID→自身后，实际 probe 的双向读写均拒绝，合成残留为 false。此结果验证当前 Sandbox 的机制，不能替代 CT110 上 systemd/LXC 的实际验收；不支持 userns 或任何 probe 不通过时拒绝绑定秘密，不能静默降级。

## 第二轮实现修订

- 首个peer的agent base/config/JAR目录和controller HOME下casc路径是固定运行契约；不支持的变量覆盖在写配置前拒绝。activate=false若遇到活动runner同样拒绝，需通过获准维护停机后再stage。activate=true重跑发现停止的agent会排队独立维护，不在当前job内重启runner；维护完成后再跑verify。
- runtime材料检查所需openssl/SSH工具在已有安装授权下先准备，再验证TLS/SSH，最后写秘密。admission policy的`server_ca`是明确绝对路径，用于验证server证书；`peer_ca`只定义客户端信任，可与server CA不同。agent的trust文件可包含所需公开CA链。
- admission TLS握手、HTTP headers和body读取共用3秒截止时间；读完即取消，源归档等有界业务准备不受该读期限误杀。controller和runner都拒绝非整数或不在1..3600秒内的执行timeout，控制记录再保留900秒余量。
- 成功run先落签名证据和结果，complete通知异常由保留期限兜底。Notion默认关闭；启用后同步传输失败或ready超时只记录同步failed，部署结果保留；凭据版本/范围异常仍拒绝。ID/token尾换行按文本凭据处理。
- controller tuple纳入根级XML配置但排除queue.xml/nodeMonitors.xml运行态；no-op还核验恢复helper的字节、root所有权和0500权限。新实测candidate可替换损坏旧verified；损坏旧档以quarantined引用保留，须管理员另行核查，不能自动当作普通retired资料删除。
