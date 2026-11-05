# 对抗评审：IaC CI-Only Execution 架构 spine

- 评审日期：2026-11-05
- 评审对象：`.worktrees/ci-only-architecture/docs/architecture/ci-only-execution-architecture.md`（未提交的工作副本，与 `_bmad-output/.../architecture-ci-only-execution.md` 内容一致）
- 上下文：`docs/planning/jenkins-peer-agent-recovery.md`、`AGENTS.md`、`decisions-2026-11-05.md`、`initiative-ci-only-execution.md`
- 方法：构造下一层的两个单元，每个都逐字遵守全部 AD，再看它们能否兼容。证据取自仓库代码和 `remotecc/wsctl` 私有代码，只读。

## 结论

**不通过，spine 不能保持 `status: final` 作为构建基底。** 范式本身成立。问题集中在一点：AD-4 的锁、AD-6 的路径分类和 AD-1 的所有权都只在 Jenkins 这一个执行面内定义，而真实冲突全部发生在执行面之间，也就是 wsctl、基线流水线、本地、私有应用作业与 peer 之间。

共 10 个洞：3 个高危，4 个中危，3 个低危。前 5 个必须在开始 S6 之前关闭。

### 评审局限

- **路由偏差：** `docs/agent/bmad-review-routing.md` R0 要求架构一致性 adversarial 走 PAL 已批准的 reviewer provider，R1 不允许静默降级为同模型。本次由调用方直接派给 Claude，**没有走 PAL，不算跨模型审核**。是否补跑由协调者决定。
- **未接触线上：** 没有读 HCP state、Jenkins UI 或 job 配置。"两个 root 没有重复资源"只在 `.tf` 层面核对过。
- **未读私有 n8n 仓库：** `/opt/n8n-rental` 的 rsync 行为只能从契约文档推断。
- **Terraform 行为未实测：** H-5 中 plan 会占 HCP 工作区锁，依据是 Terraform 的默认锁行为和 `-lock=false` 的文档语义，本次没有运行。
- "无人运行"的结论只来自 grep `remotecc/wsctl` 和 `semaphore-bootstrap.py`，不排除手工运行。

---

## 高危

### H-1 锁只在 Jenkins 内部成立，而且锁名之间不可比较

**对子 A：Jenkins 维护作业 vs wsctl，都写 pve2**

- 单元 A：`maintenance` 的 manual playbook 模式运行 `configure-pve2-local-ssd.yml` 或 `upload-snippet.yml`（`hosts: proxmox_cluster`），持有 AD-4 的 `platform:pve2` 锁。符合 AD-1、AD-4、AD-6。
- 单元 B：wsctl 运行 `configure-oci-hub-router.yml`，经 `oci-hub-pve` 角色在 pve2 上执行 `/usr/local/lib/oci-hub-pve-sdn.py`，持有 `/run/wsctl.lock`。符合 AD-1 的 RemoteCC 例外。
- 冲突：两把锁互不可见。pve2 上同时有 Jenkins 这边的 PBS（VM100）、container-lab（108）、CT120，以及 RemoteCC 这边的 VM500、模板 9000 和全部员工 VM。AD-4 的 "conflict domain" 没有一条跨到 wsctl，spine 的一句 "RemoteCC is outside this spine" 把共享物理节点也一起划了出去。
- 硬约束：`initiative-ci-only-execution.md` 第 66 行规定不得改变 wsctl 执行路径，所以 wsctl 不能被要求去取 Jenkins 的锁。修复只能靠对象分区和 Jenkins 单侧的限制。真正的互斥需要用户另行决定是否放开这条约束。

**对子 B：两个合规的 conflict domain 落到同一台主机**

- 单元 A：`deploy-n8n.yml` 与 `n8n-rental` 用 `service:n8n-rental`（`ci/agent-jobs.yml`、契约第 5 条）。
- 单元 B：`install-tailscale.yml` 或 `site.yml` 走 maintenance，声明 `inventory:tailscale` 或 `inventory:all`。AD-4 明确允许 "platform, service, inventory group, or control plane"。
- 冲突：字符串不同，所以不互斥，却都命中 CT106。AD-4 只要求"解析出的主机落在已锁域内"，每个单元都能通过自检，两者仍会并发。

