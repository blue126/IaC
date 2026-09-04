# Jenkins Agent 控制平面的第一性原理

**日期**：2026-08-30

**标签**：`rf-first-principles`、`Jenkins`、`CI/CD`、`Security`、`Ansible`、`Proxmox`

**来源**：以 CI-only execution 的 CAP-8、AD-9、AD-10、AD-11 及现有 Jenkins controller 实况为案例。

## 核心洞察

Jenkins controller 负责决定“什么可以执行”，peer agent 负责真正执行工作。为了让
Terraform 与 Ansible 只能通过 CI 修改受管环境，controller 不能继续兼任普通
executor；但在第一个 peer agent 尚未验证前，也不能提前关闭 controller executor。

因此迁移必须同时解决五个彼此独立的问题：执行位置、权限身份、配置所有权、运行时
版本和首次引导。

## 根本问题

| 根本问题 | 通俗说法 | 对应机制 |
|----------|----------|----------|
| 工作在哪里执行 | 谁真正运行 Terraform 和 Ansible？ | Peer Jenkins agent LXC |
| 用什么权限执行 | Plan 为什么不能接触 deploy 权限？ | `iac-plan`、`iac-deploy` 独立身份 |
| 配置由谁决定 | UI 中创建的 node 丢失后如何恢复？ | Jenkins Configuration as Code |
| 作业由谁定义 | Pipeline job 如何避免 UI 漂移？ | Job DSL，后续独立引入 |
| 用什么版本执行 | 为什么重建后仍应得到相同结果？ | 版本 BOM 和 checksum |
| 第一个 agent 谁来创建 | 没有 agent 时谁执行 agent 部署？ | AD-9 一次性 bootstrap |

## 三层身份必须一一对应

一个安全执行身份需要在三个层面同时存在：

```text
Jenkins node: iac-plan
  └── systemd service: jenkins-agent@iac-plan
      └── Unix account: iac-plan

Jenkins node: iac-deploy
  └── systemd service: jenkins-agent@iac-deploy
      └── Unix account: iac-deploy
```

Jenkins node 决定调度边界，systemd service 决定进程边界，Unix account 决定文件和
操作系统权限边界。只建立其中一层不能形成完整隔离。例如两个 pipeline 共用一个
Jenkins node 时，即使 pipeline 名称不同，也可能共享进程、workspace、临时文件和
注入凭据。

## JCasC 与 Job DSL 的分工

Jenkins Configuration as Code（JCasC）管理 controller 元数据，例如：

- controller executor 数量；
- agent node 名称和 remote filesystem；
- inbound launcher；
- 全局安全和工具配置。

Job DSL 管理 job、multibranch pipeline、参数和触发器。它回答的是“执行什么”，而
JCasC 回答的是“谁可以执行以及 controller 如何配置”。

首个 agent bootstrap 只需要 JCasC 管理两个 node。此时同时引入 Job DSL 会扩大变更
面，因此 Job DSL 应在 agent 稳定并完成恢复验证后单独迁移。

## 为什么需要版本 BOM

版本 BOM 是执行环境的可重建契约，而不是简单的软件清单。2026-08-30 的只读探测
得到以下事实：

| 组件 | 当前值 |
|------|--------|
| Jenkins package | `2.541.1` |
| Java | `17.0.18` |
| Terraform | `1.14.4` |
| Ansible | 当前 controller PATH 中不可用 |
| Controller executors | `2` |
| JCasC plugin | 未安装 |
| Job DSL plugin | 未安装 |
| `agent.jar` SHA-256 | `2a814594ae8df13fe6b490f7a802f3befcf14483ff3cdb778b771e0582ecd726` |

如果不固定 core、Java、Terraform、Ansible、collections、plugins 和 agent runtime，
即使 Git SHA 不变，重建后的 plan 或执行语义也可能改变。Pipeline 应在版本不匹配时
失败，而不是构建期间静默升级。

## Secret 的正确边界

Git/JCasC 只声明 node 名称、路径、label 和 launcher 类型。Jenkins controller 生成
inbound connection secret，Ansible Vault 保存 secret 值，Ansible role 再以
`no_log` 方式部署到对应 agent 的受限文件。

