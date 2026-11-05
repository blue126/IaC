# CI-Only 架构 Spine 现实核查

**结论：** 这份 spine 依赖的外部协议和产品行为大多属实，但它还不能算已经过现实核查：主线触发机制按仓库的既定配置走不通，版本基线已落后于公开的安全修复，AD-13 的验收探针会误判通过。

- 被审文件：`docs/architecture/ci-only-execution-architecture.md`（worktree `ci-only-architecture`，未提交版本）
- 核查日期：2026-11-05
- 未修改仓库。核查时做了以下只读操作：
  - 对 `jenkins.willfan.me` 发 4 个匿名 GET。
  - 用 `gh api` 读仓库的 hooks 和 rulesets。`gh` 在沙箱内 TLS 校验失败，这两次读取在沙箱外运行。
  - 没有向 webhook 发 POST，没有使用 HCP、Jenkins 或 Cloudflare 凭据。

## 研究可追溯性

Spine frontmatter 只列了 3 个外部来源：`plugins.jenkins.io/github`、GitHub 校验文档、Terraform `cli/cloud`。

- Cloudflare 路径匹配、Jenkins `input`、Mailer、JCasC、Job DSL、HCP API、`-lock-timeout`、工具版本都没有列来源。这些结论有的恰好正确，但文档里看不出它们经过了核实。
- 列出的 GitHub 插件页面并不包含 webhook 签名内容。真正的依据是插件源码 `RequirePostWithGHHookPayload.java`。
- 建议补一节“已核实事实”：写明来源、版本和核查日期。

## 发现（按严重度）

严重（critical）：无。没有发现已经造成破坏的问题。下面三个高危项在切换前都必须解决。

### 高

**H1. 主线 push 触发按既定配置走不通，spine 写的“may”低估了问题，也没有给出机制。**

- Spine 第 164 行只说“a pipeline with no checkout may leave polling with no baseline”，并把它留给验收。
- 触发链路（源码已确认）：
  - `GitHubPushTrigger.runPolling()` 调用 `item.poll()`，只有 `hasChanges()` 为真才排队构建。
  - `WorkflowJob.poll()` 遍历上次构建的 checkouts。没有 checkout 时结果就是 `NO_CHANGES`。只有完全没有历史构建时才返回 `BUILD_NOW`。
  - `CpsScmFlowDefinition` 的 lightweight 路径不产生 checkout。full 路径才 `setPoll(true)`。
- 仓库现状：
  - `Jenkinsfile-peer:5` 设了 `skipDefaultCheckout(true)`，全文没有 `checkout`。
  - `docs/guides/jenkins-agent-bootstrap.md:29` 明确写的是“standalone `CpsScmFlowDefinition` 轻量 SCM job”。
- 影响：这种配置下，第一次新入口构建完成后，之后每次 push 都会被静默丢弃。这不是“可能”。“连续两次 push”的验收能发现问题，但 spine 没有可行的修复路径。
- 建议：在 spine 里定死触发机制，例如 job 必须 non-lightweight（Job DSL 显式设置），并同时确认：
  - 控制器能拿到 Git 凭据（full checkout 走控制器的 `workspace@script`）。
  - `controller-admission.py:66-75` 的 `standalone_entry` 路径在 non-lightweight 下仍成立。
  - 否则就换掉 `GitHubPushTrigger`。
- 未核实：线上 `IaC-Homelab-Pipeline` 的 lightweight 实际取值（需要 Jenkins 权限）。

**H2. BOM 固定的 Jenkins 版本已落后于公开安全修复，而且线上正在运行。**

- `ci/toolchain-bom.yml:6` 固定 core `2.568.3`。线上响应头 `x-jenkins: 2.568.3` 确认了这一点。
- 2026-10-28 公告列出 15 个 core 漏洞，影响 LTS ≤ 2.580.1，修复版本 2.580.2，其中 13 个为 High：https://www.jenkins.io/security/advisory/2026-10-28/
- 2026-09-16 公告影响 BOM 的两个固定版本（https://www.jenkins.io/security/advisory/2026-09-16/）：
  - `script-security` `1412.v7737b_3405f86`（`toolchain-bom.yml:721-722`；受影响 ≤ 1415，修复 1422）
  - `pipeline-groovy-lib` `798.v5cc688825312`（`toolchain-bom.yml:643-644`；受影响 ≤ 805，修复 806）
