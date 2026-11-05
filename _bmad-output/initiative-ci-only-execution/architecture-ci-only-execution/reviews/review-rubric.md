# Rubric 评审：IaC CI-Only Execution 架构脊柱

- 日期：2026-11-05
- 评审对象：`.worktrees/ci-only-architecture/docs/architecture/ci-only-execution-architecture.md`（工作区未提交版本，与 `architecture-ci-only-execution/architecture-ci-only-execution.md` 逐字相同）
- 依据优先级：`decisions-2026-11-05.md` 与 `initiative-ci-only-execution.md` 最高，其次 `docs/planning/jenkins-peer-agent-recovery.md`（peer 规格）和 `AGENTS.md`
- 只读评审：没有改动脊柱或任何仓库文件

## 结论

**需要修订，暂不能作为 epic 的绑定基线。**

方向正确，决策 1–5 的主体都落地了：GitHub 权威、范围收窄、AD-1 移交后生效、同一运维者两条审批记录、AD-13。AD-2、AD-3、AD-5、AD-8、AD-10 基本可以直接约束下层。

但有 5 个阻断项。其中 3 个会让两个 epic 各自做对、合起来出错：

| # | 问题 | AD | 严重度 |
|---|---|---|---|
| F1 | 移交点定在 executor 归零，但 OCI 和维护通道都还不存在；AD-9 的措辞与 peer 规格矛盾 | AD-1、AD-9 | 阻断 |
| F2 | HMAC 必须最先做，却被 JCasC 和 controller 变更门禁挡住；顺序没有写进脊柱，校验默认失败开放，隧道路径也不是精确匹配 | AD-13、AD-11 | 阻断 |
| F3 | 变更检测基线未定义，代码只比较第一父提交，失败或合并的构建会静默漏部署 | AD-6、AD-2 | 阻断 |
| F4 | OCI 只写了一行映射，没有设计：inventory 刷新是空操作、凭据来源未定、与 `wsctl` 共享主机却没有共享锁 | AD-4、AD-5、AD-7 | 阻断 |
| F5 | 审计记录不持久；`iac-apps` 和 controller 维护不在任何通道里 | Conventions、AD-1、AD-2、AD-11 | 阻断 |

## 阻断项

### F1. 移交点早于 OCI 和维护能力（AD-1、AD-9）

**事实**

- AD-1 把移交定义为“controller executors reach 0 under the peer specification”。这一刻 Jenkins 独占写权限，本地写操作被禁止。
- 第一个 epic 是 peer 的 S1–S8（决策 5），它只覆盖 Proxmox。
  - `ci/agent-jobs.yml` 的 `IaC-Homelab-Pipeline` scope 只有 `root:proxmox`，凭据只有 `hcp-proxmox-deploy`、`proxmox-deploy`。
  - `scripts/jenkins/transaction.py` 把 root 写死为 `terraform/proxmox`，manifest 写死 `'root':'proxmox'`。
  - 它的 `classify_changes` 把 `terraform/oci/*` 判为 unmatched。
- `Jenkinsfile-maintenance` 和 `ci/execution-map.yml` 在 Structural Seed 里都标着“To add”，也不在 S1–S8 内。

**后果**

归零之后、OCI 和维护 epic 落地之前：

- OCI 变更、Terraform import/state/destroy 和手动 playbook 都没有合法入口；
- AD-7 把未修复的 playbook 定为 maintenance-only，它们同样没有入口；
- AD-9 明确“No later feature or configuration change qualifies”，所以例外也走不通。

下层只有两种做法：把 OCI 和维护塞进第一个 epic，或者在禁令下继续本地写。两者都与脊柱不一致。

**AD-9 的两处矛盾**

- AD-9 写“after verification, controller execution is disabled”。peer S7 和 initiative 要求的是真实恢复证据、全部 job 映射、幂等验证，再单独批准，才能归零。按 AD-9 字面读，peer 验证后就能归零。
- AD-9 的记录义务以“After handoff”开头，但首次 bootstrap 发生在移交之前，而 peer S1 和 S5 要求这次引导按 AD-9 留记录。字面上这条义务管不到它要管的那次操作。

**修复**

