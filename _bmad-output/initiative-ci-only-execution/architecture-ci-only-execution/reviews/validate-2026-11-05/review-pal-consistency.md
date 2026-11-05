# Architecture-consistency 对抗评审：IaC CI-Only Execution

**结论：不通过。我构造出 17 组逐字遵守现有 AD 却仍互不兼容的单元对（3 critical、7 high、4 medium、3 low），根因集中在 OCI hub 与 control-plane 的归属、watermark 和锁的 owner，以及 credential 与 audit 的存储面。**

评审范围与限制：
- 只读，未修改或执行任何内容。
- 代码证据表示单元今天的行为。spine 中标为 "To add" 的内容（`ci/execution-map.yml`、`Jenkinsfile-maintenance`）在仓库中不存在，这些对只能从 AD 文字构造。
- 未读取 `terraform/remotecc/oci-hub-workspace.tf`、`terraform/oci/compute.tf`、`Jenkinsfile-webhook-router-peer`，以及 `docs/planning`、`docs/reference` 下的 peer 文档。
- 因此未确认 `oracle-cloud-ubuntu2404` 是否就是 OCI hub，相关结论已限定。

---

## Critical

### ACR-01 — `terraform/oci` 内的 OCI hub 对象有两个 owner
- **Severity：** critical
- **单元 A：** OCI root rollout，遵守 AD-1、AD-4（`terraform/oci` → `iac-oci`，Jenkins 写入）。
- **单元 B：** RemoteCC 侧 OCI hub 管理，遵守 AD-1、AD-14（Jenkins 从不 target OCI hub）。
- **不兼容点：**
  - AD-4 把整个 root 交给 Jenkins，AD-14 却禁止 Jenkins 触碰其中的 hub 对象。
  - A 的一次普通 `terraform apply` 会改写 hub 的 WireGuard 入站规则。
  - B 按 AD-14 认定该对象归自己，并由 RemoteCC 侧修改 `oci_hub_ingress`。AD-14 明确没有跨平面锁，所以两边互相看不见。
  - 路径分类也会撞车：`terraform/oci/oci-hub.tf` 同时是 root 路径和 `excluded` 候选。
- **证据：**
  - `terraform/oci/oci-hub.tf:27`、`terraform/oci/oci-hub.tf:39` 定义 NSG 和 rule。
  - `terraform/oci/oci-hub-ingress.auto.tfvars.json:3-4,11` 显示该配置已启用（非 null，`dynamic` 模式）。
- **新 AD（AD-14a）：** "Ownership is per Terraform address, not per root. Before `terraform/oci` handoff, every `oci_hub*` resource, variable, and tfvars file moves to `terraform/remotecc` through a recorded state move, or is listed in `ci/execution-map.yml` as `remotecc_owned_addresses`. Jenkins plan fails closed if any planned action touches a listed address. No address may have two owners, and `terraform/oci` handoff is blocked until this list is verified."

### ACR-02 — control-plane 目标没有合法的执行 owner，main lane 可以修改自己脚下的 LXC
- **Severity：** critical
- **单元 A：** main lane 加 execution map，遵守 AD-1（每个 playbook 恰有一个 owner）、AD-4（`terraform/proxmox` 归 Jenkins）。
- **单元 B：** watchdog，遵守 AD-11（agent 更新不从被更新 agent 上的 job 运行；pipeline 不重启自己的 controller）。
- **不兼容点：**
  1. AD-1 的 owner 枚举只有 `jenkins|maintenance|remotecc|retired`。`deploy-jenkins.yml`、`deploy-jenkins-agent.yml`、`upgrade-jenkins.yml` 只能标 `jenkins` 或 `maintenance`，而这两者都在 CT110 的 job 里运行，与 AD-11 矛盾。AD-9 又排除配置变更，所以合法路径为空。
  2. `jenkins.tf`、`jenkins-agent.tf` 位于 `terraform/proxmox`。一份合法的 saved plan 可以 replace CT110 或 CT107，而执行者正在 CT110 上。没有任何 AD 拒绝这种 plan。
  3. AD-13 的 tunnel 规则由 `host_vars/jenkins.yml` 持有，`deploy-cloudflared.yml` 和 `deploy-gitea.yml` 的目标都是 `jenkins` 主机。按现有实现，main lane 拒绝该主机，所以 tunnel 规则和 Gitea 在 handoff 后没有写入路径。
