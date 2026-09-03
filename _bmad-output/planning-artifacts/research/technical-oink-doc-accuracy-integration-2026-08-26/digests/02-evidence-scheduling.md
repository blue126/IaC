# 证据接口、调度与安全模型

## 结论摘要

**[事实]** HCP Terraform 是本组系统中 revision 绑定最完整者：State Versions API 暴露不可混用的 `state-version-id`、workspace、`serial`、`lineage`、run、创建时间、`vcs-commit-sha`；配置版本另有 `configuration-version-id` 与 ingress `commit-sha`。输出解析是异步的，只有 `resources-processed=true` 才能把“无输出”判定为空；当前输出端点处理未完成时可返回 503，敏感值在受限端点返回 `null`。[S1][S2][S3] **[建议]** 事实主键用 `(workspace_id,state_version_id)`，revision 同时保存 `serial+lineage+run_id+configuration_version_id+commit_sha`；缺字段不得用“最新”补齐。

**[事实]** Ansible 的 `ansible-inventory --list` 默认输出 inventory-script JSON，`setup` 返回 `ansible_facts`，可按 subset/filter 缩减；事实默认仅驻留当次运行内存，持久缓存需显式插件，长运行中的 `ansible_date_time` 会陈旧。[S4][S5] **[推论]** Ansible 没有跨主机原子 revision。**[建议]** 身份至少取 `inventory_hostname` 加受控采集的 `machine_id`，绑定控制端 Git SHA、inventory digest、Ansible 版本、`observed_at`，逐主机记录成功/失败，禁止用旧缓存伪装本次观测。

**[事实]** NetBox REST API 以 JSON、对象 `id`、`last_updated` 提供读取；`/api/extras/object-changes/` 是只读变更流，含用户、时间、request UUID 及变更前后 JSON 快照。Event Rule webhook 经 Redis/rqworker 异步发送，失败任务可检查，因此 webhook 到达不等于数据已完整同步。[S6][S7][S8] **[推论]** request UUID 是因果关联键，不是全库 snapshot revision。**[建议]** 事件只携带 `(object_type,id,request.id,event_time)` 触发定向重读，周期全量扫描用 `(type,id,last_updated)` 校验并修复漏事件。

**[事实]** Proxmox VE 提供 JSON REST API且 API 由 JSON Schema 描述；`PVEAuditor` 为只读角色，分离权限 token 的有效权限是用户与 token ACL 的交集并可设过期时间。[S9][S10] **[推论]** 常规资源 GET 是实时视图，官方接口未给出与 HCP state version 等价的全局不可变 revision。**[建议]** 身份用 `(cluster,node,vmid/type)`，保存 PVE 版本、endpoint、响应 digest、`observed_at`；跨 endpoint 结果标记 `non_atomic=true`。

## Reconciliation 与失败语义

**[事实]** GitHub `schedule` 只在默认分支最新提交运行；高负载可延迟甚至丢弃队列，公共仓库 60 天无活动会禁用。Jenkins `H` 是按 job 名稳定散列以摊平负载；Pipeline 提供 timeout、retry、禁并发及 `failure/unstable/aborted/unsuccessful` 状态。[S11][S12] **[建议]** 采用“周期扫描保完整性 + HCP/NetBox webhook 降延迟”：任务幂等、单飞、带抖动；持久化 `scheduled_for, started_at, completed_at, source_revision, coverage, outcome`。发现时间窗缺口即补跑，不把“未触发/被丢弃”当成功；只有完整覆盖且所有强制源 fresh 才发布新事实集。

状态机建议为：`known`（revision 与身份齐全且在 freshness TTL 内）、`stale`（最后成功值仍可展示但超 TTL）、`unknown`（从未成功、身份冲突、异步未完成或本轮覆盖不全）、`failed_closed`（认证/授权、schema、revision 倒退或秘密风险）。面向自动决策时 `unknown/stale` 均不得降级为 false 或沿用旧值；展示层可显示旧值，但必须连同 `observed_at`、失败原因和 last-known revision。

## 数据最小化

**[事实]** Terraform raw state/plan 可含凭据；`sensitive` 只遮蔽显示，值仍在 state，`-json/-raw` 可明文输出；HashiCorp 建议输出专用接口而非授予整份 state。Ansible 日志可能暴露参数，`no_log` 不保护 debug 输出。[S2][S13][S14] **[建议]** 禁止下载、落盘或归档 raw state/plan；仅拉白名单非敏感 outputs/资源元数据，`null+sensitive=true` 保持 unknown。使用只读最小权限、短期 token，日志与 artifact 做字段级 allowlist，禁 body/header/debug 转储；凭据仅经 secret store 注入并限制工作区与保留期。

## 来源

- [S1] HashiCorp, 2025-05-27, accessed 2026-08-26, https://developer.hashicorp.com/terraform/cloud-docs/api-docs/configuration-versions
- [S2] HashiCorp, 2025-05-27, accessed 2026-08-26, https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-versions
- [S3] HashiCorp, 2025-05-27, accessed 2026-08-26, https://developer.hashicorp.com/terraform/cloud-docs/api-docs/state-version-outputs
- [S4] Ansible Project, n.d., accessed 2026-08-26, https://docs.ansible.com/ansible/latest/cli/ansible-inventory.html
- [S5] Ansible Project, n.d., accessed 2026-08-26, https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_vars_facts.html
- [S6] NetBox Labs, n.d., accessed 2026-08-26, https://netboxlabs.com/docs/netbox/integrations/rest-api/
- [S7] NetBox Labs, n.d., accessed 2026-08-26, https://netboxlabs.com/docs/netbox/models/core/objectchange/
- [S8] NetBox Labs, n.d., accessed 2026-08-26, https://netboxlabs.com/docs/netbox/features/event-rules/
- [S9] Proxmox Server Solutions GmbH, 2026-08-04, accessed 2026-08-26, https://pve.proxmox.com/pve-docs/pve-admin-guide.html
- [S10] Proxmox Server Solutions GmbH, 2026-05-21, accessed 2026-08-26, https://pve.proxmox.com/wiki/User_Management
- [S11] GitHub, n.d., accessed 2026-08-26, https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- [S12] Jenkins Project, n.d., accessed 2026-08-26, https://www.jenkins.io/doc/book/pipeline/syntax/#cron-syntax
- [S13] HashiCorp, 2025-11-19, accessed 2026-08-26, https://developer.hashicorp.com/terraform/language/manage-sensitive-data
- [S14] Ansible Project, n.d., accessed 2026-08-26, https://docs.ansible.com/projects/ansible/latest/reference_appendices/logging.html