1. 在 AD-1 里把移交拆成两层，二选一写死：
   - 方案 A（推荐）：移交按 root 和能力生效。`terraform/proxmox` 及其 playbook 在归零并获批时移交；`terraform/oci` 在第一次 Jenkins 获批 apply 后移交；import、state、destroy 在 maintenance lane 通过后移交。此前该项继续按 `AGENTS.md` 本地执行。
   - 方案 B：归零推迟到 OCI 和 maintenance lane 都可用。这会与“第一个 epic 是 S1–S8”冲突，需要用户改决策。
2. AD-9 把“after verification, controller execution is disabled”改成“归零只按 peer S7 的 gate 和单独批准执行”。
3. AD-9 第一句改为“首次 bootstrap（无论是否在移交前）和移交后的已声明灾难恢复都必须留记录”，并写明记录存放位置。

### F2. HMAC 排最前，但脊柱里走不通（AD-13、AD-11）

**事实**

- 决策要求 HMAC 列入第一个 epic，排在最前面，因为公网入口当前可能已经在触发流水线。脊柱全文没有这条顺序。
- HMAC 是 GitHub plugin 的全局配置（`hookSecretConfigs`），属于 controller 配置变更。
- 配置通路目前是关的：
  - `ansible/inventory/host_vars/jenkins.yml` 和 role defaults 都是 `jenkins_manage_casc: false`，注释写明等 watchdog 和实测备份就绪。
  - peer S5：未得到真实证据前不启用 JCasC 变更。
  - AD-11：JCasC 在 restore gate 通过后才接管。
  - R2：没有有效证据时 controller 变更被拒绝。
- 也就是说 HMAC 要排在 S1 之前，而它依赖的 gate 在 S5 之后。下层要么违反 R2，要么违反决策。

**校验失败开放（已核对插件源码）**

GitHub plugin v1.47.0 的 `RequirePostWithGHHookPayload`：“If no hook secret is configured, then the signature is ignored”。默认算法是 SHA-256，所以 AD-13 的 HMAC-SHA256 技术上可行。但只要 `hookSecretConfigs` 为空，所有请求都放行。

这对 AD-11 的恢复流程有直接影响：恢复一份 HMAC 之前的备份，或者 JCasC 渲染出空列表，都会悄悄回到无校验状态，而 AD-13 没有任何东西能发现。

**路径不是精确匹配（已核对 Cloudflare 文档）**

`host_vars/jenkins.yml` 的 `path: /github-webhook/` 在 cloudflared 中是正则，未锚定，所以 `/x/github-webhook/y` 也会到达 Jenkins。AD-13 写的是“every other path returns 404”，现有配置不满足。脊柱把这件事写成既成规则，下层容易认为无事可做。

**切换顺序未定**

GitHub 端和 Jenkins 端先改哪边没有规定。Jenkins 先配会让合法 delivery 被拒；GitHub 先配则继续不校验，这一侧是安全的过渡。

**修复**

在 AD-13 增加：

1. “本规则最先落地，先于 S1。这是 R2、AD-11 门禁的唯一具名例外：只改 `hookSecretConfigs` 这一项，不重启或走已批准的最小重启，变更单独授权并留 AD-9 式记录。JCasC 启用后接管同一配置，Vault 为来源。”若用户不接受例外，则改决策，并写明过渡期措施（例如先关闭 job 的 push trigger）。
2. 验收必须含反例：无签名和错误签名的 POST 返回 4xx 且没有构建；controller 恢复后、以及每次 JCasC 应用后重跑这个探测。secret 为空时判失败。
3. 路径改为 `^/github-webhook/$`，并用反例验证 `/x/github-webhook/` 返回 404。
4. 写明顺序：先 GitHub 配 secret，再 Jenkins 开校验，最后用一次真实 delivery 确认。

### F3. 变更检测基线未定义，AD-6 防不住它声称要防的问题（AD-6、AD-2）

**事实**

- AD-6 的 Prevents 是“silently skipping deployments”，但 rule 没有定义“changed paths”相对于什么计算。
- 当前代码：`scripts/jenkins/controller-admission.py` 的 `changed_paths` 把 SHA 与第一父提交比较（注释写 matching the legacy pipeline）；旧 `Jenkinsfile` 用 `HEAD~1`。
- 流水线有 `disableConcurrentBuilds()`。等审批期间合并的多个提交会被合并成一次排队构建。Jenkins 只构建最新 SHA，中间提交的 diff 永远不被看到。
- AD-6 的重试规则是“retry starts from observed state with a new plan and approval”，但有两种情况重试什么也不会做：
  - Terraform 已 apply，Ansible 审批过期（代码里是 900 秒）或被拒。之后的新构建若 diff 不含这些路径，Ansible 就永远不跑。
  - 构建 N 失败，构建 N+1 只改了别的文件，N 的变更被静默跳过。