- **证据：**
  - `scripts/jenkins/transaction.py:108-111`：拒绝 `jenkins`，但只要有 `control-plane:jenkins-agent` 就放行 agent playbook。
  - `scripts/jenkins/transaction.py:128-133`：`terraform/proxmox/jenkins-agent.tf` 映射到 `deploy-jenkins-agent.yml`。
  - `ansible/roles/jenkins-agent/handlers/main.yml:6`：写 `agent-update-pending`，说明 playbook 先改 agent 再异步交给 watchdog。
  - `terraform/proxmox/jenkins-agent.tf:4,9`、`ansible/playbooks/deploy-cloudflared.yml:3`、`ansible/playbooks/deploy-gitea.yml:3`、`ansible/inventory/host_vars/jenkins.yml:12-14`。
- **新 AD（AD-11a）：** "Add owner value `control-plane` to AD-1. Every playbook, role, host variable, or Terraform address that reaches CT107 or CT110 is `control-plane`. Only a signed independent bundle executed by the watchdog applies it, under a dedicated `control-plane` approval and the same lock store. Main and maintenance plans fail closed if any action touches a `control-plane` address. The map states which co-resident services on CT107 (Gitea, cloudflared) use this path."

### ACR-03 — `last_verified_sha` watermark 有多个隐含写者，且存储位置未定义
- **Severity：** critical
- **单元 A：** main lane，遵守 AD-6（验证通过后推进）。
- **单元 B：** maintenance lane 的 manual playbook，同样遵守 AD-6（验证通过且 SHA 不可变）。
- **单元 C：** watchdog restore，遵守 AD-11。
- **不兼容点：**
  - AD-6 只说 "stored durably"，没有定义 owner、存储位置或单调性。
  - maintenance 在 SHA X 验证通过后推进，可能跳过 `last..X` 中未部署的变更，也可能把 main 的 watermark 回退。
  - 存在 CT107 时，restore 会回滚 watermark，已部署的变更会被重选。存在 CT110 时，它又与恢复后的 controller 记录分叉。
  - Terraform root 没有 verify 合约，因此 root 的 "verification" 是 apply 成功，还是下游 Ansible verify 成功，两种解读都合法。
- **证据：**
  - `scripts/jenkins/controller-admission.py:212-220`：今天按 first-parent diff 计算，不存在 watermark。
  - job 无持久可写路径，运行目录在 `scripts/jenkins/job-runner.py:424-460` 被清除。
- **新 AD（AD-6a）：** "The root runner's registry on the peer agent is the single owner of `last_verified_sha`, keyed by root or playbook. Only the runner writes it, in one atomic compare-and-swap, from a signed verification result, and only forward along `origin/main` first-parent ancestry. A root advances after its apply and all dependent playbooks in the DAG verify. Maintenance never advances a watermark except through a named `reconcile` mode that proves the whole range was applied. The store is backed up independently of Jenkins home and is unaffected by controller restore."

---

## High

### ACR-04 — 锁集合的计算者、输入和词汇都未定义
- **Severity：** high
- **单元 A：** root runner，遵守 AD-4、AD-10。
- **单元 B：** main lane change selection，遵守 AD-4、AD-6（每次按所选 root 和 domain 加锁）。
- **不兼容点：**
  - runner 只接受与 profile 完全相同的静态 scope，lease 也禁止变化，而 AD-6 要求按 watermark 动态选择。两者都合规，但无法拼接。
  - AD-4 规定 key 只有 `root:` 和 `host:`，现有 scope 却使用 `service:`、`control-plane:`、`integration:`。
  - `<name>` 是 `proxmox` 还是 `terraform/proxmox` 未定义。
  - 新建主机在 plan 前不在 inventory 中，因而无法预先展开。不同 SHA 的 map 也会把同一 service 展开成不同的 host。
