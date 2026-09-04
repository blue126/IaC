# Observation Policy

本 companion 回答 SPEC 原有的四个 open question，定义 CAP-1 至 CAP-4 在取证阶段必须遵守的策略：管理范围如何判定、观察哪些目标、可达性如何重试、哪些陈述值得审计、允许接触什么、证据留多久。与 [evidence-model.md](evidence-model.md) 配合使用——evidence-model 定义 gate 如何裁决，本文件定义喂给 gate 的证据怎么取。

## 1. Active Management Standard / 有效管理判定

一个组件只有**同时**满足以下两项，才算"仍由 IaC 有效管理"：

1. 仓库中存在管理该组件的代码——Ansible role/playbook **或** Terraform resource/module；
2. 目标主机出现在**当前** inventory 中——Terraform 动态 inventory（`cloud.terraform.terraform_provider`）、`ansible/inventory/bare_metal/hosts.yml`，或 `ansible/inventory/oci/hosts.yml`。

只认 Ansible 是不够的：§3 把 CPU、内存、磁盘规格列为 V1 关键 claim，而这些由 Terraform 供给（例如 `terraform/modules/proxmox-vm/main.tf` 的 `cores` 与 `memory`），只看 Ansible 会把这类候选全部判为"无代码"。OCI 主机同理——AGENTS.md 明确记载它们是不走 Terraform 插件的静态 inventory 例外。

| 代码 | 在册 | 判定 | 允许动作 |
|---|---|---|---|
| 有 | 有 | 有效管理 | 进入 truth priority 表 |
| 有 | 无 | **不确定** | 升级人工，不得视为有效管理 |
| 无 | 有 | **不确定** | 升级人工 |
| 无 | 无 | 非管理边界（须另有文档声明） | 见 evidence-model truth priority |

只有代码存在就判定为有效管理，正是原 open question 所指的失效模式：**残留的废弃代码会被误读为现行事实**。llm-server 退役过程中曾同时存在 role、playbook 与文档，而服务已在关停——当时任何只看代码的判定都会出错。

**只有走 Terraform 动态 inventory 的目标需要 Terraform state。** `*.tfstate` 被 `.gitignore` 排除、不在 checkout 里，`scripts/refresh-terraform-state.sh` 通过 `terraform state pull` 从 HCP 取得，因此这一分支需要凭据，见 §4。

登记在 `bare_metal/hosts.yml` 或 `oci/hosts.yml` 的目标不受此限：那是已提交文件，两项判据都能直接从 checkout 得出。对它们要求 state，只会在 HCP 拉取不可用时无谓地阻塞审计。

## 2. Observation Registry and Retry Tiers / 观察目标登记与重试分级

### 显式登记

观察目标是**显式 opt-in 的登记表**，不由代码或 inventory 自动推导。每个条目声明自己的层级；周期性条目还须声明自己的窗口长度。

**未登记的目标一律不探测、不因不可达而升级。** 这不是遗漏，是主动选择。

代价必须明说：未登记目标的相关陈述只有文档与代码两条腿，生产状态未知。`consistent` 按 [evidence-model.md](evidence-model.md) 的定义要求三方证据一致，因此这类结果**只能是 `unresolved`**——既不能判 `consistent`，也不可能到达 `document_drift`。把一个目标排除在观察之外，同时也就是放弃对它上面一切内容的自动修复。

### 层级

| 层级 | 适用目标 | 最少尝试次数 | 最短观察窗口 |
|---|---|---|---|
| 常在线 | 持续运行的主机与服务 | 3 | ≥ 24 小时 |
| 周期性 | 登记时声明了自身周期的目标 | 覆盖 ≥ 2 个完整周期 | 由登记声明的周期决定 |

周期长度**只能来自登记声明，不得由观测历史反推**——反推会把"停机久了"读成"周期变长了"。

对周期性目标套用常在线层级本身即为策略违规，而不只是"结果比较吵"：短窗口必然错过上线时刻，会把该目标的**正常状态**稳定误报为持续不可达。

跨时段重试后仍失败，只能升级人工。任何层级下，不可达都不构成废弃的证据。

### 登记表位置与 schema