**真实情况比文字更糟**

`scripts/jenkins/` 里没有任何 conflict-domain 的获取逻辑。`scope` 只是 admission 里的静态列表，真正起作用的是 CT110 的 `global.lock`（`job-runner.py:280`），另有 CT107 的 `control-plane.lock`。也就是说 AD-10 的全局锁已经让 AD-4 的域锁在 CT110 内部变成冗余，而 AD-4 本该起作用的三处（wsctl、基线流水线、AD-9 本地写）恰好都不在锁内。锁存储也没有指定，一个实现者用 Lockable Resources、另一个用 flock，都算合规。

### H-2 改动选择可以丢失部署，而每个单元都合规

- 单元 A：admission 的 `changed_paths` 只比较构建提交与其第一父提交（`controller-admission.py:213`），`Jenkinsfile` 基线同样用 `HEAD~1`。AD-6 只说"classifies changed paths"，没有定义基准。
- 单元 B：runner 用 `LOCK_NB`，忙时直接 `Refused`（`job-runner.py:282`）；`resolve_source` 对非最新 main 的 SHA 也 `Refused`（`controller-admission.py:136`）。这都符合 AD-2 和 AD-10。
- 冲突场景：
  1. 合并 A 改了 `ansible/roles/caddy/`。此时另一作业正持锁，比如 main lane 正等审批，或 n8n 正在发布。A 的构建被拒绝。
  2. 合并 B 只改了 `ansible/roles/homepage/`。B 的构建成功，但它的 diff 里没有 A。
  3. `deploy-caddy.yml` 再也不会运行，也没有任何告警。
- 队列合并同样触发：`disableConcurrentBuilds` 下排队的两次 push 合成一次构建，只看到最后一个提交。
- Terraform 下次 plan 会自然收敛，Ansible 不会。这正是 AD-6 声称防止的 "silently skipping deployments"。

**相关后果：** 一次事务跨两次人工审批，全程持全局锁。代码里每次审批期限 900 秒，作业 60 分钟。这段时间内 `IaC-ReadOnly-Plan` 和 n8n 发布都被拒绝，而操作员最想跑只读 plan 的时刻正是这时。spine 没有写明接受这一点。

### H-3 所有权靠 "employee" 一词划分，导致一批对象两个 owner 或没有 owner

**对子 A：`excluded` 分类 vs 共享代码**

- 单元 A：execution map 把 RemoteCC 路径标为 `excluded`。
- 单元 B：同一 map 把 `terraform/modules/proxmox-vm`、`ansible/roles/common`、`tailscale` 标为 Jenkins 路径。
- 冲突：这些路径两边都用（模块被 proxmox 11 个文件、remotecc 2 个文件引用；`common`、`tailscale` 也进 `deploy-remotecc-ops.yml`）。AD-6 只有 root、playbook、excluded 三类，没有 shared。合规的 map 会让 Jenkins 单边滚动共享模块，RemoteCC 在下次 wsctl 时才带上，且那时 SHA 不受控。

**对子 B：AD-3 与 AD-1 字面矛盾**

- AD-3："No mirror of this repository may feed execution."
- 现实：`remotecc-ops-runtime` 角色维护 `/srv/git/iac.git`，post-receive 检出到 `/srv/iac`，手册第 6.2 节用 `git push remotecc-ops origin/main:main` 更新。这就是 IaC 仓库的副本在驱动 `terraform/remotecc` 和员工 play，而 AD-1 要求这条路径继续存在。
- 后果：两个执行面运行不同 SHA 的同一批角色和模块，手工推送决定落后多久，没有任何规则约束这个副本只能快进。

**对子 C：没有 owner 的 play**