- 这些漏洞多数需要 Overall/Read 或更高权限。这个控制器将托管部署凭据和审批，又有公网入口，所以仍应在 AD-13 上线和交接之前升级。
- 未核实：线上插件的实际版本；2.580.2 与当前插件锁的兼容性。

**H3. AD-13 的“POST 必须返回 400”验收会误判通过，规则本身也不完全成立。**

- 拦截器顺序（`RequirePostWithGHHookPayload.java`）：POST 方法检查 → URL 校验头 → 事件与 payload 检查 → 签名检查。
- 缺 `X-GitHub-Event`、事件未知、payload 为空，或 `Content-Type` 不受支持时，都在签名检查之前返回 400。
- 所以一个简单的 `curl -X POST` 在**完全没配 secret**时也返回 400，而这正是 AD-13 要抓的失败开放状态。
- 探针必须带 `X-GitHub-Event: ping`、`Content-Type: application/json` 和非空 JSON。不要用 `push` 事件，否则在未配置 secret 时会触发一次轮询。
- 判定方式：无 secret 时这个探针不返回 400，配了 secret 后才返回 400。
- 例外：带 `X-Jenkins-Validation` 头的 POST 在验签前直接返回 200，并带回实例公钥。这不会启动构建，但“unsigned POST 一律 400”的字面规则不成立，需要写明这个例外，或在隧道层处理。

**H4. 线上隧道没有做到 AD-13 的“精确匹配”，rollout 也没有列这一步。**

- 仓库现状：`ansible/inventory/host_vars/jenkins.yml:13` 是 `path: /github-webhook/`，未加锚点。cloudflared 按正则匹配（`ingress/rule.go:61`，`MatchString`）。
- 线上实测：

| 路径 | 结果 | 含义 |
| --- | --- | --- |
| `GET /x/github-webhook/` | 403，带 `x-jenkins: 2.568.3` | 请求到达了 Jenkins |
| `GET /login` | 404，无 `x-jenkins` | 走了 catch-all |
| `GET /` | 404，无 `x-jenkins` | 走了 catch-all |
| `GET /github-webhook/` | 405，带 `x-jenkins` | 符合预期 |

- 也就是说，今天任何路径里含 `/github-webhook/` 的 Jenkins URL 都能从公网到达。
- `^/github-webhook/$` 的写法本身是对的。但 AD-13 说“the first change”时只提到 secret，rollout 必须把隧道锚定也列进去。
- 同时也要处理 H2：这个入口暴露的是一个未修补的 core。

### 中

**M1. HCP 组织版本未知，而 AD-5 的凭据隔离依赖它。**

- HashiCorp 文档：“Teams are not available to free-tier users on HCP Terraform”，免费组织“will only have an owners team”。来源：https://developer.hashicorp.com/terraform/cloud-docs/architectural-details/security-model
- AD-5 的 root-scoped 凭据、`hcp-proxmox-deploy`，以及专用只读 state 身份都需要按 workspace 限权。`plan-snapshot.py:39-41` 发现多余权限就拒绝。
- 如果组织在 Free 上，只读 plan 任务大概率无法启用，per-root 隔离也无法实现。Legacy Free 已于 2026-03-31 结束。
- `force-unlock` 维护模式需要 workspace Admin 权限（API 文档），这与最小权限存在张力。
- 未核实：`homelab-roseville` 的实际版本。这是本次最值得用户去确认的一项。

**M2. Job DSL 被当作配置 owner，但没有固定，也没有使用。**

- AD-11 写“Jenkins Configuration as Code/Job DSL owns Jenkins metadata”。`job-dsl` 不在 BOM 中，`ci/`、`ansible/`、`scripts/`、`docs/` 全部没有出现。
- `ansible/roles/jenkins/templates/jenkins.yaml.j2` 只配置 executors 和 nodes。
- 插件仍在维护：最新 `3732.v9a_c49a_61a_313`，要求 core 2.479.3，页面标注“seeking co-maintainers”。
- 需要补入 BOM，并验证它能声明 `GitHubPushTrigger` 和 lightweight 设置。

