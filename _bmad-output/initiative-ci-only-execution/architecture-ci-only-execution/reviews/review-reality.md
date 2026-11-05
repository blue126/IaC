# 技术现实核验：IaC CI-Only Execution 架构脊柱

- 日期：2026-11-05
- 被审对象：`.worktrees/ci-only-architecture/docs/architecture/ci-only-execution-architecture.md`（工作区未提交版本）
- 方法：原生联网核验 + 仓库核对 + 只读线上探测。未修改脊柱或任何仓库文件。
- 只读线上动作：`gh api` GET（webhook、ruleset、Actions secret 名称）；对 `jenkins.willfan.me` 的 6 个路径发 GET，只看状态码和响应头。

## 结论：需修改后才能作为 build substrate

AD-13 对 GitHub 插件的核心判断成立：共享密钥、HMAC-SHA256、签名失败返回 400、webhook 只触发轮询。但有四处与现实不符，其中 F1、F2 会让 AD-13 的规则落地后不成立或不工作。

| # | 严重度 | 问题 | 涉及 |
| --- | --- | --- | --- |
| F1 | 高 | 隧道规则是未锚定正则，“其他路径一律 404”已被线上实测否定 | AD-13、AD-12 |
| F2 | 高 | 切到 `Jenkinsfile-peer` 后，push 很可能不再触发构建 | AD-13、AD-2 |
| F3 | 高 | 插件验签是 fail-open：未配置密钥时完全不验；脊柱没有要求断言这一点 | AD-13 |
| F4 | 中 | `repo-validation` 不是必需检查，main 规则集不要求任何状态检查 | AD-2、架构图 |
| F5 | 中 | OCI 在范围内，但没有任何作业、凭据或代码，也没标“待新增” | 范围、AD-4、结构种子 |
| F6 | 中 | Job DSL 和 webhook 密钥的配置路径不存在 | AD-11、AD-13、AD-10 |
| F7 | 低 | `No mirror` 与 CT107 的 root 裸仓库字面冲突 | AD-3 |
| F8 | 低 | 引用的插件页面不支撑 AD-13 的签名论断 | sources |

## 重点问题逐项回答

### 1. 插件 1.47.0 是否通过共享密钥验证签名？是，但有条件

- 版本：保存的 job 配置（`.local/proxmox-migration-closure-20261027/jenkins/jenkins-after.xml`，job `IaC-Homelab-Pipeline`）写的是 `github@1.47.0`，`ci/toolchain-bom.yml` 也固定 1.47.0。线上实际版本需登录才能看，未核验。线上 core 版本由响应头确认是 2.568.3，与 BOM 一致。
- `ansible/roles/jenkins/defaults/main.yml` 里的 `github: "1.45.0"` 是旧升级源基线，不是现行版本，不矛盾。
- 算法：`SignatureAlgorithm` 枚举定义 SHA256（`X-Hub-Signature-256`，`HmacSHA256`）和已弃用的 SHA1，1.45.0 起支持。默认 SHA-256，可被系统属性 `jenkins.github.webhook.signature.default` 或单条配置改回 SHA-1。比较用 `MessageDigest.isEqual`，是常量时间比较。
- 密钥来源：全局 GitHub 插件配置里的 `HookSecretConfig`，通过 `credentialsId` 引用 Secret text 凭据。这是全局配置，不是按 job 配置。

### 2. 未签名或签名错误的投递会怎样？

依据 `RequirePostWithGHHookPayload.Processor`（tag `v1.47.0`）：

| 情况 | 结果 |
| --- | --- |
| 已配置密钥，头缺失、前缀不对或摘要不匹配 | HTTP 400 `No valid signature found...`，`doIndex` 不执行，不会碰任何 job |
| 已配置条目，但凭据找不到（`getHookSecret()` 为 null） | 跳过该条目，最终 400（fail-closed） |
| **`hookSecretConfigs` 为空** | **`If no hook secret is configured, then the signature is ignored`，直接放行** |
| 带 `X-Jenkins-Validation` 头的 POST | 验签之前就返回 200 和实例公钥。不触发 job，信息量低 |

所以“before any job starts”成立，“rejects any delivery”只在配置了密钥时成立。见 F3。