**相关：批准的 SHA 可能已不是 `main` 头**

AD-2 和 Conventions 让“newer mutation”使审批失效，但 `main` 前进了不算 mutation。运维者可以 apply 一个旧 SHA 的计划，紧接着排队的构建再推进，中途存在回退窗口。

**修复**

在 AD-6 增加：

1. “变更集相对于每个 root 或 playbook 最后一次完整 Verify 成功的 SHA 计算，该记录持久保存，不依赖 Jenkins 构建保留。基线缺失时按 broad-impact 处理。”
2. “Terraform 成功而 Ansible 未完成时，该 playbook 保持待部署，直到 Verify 通过。”
3. 在 Conventions 的 Plans 里写明：审批和 apply 前检查 SHA 是否仍是 `origin/main` 头，或显式声明允许旧 SHA 并说明理由。
4. 一次构建选中多个 root 时，写明是每 root 一条审批记录还是一条记录绑定全部 manifest。AD-6 只说 root 互相独立，Conventions 只说“两条记录”。

### F4. OCI 只有映射，没有设计（AD-4、AD-5、AD-7）

R6 和 Done when 要求 `terraform/oci` 经 Jenkins 完成一次获批 apply。脊柱实际只为它写了一行表格和一句“static-inventory exception”。

**a. AD-7 的 inventory 刷新对 OCI 是空操作**

- `ansible/inventory/oci/hosts.yml` 写死 `ansible_host: 159.13.46.201`。
- `terraform/oci/compute.tf` 是 `assign_public_ip = true`，没有 reserved IP，也没有公网 IP 的 output。
- 实例被替换后 IP 会变，但静态 inventory 不变，digest 也不变。运维者批准的是一个“已刷新”的旧地址，这正是 AD-7 要防的“stale hosts”。
- `transaction.py` 的 `inventory_scope` 只解析 Terraform 来源、不读 group/host vars，OCI 主机根本进不了 scope。

**b. 凭据来源未决定**

- `scripts/get-secrets.sh` 只从 Vault 取 `vault_oci_private_key_path`，这是工作站路径，不是密钥本身。`terraform/oci` 还用 `file(var.ssh_public_key)`。
- AD-5 说 OCI 私钥是 build-scoped，但它从哪来没有定义。而 `AGENTS.md` 禁止搜索其他私钥位置，也禁止改动 `~/.oci`。
- CT110 的网络出口也只批准了 Proxmox 范围。`ci/agent-toolchain.lock.json` 里是否带 OCI provider 没有查到记录（`grep oracle|oci` 无命中），AD-10 的 provider mirror 未覆盖。

**c. 与 `wsctl` 共享主机，但锁不共享**

- inventory 里 `oci` 组只有 `oracle-cloud-ubuntu2404`。`deploy-unified-proxy.yml`、`deploy-anki-oci.yml`、`deploy-bookorbit-oci.yml` 和 `deploy-oci-hub.yml` 都打到它。
- 私有 `remotecc/wsctl/` 的 `hub-onboard.py`、`hub-terminal.py`、`hub-retire.py`、`hub-access.py` 也引用这台主机。
- AD-4 的 conflict-domain 锁只在 Jenkins 内部。Jenkins 和 `wsctl` 可以同时写同一台机器，AD-1 的“standing exception”没有回答这一点。Initiative 又规定不得改 `wsctl` 路径，所以这必须写成一条明确取舍。
- `terraform/oci/oci-hub.tf` 和被跟踪的 `oci-hub-ingress.auto.tfvars.json` 是员工入口的 NSG。按 AD-4 它归 Jenkins，私有 `wsctl` 目录里也查不到对它的引用。脊柱应明说它留在 Jenkins，以免下层按“员工相关”把它排除。

**修复**