- wsctl 实际运行：`configure-oci-hub-router`、`deploy-oci-hub-workspace`、`configure-oci-hub-mosh-boundary`、`bind-oci-hub-workspace-hook`、`deploy-oci-hub-terminal`、`prepare-employee-desktop`、`hapi-registry`。
- 另有 11 个 play 在 wsctl 和 Semaphore 中都没有引用：`deploy-oci-hub`、`deploy-hapi-control-plane`、`deploy-hapi-shared-hub`、`prepare-employee-pve`、`configure-oci-hub-portal-public`、`update-oci-hub-authority`、`verify-oci-hub-portal-isolated`、`deploy-remotecc-ops`、`prepare-vm502-desktop`、`remove-retired-workspace-boundary`、`deploy-unified-proxy`。
- 它们是 "employee play" 吗？一个实现者判 wsctl，另一个判 Jenkins，都不违反 AD-1。
- 最尖锐的是 `deploy-remotecc-ops.yml`。手册第 444 行说它在 Sandbox 本地运行，移交后 AD-1 禁止本地写。Jenkins 又看不到这台主机，因为 `remotecc-ops` 只存在于 `iac-remotecc` state，`transaction.py` 只读 proxmox state。wsctl 也不运行它。结果是**执行器自身移交后没有合法的配置路径**。
- 反向依赖：员工 Hub 的入站 NSG 在 `terraform/oci/oci-hub.tf`，属于 Jenkins 的 root。Jenkins 一次 OCI apply 就能切断员工接入，spine 没有提到这条依赖。

**对子 D：同一凭据两个 owner**

`get-secrets.sh` 明写 remotecc root 使用同一套 Proxmox 凭据。AD-5 把它算作 Vault 管理的 root-scoped 凭据并把版本写入 manifest，AGENTS.md 又把 "Proxmox Terraform variables" 和 IaC vault password 列为 BWS 的 `executor/*`。按 AD-5 轮换 Vault 后 wsctl 会失效，且 BWS 里的 IaC vault password 能解密全部 IaC 秘密，"root-scoped" 只在 Terraform 这一层成立。

---

## 中危

### H-4 切换期：基线与 peer 同时存在，却只有一边算事务

- 单元 A：`Jenkinsfile` 基线留在 controller，只靠 `disableConcurrentBuilds`。"Entry cutover" 约定明确让它留到新入口验证通过。
- 单元 B：`Jenkinsfile-peer` 的 staged run 在 CT110 做真实运行，持 CT110 的全局锁。
- 冲突：
  - 基线不是 "deployment transaction"，不受 AD-4 约束，两边对同一 root 不互斥。移交前本地写同样合法，是第三个写入者。
  - "staged run" 无法同时满足 spine 和 admission。用同一 job 名就等于已经切换。用新 job 名则不在 `ci/agent-jobs.yml` 里，`policy['profiles'][job]` 直接拒绝。
  - `GitHubPushTrigger` 在 job 配置里而不在仓库。两个 job 都带触发器时一次 push 启动两条流水线。
  - 恢复规格 S6 按 job 逐个迁移。`n8n-rental` 还在 controller、`deploy-n8n.yml` 已上 CT110 的窗口里，两者对 CT106 没有任何互斥，`service:n8n-rental` 只在同一节点内有效。
  - 入口状态有四个开关：`ci/agent-jobs.yml` 的 `cutover_authorized` / `controller_mode` / `enabled`，`jenkins_controller_mode`，root 策略的 `profile.enabled`，Jenkins job 配置。AD-11 让 Job DSL 等 restore gate，这之前 job 定义归 UI。
  - AD-1 把移交定义为 executors 归零。但 `Jenkinsfile` 是 `agent any`，用全局 `terraform-cloud-token` 和 `ansible-vault-password`。归零后若回退到它，会落到 agent 节点并带全局秘密。spine 没有要求移交时撤销这些凭据。

### H-5 本地只读 plan 与 Jenkins 的锁和凭据模型不兼容

