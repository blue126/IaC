# Architecture Spine 评审：IaC CI-Only Execution

**结论：不通过。** 这份 spine 对 ticket 的主线覆盖较完整，但存在 1 个 critical 和 4 个 high 问题：AD-14 与 `terraform/oci` 的实际内容直接冲突，inventory、锁和 watermark 这几个关键分歧点也没有定死或与现有代码相悖。

**本次未覆盖的范围**
- 未读 `docs/guides/jenkins-agent-bootstrap.md`，未检查 `docs/architecture/ci-only-execution-architecture.md`，因此没有核对这两份文档与 spine 是否一致。
- 未读 `terraform/oci/oci-hub-ingress.auto.tfvars.json` 和 `ansible/inventory/terraform-remotecc.yml` 的内容，只确认了文件存在。
- 未检查 `terraform/proxmox` 是否含 RemoteCC 对象。
- 未执行任何代码。线上 Jenkins、GitHub ruleset 和 HCP 的状态均未验证。

## 逐项结果

| # | 清单项 | 结果 | 说明 |
|---|---|---|---|
| 1 | 固定下层真实分歧点，无遗漏 | **finding** | F-02、F-03、F-04、F-06、F-07、F-08 |
| 2 | 每条 AD Rule 可执行且能防住所述分歧 | **finding** | F-01、F-05、F-11、F-12 |
| 3 | Deferred 不会让两个单元分歧 | **finding** | F-05、F-13 |
| 4 | 具名技术已验证为最新 | **not executed** | 无 web 访问，由其他 reviewer 负责 |
| 5 | 追认而非违背 brownfield | **finding** | F-01、F-02、F-03、F-04、F-10 |
| 6 | 覆盖 ticket 全部要求 | **finding** | 见下表，以及 F-14、F-15 |
| 7 | 不弱化继承的 parent spine | **not executed** | 无 parent spine，此项不适用 |
| 8 | 本层级维度都已决定、推迟或列为开放问题 | **finding** | F-08、F-09；Open Questions 写 "None" 也不成立，见 F-15 |

**Ticket 覆盖情况**

| 要求 | 对应 AD | 结果 |
|---|---|---|
| R1 | AD-10 | 覆盖 |
| R2 | AD-11 | 覆盖 |
| R3 | AD-5 | 部分覆盖，未要求"明确报告盲区"（F-15） |
| R4 | AD-9、AD-10、Entry cutover | 基本覆盖 |
| R5 | AD-2 | 覆盖，但 PR 定义来源约束缺失（F-14） |
| R6 | AD-4 | 与 AD-14 冲突（F-01） |
| R7 | AD-7 | inventory 来源不完整（F-02） |
| R8 | AD-6 | 覆盖，但 controller 类 playbook 没有合法归属（F-06） |
| R9 | AD-3、AD-13 | 覆盖 |
| R10 | AD-1、AD-9 | 规则已写，但无法强制（F-05）；另多出 watchdog 例外（F-15） |

## Findings

### Critical

#### F-01：AD-14 禁止触碰 OCI hub，但 Jenkins 被要求接管包含 hub 资源的 `terraform/oci`
- **位置：** AD-1、AD-4、AD-14；`terraform/oci/oci-hub.tf:27-52`
- **问题：** AD-14 规定 Jenkins 绝不针对 OCI hub，AD-4 又让 Jenkins 独占 `terraform/oci` 的写入。Ticket 的 Done-when 还要求 Jenkins 对该 root 完成一次获批 apply。两条规则无法同时成立。
- **证据：**
  - `terraform/oci/oci-hub.tf:27-32` 定义 `oci_core_network_security_group.oci_hub`，`:39-52` 定义 WireGuard 入站规则，端口 51824 和 51825，来源包含 workspace 网段。
  - 同目录有 `oci-hub-ingress.auto.tfvars.json`。
  - Hub play 与非 RemoteCC play 共用同一主机 `oracle-cloud-ubuntu2404`：`configure-oci-hub-portal-public.yml:3`、`update-oci-hub-authority.yml:3`，以及 `deploy-anki-oci.yml:18`、`deploy-bookorbit-oci.yml:3`、`deploy-unified-proxy.yml:21`。
  - AD-1 只排除了 hub 的 play，没有排除 `terraform/oci` 里的 hub 资源。
