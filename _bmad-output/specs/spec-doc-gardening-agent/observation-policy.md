# Observation Policy

本 companion 回答 SPEC 原有的四个 open question，定义 CAP-1 至 CAP-4 在取证阶段必须遵守的策略：管理范围如何判定、观察哪些目标、可达性如何重试、哪些陈述值得审计、允许接触什么、证据留多久。与 [evidence-model.md](evidence-model.md) 配合使用——evidence-model 定义 gate 如何裁决，本文件定义喂给 gate 的证据怎么取。

## 1. Active Management Standard / 有效管理判定

一个组件只有**同时**满足以下两项，才算"仍由 IaC 有效管理"：

1. 仓库中存在管理该组件的代码（Ansible role 或 playbook）；
2. 目标主机出现在**当前** inventory 中——Terraform 动态 inventory（`cloud.terraform.terraform_provider`）或 `ansible/inventory/bare_metal/hosts.yml`。

| 代码 | 在册 | 判定 | 允许动作 |
|---|---|---|---|
| 有 | 有 | 有效管理 | 进入 truth priority 表 |
| 有 | 无 | **不确定** | 升级人工，不得视为有效管理 |
| 无 | 有 | **不确定** | 升级人工 |
| 无 | 无 | 非管理边界（须另有文档声明） | 见 evidence-model truth priority |

只有代码存在就判定为有效管理，正是原 open question 所指的失效模式：**残留的废弃代码会被误读为现行事实**。llm-server 退役过程中曾同时存在 role、playbook 与文档，而服务已在关停——当时任何只看代码的判定都会出错。

两项判据均可由 checkout 加 Terraform state 直接得出，**不需要任何凭据**。

## 2. Observation Registry and Retry Tiers / 观察目标登记与重试分级

### 显式登记

观察目标是**显式 opt-in 的登记表**，不由代码或 inventory 自动推导。每个条目声明自己的层级；周期性条目还须声明自己的窗口长度。

**未登记的目标一律不探测、不因不可达而升级。** 这不是遗漏，是主动选择。

代价必须明说：未登记目标的相关陈述只有文档与代码两条腿，按 [evidence-model.md](evidence-model.md) 的 truth priority，它们永远只能是 `consistent` 或 `unresolved`，**不可能到达 `document_drift`**。因此把一个目标排除在观察之外，同时也就是放弃对它上面一切内容的自动修复。

### 层级

| 层级 | 适用目标 | 最少尝试次数 | 最短观察窗口 |
|---|---|---|---|
| 常在线 | 持续运行的主机与服务 | 3 | ≥ 24 小时 |
| 周期性 | 登记时声明了自身周期的目标 | 覆盖 ≥ 2 个完整周期 | 由登记声明的周期决定 |

周期长度**只能来自登记声明，不得由观测历史反推**——反推会把"停机久了"读成"周期变长了"。

对周期性目标套用常在线层级本身即为策略违规，而不只是"结果比较吵"：短窗口必然错过上线时刻，会把该目标的**正常状态**稳定误报为持续不可达。

跨时段重试后仍失败，只能升级人工。任何层级下，不可达都不构成废弃的证据。

### V1 的登记内容

周期性层级**当前没有成员**。T7910 冷备份服务器及其上的资源**不登记**：其开机节奏不规律，可能超过半个月不上线，无法声明一个可靠的周期。层级定义保留，以便日后新增条目时无需重新决策。

## 3. Key Claims for V1 / V1 关键陈述

V1 只审计**能绑定确定性 oracle 的标量陈述**：

- 端口
- 镜像 tag 与版本
- 文件路径
- 资源规格（CPU、内存、磁盘容量）
- 主机名与 IP

形态与 `tools/check-doc-claims.py` 现有的 claim 集一致，因此 V1 是对它的扩展而非替换。

明确排除在 V1 之外：

- **拓扑与依赖关系陈述**（谁连谁、谁依赖谁、流量经过哪里）——无法绑定确定性 oracle
- **运维流程步骤**（部署与恢复步骤是否仍然有效）——验证它们等同于执行它们，与只读约束冲突

没有确定性 oracle 的陈述属于 V1 范围之外，**即使模型对它很有把握，也不得提名进入修复路径**。

## 4. Authorized Runtime Interfaces / 授权的运行时接口

V1 只授权一类运行时观察：

- **无凭据网络探测** —— TCP 连通性、HTTP 健康检查

未授权，需新决策方可使用：NetBox API、Proxmox API、HCP、Terraform state 远程读取，以及任何需要 token、密钥或口令的接口。

**V1 的文档治理工具不持有任何生产凭据。** 这与第 1 节共同成立：管理范围的判定不需要凭据，运行时观察也不需要，因此整个 V1 不引入凭据边界。

所有观察必须只读、无影响、无破坏，并按 evidence-model 的 Audit Record 要求记录方法、目标、时间与结果。

## 5. Observation Retention / 观察证据保留

运行时观察写入 gitignore 的 `tmp/` 路径，**保留 15 天**。

观察保存在本地而非 CI artifact，因此 CI artifact 的 14 天保留期不构成约束。

`tmp/` 是工作目录状态，不进版本库、不做备份：clean 或重新 clone 会丢掉观察历史。这可以接受——观察随时可以重新探测取得——但代价是**一个整窗口离线的目标会丢掉此前的尝试记录，重试计数从头开始**。