**M3. JCasC 接管凭据时，可能清掉 UI 上传的 OCI 私钥。**

- AD-5 规定 OCI key 由运营者在 UI 上传。AD-13 要求 webhook secret 由 JCasC 接管，来源是 Vault。
- JENKINS-64079 记录了 reload 时 UI 添加的凭据被清除，状态 Open/Unresolved。早期维护者讨论也说这是替换而不是合并。
- Spine 没有说明 secret 怎样从 Vault 进入 JCasC，也没有说明是否使用 `credentials:` 根节点。
- 这是公开 issue 的结论，没有在 configuration-as-code `2117` 上实测，需要在 AD-11 恢复门禁里测。
- 附带确认：JCasC 键名是 `unclassified.githubpluginconfig.hookSecretConfigs`（插件测试资源）。

**M4. ansible-core 2.19 本月 EOL，升级路径被多重锁死。**

- BOM 固定 `2.19.12`。2.19 线已到 `2.19.15`（2026-11-02）。官方矩阵显示 2.19 的 EOL 为 Nov 2026。
- 三重约束：
  - `ci/agent-toolchain.lock.json:4` 是 Python 3.11，LXC 模板是 Debian 12（`terraform/proxmox/jenkins-agent.tf:10`）。ansible-core 2.20 起控制节点要求 Python ≥ 3.12。
  - `requirements.txt` 限定 `<2.21`。
  - `cloud.terraform` 最新仍是 4.0.0，main 分支仍调用 `get_bin_path("terraform", required=True)`。
- `community.general` 固定 13.3.0，Galaxy 最新 14.0.0（未核实 13.x 的维护状态）。
- 来源：https://docs.ansible.com/projects/ansible/devel/reference_appendices/release_and_maintenance.html

**M5. 仓库实现落后于 AD-4 的多项断言。**

- `transaction.py:206,220` 没有 `-lock-timeout`，而 AD-4 要求有界超时。默认不等待，锁冲突会立刻失败。
- 工作区预检（local 模式、组织、版本）只出现在 `plan-snapshot.py:30-38`，并硬编码 `iac-proxmox-lab`。主线 `transaction.py` 只校验 state 身份。
- OCI 路径未实现：`Jenkinsfile-plan:9` 只有 `proxmox`，`transaction.py` 的 manifest 写死 `root:'proxmox'`。Structural Seed 没有把它标为“To add”。

**M6. AD-4 的 Terraform 版本与 lineage 断言措辞不准。**

- local 模式下，工作区的 `terraform-version` 不起作用。Terraform 源码（v1.14.4 `internal/cloud/backend.go:1093`）称其“effectively meaningless”并跳过校验。
- 这个字段不能证明实际使用的 CLI 版本。应改为校验本地 `terraform version` 与 BOM 一致，并辅以 `current-state-version` 的 `terraform-version`。
- 文档里的 state version API 响应没有 `lineage`（只出现在创建请求）。必须读原始 state，仓库也是这么做的：`transaction.py:36`，`plan-snapshot.py:92`。AD-4 的 “through HCP configuration/API” 应写清楚这一点。

### 低

- **L1. Mail：** `mail` 步骤和 Mailer 都存在，但 `jenkins.yaml.j2` 没有 SMTP 配置，全仓也找不到 Jenkins 邮件来源。`MailStep` 直接 `Transport.send`（第 145 行）。发信失败是否中断部署取决于 pipeline 怎么包裹，审批前通知应写成不阻塞。`Jenkinsfile-peer` 目前没有 `mail`。
- **L2. 保留策略：** spine 要求至少 200 个构建。`Jenkinsfile-peer:9` 和 `Jenkinsfile:13` 都是 `numToKeepStr: '10'`，`Jenkinsfile-plan` 没有设置。Declarative `options` 在运行时写回 job 属性，单靠 Job DSL 设置大概率不够（这一点由 Jenkins 常识推断，未实测）。
- **L3. Terraform：** BOM 的 1.14.4 不是 1.14 线最新版（1.14.9），全局最新是 1.17.1（2026-10-28）。我没有找到 CLI 的官方补丁支持窗口，所以 1.14 是否仍在维护未核实。
- **L4. cloudflared：** 通过 apt 安装且未固定版本（`ansible/roles/cloudflared/tasks/main.yml:22-27`），不在 AD-10 的 BOM 内。
- **L5. 过期默认值：** `ansible/roles/jenkins/defaults/main.yml:60-70` 的是升级前的源版本清单（如 `github: 1.45.0`），不是当前基线，不要把它当作现状引用。
- **L6. 签名算法：** 省略 `signatureAlgorithm` 时默认 SHA-256，但系统属性 `jenkins.github.webhook.signature.default` 可以改默认值。JCasC 应显式写 SHA256。凭据 ID 配错时全部投递都返回 400，这是失败关闭，但 push 会被静默丢失。