- **建议：** 二选一并写入 AD-14。
  - 把 hub 资源迁到 `terraform/remotecc`，作为 OCI apply 的前置条件。
  - 或声明这些资源由 `iac-oci` 持有，Jenkins 是其 owner，并收窄 AD-14 的 "OCI hub" 定义。
  - 同时把 `oracle-cloud-ubuntu2404` 明确列为共享主机。

### High

#### F-02：Inventory 契约漏掉两个现存来源，Jenkins 可能依赖 RemoteCC state
- **位置：** AD-7、AD-4、AD-14、Structural Seed 的 `ansible/inventory/`
- **问题：** Spine 把 inventory 描述为 "Terraform-backed Proxmox plus static OCI"，实际还有 `bare_metal` 和 RemoteCC 来源。按 Ansible 对目录型 inventory 的处理，两者都会被加载。
- **证据：**
  - `ansible/ansible.cfg:6` 为 `inventory = inventory`。目录下有 `bare_metal/hosts.yml`、`oci/hosts.yml`、`terraform.yml`、`terraform-remotecc.yml`。
  - `transaction.py:100` 在 `workspace/ansible` 运行 `ansible-inventory --list`，走的是这份目录配置。
  - `scripts/refresh-terraform-state.sh:11` 的 `ALL_WORKSPACES` 含 `remotecc`。
  - `transaction.py:71-96` 只解析 `terraform/proxmox`，目标缺失时在 `:91` 拒绝。而 `deploy-caddy.yml:3` 的目标是 `pve0`，`upload-snippet.yml:3` 的目标是 `proxmox_cluster`；OCI 静态主机也不在这条解析路径内。
- **建议：** 在 AD-7 中列全允许的 inventory 来源，并规定 Jenkins 使用排除 `terraform-remotecc.yml` 的固定 inventory 集，且不持有 `iac-remotecc` 的读取能力。同时定义 `bare_metal` 主机的 lock key 和归属。

#### F-03：全局锁、细粒度锁与等待语义互相打架，且与现有 runner 相反
- **位置：** AD-4、AD-10、Concurrency 约定
- **问题：**
  - AD-10 要求所有身份一次只跑一个 job，且"busy runner 绝不拒绝"。现有实现是直接拒绝。
  - Spine 没有决定全局锁在人工审批期间是否释放。不释放时，AD-4 的 key 锁在 peer 上永远不会发生竞争，一次待审批事务还会阻塞 plan 和 apps。释放时，AD-10 的"先锁后绑定秘密、逐个运行"就不再成立。
  - 队列上限、队列归属（Jenkins 还是 runner）、等待超时都没有定义。
- **证据：**
  - `job-runner.py:120-121` 抛 `peer is busy or fenced`；`:280-284` 用 `LOCK_NB` 取全局锁，失败即 `Refused`。
  - `Jenkinsfile-peer:31`、`Jenkinsfile-plan:23` 把 `refused` 当失败。
  - 审批发生在 job 内部（`transaction.py:214,230`），每次最长 900 秒（`:213,228`）。
  - `Jenkinsfile-plan:6` 超时 20 分钟，`Jenkinsfile-peer:10` 超时 60 分钟。
  - 在 `scripts/jenkins/` 内 6 个控制脚本的定向搜索中，未发现按 `root:`/`host:` key 取锁的实现。`ci/agent-jobs.yml:25` 与 `transaction.py:108-110` 使用的是 `service:`、`control-plane:` 这类 scope。
- **建议：** 明确全局锁在审批期间的行为，定义队列位置、上限、超时和溢出结果，并让这些值与 Jenkins 超时兼容。在 Structural Seed 中标明 runner 和 Jenkinsfile 的拒绝语义需要修改，并写明现有 scope 名到 canonical key 的映射。