### 3. 投递是否只让 job 轮询 SCM，payload 不能选 ref？成立，有两点要补

`DefaultPushGHEventSubscriber` 从 payload 只读 `repository.html_url` 和 `pusher.name`，不读 `ref`。`GitHubPushTrigger.onPost` 调 `item.poll(listener).hasChanges()`，有变化才 `scheduleBuild(cause)`，没有传任何参数。所以 AD-13 的“no payload field reaches a job parameter, ref, or command”成立。

- payload 不是完全不起作用：`repository.html_url` 决定戳哪些带该 trigger 的 job，`pusher.name` 进入构建原因文本。两者都到不了 ref 或命令。
- “A delivery only requests a build”不够准确，它请求的是轮询。没有变化就不构建。例外：`WorkflowJob.poll` 在 job 从未构建过时返回 `BUILD_NOW`，所以新建 job 后第一次投递（哪怕来自其他分支的 push）会启动构建。
- 执行的 SHA 也不来自 payload：独立 CpsScm job 没有 `SCMRevisionAction`，`controller-admission.py` 的 `resolve_source` 在准入时取 `origin/main` 的 HEAD，这与 AD-2 一致。

### 4. GitHub webhook 是否过不了 Cloudflare Access 登录？确实过不了

- GitHub webhook 的 `config` 只有 `url`、`content_type`、`secret`、`insecure_ssl` 四个字段，没有自定义请求头，也没有客户端证书选项。
- Access 的机器认证要 mTLS 或 service token（`CF-Access-Client-Id`/`Secret` 两个头，或单头 `read_service_tokens_from_header`），都需要发送方能设头或出示证书。
- 唯一能让投递通过的是 Bypass，而 Bypass 不做任何 Access 校验、也不记日志。可以把 Bypass 限定到 GitHub 的 `hooks` 网段（`api.github.com/meta` 当前列出），这是来源过滤，不是认证，且网段会变。
- 线上：`/` 返回 Cloudflare 的 404，不是 Access 跳转；当前没有 Access 挡在前面。
- 注意：脊柱全文没有提 Cloudflare Access。这个结论只活在讨论里。建议在 AD-13 写一句“此路径不用 Access，HMAC 是唯一认证”，否则后来的人可能给它加上 Access 把 webhook 弄断。

## 发现详情

### F1（高）隧道路径是未锚定正则，其他路径能到达 Jenkins

**脊柱：** “The tunnel publishes only `/github-webhook/`; every other path returns 404”。

**现实：** `ansible/inventory/host_vars/jenkins.yml` 写的是 `path: /github-webhook/`。Cloudflare 文档说 `path` 是正则。cloudflared `ingress/rule.go` 用 `r.Path.MatchString(path)`，是子串匹配，不是全匹配。

**线上实测（GET，看 `X-Jenkins` 响应头）：**

| 路径 | 状态 | X-Jenkins | 由谁回应 |
| --- | --- | --- | --- |
| `/` | 404 | 无 | 隧道 catch-all |
| `/github-webhook/` | 405 | 2.568.3 | Jenkins |
| `/x/github-webhook/` | **403** | 2.568.3 | **Jenkins** |
| `/login/github-webhook/` | 404 | 2.568.3 | **Jenkins** |
| `/instance-identity/github-webhook/` | 404 | 2.568.3 | **Jenkins** |
| `/tcpSlaveAgentListener/github-webhook/` | 404 | 2.568.3 | **Jenkins** |

任何含 `/github-webhook/` 的路径都穿过了隧道，所以这条规则今天就没有兑现。

**对 AD-12/AD-13 的影响（推断，未实测）：** “the NetBox endpoint is never published”可能也不成立。Stapler 的 `NameBasedDispatcher` 分派 `doXxx` 时不要求路径已结束，而 `GenericWebHookRequestReceiver` 是 `UnprotectedRootAction`，所以 `/generic-webhook-trigger/invoke/github-webhook/` 很可能进入 `doInvoke`。路由 job 用 `tokenCredentialId`，token 仍是一道门，但“仅内网”这条边界就没了。我没有探测这个路径，因为如果线上有未设 token 的 GenericTrigger job，一次 GET 就可能启动构建。