- AD-7：增加 OCI 规则，给 `terraform/oci` 加公网 IP output，Jenkins 比对静态 `ansible_host` 与 state，不一致就在 Ansible 前停止，改 inventory 走新 PR。
- AD-5：写明 OCI 私钥内容的存放处（Vault 内容或 Jenkins 凭据，不是路径），以及 `ssh_public_key` 的来源。
- AD-1 或 AD-4：二选一写死。要么声明 Jenkins 与 `wsctl` 在共享主机上不互斥并接受风险，要么在不改 `wsctl` 执行路径的前提下给出运维约束。同时写明 `oci-hub.tf` 的归属，以及 `deploy-oci-hub*.yml`、`deploy-remotecc-ops.yml` 属于 execution map 的哪一类。
- AD-2：写明 `IaC-ReadOnly-Plan` 的 fixed root 现在只有 `proxmox`（R3 和 peer 规格一致），OCI 没有只读预测，或列入 Deferred。

### F5. 审计不持久，且两类写入不在任何通道里（Conventions、AD-1、AD-2、AD-11）

**审计**

- Conventions 的 Identity 和 Approval 要求每次运行记录 SHA、范围、审批人。决策 4 把“两条独立记录”当作同一运维者审批的唯一保证。
- 但脊柱没有说这些记录存在哪里、保留多久。
- `Jenkinsfile-peer` 的 `buildDiscarder(logRotator(numToKeepStr: '10'))` 只保留 10 次构建，审批落在 Jenkins input 记录中。
- AD-11 的恢复会把 Jenkins home 回滚到备份，备份之后的审批记录会丢失。

这样 R6 的“可审计”和 Done when 的“全部追溯到同一 SHA”过 10 次构建或一次恢复就不成立了。F3 需要的“最后 Verify 成功的 SHA”也依赖同一存储。

**修复：** 在 Conventions 增加 Audit 行，写明记录存放在 Jenkins home 之外（只追加）、保留期，以及恢复后如何对账。

**`iac-apps` 通道缺失**

- AD-10 创建 `iac-apps`，AD-3 提到 `n8n-rental`。但 Conventions 的 lanes 只有 `pr`、`main`、`read-only-plan`、`maintenance`。
- `n8n-rental` 会用 CT106 发布 SSH 和 Google clasp 写外部系统。按 lanes 那句“every other mutation requires current explicit approval”，它的审批形式没有定义。
- 现有 `docs/guides/jenkins-private-app-ci-contract.md` 已有 `APPS-PUBLISH-<digest>`、`APPS-GOOGLE-<digest>`。peer 规格的共享冲突域 `service:n8n-rental` 也没有写进脊柱。

**修复：** 增加第五个 `apps` lane，引用私有应用契约和 `service:n8n-rental`，写明 Gitea 只读 SCM 是 AD-3 下 lane 的唯一 SCM 例外。

**Controller 和 agent 维护与 AD-1 冲突**

- peer 规格规定 controller 和 agent 更新脱离流水线，由 CT110 root maintenance 执行。`transaction.py` 也拒绝 `deploy-jenkins.yml`。
- 这是 Jenkins 之外的常规写入，不属于 AD-9。而 AD-1 写“Jenkins alone”，R10 写例外只有 AD-9 和 `wsctl`。
- AD-11 只管 controller 重启，peer 规格的 agent 自更新规则（普通 handler 不得重启运行自己的服务）没有落地。`transaction.py` 目前还允许带 `control-plane:jenkins-agent` 的 `deploy-jenkins-agent.yml` 走 deploy 事务。

**修复：** AD-1 增加第三个具名入口“AD-11 独立维护入口”，并请用户确认它与 R10 的关系（R10 优先，需显式决定）。AD-11 增加 agent 自更新规则。

## 其他发现