- 单元 A：Mac 按 AD-1 运行 `terraform plan`。默认会取 HCP 工作区锁。
- 单元 B：`transaction.py` 运行 `terraform apply <saved>`，没有 `-lock-timeout`，AD-4 把 HCP 锁称为 "additional safeguard"。
- 冲突：只读操作恰好占锁时，已批准的 apply 立刻失败，而 AD-6 要求新 plan 和新审批。AD-1 允许的动作能作废 AD-2 的审批。
- 陈旧锁：Mac 崩溃或作业被杀后留下 HCP 锁时，解锁是状态写操作。AD-6 的五种 maintenance 模式里没有它，AD-9 又只给灾难用。
- 凭据：AD-5 只定义了 Jenkins 的三个身份，没有本地这一条。本地 plan 依赖 `get-secrets.sh`，拿到的是可写 PVE token、HCP 可写 token 和 Vault。"不写"只是自律。换成只读 token 也跑不通，恢复规格第 87 行已说明 provider 读取涉及 `query-url-metadata`（默认拒绝，且不授 `Sys.Modify`）。
- 这条不能靠删本地 plan 解决。AD-2 禁止 Jenkins 碰 PR ref，`IaC-ReadOnly-Plan` 只读 main，而用户的规则是基础设施 PR 合并前必须跑真实 plan。移交后这一步只能在本地做，所以 Mac 的凭据实际上会永久保留。spine 对这件事没有结论。

### H-6 n8n 作业不属于任何 lane，且 CT106 有两个写入者

- 单元 A：`deploy-n8n.yml` 的 `n8n` 角色写 `/opt/n8n-rental/docker-compose.override.yml` 和 env，运行 compose，Verify 断言 `n8n_version`。
- 单元 B：`n8n-rental` 用 rsync 和 SSH 发布到 CT106，Docker 操作也在 CT106（契约第 4 条）。
- 冲突：
  - Conventions 列出的 lane 是 `pr`、`main`、`read-only-plan`、`maintenance`，n8n 不在其中。AD-2 的 manifest 和审批只有 Terraform、Ansible 两种形状，而代码已有 `apps-publish`、`apps-google` 两个阶段，`APPS-PUBLISH-<digest>` 的 digest 形状由私有仓库决定。
  - 对 `/opt/n8n-rental` 的文件归属没有划分。`host_vars/n8n.yml` 还留着 `n8n_app_ref: 754bd88`，发布基线是 `a1fd564`（`n8n_checkout_app: false`，目前未被使用，但这就是两个版本源）。
  - 冲突域 `service:n8n-rental` 由 GitHub 的 execution map 声明，由 Gitea 来源的作业使用，后者读不到 map。IaC 作业的 scope 是静态写死的，每次都带这个域，这也不是 AD-4 说的按选择推导。
  - `apps-validation` 没有秘密、不做变更，却声明了同一冲突域。

### H-7 scope 有四种形状，且 map 能授权自己

- 单元 A：实现者按 AD-6 在构建 SHA 读 `ci/execution-map.yml`。
- 单元 B：实现者按恢复规格用 root 持有的 `trust.ansible_scopes`（`transaction.py` 的静态主机到地址表）。`ci/agent-jobs.yml` 的 `scope` 又是第三份，admission 策略的 `profile.scope` 是第四份。
- 冲突：repo map 优先时，一个合并能在同一次运行里扩大自己的范围。root 策略优先时，新服务的 playbook 被 `changed playbook is outside the approved execution map` 拒绝，必须先改 root 配置，而 AD-6 把 map 定为权威。`classify_changes` 还把 `ci/` 的改动直接跳过，所以改 map 不触发任何东西。
- AD-4 要求"解析主机落在已锁域内"，代码做的是与静态表比较。这是两种不同的数据形状。

---

## 低危

### H-8 terraform/proxmox 与 terraform/remotecc 共用 VMID 和地址空间