#### F-04：`last_verified_sha` 的存储和种子值都没有定义，现有基线也无法提供
- **位置：** AD-6
- **问题：** 这个 watermark 是"失败构建不丢变更"的核心保证，但 spine 只写了 "stored durably"，没有指定存储位置和写入者，也没有说明它如何与 controller 回滚交互。AD-4 明确写了 lock store，这里没有。"种子取基线已验证的最后 commit"也缺少数据来源。
- **证据：**
  - `Jenkinsfile:28,49` 用 `HEAD~1` 比较，不记录已验证的 SHA。
  - `Jenkinsfile:341-357` 的部署阶段没有单独的 verify 记录。
  - `controller-admission.py:215-218` 只比较单个 commit 与其第一父提交。
  - 新增 playbook 没有初始 watermark，unmatched 路径也不属于任何 root 或 playbook，这两种情况的选择范围没有定义。
- **建议：** 指定唯一存储、写入者和签名方式，定义新 playbook 与 unmatched 路径的处理。规定 CT107 回滚或 CT110 丢失时 watermark 只能保持或回退，不能前进。再定义一个由人工确认的 cutover 种子流程。

#### F-05：本地禁写只靠流程约束，且 Deferred 引用的决定在决策文件中找不到
- **位置：** AD-1、AD-5、Deferred 第 6 条
- **问题：**
  - AD-1 声称防止未审查的工作站变更，但 AD-5 承认 Mac 保留全部凭据，Deferred 也放弃了技术限制。这样一来，移交后本地写入既绕过 Jenkins 的事务锁，也不会被任何机制发现。
  - AD-1 把 `ansible-playbook --check --diff` 列为只读，这一点也不成立。
  - Deferred 写该限制 "declined on 2026-11-05"，但 `decisions-2026-11-05.md:18` 只写了"允许本地只读 plan，不允许写"，没有记录这次否决。
- **证据：** `check_mode: false/no` 在 `ansible/` 下有 89 处，分布于 33 个文件，例如 `deploy-netbox.yml` 6 处、`configure-pve2-local-ssd.yml` 7 处。这些任务在 `--check` 下仍会真实执行。我没有逐条判断它们是否都只读，所以这只说明 `--check` 不能作为只读保证。
- **建议：**
  - 让用户确认这项否决并把它写入决策记录。
  - 增加检测型控制，例如核对 HCP state version 是否都能对应到 Jenkins 构建，发现不匹配就告警。
  - 把本地 Ansible 的 dry run 收窄为经审计可用的 playbook 清单。
  - 修改 AD-1 的 Prevents 措辞，使其与实际能力一致。

### Medium

#### F-06：执行映射的 owner 枚举放不下 control-plane playbook
- **位置：** AD-1、AD-6、AD-11、AD-13
- **问题：** Owner 只有 `jenkins`、`maintenance`、`remotecc`、`retired`。CT107 上的 playbook 归入 `jenkins` 会被 runner 拒绝，归入 `maintenance` 又可能由运行中的 pipeline 改动 controller，违反 AD-11。AD-6 的 maintenance 模式也没有 controller 或 watchdog 模式。AD-13 的隧道规则后续变更同样没有合法路径。
- **证据：** `deploy-jenkins.yml:3`、`upgrade-jenkins.yml:3`、`deploy-gitea.yml:3`、`deploy-cloudflared.yml:3` 都以 `jenkins` 为目标；`transaction.py:108-109,241` 拒绝这类范围。
- **建议：** 增加 `control-plane` owner，定义其入口。同时说明 Gitea 与 cloudflared 这类同住 CT107 的服务如何变更。