登记表是 [`tools/doc-gardening/observation-registry.yml`](../../../tools/doc-gardening/observation-registry.yml)，与读取它的工具同处一地。每个条目：

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | kebab-case，唯一，与 inventory 主机名一致 |
| `address` | 是 | 探测连接的 IP 或主机名 |
| `tier` | 是 | `always_on` 或 `periodic` |
| `window` | 仅 `periodic` | 一个周期的 ISO-8601 时长，登记声明，不得反推 |
| `probes` | 是 | 一或多项，`type` 为 `tcp` 或 `http`，带 `port`；`http` 另有 `path` |

### V1 的登记内容

常在线层级两个成员：**immich**（`192.168.1.101:2283`）与 **jenkins**（`192.168.1.107:8080`）。

immich 是个说明性的例子：`docs/deployment/immich-deployment.md` 写着 `immich_port: 2283`，而 role defaults 里没有对应的 `immich_port` 标量——正因如此它被 Phase 1 的 claim registry 明确排除。观察实际监听端口是验证这条文档陈述的唯一途径。

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

V1 授权以下只读接口，每一项都绑定它是唯一验证途径的 claim 类别：

| 接口 | 凭据 | 用途 |
|---|---|---|
| TCP 连通性、HTTP 健康检查 | 无 | 端口与可达性类 claim |
| HCP `terraform state pull` | 是 | §1 在册判据的**动态 inventory 分支**；state 不在 checkout 内 |
| NetBox 只读 API | 是 | 设备/服务/IP 登记事实 |
| Proxmox 只读 API（PVEAuditor） | 是 | VM/LXC 的 CPU、内存、磁盘规格 |
| Ansible ad-hoc 只读采集 | 复用既有 SSH | guest 内的文件路径与**应用容器镜像 tag** |

最后一项不可省略。宿主层接口看不见 guest 内部：`service.qwen3-tts.vllm-image` 的 `vllm/vllm-omni:v0.28.0` 是 guest 里由 compose 跑起来的容器镜像，不是 Proxmox 的 VM 模板；`immich_app_dir: /opt/immich` 这类文件路径同样只存在于 guest 文件系统。若不授权这一项，§3 声明的四类关键 claim 里有两类永远没有生产证据，只能 `unresolved`。

Ansible 采集必须**只读**：收集 facts、`stat` 路径、读取生效的 compose 配置。不得执行 playbook、不得改变状态、不得使用有副作用的模块。它不引入新的凭据类别——Ansible 本就持有全部受管主机的 SSH 访问。

**此前"V1 不持有任何生产凭据"的结论已撤回，它是错的。** 无凭据探测最多证明端点可达，证明不了镜像 tag、文件路径或资源规格与代码一致；而 evidence-model 要求生产证据支持代码才允许 `document_drift`。若坚持零凭据，§3 列出的大部分 claim 类别将永远无法闭环。§1 的"在册"判据同样需要凭据。

超出上表的任何接口仍需新决策。凭据必须是专用只读身份，且不得出现在任何 artifact、run record、报告或日志中。按 `spec-oink-doc-accuracy-integration` 的边界，collector 与 detector 是两个信任面：detector、OINK 与 Pages 只消费脱敏产物，永不接收凭据。

**前置条件**：Phase 2 的 `contains_secret()` 目前不认 `$ANSIBLE_VAULT` header，也不认 `vault_*` 赋值。在任何持凭据的 collector 运行之前，这个缺口必须先补上。

所有观察必须只读、无影响、无破坏，并按 evidence-model 的 Audit Record 要求记录方法、目标、时间与结果。

## 5. Observation Retention / 观察证据保留

运行时观察写入 gitignore 的 `tmp/` 路径，保留期取 **15 天与「最长已登记周期 × 2」两者中的较大值**。

乘 2 是必须的：registry 的 `window` 定义的是**一个**周期，而周期性层级的门禁要求覆盖**两个**。登记一个 `P10D` 的目标需要 20 天，只取 `max(15, 10)` 会让首轮观察在第 15 天过期，持续不可达的判定永远闭合不了。

观察保存在本地而非 CI artifact，因此 CI artifact 的 14 天保留期不构成约束。

`tmp/` 是工作目录状态，不进版本库、不做备份：clean 或重新 clone 会丢掉观察历史。这可以接受——观察随时可以重新探测取得——但代价是**一个整窗口离线的目标会丢掉此前的尝试记录，重试计数从头开始**。