**修复：** 改成 `path: ^/github-webhook/$`，并在 `deploy-jenkins` 的 verify 里加反向断言（如 `/x/github-webhook/` 响应没有 `X-Jenkins`）。改完用上表重测，并在安全时段确认 generic-webhook-trigger 路径。

### F2（高）切到 `Jenkinsfile-peer` 后 push 很可能不再触发构建

**现实链条：**

1. 触发器走 `WorkflowJob.poll`，它遍历上一次成功构建的 `checkouts()`。列表为空就保持 `NO_CHANGES`。
2. 保存的 job 配置是 `<lightweight>true</lightweight>`。`CpsScmFlowDefinition` 的轻量路径用 `SCMFileSystem` 读脚本后直接返回，不走 `delegate.checkout`，不记录 checkout 和轮询基线。
3. 今天能工作，是因为基线 `Jenkinsfile` 是 `agent any` 且有隐式 checkout。
4. `Jenkinsfile-peer` 是 `agent none` + `skipDefaultCheckout(true)`，全文没有 `checkout`。代码由 admission 打包给 runner，Jenkins 看不到这次 checkout。

**后果：** 第一次构建（`BUILD_NOW`）之后，每次投递都应该是 `No changes`。main 车道静默停止，GitHub 投递状态仍是 200，看起来一切正常。

**可信度：** 由源码推出，未在实机验证。`workflow-job`/`workflow-cps` 读的是 master，不是线上版本。佐证：Jenkins 社区说明轻量 checkout 需要 `checkout scm` 才有轮询；JENKINS-61515 报告过 `skipDefaultCheckout()` 下轮询找不到变化（该 issue 后来标为 Cannot Reproduce，所以它不是决定性证据）。`docs/planning/jenkins-peer-agent-recovery.md`、`docs/guides/jenkins-agent-bootstrap.md` 和 `controller-admission.py` 都没有提到轮询。

**修复：** 二选一，写进 AD-13 或 Entry cutover：

- 把该 job 改成 `lightweight=false`。`CpsScmFlowDefinition` 会在 controller 上做 `setPoll(true)` 的 checkout，建立基线。不需要 executor，也不在 controller 跑 shell，但 controller 上会多一份工作副本。
- 在流水线里加一个专门建立基线的 `checkout`，需要先定它在哪个节点跑，且不能破坏“job 工作区不碰代码”的隔离。

无论选哪个，peer 的 staged run 都要包含“连续两次真实 push 都能触发”的验收，而不是只手动点一次。

### F3（高）验签是 fail-open，脊柱没有防住

**现状：** GitHub API 显示 hook `594682774` 没有 secret，最近投递全部 200。`cicd-architecture.md` 已如实写明目前不验签。

**风险：**

- Jenkins 全局配置为空时，插件静默放行。配置被清掉、JCasC 或恢复备份时丢失，都不会报错，“rejects”就悄悄失效。
- 顺序错误有不同结果：只配 GitHub 时 Jenkins 继续放行；只配 Jenkins 时所有投递 400。应先配 GitHub 密钥，再配 Jenkins，然后立刻做正反两向测试。
- SHA-1 可以通过系统属性或单条配置回到生效状态。脊柱写的是 HMAC-SHA256，但没有要求固定。

**修复：** AD-13 增加：`hookSecretConfigs` 非空且只有 `signatureAlgorithm: SHA256`，preflight 或 verify 用未签名和错签 POST 断言 400。没有这条证据就不算切换完成。

注意：未签名伪造的实际危害比“Prevents”写的小。轮询只比较远端 main，伪造请求没有新提交就不会产生构建，所以“filling the approval queue”不是真实后果。主要收益是挡住轮询滥用，建议改写 Prevents，以免高估。

### F4（中）`repo-validation` 不是必需检查

架构图写 `repo-validation ... --> Required checks --> merge to main`，AD-2 绑定“GitHub branch protection”。

实际：`main` 没有经典分支保护（API 返回 404），只有规则集 `Protect main`（active，bypass 为空），规则是 `deletion`、`non_fast_forward`、`pull_request`（`required_approving_review_count: 0`）。**没有 `required_status_checks`**。`cicd-architecture.md` 也称它为 shadow CI。

所以校验失败的 PR 也能合并，合并后 main 车道就会开始。后面还有两次人工审批，所以不是直通，但图上的门并不存在。