#### F-07：Notion 同步这条现存外部写入路径完全没有提及
- **位置：** AD-5、AD-7、Consistency Conventions
- **问题：** Spine 没有决定 Notion 同步是保留、退役还是推迟。它也没有说明这个步骤算不算 Verify 之后的事务内步骤，失败如何影响结果。
- **证据：** `Jenkinsfile:359-374`；`transaction.py:149-167,246`，其中 `:164-165` 还会用到 Vault 密码；`docs/architecture/cicd-architecture.md:481-503`。
- **建议：** 增加一条决定，写明范围、凭据阶段、失败语义和审批摘要中的呈现方式。

#### F-08：OCI 与多 root 事务没有定义，现有实现全部是 Proxmox 单 root
- **位置：** AD-2、AD-5、AD-6、Plans 与 Approval 约定
- **问题：**
  - Proxmox 和 OCI 同时变更时，是一条审批绑定多份 manifest，还是每个 root 一条审批，没有定义。"Two separate records" 与 "One saved plan per root" 无法直接组合。
  - `IaC-ReadOnly-Plan` 是否支持 OCI 也未决定。
  - CT110 到 OCI 的网络路径和 SSH 身份未定义。
- **证据：**
  - `transaction.py:176,211,222` 写死 proxmox。
  - `ci/agent-jobs.yml:15,25` 的 scope 只有 proxmox 和 n8n。
  - `Jenkinsfile-plan:9` 只有 `proxmox`。
  - `ci/agent-toolchain.lock.json:4645` 绑定 proxmox 的 provider lock。
  - `ansible/inventory/oci/hosts.yml:4-5` 使用公网地址和 `ubuntu` 用户，而 `ansible.cfg:7` 默认 `root`。
- **建议：** 定义多 root 审批模型、部分 apply 后的审批失效规则、OCI plan 的支持边界，以及 peer 的 OCI 出口与身份。

#### F-09：运行环境与运维维度缺口
- **位置：** 全文。Open Questions 和 Deferred 都没有收录这些事项
- **问题：** 下列事项既没有决定，也没有推迟：
  - **环境策略：** 只有 production、没有 staging 的现状未写入（`cicd-architecture.md:760-767`）。
  - **容量：** 2 GiB 的 CT110 还要承载 OCI 工作负载，recovery 规格的内存预算（`jenkins-peer-agent-recovery.md:105`）未被 spine 继承。CT107 的 16G 磁盘（`cicd-architecture.md:193`）也未评估 200 构建保留量。
  - **Quarantine 运维：** 现有代码和规格都有隔离与人工解除机制（`job-runner.py:81-105`、recovery `:95`），spine 只要求"证明清理"，没有定义失败后的运维路径。
  - **CT110 丢失：** 按 AD-4，锁 registry 存放在 peer 上，却没有备份和重建规则。
  - **凭据轮换：** AD-5 标题写 lifetime-bound，但全文没有任何有效期或轮换规则，webhook secret、HCP token、OCI key 都没有覆盖。
  - **CI 自身监控：** Jenkins 宕机时 Mailer 也无法通知，没有独立告警。
- **建议：** 增加 AD 或写入 Deferred 和 Open Questions，至少覆盖环境、容量上限、peer 状态恢复、轮换和外部健康告警。

#### F-10：AD-11 与 Notification 依赖的配置和插件未被现有 pin 覆盖
- **位置：** AD-10、AD-11、AD-13、Notification 约定
- **问题：** AD-11 指定 JCasC/Job DSL 为配置 owner，AD-10 要求 BOM 拥有 pin，但这些插件 id 在 BOM 中都找不到。JCasC 模板也没有 Mailer 或 webhook secret 配置。
- **证据：**
  - 在 `ci/toolchain-bom.yml` 中搜索 `job-dsl`、`generic-webhook`、`ansicolor`、`timestamper`、`pipeline-input`、`pipeline-model`，结果均为 0。
  - `Jenkinsfile-peer:7-8` 使用 `timestamps()` 和 `ansiColor`。
  - `Jenkinsfile-webhook-router-peer:10` 使用 `GenericTrigger`。
  - `ansible/roles/jenkins/templates/jenkins.yaml.j2` 中搜索 `mailer`、`smtp`、`hookSecret`、`githubPluginConfig`、`jobs:`、`securityRealm`，均无命中。