| # | AD | 问题 | 修复 |
|---|---|---|---|
| M1 | AD-1 | “must not write”不可执行。工作站保留 HCP 写 token、Vault 密码和 SSH 私钥，没有检测手段。`--check` 也不等于只读：`ansible/roles`、`ansible/playbooks` 下 33 个文件含 `check_mode: false`，这些任务在 check 模式下真实执行（本次未逐一审计是否写入） | 增加检测规则：preflight 比对 HCP state serial 与 Jenkins 记录，出现无 AD-9 记录的前进时阻断。说明本地 check 只允许对已审计的 playbook 运行 |
| M2 | AD-2 | Initiative 约束“PR 流水线定义来自受保护的 `main`”未落地。`repo-validation.yml` 用 `pull_request` 事件，检出 PR head 并运行 PR 自带的 `scripts/ci/` | 向用户确认该约束只针对 Jenkins 管线（无 Jenkins PR lane 后自然成立），GitHub Actions 靠“无基础设施凭据”兜底，并写进 AD-2 |
| M3 | AD-2、AD-3 | “protected main”是前提，本次未能验证（`gh api` 被沙箱证书拦截）。“Actions 不持凭据”没有机器检查 | 在 `tests/ci/` 增加 workflow secret 白名单（当前只见 `CLAUDE_CODE_OAUTH_TOKEN`）。上线前用真实 API 核对保护规则 |
| M4 | AD-11 | “Job DSL owns Jenkins metadata”无对应工具：`ci/toolchain-bom.yml` 没有 job-dsl，peer 规格也只提 JCasC，AD-10 又要求一切都在 BOM。AD-13 依赖的 job config 目前是 UI 配置 | 加入 BOM，或改写成现有方式（`scripts/jenkins/*.groovy`），并写明门禁前 job 配置由谁负责 |
| M5 | AD-12 | 标 [DEFERRED]，却是 S6 要实现的现行规则。`Jenkinsfile-webhook-router-peer` 和 `ci/agent-jobs.yml` 仍路由到 `Proxmox-Provisioning`、`Physical-Device-Sync`；一旦有人建了同名 job，就违反“No event may start mutation” | 把 rule 与 deferred 能力分开：router 收紧是现行规则，并规定这两个下游 job 不得存在，由合约测试保证 |
| M6 | AD-10 | 版本钉选不一致：BOM 和 `transaction.py` 是 Terraform 1.14.4，`repo-validation.yml` 是 1.14.9。PR 验证的版本与执行版本不同，而 `transaction.py` 的硬编码绕开了 BOM | AD-10 增加“PR 验证也消费 BOM”，或明确接受差异 |
| M7 | AD-6 | 三处都在声明范围：`ci/execution-map.yml`、`ci/agent-jobs.yml` 的 scope、runner trust 的 `ansible_scopes`。优先级未定义 | 写明 execution map 是唯一来源，另两处由它派生或被校验 |
| M8 | AD-6、Conventions | Plan manifest 的 expiry 没有数值，代码是 900 秒。Conventions 也未定义 `iac-approvers` 的来源（JCasC 模板里没有授权配置） | 写入 15 分钟；写明授权组的配置所有者和 Jenkins RBAC 要求（peer 规格已要求限制 Configure 和 Credentials） |
| M9 | AD-5 | “retain them through apply”比实际短：`transaction.py` 在 apply 后、审批前后都要 HCP 凭据做刷新和 `state_identity` | 改成“through the final pre-deploy state check” |
| M10 | AD-7 | `deploy-netbox.yml`、`deploy-gitea.yml` 含 tailscale 角色，而已记录的决定是 NetBox 和 Jenkins 暂不加入 tailnet。AD-7 的 Verify 条件会把它们放进 auto-deploy | execution map 把这些 playbook 定为 maintenance-only，直到决定变更 |
| M11 | AD-4、AD-7 | `ansible/inventory/` 目录含 `terraform-remotecc.yml`，`verify_deploy_scope` 用默认 inventory，而 Jenkins 的 HCP token 是 root-scoped。Jenkins 读取 `iac-remotecc` 与否未定，AD-4 只说不写 | 明确 Jenkins 不读 `iac-remotecc`，deploy 时排除该 inventory 源。实际行为待验证 |
| M12 | 格式 | AD-4–AD-7、AD-9–AD-11、AD-13 没有状态标签。缺 Open Questions 一节。Structural Seed 未列 `ci/agent-toolchain.lock.json` | 补标签，增加 Open Questions |

## 分项判断

### 1. 下层分歧点是否都已锁定

已锁定：代码权威、PR 与 main 分工、root 到 workspace 映射、身份和网络隔离、saved plan、两阶段审批、lane 概念、webhook 信任边界。

遗漏（下层会各自决定）：

- 移交粒度（F1）
- HMAC 顺序（F2）
- 变更基线和重试语义（F3）
- 多 root 审批粒度（F3）
- OCI inventory、凭据、与 `wsctl` 的并发（F4）
- 审计存储（F5）
- `apps` lane 和控制面维护入口（F5）
- 范围声明的单一来源（M7）