**修复：** 把 `repo-validation` 设为必需（这是 GitHub 配置变更，需单独授权），或把图和 AD-2 改成如实描述。另外 `binds` 里的“branch protection”应改成“ruleset”。

### F5（中）OCI 没有落地痕迹

脊柱 scope、AD-1、AD-4 都把 `terraform/oci` 列为 Jenkins 范围。结构种子把缺失项标了“To add”，但 OCI 没有。

实际：`ci/agent-jobs.yml` 只有 `root:proxmox`；`Jenkinsfile-plan` 的 `ROOT` 只有 `proxmox`；`transaction.py` 和 `plan-snapshot.py` 写死 `proxmox` 和 `iac-proxmox-lab`；`scripts/jenkins/` 和 `ci/` 里没有 OCI 凭据或 root。

**修复：** 标注 OCI 是待新增，并说明 AD-1 的移交是否要等 OCI 就绪。否则按“controller executors 归零即移交”，OCI 写操作会在 Jenkins 还不能执行时就被禁止在本地运行。

### F6（中）Job DSL 和 webhook 密钥没有配置路径

- AD-11 说 JCasC/Job DSL 拥有 Jenkins 元数据。`ci/toolchain-bom.yml` 有 `configuration-as-code`，但 `ci/`、`ansible/` 里找不到 Job DSL，违反 AD-10“BOM 拥有 pin”的前提。`generic-webhook-trigger` 也不在 `ci/` 里，而路由流水线依赖它。
- `ansible/roles/jenkins/templates/jenkins.yaml.j2` 只有 20 行，只管 nodes；`jenkins_manage_casc: false`。
- AD-13 说密钥源是 Ansible Vault，但目前没有代码把它变成 Jenkins 凭据和 `hookSecretConfigs`。
- `GitHubPushTrigger` 在 job 配置里，不在 Jenkinsfile 里，切换入口时也需要有东西保住它。

`ci/agent-jobs.yml` 已经写明这些是 staged 状态，所以这是计划缺口，不是错误。但 webhook 密钥在决策记录里排第一，而它依赖的 restore gate 排在后面，需要确定先用哪条路径下发。

### F7（低）AD-3 的 “No mirror” 与实现字面冲突

`controller-admission.py` 从 CT107 上 root 拥有的裸仓库 `git archive` 出代码包。该裸仓库校验 origin 等于固定 URL，并在每次准入时 fetch main，功能上是缓存，不是第二权威。建议改成“除校验 origin 且每次刷新的 root 缓存外，无其他副本”。

### F8（低）来源不支撑论断

`https://plugins.jenkins.io/github/` 页面不提共享密钥、HMAC 或 SHA-256，README（v1.47.0）也没有。AD-13 的来源应改成 tag `v1.47.0` 的 `RequirePostWithGHHookPayload.java` 和 `SignatureAlgorithm.java`。

## 已确认的其他声明

| 声明 | 结果 | 依据 |
| --- | --- | --- |
| `Jenkinsfile`、`-peer`、`-plan`、`-webhook-router`、`-webhook-router-peer` 存在 | 成立 | 均已跟踪 |
| `Jenkinsfile-maintenance`、`ci/execution-map.yml` 不存在 | 成立，已标 To add | 文件缺失 |
| `ci/toolchain-bom.yml`、`ci/agent-jobs.yml`、`ci/proxmox-plan-policy.json` | 成立 | 均已跟踪 |
| `IaC-ReadOnly-Plan` | 成立 | `ci/agent-jobs.yml`：`manual_only`、`enabled: false`、`secrets: []` |
| `iac-plan`/`iac-deploy`/`iac-apps` | 成立 | agent-jobs、deploy-jenkins-agent、角色断言 |
| CT107、CT110 | 成立 | `jenkins.tf` vmid 107，`jenkins-agent.tf` vmid 110 |
| `repo-validation.yml` 无基础设施凭据 | 成立 | 权限 `contents: read`，不引用 secrets |
| GitHub Actions 无基础设施凭据 | 成立 | 仓库 Actions secret 只有 `CLAUDE_CODE_OAUTH_TOKEN`；环境级和组织级未列 |
| 隧道规则在 `host_vars/jenkins.yml` | 成立，语义见 F1 | 文件第 12-15 行 |
| 工作区表，netbox/esxi 无 cloud 块 | 成立 | `versions.tf` |
| 全局锁 | 成立 | `job-runner.py` `flock` |
| HCP 预检 execution-mode/lineage | 部分 | 代码查了 `local` 和 lineage；AD-4 要求的 Terraform 版本断言未见 |
| saved plan 明文敏感 | 成立 | Terraform `plan` 文档 |
| AD-12 token 认证、不能传 ref | 成立 | `Jenkinsfile-webhook-router-peer`；“内网”见 F1 |
| Gitea 为 n8n-rental 只读 SCM | 成立 | 恢复计划第 72 行 |
| 三个来源 URL | 均可解析 | plugins.jenkins.io、docs.github.com、developer.hashicorp.com |