- **建议：** 补齐 BOM，或写明 BOM 的实际覆盖边界。把 SMTP 和 webhook secret 列入 AD-11 的 restore gate，并为"JCasC 采纳 AD-13 配置"设定验证项。

#### F-11：AD-12 的"事件不可触发变更"依赖下游 job 不存在，而不是路由本身
- **位置：** AD-12
- **问题：** Router 仍会发起下游构建。只要有人创建同名 job，NetBox 事件就能启动它。规则没有说明由什么机制阻止这件事。
- **证据：** `Jenkinsfile-webhook-router-peer:76-92` 调用 `Proxmox-Provisioning` 和 `Physical-Device-Sync`，且传入事件字段；`ci/agent-jobs.yml:36-38` 保留这些路由。
- **建议：** 让 router 在推迟期内只记录不转发，或用 Job DSL 校验禁止这些下游存在，并加入合约测试。

#### F-12：AD-14 的"确认另一侧空闲"没有留下任何记录
- **位置：** AD-14、Approval 约定
- **问题：** "Whole-host operation"没有定义，确认动作也不进入审批摘要，事后无法审计。AD-9 的 "preferably" 同样不可判定。
- **建议：** 在 execution map 中标记共享主机和 whole-host 操作，要求把确认写入 Ansible 审批摘要。把 "preferably" 改为有明确条件的规则。

#### F-13：Deferred 的共享代码分离会让两个执行面在同一 `main` 上发生漂移
- **位置：** Deferred 第 5 条、AD-3、AD-6
- **问题：** AD-6 的 `shared` 类只约束 Jenkins 一侧。`/srv/iac` 会快进到 `origin/main`，于是同一次合并在 RemoteCC 和 Jenkins 上的生效时间可能不同，且没有跨面记录。
- **建议：** 至少规定 `shared` 变更的合并要求，例如同时记录 RemoteCC 侧的处理状态，并把它写入 execution map。

#### F-14：审计存储与 PR 约束存在缺口
- **位置：** AD-2、AD-9、Audit 约定
- **问题：**
  1. Jenkins 构建记录是唯一审计存储，但 AD-9 事件恰恰发生在 Jenkins 不可用时，AD-11 回滚也可能丢失备份点之后的记录。
  2. Ticket 要求保留 200 个构建的审计能力依赖新配置，而现有 Jenkinsfile 只保留 10 个（`Jenkinsfile:13`、`Jenkinsfile-peer:9`）。
  3. Ticket 约束要求"PR 流水线定义来自受保护的 `main`"，但 `repo-validation.yml:3-4,27` 走 `pull_request` 并检出 PR head，spine 没有处理这条约束。
  4. `repo-validation` 成为 required check 的时机没有绑定到移交 gate。
- **建议：** 指定 AD-9 记录的独立落点和回滚后的审计对账方式，并把保留数写入 Seed 的变更项。说明 PR 约束的处理：要么修订约束，要么由受保护定义校验。把 required check 列为 main lane 移交的前置 gate。

### Low

#### F-15：小型一致性问题
- **位置：** AD-1、AD-5、Entry cutover、Open Questions、Structural Seed
- **问题与建议：**
  - **例外清单：** R10 只允许 AD-9 和 `wsctl` 两种例外，AD-1 增加了 watchdog。应在 ticket 或 AD-1 中对齐。
  - **旧入口：** Entry cutover 在验证期禁用旧入口，而 ticket 要求"旧入口不下线"，recovery S8 要求失败时保留上一个已验证入口。应补充失败回退规则。
  - **开放问题：** Open Questions 写 "None"，但决策文件 `:19` 写着线上状态"待登录确认"。应列入。
  - **R3：** AD-5 没有要求明确报告盲区，应补上。
  - **授权边界：** CT110 部署和真实密钥使用的单独授权未写入，只提到了归零和 ruleset。应补全。
  - **Seed：** `ci/execution-map.yml` 的注释漏了 `shared` 类，应修正。