### 2. 每条 AD 的可执行性

| AD | 可执行 | 能防住声明的分歧 | 说明 |
|---|---|---|---|
| AD-1 | 否 | 部分 | 无检测手段；移交点有缺口（F1、M1） |
| AD-2 | 是 | 大部分 | 旧 SHA 窗口和前提未验证（F3、M2、M3） |
| AD-3 | 是 | 是 | 缺 Actions 机器检查（M3） |
| AD-4 | 是 | 部分 | 只防 Jenkins 内部 writer，不防 `wsctl`（F4） |
| AD-5 | 是 | 部分 | OCI 来源未定（F4）；M9 |
| AD-6 | 部分 | 否 | 基线未定义，防不住静默漏部署（F3） |
| AD-7 | 是（Proxmox） | OCI 上否 | 静态 inventory 使刷新失效（F4） |
| AD-8 | 是 | 是 | 无问题 |
| AD-9 | 部分 | 部分 | 时间范围和归零条件有误，“declared”无记录位置（F1） |
| AD-10 | 是 | 是 | peer 有反例测试；M6 |
| AD-11 | 部分 | 部分 | Job DSL 无工具，agent 未覆盖（M4、F5） |
| AD-12 | 是 | 部分 | 下游 job 未禁止（M5） |
| AD-13 | 部分 | 部分 | 失败开放，路径未锚定，顺序未写（F2） |

### 3. Deferred 能否造成分歧

- **跨节点 HA：** 不会造成单元分歧，但见恢复维度的异地备份问题。
- **HCP remote execution：** 不会。
- **NetBox 事件和接管：** AD-8 没问题；AD-12 把现行规则和推迟能力混在一起，可能分歧（M5）。
- **Gitea 权威和镜像：** 已拒绝，不会。
- **Retiring Gitea：** 不会。

未列入 Deferred 却事实上被推迟的项目才是风险：OCI 只读 plan、异地备份、监控告警。

### 4. 与仓库和 peer 规格是否一致

一致：workspace 映射、`terraform/esxi` 和 `netbox-integration` 的处理、`wsctl` 边界、CT110 三身份、全局锁、Router 约束、entry cutover、`GitHubPushTrigger` 在 job 配置（`docs/architecture/cicd-architecture.md` 的改动与之一致）。

矛盾：

- AD-9 的归零条件（F1）
- AD-1 与 peer 的独立维护入口（F5）
- AD-11 的 Job DSL 与 BOM（M4）
- AD-13 的路径规则与现有 tunnel 配置（F2，属目标与现状之差，脊柱应写明要改）
- AD-13 的 HMAC 与 `jenkins_manage_casc: false`（F2）

### 5. R1–R10 覆盖

| 需求 | 覆盖 | 位置 | 缺口 |
|---|---|---|---|
| R1 | 是 | AD-10 | 验收细节由 peer 规格承接，可接受 |
| R2 | 部分 | AD-11 | “无证据时归零被拒绝”未写，AD-9 反而放宽（F1） |
| R3 | 是 | AD-2、AD-5 | “明确报告盲区”未写；root 只有 Proxmox 未明说 |
| R4 | 部分 | Entry cutover、AD-1 | “全部存续 job”“调度和清理证据”未写 |
| R5 | 是 | AD-2 | 旧 SHA 窗口（F3） |
| R6 | 部分 | AD-4 | OCI 未设计，审计不持久（F4、F5） |
| R7 | 部分 | AD-7 | OCI 刷新失效（F4） |
| R8 | 是 | AD-6 | 上线顺序（F1） |
| R9 | 是 | AD-3、AD-13 | 失败开放、顺序（F2） |
| R10 | 部分 | AD-1、AD-9 | 控制面入口冲突，无法执行（F5、M1） |

### 6. 约束和决策覆盖