- **证据：** `scripts/jenkins/job-runner.py:39`、`scripts/jenkins/transaction.py:43-44`、`scripts/jenkins/transaction.py:108-110`、`scripts/jenkins/transaction.py:152`、`ci/agent-jobs.yml:15,25,48`。代码中尚无 key lock，只有 `global.lock`。
- **收紧 AD-4：** "Controller admission computes the lock set from the execution map at the admitted SHA and signs it as `lock_keys`. The runner acquires it atomically in sorted order and rejects any other format. Canonical forms are `root:proxmox`, `root:oci`, and `host:<inventory_hostname>`. Non-canonical names are map-only aliases and never reach the runner. A Terraform-created host must be declared in the map before planning. Each lock set records the map digest."

### ACR-05 — verify 失败后的锁释放、重试和 `force-unlock` 三者不相容
- **Severity：** high
- **单元 A：** main lane，遵守 AD-7（"verification must pass before locks release"）。
- **单元 B：** maintenance 或重试，遵守 AD-6（"same transaction locks"，新 plan 重试）。
- **不兼容点：**
  - 按 AD-7 字面，失败的事务永不释放锁，B 永远阻塞。
  - 若失败时释放锁（代码现状），其他事务可能进入半部署的主机。
  - `force-unlock` 指 HCP state lock 还是 AD-4 registry lock也未定义。若它本身也要先获取 "same locks"，就无法解除孤儿锁。
  - runner 重启后 quarantine，已持有的 key 如何处置同样未定义。
- **证据：** `scripts/jenkins/job-runner.py:400-410`（`finally` 中无条件结束 active）、`scripts/jenkins/job-runner.py:87-98`、`scripts/jenkins/job-runner.py:476-486`。
- **收紧 AD-4、AD-6、AD-7：** "A failed transaction moves its keys to `failed-held`, owned by that transaction record. Only a retry or maintenance run that names the record may inherit them, and inheritance creates a new plan and approval. `force-unlock` is split into `force-unlock-hcp` and `release-registry-lock`. Both take a typed target and confirmation, and the second is the only path that bypasses holders. Quarantine preserves lock records, and `verify-and-release` must resolve them explicitly."

### ACR-06 — global lock、queue 与 key lock 的语义互相架空
- **Severity：** high
- **单元 A：** root runner，遵守 AD-10（一次一个 job；busy 从不 refusal；bounded queue）。
- **单元 B：** main lane，遵守 AD-2、AD-4（审批暂停，锁跨 plan 到 verify）。
- **单元 C：** controller admission，遵守 AD-5 的短时绑定。
- **不兼容点：**
  - 若 job 持 global lock 穿过两次人工审批，单个 job 内 key lock 永远不会竞争，AD-4 形同虚设，read-only plan 和 apps 也要等人。
  - 若审批期间释放 global lock，又违反 "cleanup before next job"。
  - "bounded" 与 "never a refusal" 在队列满时直接矛盾，refusal 还会使 main build 失败。
  - 60 秒的 admission TTL 无法在队列等待中存活，20 分钟的 plan timeout 也可能短于等待时间。
- **证据：**
  - `scripts/jenkins/job-runner.py:120-121`、`scripts/jenkins/job-runner.py:280-284`：busy 时拒绝，`flock` 的持有范围覆盖 execute 全程。
  - `scripts/jenkins/controller-admission.py:190`：60 秒 TTL。
  - `scripts/jenkins/transaction.py:213,228`：每次审批 900 秒。
  - `Jenkinsfile-plan:6`、`Jenkinsfile-peer:10`、`Jenkinsfile-peer:31`。
- **收紧 AD-10：** "A job holds the global lock for its whole run, including approval waits. Key locks exist for state that outlives one job, per ACR-05. The queue lives before admission: a waiting build holds no signed admission, and a fresh admission is issued when it reaches the head. The depth is fixed. Overflow leaves the Jenkins build waiting and is reported as `queued-overflow`, not refused. Pipeline timeouts count execution only."