systemd 使用 `-secret @secret-file` 读取凭据，避免把 secret 直接放入命令行参数。
仓库中只保留 Vault 间接引用，不记录实际 secret，也不臆造 Jenkins credential ID。

## 为什么不能立即关闭 Controller Executor

目标状态是 controller 的 `numExecutors: 0`，但关闭顺序很重要：

```text
提前关闭 controller executor
  → peer agent 尚未连接或无法运行
  → 没有 executor 可以修复 agent
  → CI 控制平面失去自救通道
```

AD-9 因而允许一次性 bootstrap：

1. 暂时保留现有 controller executors；
2. 创建 `iac-plan`、`iac-deploy` inbound nodes；
3. 将生成的 secret 安全写入 Vault；
4. 从健康的现有 controller executor 部署 peer agent；
5. 验证两个 agent 的身份、workspace、权限和连接；
6. 验证 peer agent 可承接 controller watchdog；
7. 把 controller executor 改为 `0`；
8. 通过正常 Jenkins plan 对账。

## 推荐的增量顺序

1. 建立 peer agent LXC、两个 Unix 身份和 agent services。
2. 建立版本 BOM，选择与 Jenkins core 兼容的 JCasC plugin pin。
3. 由 JCasC 管理两个 inbound nodes，但暂时保持两个 controller executors。
4. 执行一次性 bootstrap，并验证 agent 能独立运行无害任务。
5. 禁用 controller executor，并由正常 plan 对账。
6. 再引入 Job DSL 和完整的 PR/main/maintenance/event jobs。

每一步只改变一个主要安全边界，失败时可以明确知道回退位置。

## Q&A

### 为什么同一个 LXC 仍要建立两个 Jenkins nodes？

因为 LXC 只隔离它与 controller，不能隔离 LXC 内的 plan 与 deploy。两个 node 分别
绑定两个 Unix account、systemd service、home、workspace 和 secret，才能让 Jenkins
调度身份与操作系统权限身份一致。

### 为什么不用 Docker-in-Docker 做临时 agent？

Docker daemon 通常是主机级特权边界。向 plan 身份暴露 Docker socket，实际上可能
赋予接近 root 的能力；Docker-in-Docker 还增加镜像、缓存、存储和嵌套内核能力的
生命周期。本阶段使用原生 LXC 和非 root service，安全边界更容易审计。

### JCasC 和 Job DSL 是否必须同时部署？

不是。JCasC 足以管理 controller 与 nodes；Job DSL 只在 jobs 迁移到代码所有权时
需要。分开实施可减少首次 bootstrap 的插件和回滚范围。

### 为什么 agent secret 不作为普通 Jenkins credential ID？

Inbound agent secret 是 controller 根据 node identity 管理的连接材料，不等同于
pipeline 中通过 credential binding 注入的业务凭据。它应通过 Vault 保存并以受限
文件交付给对应 service，而不是在代码中假设一个 credential ID。

### 什么条件满足后才能把 `numExecutors` 改为 `0`？

两个 agent 必须稳定在线、身份和目录隔离验证通过、无害任务成功运行、bootstrap
记录完整，并且 peer agent 已能独立执行 controller watchdog/rollback bundle。仅仅
看到 node 显示 online 不足以关闭最后的恢复通道。

## 边界与未完成事项

- JCasC plugin 已按当前 Jenkins core 固定版本与 checksum，但尚未经过隔离的
  restore-and-boot runtime validation。
- Agent 尚未实际 bootstrap，Vault 中也尚未加入两个 connection secret。
- Executor 工具依赖、所有 collection 与完整 controller plugin tuple 尚未全部纳入
  可恢复 BOM。
- `iac-plan` mutation 网络限制、`iac-deploy` 全局串行与清理证明属于后续 pipeline
  实施，不由本笔记假定已经完成。

## 相关内容

- [IaC CI-Only Execution 架构](../designs/2026-08-30-ci-only-execution-architecture.md)
- [CI/CD 架构设计](../designs/cicd-architecture.md)
- [Ansible Role 架构](../designs/ansible-role-architecture.md)
- [Ansible Vault 架构](../designs/ansible-vault-architecture.md)
- 绑定 SPEC：`spec-ci-only-execution`（该 spec 未提交进本仓库，内容见上方架构设计文档）