## 逐项声明核查

状态：confirmed = 已确认，wrong = 与事实不符，unverified = 未能核实。

### Jenkins GitHub 插件（AD-13）

| 声明 | 状态 | 依据 |
| --- | --- | --- |
| 校验 HMAC-SHA256 | confirmed | v1.45.0 起支持，默认 SHA-256：[RequirePostWithGHHookPayload.java](https://github.com/jenkinsci/github-plugin/blob/master/src/main/java/org/jenkinsci/plugins/github/webhook/RequirePostWithGHHookPayload.java)，[releases](https://github.com/jenkinsci/github-plugin/releases) |
| 错误签名或无签名返回 400 | confirmed，有例外 | 同上。例外见 H3（`X-Jenkins-Validation` 返回 200） |
| 未配置 secret 时接受一切 | confirmed | 源码注释：“If no hook secret is configured, then the signature is ignored” |
| 在任何 job 启动前拒绝 | confirmed | 验签在 `target.invoke` 之前 |
| 先在 GitHub 配 secret，再配 Jenkins | confirmed | 由上述逻辑推出：无配置时忽略签名，反向顺序会拒收投递 |
| 插件版本 1.47.0 | confirmed（BOM 与最新版一致） | `toolchain-bom.yml`；[插件页](https://plugins.jenkins.io/github/)；发布于 2026-06-10，要求 core 2.504.3；包含 SECURITY-3704 修复 |
| 线上实际运行 1.47.0 | unverified | 公网无法读取 |
| payload 不能选择代码 | confirmed，有小注 | 只用于匹配仓库并触发轮询；pusher 名进入 build cause 文本：`DefaultPushGHEventSubscriber.java` |
| 线上 webhook 当前没有 secret | confirmed | `gh api`：`secret: null`，`events: [push]`，`content_type: json` |

### GitHub 与 Cloudflare（AD-2、AD-13）

| 声明 | 状态 | 依据 |
| --- | --- | --- |
| webhook 不能发送自定义 header | confirmed | [REST 文档](https://docs.github.com/en/rest/repos/webhooks#create-a-repository-webhook)：`config` 只有 `url`、`content_type`、`secret`、`insecure_ssl` |
| Access service token 要靠 header | confirmed | [Cloudflare 文档](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)；单 header 变体同样需要自定义 header |
| ingress 支持路径正则 | confirmed | [配置文档](https://developers.cloudflare.com/tunnel/advanced/local-management/configuration-file/)；`ingress/rule.go:61`；Go `regexp/syntax` |
| 其余路径走 404 catch-all | confirmed（机制） / wrong（线上现状） | `config.yml.j2` 有 `http_status:404`，但 H4 的路径绕过了精确匹配 |
| `repo-validation` 当前不是 required check | confirmed | ruleset “Protect main” 只有 deletion、non_fast_forward、pull_request |

### HCP Terraform（AD-1、AD-2、AD-4）

| 声明 | 状态 | 依据 |
| --- | --- | --- |
| local execution 下 plan/apply 在本地跑，HCP 只存 state | confirmed | [Workspaces API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/workspaces)；v1.14.4 `cloud/backend.go:899` |
| API 能断言组织、execution-mode | confirmed | 同上 |
| API 能断言 Terraform 版本 | 部分 wrong | 字段存在，但 local 模式下不起作用（M6） |
| API 能断言 state lineage | 部分 wrong | [state-versions API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-versions) 响应无 lineage，需读原始 state |
| `-lock-timeout` 对 cloud backend 生效 | confirmed（源码），未实测 | `cloud/state.go` 在 `ErrWorkspaceLocked` 时设置 `lockErr.Info`；`statemgr.LockWithContext` 据此重试 |
| saved plan 可用于 local-exec cloud workspace | confirmed | `Jenkinsfile:265,298` 现有流程就是这样；`cloud.State` 实现 `StateSnapshotMeta`；状态变化时报 “Saved plan is stale”（`backend_local.go:331`）。未找到 HashiCorp 专门说明这一组合的文档 |
| `plan -lock=false` 只读可用 | confirmed（源码），未实测 | local 路径；`cloud/state.go` 的 `disableLocks` |
| 组织版本支持 AD-5 的隔离 | unverified | 见 M1 |
| 工作区映射 | confirmed | `terraform/proxmox/versions.tf`、`terraform/oci/versions.tf` |

### Jenkins 运行时（AD-11、约定表）

| 声明 | 状态 | 依据 |
| --- | --- | --- |
| `input` 记录审批人 | confirmed | run 上有 `ApproverAction`，flow node 上有 `InputSubmittedAction`：`InputStepExecution.java`；管理员可绕过 submitter 检查，但 `controller-admission.py:59` 重新校验了组 |
| `iac-approvers` 组真实可用 | unverified | realm 不在仓库中；Jenkins 自带用户库不提供组，`ldap` 在 BOM roots 里，线上 realm 未知 |
| 保留至少 200 个构建 | wrong（相对仓库现状） | 见 L2 |
| Mailer `mail` 步骤 | confirmed（步骤存在），SMTP unverified | [步骤文档](https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/)；`MailStep.java`；见 L1 |
| JCasC 可管理 webhook secret | confirmed（配置键），未实测 | 插件测试资源 `configuration-as-code.yml` |
| Job DSL 可管理 job | 技术可行，但仓库中缺失 | [插件页](https://plugins.jenkins.io/job-dsl/)；见 M2 |
| JCasC 不影响 UI 凭据 | unverified，有反证 | [JENKINS-64079](https://issues.jenkins.io/browse/JENKINS-64079)；见 M3 |
| 无 checkout 时轮询可能无基线 | confirmed，但低估 | 见 H1 |

### 工具链固定版本

| 版本 | 状态 | 依据 |
| --- | --- | --- |
| Jenkins 2.568.3 | 已被安全修复超越 | [LTS changelog](https://www.jenkins.io/changelog-stable/)：最新 2.580.2；见 H2 |
| Java 25 / Temurin 25.0.4.1 | confirmed 支持 | [Java 支持策略](https://www.jenkins.io/doc/book/platform-information/support-policy-java/)：至 2029-09；最新补丁版本 unverified |
| Terraform 1.14.4 | 存在但已旧 | HashiCorp releases；见 L3 |
| ansible-core 2.19.12 | 本月 EOL | 见 M4 |
| community.general 13.3.0 | 有更新版本 | Galaxy：14.0.0 |
| script-security、pipeline-groovy-lib | 受公告影响 | 见 H2 |
| configuration-as-code 2117 | 最新性 unverified | 未核查 |

## 无法核实的内容

- 线上 `IaC-Homelab-Pipeline` 的 job 配置（lightweight、trigger）。
- 线上安全 realm、SMTP 配置、插件实际版本。
- HCP 组织版本、工作区 `terraform-version` 实际值、现有 token 类型。
- cloudflared 线上版本。
- 没有实际运行过 `-lock-timeout`、`plan -lock=false` 或 JCasC 重载。
- 我没有向 webhook 发 POST，所以签名行为全部来自插件源码，不是线上观察。
- 所有 Jenkins 插件源码读取的是 master 分支，不是 BOM 固定版本的 tag。Terraform 的 `cloud/state.go` Lock、`cloud/backend.go`、“Saved plan is stale” 已在 v1.14.4 tag 上核对；`LockWithContext` 和 `StateSnapshotMeta` 只读了 main 分支。
- `canSettle`、`User.getAuthorities()` 在 admission 上下文里的行为未实测。