### ACR-07 — OCI root 无法套入 main lane 的共享数据形状
- **Severity：** high
- **单元 A：** OCI rollout，遵守 AD-5、AD-6（root 独立）、AD-7（static inventory）。
- **单元 B：** main lane，遵守 AD-2、manifest 与 approval 约定。
- **不兼容点：**
  - manifest 按单 root 绑定，approval 却写成 "Terraform plan manifest" 单数。Proxmox 和 OCI 同时选中时，可以是一条或两条 approval，先后顺序也未定义。
  - Proxmox apply 成功、OCI 失败时，"downstream stop" 与 "roots independent" 给出不同结果。
  - Terraform-backed inventory 解析遇到 OCI 静态主机会以 "target missing" 拒绝。
  - `IaC-ReadOnly-Plan` 没有 OCI 的形状：broker 策略是 proxmox 专用的。
- **证据：** `scripts/jenkins/transaction.py:26`（单 workspace）、`scripts/jenkins/transaction.py:80-81`、`scripts/jenkins/transaction.py:91`、`scripts/jenkins/transaction.py:176`、`scripts/jenkins/transaction.py:211`、`Jenkinsfile-plan:9`、`ci/agent-jobs.yml:15`。
- **新 AD（AD-6b）：** "One transaction may contain several roots, but each root has its own manifest, approval record, and DAG node, applied in map order. A failed root stops only its descendants. Inventory is a typed union: `terraform:<root>` or `static:<path>`, and the Ansible digest covers both. A root may be selected for read-only plan only if it has its own projection policy."

### ACR-08 — credential 有两套不相容的存储面
- **Severity：** high
- **单元 A：** OCI credential rollout，遵守 AD-5（OCI key 是 UI 上传的 Jenkins secret-file）。
- **单元 B：** root runner 和 admission，遵守 AD-5（manifest 绑定 version 与 digest）。
- **单元 C：** JCasC adoption，遵守 AD-11（JCasC 拥有 credential metadata）。
- **不兼容点：**
  - runner 只绑定 controller 根文件里带 version 的 secret，不走 Jenkins Credentials。UI 上传的 key 既无 version，也不在这条路径上。
  - C 声明 credential metadata 时，可能覆盖 UI 上传的条目。这一点来自我对 JCasC 的了解，未在仓库验证，需针对 pin 的插件版本确认。
  - AD-13 把 Vault 定为 secret 来源，但没有定义 Vault 到 Jenkins 的写入者。
- **证据：** `scripts/jenkins/controller-admission.py:119-123`、`scripts/jenkins/job-runner.py:185-197`、`ci/agent-jobs.yml:26-28`。
- **收紧 AD-5：** "Every credential has one declared store, listed by ID: `runner-root-file` for all job-bound secrets, or `jenkins-credential` for controller-only uses such as the webhook secret. OCI private key uses `runner-root-file`, with an operator-supplied version. JCasC references credentials and never creates or removes values it does not declare. One named writer is recorded for each ID."

### ACR-09 — controller restore 会抹掉 audit store
- **Severity：** high
- **单元 A：** 审计，遵守 Audit 约定（Jenkins build record 是 audit store，至少 200 builds）。
- **单元 B：** watchdog，遵守 AD-11。
- **不兼容点：**
  - 备份包含整个 Jenkins home，restore 替换 home，提交后删除旧目录。备份点之后的 build、`input` 审批人和已完成 mutation 的记录都会消失。
  - AD-6 的 audit log 和 AD-9 的事件记录也没有定义存储。
  - 现有 `Jenkinsfile-peer` 只保留 10 个 build，与约定直接冲突。
- **证据：** `scripts/jenkins/controller-maintenance.py:179-188`、`scripts/jenkins/controller-maintenance.py:314-315`、`scripts/jenkins/controller-maintenance.py:345-346`、`Jenkinsfile-peer:9`。
- **收紧 Audit：** "Before and after each mutation, the runner writes a signed append-only record (identity, approvers, digests, result) to a store outside Jenkins home that survives controller restore. Maintenance, watchdog, and AD-9 events use the same store. Jenkins builds are a view, not the only copy. Restore keeps the replaced `builds` tree until records are reconciled."