| 项 | 状态 |
|---|---|
| 移交前本地执行和 dry run 照旧 | 已落地（AD-1） |
| PR 流水线定义来自受保护 `main` | 未落地（M2） |
| 三身份隔离 | 已落地（AD-10） |
| 分别审批和两条记录 | 已落地，记录不持久（F5） |
| root 对应 workspace，校验 local mode 和 lineage | 已落地（AD-4） |
| Secret 不进 Git、日志、持久 workspace | 已落地（AD-5） |
| 回滚只用已验证备份 | 已落地（AD-11） |
| bootstrap=2、旧入口不下线 | 部分落地（Entry cutover；bootstrap=2 没写，AD-9 相反） |
| CT110、真实密钥、归零、提交推送单独授权 | 未落地 |
| 决策 1 Git 权威 | 已落地 |
| 决策 1 公网入口风险重答 | 部分落地（F2） |
| 决策 2 范围 | 已落地，OCI 共享边界未答（F4） |
| 决策 3 AD-1 目标状态 | 已落地 |
| 决策 4 审批人 | 已落地 |
| 决策 5 第一个 epic 是 S1–S8 | 未写，并与 AD-1 冲突（F1） |
| Gitea 保留、n8n 只读 SCM | 已落地（AD-3） |
| Actions 不持凭据，webhook 不选代码 | 已落地 |
| 本地只读 plan 允许 | 已落地 |
| 解除冻结，线上状态待确认 | 未落地，应列 Open Question |
| HMAC 排最前 | 未落地（F2） |

### 7. 维度覆盖

| 维度 | 已决定 | 未决定也未延期 |
|---|---|---|
| 部署和环境 | CT107、CT110 分离；单一生产环境；同节点风险已延期 | OCI 对 CT110 的出口和 provider mirror；CT110 规格由 peer 承接 |
| 运维 | 审批、锁、失败行为、工具链钉选 | 流水线失败和审批超时的告警；Jenkins、runner quarantine、备份新鲜度的监控；审计保留（F5）；webhook secret 和 HCP token 轮换周期（peer 只覆盖矩阵）；Notion 同步的归属（旧 pipeline 有，`transaction.py` 带可选 `notion_sync`，脊柱未提） |
| 恢复 | controller 回滚（AD-11）；bootstrap 和灾难例外（AD-9）；部分失败不回滚（AD-6） | CT110 本身丢失时的重建路径和所需本地凭据；已验证备份只存于 CT110、与 controller 同节点，含 `master.key`，物理主机丢失时无副本，是否要异地副本；HCP 不可用时的处理；AD-11 恢复后的 webhook 和审计对账 |

未决定项全部没有标记，因为脊柱没有 Open Questions 一节。建议至少列入：

1. 线上 `IaC-Homelab-Pipeline` 的冻结状态和当前 webhook 暴露情况
2. 备份异地副本
3. CT110 丢失的恢复路径
4. 告警和监控的归属
5. OCI 只读 plan

## Initiative 中未落地的关键内容

1. “给 `/github-webhook/` 加 HMAC secret……列入第一个 epic，排在最前面，因为公网入口当前可能已经在触发流水线。”（Notes）
2. “Decision: 2026-11-05 第一个 epic 是 peer 生产落地（S1–S8）。”（Notes，决策 5）
3. “取得真实恢复证据、完成全部 job 映射前，controller 保持 bootstrap=2，旧入口不下线。”（Constraints；bootstrap=2 和证据条件缺失）
4. “没有有效证据时，controller 变更和归零都被拒绝。”（R2；归零部分缺失）
5. “CT110、真实密钥、controller 归零、提交和推送都要单独授权。”（Constraints）
6. “PR 流水线定义来自受保护的 `main`。”（Constraints；只有 `IaC-ReadOnly-Plan` 落地）
7. “私有应用代码归应用所有者，本 initiative 只交付接入契约。”（Boundaries）
8. “线上现状待登录确认。”（Notes，解除冻结）
9. “Terraform 变更只有 CT110 及其 inventory。”（R1；由 peer 规格承接，可不写进脊柱）
10. peer 验收的“Jenkins 独立恢复且 Gitea 未被回滚”，AD-11 未提。

## 评审范围说明

- **评审通道：** `docs/agent/bmad-review-routing.md` R0 规定 architecture rubric walker 走 PAL 已批准的 reviewer provider。本次由调用方直接派给当前 Claude 子代理，没有经过 PAL，所以不算 R0 要求的跨模型审核。
- **未验证：** GitHub 分支保护和 Rulesets（`gh api` 失败）、线上 Jenkins、线上 tunnel 配置和 hook 状态。这些判断只基于仓库内容和本地记录。
- **`check_mode: false`：** 只统计了文件数，未逐一判断是否写入。
- **外部核对：** GitHub plugin v1.47.0 源码、Cloudflare Tunnel 配置文档。