- `oci-hub-workspace.tf` 只校验 `vmid >= 100 && != 500` 和 root 内唯一，pve2 上的 100、108、120 属于 proxmox root。
- `remotecc-ops` 占 pve0 的 116 和 192.168.1.116，CT110 只靠部署前人工复核 IPAM。
- 两个 root 向同一个 `pve_vms` 组写主机。`remotecc-ops` 与 CT106 同组，任何按组解析的 play 都会受"是否加载了 remotecc 库存"影响。`ansible/inventory/` 同时含两个 Terraform 插件文件，实际 `ansible.cfg` 没有 `any_unparsed_is_failed`，未初始化时 remotecc 主机被静默丢弃，而 AD-5 又不给 Jenkins 这个 root 的令牌。
- 同理，AD-7 的摘要在只含 proxmox 的临时库存上计算，部署却用完整库存。
- PVE 对重复 VMID 会报错，所以这是失败而不是静默损坏，故定为低危。

### H-9 CT107 上的 Gitea 和 cloudflared 没有合法路径；main lane 能替换自己

- `deploy-gitea.yml` 和 `deploy-cloudflared.yml` 都是 `hosts: jenkins`，`validate_scope` 对 `jenkins` 主机一律拒绝。AD-11 的独立维护只定义了 Jenkins 本身。AD-13 的隧道配置移交后更新不了。
- `terraform/proxmox/jenkins.tf`、`jenkins-agent.tf` 在 main lane 的 root 里。一次模块改动经显式 scope 通过后，plan 可以包含替换 CT110 的动作，而 apply 正运行在 CT110 上。AD-11 只防重启 controller，没有防这一点。

### H-10 OCI 在 AD-4 表里，但下一层接不上

- `ci/agent-jobs.yml` 只有 `root:proxmox`，`transaction.py` 写死 proxmox，`IaC-ReadOnly-Plan` 只接受 `root=proxmox`。这是恢复规格的范围，不算错，但 spine 没有说明 OCI 何时、以什么顺序接入。
- `vault_oci_private_key_path` 是路径而不是密钥。AD-5 说 OCI 私钥由构建注入，AGENTS.md 又把 `~/.oci` 列为不得改动的本地材料。私钥进 Jenkins 的来源没有定义。

---

## 攻击过但成立的部分

- `.tf` 层面两个 root 没有同名资源，wsctl 不写 `terraform/oci`，也不引用 OCI 主机名。一实体两份 state 的攻击不成立。
- AD-13 的 webhook 不能选代码、不能选 ref。没有找到合规单元能绕过。
- saved plan 和 digest 绑定在代码里兑现了：apply 前重查 state，Ansible 前重查库存。
- AD-12、AD-8 的推迟边界清楚。

---

## 建议规则文本

规则保持英文，便于直接并入 spine。

### 关闭 H-1：收紧 AD-4，新增 AD-14

**AD-4 增加：**

> Transaction locks live in one store: the root runner's registry on the peer agent. Jenkins Lockable Resources and per-job options do not count as transaction locks. A lock key is atomic and canonical: `root:<name>` or `host:<inventory_hostname>`. Service, group, platform, and control-plane names in the execution map are aliases that expand to those keys before acquisition, so overlapping domains always contend. Every mutating Jenkins job, including application publish and maintenance, acquires through this store.

**新增 AD-14 — Shared substrate has one writer per object：**

> Jenkins and `wsctl` hold no common lock, so safety between them comes from partition. `ci/shared-substrate.yml` lists every host that carries guests of both planes and assigns each host-level object (SDN, storage, firewall, hook scripts, snippets) to exactly one plane. It also reserves VMID and address ranges per Terraform root, and each root validates against those ranges at plan time. The main lane never targets a shared host. Maintenance may target one only for objects Jenkins owns, after a read-only check shows no `wsctl` run, and its confirmation text must name that check. Mutual exclusion enforced on the `wsctl` side needs a separate decision because the initiative freezes that path.

### 关闭 H-2：收紧 AD-6 和 AD-10

**AD-6 增加：**

> Change selection runs over `last_verified_sha..build_sha` for the lane, not over the build commit alone. The watermark lives in the run registry and advances only after a transaction passes verification. Cutover seeds it from the last commit the baseline pipeline verified. If the watermark is not an ancestor of the build SHA, the run requires an explicit operator scope.

**AD-10 增加：**