### ACR-10 — owner 是 per-playbook，而 AD-14 的边界是 per-host
- **Severity：** high
- **单元 A：** execution map，遵守 AD-1（每个 playbook 一个 owner）。
- **单元 B：** RemoteCC 侧，遵守 AD-14。
- **不兼容点：**
  - `site.yml` 打到 `all` 减几个组，`install-tailscale.yml`、`upload-snippet.yml`、`sync-netbox.yml` 打到宽泛的组。这些 playbook 标为 `jenkins` 完全合规，但默认 inventory 是整个目录，包含 `terraform-remotecc.yml`，可能解析出 RemoteCC 对象。
  - 共享 PVE 上的 whole-host 操作需要操作员确认另一侧空闲，但确认没有进入 Ansible digest，不可审计。
- **证据：** `ansible/playbooks/site.yml:8`、`ansible/playbooks/install-tailscale.yml:3`、`ansible/playbooks/upload-snippet.yml:3`、`ansible/playbooks/sync-netbox.yml:3`、`ansible/ansible.cfg:6`、`ansible/inventory/terraform-remotecc.yml`、`ansible/playbooks/configure-pve2-local-ssd.yml:3`。
- **收紧 AD-1、AD-14：** "Each `jenkins` or `maintenance` playbook declares a host allow-list. The resolved set must be within that list and disjoint from the RemoteCC denylist, or the run stops. Jenkins inventory excludes `terraform-remotecc.yml`. Shared hosts are marked `shared_host`, and a typed `other_side_idle` confirmation is included in the Ansible digest."

---

## Medium

### ACR-11 — owner、handoff 状态和路径分类分散在两个注册表
- **Severity：** medium
- **单元 A：** execution map，遵守 AD-1、AD-6。
- **单元 B：** job rollout，遵守 AD-1（verified entry 决定 handoff）和 Entry cutover。
- **不兼容点：**
  - map 的 `owner: jenkins` 不代表已 handoff，真实状态在 `agent-jobs.yml` 的 `enabled` 和 `evidence` 里，而且只有 job 粒度。Mac 和 Jenkins 可能对同一 playbook 同时认为自己有写权。
  - 变更命中 `maintenance` owner 的 playbook 时，main 可以 fail 整个 build，也可以跳过并推进 watermark。第二种会丢变更。
- **证据：** `ci/agent-jobs.yml:17-18,29-30`、`scripts/jenkins/transaction.py:141-144`。
- **收紧 AD-1、AD-6：** "The execution map is the only registry of handoff per root, playbook, and mode: `handoff: pending|verified` plus an evidence reference. Before `verified`, Jenkins does not select the entry. A change to a `maintenance` playbook does not fail the lane, leaves that playbook's watermark in place, and raises a `pending-maintenance` notification."

### ACR-12 — maintenance 可在旧的不可变 SHA 上覆盖 main
- **Severity：** medium
- **单元 A：** main lane，遵守 AD-2。
- **单元 B：** maintenance，遵守 AD-6（"immutable SHA"）。
- **不兼容点：** B 选择一个旧的 `main` commit 完全合规，却把 service 回退到 main 已验证版本之前。AD-6 只要求 SHA 不可变，不要求是当前 HEAD。
- **证据：** `scripts/jenkins/controller-admission.py:136`（现有 profile 强制 head，但这不是 AD 约束）。
- **收紧 AD-6：** "Maintenance runs only at the current `origin/main` head at admission. Running an older SHA is a separate typed `rollback` mode with its own confirmation, and leaves the target marked for reconcile."

### ACR-13 — state backup 被 cleanup 删除，recovery 无料可用
- **Severity：** medium
- **单元 A：** maintenance，遵守 AD-6（before/after backup 和 recovery procedure）。
- **单元 B：** runner cleanup，遵守 AD-5、AD-10（state backup 是 build-scoped，无条件清除）。
- **不兼容点：** `destructive state removal` 的备份在 run 结束时被证明已删除，而恢复恰好发生在之后。
- **证据：** `scripts/jenkins/job-runner.py:449-460`。
- **收紧 AD-5、AD-6：** "A maintenance state backup is the HCP state-version ID recorded before and after in the audit record, verified as retrievable. Local copies remain build-scoped. A mode whose recovery needs anything else must name an encrypted retained store first."