## 未核验

- 线上 Jenkins 的 `hookSecretConfigs` 和插件版本（需要登录；未使用任何凭据）。
- `iac-approvers` 在 LDAP 里是否存在，仓库里只有引用。
- `/generic-webhook-trigger/invoke/github-webhook/` 是否真能到 `doInvoke`（故意未探测）。
- F2 未在实机验证。验证办法：staged peer job 连续两次真实 push。

## 来源

- github-plugin v1.47.0：[RequirePostWithGHHookPayload](https://github.com/jenkinsci/github-plugin/blob/v1.47.0/src/main/java/org/jenkinsci/plugins/github/webhook/RequirePostWithGHHookPayload.java)、[SignatureAlgorithm](https://github.com/jenkinsci/github-plugin/blob/v1.47.0/src/main/java/org/jenkinsci/plugins/github/webhook/SignatureAlgorithm.java)、[GHWebhookSignature](https://github.com/jenkinsci/github-plugin/blob/v1.47.0/src/main/java/org/jenkinsci/plugins/github/webhook/GHWebhookSignature.java)、[DefaultPushGHEventSubscriber](https://github.com/jenkinsci/github-plugin/blob/v1.47.0/src/main/java/org/jenkinsci/plugins/github/webhook/subscriber/DefaultPushGHEventSubscriber.java)、[GitHubPushTrigger](https://github.com/jenkinsci/github-plugin/blob/v1.47.0/src/main/java/com/cloudbees/jenkins/GitHubPushTrigger.java)、[HookSecretConfig](https://github.com/jenkinsci/github-plugin/blob/v1.47.0/src/main/java/org/jenkinsci/plugins/github/config/HookSecretConfig.java)
- [Jenkins GitHub plugin 页面](https://plugins.jenkins.io/github/)
- [WorkflowJob.java](https://github.com/jenkinsci/workflow-job-plugin/blob/master/src/main/java/org/jenkinsci/plugins/workflow/job/WorkflowJob.java)、[CpsScmFlowDefinition.java](https://github.com/jenkinsci/workflow-cps-plugin/blob/master/plugin/src/main/java/org/jenkinsci/plugins/workflow/cps/CpsScmFlowDefinition.java)
- [Disadvantages of SCM Lightweight Checkout?](https://community.jenkins.io/t/disadvantages-of-scm-lightweight-checkout/450)、[JENKINS-61515](https://issues.jenkins.io/browse/JENKINS-61515)
- [cloudflared ingress/rule.go](https://github.com/cloudflare/cloudflared/blob/master/ingress/rule.go)、[Cloudflare Tunnel 配置文件](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/configuration-file/)
- [Stapler NameBasedDispatcher](https://github.com/jenkinsci/stapler/blob/master/core/src/main/java/org/kohsuke/stapler/NameBasedDispatcher.java)、[GenericWebHookRequestReceiver](https://github.com/jenkinsci/generic-webhook-trigger-plugin/blob/master/src/main/java/org/jenkinsci/plugins/gwt/GenericWebHookRequestReceiver.java)
- [GitHub：验证 webhook 投递](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries)、[GitHub REST：仓库 webhook](https://docs.github.com/en/rest/repos/webhooks#create-a-repository-webhook)、[GitHub meta API](https://api.github.com/meta)
- [Cloudflare Access 策略](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/)、[Service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [Terraform CLI：HCP Terraform](https://developer.hashicorp.com/terraform/cli/cloud)、[terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan)