> Admission waits in a bounded queue while the global lock is held. Refusal is reserved for policy failures, and a busy runner never turns a build into a skipped change. A transaction paused for approval keeps the lock and blocks all other jobs, including read-only plan, for at most the plan-manifest expiry of each approval. This delay is accepted.

### 关闭 H-3：收紧 AD-1、AD-3、AD-6

**AD-1 替换 "employee Ansible plays" 的说法：**

> The execution map lists every playbook with exactly one owner: `jenkins`, `wsctl`, `maintenance`, or `retired`. An unlisted playbook has no lane and fails closed. The word "employee" carries no scope by itself. After handoff, `deploy-remotecc-ops.yml` has a named owner before controller executors reach 0.

**AD-3 增加：**

> Exception: `/srv/iac` on `remotecc-ops` is a fast-forward-only copy of `origin/main`. It feeds only RemoteCC execution, accepts no commit that is absent from `origin/main`, and each `wsctl` run records the SHA it used. No Jenkins job reads it.

**AD-6 增加：**

> Paths consumed by both planes, including `terraform/modules/**` and roles used by RemoteCC plays, are class `shared`. A `shared` change is broad-impact in Jenkins, and its run report names the RemoteCC follow-up. Jenkins does not perform that follow-up.

**AD-5 增加：**

> A credential used by both planes has one source of truth and a recorded rotation order covering both planes. Until the planes hold separate credentials, rotation is a coordinated change, not a routine Vault edit.

### 关闭 H-4：替换 "Entry cutover" 约定

> For each root or service, exactly one entry holds the push trigger and mutation credentials at any time. A staged run has its trigger off and runs on a fixed SHA while the old entry is disabled for that domain. The baseline pipeline and local execution are not deployment transactions, so the operator freezes both for a domain before any peer mutation on it. A service's IaC job and application job move in the same window. `ci/agent-jobs.yml` is the single desired record of entry state, and handoff also requires removing controller-held global credentials and proving that the baseline job cannot run on agent nodes.

### 关闭 H-5：收紧 AD-1 和 AD-5，补 AD-6 模式

**AD-1 增加：**

> After handoff, local `terraform plan` uses `-lock=false`. Jenkins plan and apply use a bounded `-lock-timeout`, and a lock failure before apply begins leaves the approval valid within its expiry. The local lane is defined in AD-5: it holds the least credentials that complete a plan, and the spine states which of them can write. A pre-merge real plan after handoff follows that same local lane.

**AD-6 maintenance 模式增加：** `force-unlock`，带与其他模式相同的 typed parameters、preview、confirmation 和 audit log。

### 关闭 H-6：收紧 AD-2

> `app` is a fourth Jenkins lane. It mutates only the service named by its fixed profile, from its own SCM, under the same lock store. Its approval record has the same fields as the other records: approver, time, source SHA, scope, and digest. The application job owns the application tree and image, while Ansible owns the host, runtime, and Compose override. The map records that file-level split, and a version pin has one owner.

### 关闭 H-7：收紧 AD-6

> The root-owned policy is the ceiling and the repository execution map selects within it. A map at a given SHA cannot widen its own ceiling. Changes under `ci/` are broad-impact. `ci/agent-jobs.yml` carries no scope of its own.

### 关闭 H-8 至 H-10

- **AD-7：** "The approved digest and the deployed inventory come from the same inventory source. Any unparsed source fails the run."
- **AD-11：** "A main-lane plan that replaces or destroys the Jenkins controller or agent stops before approval. Every service on the controller host, including Gitea and `cloudflared`, has a named maintenance path."
- **AD-4 / Deferred：** 写明 OCI 的接入顺序，以及 OCI 私钥进入 Jenkins Credentials 的来源。

## 需要用户决定

1. 是否放开"不改 wsctl 执行路径"，让 wsctl 接入共享锁。不放开时 AD-14 只能靠分区，无法做到互斥。
2. `deploy-remotecc-ops.yml` 和其余 10 个无 owner 的 play 分别归谁。
3. 移交后 Mac 保留哪些凭据。这决定 H-5 的本地 lane 是真只读，还是只靠纪律。