### ACR-14 — restore 后的 webhook 签名检查不在恢复门内
- **Severity：** medium
- **单元 A：** webhook hardening，遵守 AD-13。
- **单元 B：** watchdog，遵守 AD-11。
- **不兼容点：**
  - resume 只检查 health 和 tuple，没有检查 400 探针。
  - 若备份早于 secret 设置，public ingress 在恢复后会接受未签名请求。
  - 若 Vault 已轮换，恢复出的旧 secret 会拒绝全部合法 delivery。
- **证据：** `scripts/jenkins/controller-maintenance.py:435-439`、`scripts/jenkins/watchdog.py:173`。
- **收紧 AD-11、AD-13：** "Before `resume`, the watchdog re-applies the current Vault webhook secret and proves that unsigned and wrongly signed POSTs return 400. Failure keeps the fence active. Backups without a configured secret cannot be promoted to verified."

### ACR-15 — apps lane 与 main lane 在 CT106 上没有共同的 lock domain 来源
- **Severity：** medium
- **单元 A：** apps lane，遵守 Pipeline lanes 约定。
- **单元 B：** main lane，遵守 AD-4、AD-6。
- **不兼容点：**
  - `apps` 要遵守相同的锁规则，但 map 只分类本仓库路径，无法为 Gitea 应用生成 key。
  - apps 发布到 CT106 与 `deploy-n8n.yml` 指向同一主机，却只有非 canonical 的 `service:n8n-rental`。
  - `failed-held` 状态下（ACR-05），apps 是否被阻塞也没有依据。
- **证据：** `ci/agent-jobs.yml:25,48`、`ansible/playbooks/deploy-n8n.yml:3`、`terraform/proxmox/n8n.tf:13,43`、`docs/guides/jenkins-private-app-ci-contract.md:23`。
- **收紧 AD-6：** "The execution map has an `applications` section that gives each external job fixed `lock_keys`, for example `host:n8n`. Apps profiles use them unchanged, and approvals bind them."

---

## Low

### ACR-16 — router 不属于任何 lane，下游 job 不在 handoff 集合内
- **Severity：** low
- **单元 A：** router，遵守 AD-12。
- **单元 B：** control-plane 归零门，遵守 AD-9、AD-11。
- **不兼容点：** Pipeline lanes 中没有 router。它路由到 `Proxmox-Provisioning`，但该 job 既不在门控集合内，也没有 lane。
- **证据：** `ci/agent-jobs.yml:31-39`、`scripts/jenkins/controller-maintenance.py:27`。
- **收紧 Pipeline lanes：** "Add a non-mutating `router` lane. Every route target is listed in the execution map with a fixed non-mutating class, or the route stays disabled."

### ACR-17 — "mirror" 和 "checkout" 的定义与现有 source 路径不一致
- **Severity：** low
- **单元 A：** admission，遵守 AD-2。
- **单元 B：** runner bundle 路径，遵守 AD-3（无 mirror 可喂给 execution）。
- **不兼容点：**
  - CT107 的 bare repository 产生 execution bundle，字面上类似 mirror。
  - job 不做 checkout，standalone 模式下 SHA 取 admission 时的 head，而不是触发时的 commit。
- **证据：** `scripts/jenkins/controller-admission.py:79-81`、`scripts/jenkins/controller-admission.py:126-135`、`scripts/jenkins/controller-admission.py:169`、`Jenkinsfile-peer:5`。
- **收紧 AD-2、AD-3：** "A controller-side bare cache fetched from `origin/main` at admission is not a mirror if it accepts no other writes. `checkout` means a signed bundle of the admitted SHA. The admitted SHA, not the webhook payload, is the run's identity."

---

## 修复优先级
1. 先关闭 ACR-01、ACR-02、ACR-03。它们决定 OCI handoff、control-plane 变更和 change selection 能否安全开始。
2. ACR-04、ACR-05、ACR-06 应作为一组锁模型一起修改，单独修补会再次互相矛盾。
3. ACR-07、ACR-08 必须在 `terraform/oci` rollout 之前解决。