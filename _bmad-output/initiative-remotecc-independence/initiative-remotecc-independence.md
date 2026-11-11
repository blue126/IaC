---
type: initiative
title: RemoteCC 成为不依赖公开 IaC 的独立项目
parent: none
sources:
  - _bmad-output/initiative-remotecc-independence/decisions-2026-11-07.md
  - _bmad-output/initiative-remotecc-independence/research-remotecc-iac-dependencies/research-remotecc-iac-dependencies.md
  - docs/architecture/remotecc-layout.md
  - _bmad-output/backlog/story-remotecc-iac-files-moved-to-private-repo.md
  - AGENTS.md
companions:
  - _bmad-output/initiative-remotecc-independence/scope-candidates.md
  - _bmad-output/initiative-remotecc-independence/live-fact-checks.md
  - _bmad-output/initiative-remotecc-independence/live-fact-checks-results-public.md
  - _bmad-output/initiative-remotecc-independence/shared-decisions.md
after: []
risk: high
---

# RemoteCC 成为不依赖公开 IaC 的独立项目

## Description

RemoteCC 的 Terraform root 已与 IaC 分开，但共享模块、Ansible、执行器绑定、凭据桥接和 CI 仍连接两个仓库（研究 Q2–Q5）。本 initiative 让 RemoteCC 的代码、部署和验证不再依赖公开 IaC，同时不影响在线员工环境和 IaC 其余资源。“划入独立项目的单元”以 `scope-candidates.md` 的决定列为准。

## Outcome

运维者修改和发布 RemoteCC 时不再需要公开 IaC，IaC 除 S4、S5 约定的主机和网络接口外不再为 RemoteCC 保留专属路径；信号是 R1 的代表性改动和 R2 的零差异 plan。

## Requirements

- R1 (D1, story Description): 员工 VM 配置、HAPI 部署、wsctl 入口各一项代表性改动，都只在独立项目内完成和验证，不修改公开 IaC，也不读取 IaC checkout。
- R2 (research Q2, AGENTS Project-local Employee Provisioning): 在没有 IaC checkout 的环境中，RemoteCC root 能完成 Terraform 校验和 plan；切换后 plan 相对切换前基线没有资源变更，每台 VM 仍只由一份 state 管理。
- R3 (research Q3): 划入独立项目的部署入口在没有 IaC checkout 时通过语法检查和 dry run，不再经相对路径读取 IaC 内的文件。
- R4 (research Q4, layout 入口与兼容路径): 执行器上的 wsctl 和 Semaphore 入口不需要 IaC 代码根，只读检查和一次获批 dry run 都通过。
- R5 (research Open questions, layout 入口与兼容路径): 切换时尚未执行的待批准项都有记录在案的结局（先完成、作废重批或保留），没有一项未经重新批准就被放行。
- R6 (research Q2, research Q4): 独立项目取得所需凭据时不经过 IaC 的 secrets bridge，一次完整运行在 IaC 不提供这些文件时成功。
- R7 (research Q5): 独立项目的 Terraform、Ansible 和契约测试在不依赖 IaC 的环境中运行，覆盖不低于切换前；`tests/hapi-workspace` 这类手工测试仍可手工运行。
- R8 (research Open questions, D2): 每个移出公开 IaC 的单元都有非 RemoteCC 调用方核查记录，覆盖模板和动态 include。
- R9 (D1, research Q5): 独立完成后公开 IaC 不含已划走的文件，CI 分类、Terraform 校验列表、state 刷新和 secrets bridge 中没有 RemoteCC 分支，PR 校验通过，其余 root 的 plan 没有变化。
- R10 (AGENTS, layout): `AGENTS.md`、布局和部署文档及相关 Skill 都指向新的唯一入口，公开 IaC 中没有仍标为有效的旧路径说明。
- R11 (D3, research Open questions): 架构定稿前，`live-fact-checks.md` 的 L1–L7 都有核查结果，与研究不一致的结论已回到本 initiative 处理。
- R12 (D4, D5): 研究公开部分按已验收版本存放在本 initiative 目录下，`restricted/` 不进入公开 Git。
- R13 (story Notes): 切换任一步失败时，运维者能回到切换前的绑定继续执行员工写操作，回退步骤在切换前有演练或检查记录。
- R14 (D9, D12): 交付给员工的 VM 上没有管理员 SSH 公钥，管理员仍能经 PVE CLI 或控制台维护；一次新开户和一次现有 VM 维护在没有常驻管理员公钥、也不经管理员 SSH 时都通过。

## Constraints

- 公开产物不含员工信息、凭据或私有实现细节；受限证据只从 WILL-108 附件取用（decisions D4, AGENTS BMAD / Multica Integration）。
- 员工写操作只在 `remotecc-ops` 上运行，Mac 保持只读（AGENTS Ansible Vault）。
- 不创建第二台员工 VM，也不让两份 Terraform state 管理同一台 VM（AGENTS Project-local Employee Provisioning）。
- 沿用现有 `wsctl` 入口，不新建开户引擎，不迁入 Jenkins（AGENTS Project-local Employee Provisioning, Terraform Workspaces）。
- 员工、设备、密钥和交付身份不因代码目录变化而重建（layout 入口与兼容路径）。
- `employee-data`、`hapi-data` 不进入 Git；凭据、设备包、申请和模板 state 必须校验字节一致（layout 验证与保留）。
- 管理自动化不经管理员 SSH 进入员工 VM，首选 PVE API 加 QEMU Guest Agent；员工设备的 SSH 接入不受影响（decisions D12）。
- 旧迁移方案未获批准，只作输入（story Notes）。
- lifecycle epic 8–12 完成后才开始 epic 1（decisions D19）。
- 研究报告不是删除清单（research Open questions）。
- 提交、推送、PR、线上 dry run、apply、部署和 state 操作分别授权（AGENTS Version Control and External-Write Boundaries, story Notes）。

## Done when

- R1 的三项代表性改动在独立项目内完成并通过验证。
- 切换后 RemoteCC plan 相对基线无资源变更，执行器上一次获批 dry run 和一次真实员工流程通过。
- 公开 IaC PR 校验通过，其余 root 的 plan 没有变化。
- 执行器不再依赖 IaC 代码根。
- 文档和 Skill 与新边界一致。
- 员工 VM 上没有管理员 SSH 公钥，开户和维护流程仍通过。

## Boundaries

- 不做：本 initiative 不重建员工环境，不更换 BWS、HCP 或 Proxmox 平台，除 R14 的管理员访问方式外不改变 RemoteCC 产品功能。
- 不做：本阶段不做架构选择，取得共享模块和角色的方式、仓库布局和切换步骤交架构。
- 不做：本 initiative 不改 `initiative-employee-lifecycle` 的记录（看板修正在 WILL-112 另行处理），本 initiative 的记录留在 IaC 直到完成（S14）；不重写公开 Git 历史（S15）；执行器 `/srv/iac` 下线另行授权（S10）。
- Touch point: `terraform/oci` 和 OCI 共享主机：Hub 服务带走，主机和网络规则留 IaC 作为接口（S4、S5）；owner: epic-oci-hub-service
- Touch point: `ansible/inventory/oci/hosts.yml`、`host_vars/oracle-cloud-ubuntu2404.yml`：Hub 部署要用的主机清单和 `oci_hub_portal_external_url`；owner: epic-oci-hub-service
- Touch point: `caddy` role：Hub 服务只消费（S4）；owner: epic-oci-hub-service
- Touch point: `terraform/modules/proxmox-vm`、`common`、`tailscale`、`ubuntu-vm`：RemoteCC 只消费（S6、S7）；owner: epic-standalone-project
- Touch point: `group_vars/pve_vms.yml`、`group_vars/tailscale.yml`、`group_vars/all/common.yml`：`remotecc-ops` 经主机组继承这些变量；owner: epic-standalone-project
- Touch point: `terraform/proxmox/cloud-init-snippet.tf`：`remotecc_ops` 经模块默认值使用它管理的 `cloud-init-ubuntu.yml`，留 IaC 作为接口；owner: epic-standalone-project
- Touch point: `.github/workflows/`、`scripts/ci/`、`tests/ci/`、`scripts/get-secrets.sh`、`scripts/refresh-terraform-state.sh`、`ansible/inventory/groups.yml`：移除 RemoteCC 分支；owner: epic-public-iac-detach
- Touch point: `Jenkinsfile:381`：只删 `terraform/remotecc/secrets.auto.tfvars` 这一路径；owner: epic-public-iac-detach
- Touch point: `.gitignore`、`.gitattributes`、`.worktreeinclude`：清理 RemoteCC 路径规则；owner: epic-public-iac-detach
- Touch point: `scripts/jenkins/proxmox-projection.py`：旧员工字段属于 CI-only 的退役校验，保留不改；owner: epic-public-iac-detach
- Must not change: IaC 其余 root、其他 OCI 工作负载和 CI-only initiative 的 Jenkins 路径。
- Must not change: 切换完成前的现有 `wsctl` 员工流程。
- Tracer path: 只读基线 → 独立项目内校验通过 → 获批 dry run → 执行器切换 → 真实员工流程 → 公开 IaC 移除 → 退役管理员公钥。

## References

- decisions — `_bmad-output/initiative-remotecc-independence/decisions-2026-11-07.md`
- research — `_bmad-output/initiative-remotecc-independence/research-remotecc-iac-dependencies/research-remotecc-iac-dependencies.md`
- scope — `_bmad-output/initiative-remotecc-independence/scope-candidates.md`
- checks — `_bmad-output/initiative-remotecc-independence/live-fact-checks.md`
- check results — `_bmad-output/initiative-remotecc-independence/live-fact-checks-results-public.md`
- shared decisions — `_bmad-output/initiative-remotecc-independence/shared-decisions.md`
- layout — `docs/architecture/remotecc-layout.md`
- story — `_bmad-output/backlog/story-remotecc-iac-files-moved-to-private-repo.md`
- plugin — https://docs.ansible.com/projects/ansible/devel/collections/community/proxmox/proxmox_qemu_api_connection.html

## Notes

- Decision: 2026-11-07 initiative 名称和目录确定为 `initiative-remotecc-independence`（D5、D6）。
- Decision: 2026-11-07 S0–S7、S9、S10、S12–S15 和 S8a 按 `scope-candidates.md` 的建议执行（D6）。
- Decision: 2026-11-07 S11 保留等效校验要求，GitHub 私有远端问题暂缓（D7）。
- Decision: 2026-11-07 员工 VM 上不留管理员 SSH 公钥，管理员走 PVE CLI 或控制台（D9）。
- Decision: 2026-11-07 `host-firewall` 规则保留，并入执行器角色，不再单独成 role（D10、D13）。
- Decision: 2026-11-07 `remotecc-ops-runtime` 迁移时改名为 `remotecc-ops`（D14）。
- Decision: 2026-11-07 管理自动化首选 PVE API 加 QEMU Guest Agent，不经管理员 SSH（D12）。
- Decision: 2026-11-07 切分为 5 个 epic，顺序见 `tickets/tickets.toml`，按 slice.md 默认规则切分；epic 1 和 2 分开，OCI Hub 单独成 epic（D17）。
- Decision: 2026-11-07 R14 排在最后，在 Hub 和文档迁走之后（D17）。
- Decision: 2026-11-07 epic 1 最后一次同步到 epic 2 完成之间暂停 RemoteCC 改动（D17）。
- Decision: 2026-11-07 Hub 服务带走，密钥进 BWS，架构修订 AD-25、AD-30、AD-31（D18）。
- Decision: 2026-11-07 先做 lifecycle epic 8–12，再开始本 initiative 的 epic 1（D19）。
- Parked: R11 不进 epic，它是架构定稿的前置门槛，will 已知（D17）。
- Parked: R12 不进 epic，随 initiative 入公开 Git 完成，推送需 will 单独授权（D17）。
- Assumption: R7 不指定载体，载体随架构确定。
- Assumption: 切分按执行器整体切换一次，架构改为分批时重切 epic 2。
- Open question: PVE API 加 QEMU Guest Agent 能否承担开户和维护全部任务，架构用一次 spike 验证速度、API token 权限、现有 VM 的 agent 状态和员工停用 agent 时的处理。
- Open question: S11 的 GitHub 私有远端暂缓；架构需要 CI 载体时再请 will 决定。
- Open question: S3 带走 `tests/oci-hub` 而 S5 把 `oci-hub.tf` 留在 IaC，ingress 夹具如何取得该文件交架构。
- Open question: S4 带走 `oci-hub` 而 `caddy` role 仍在 IaC，`oci-hub` 如何取得 `caddy` 交架构。
- Open question: R11 未满足：WILL-110 已核实 L1、L6、L7，L2 为静态核实，L3、L4、L5 只部分核实；L3、L4 的四个问题到重核时再答，R2 的切换基线在 lifecycle epic 8–12 完成后取得。
- Source conflict: S4、S9、S10、R2、R4、R6 — lifecycle 架构 AD-28 至 AD-31 与本 initiative 冲突，已由 D18、D19 决定，AD-25、AD-30、AD-31 的修订待架构。
- Open question: L1–L7 要在 lifecycle epic 8–12 完成后重核，WILL-114、WILL-115 已改变 L1、L6 的现状。
- Open question: 搬迁基线和切换时如何处理执行器与搬迁版本的差异交架构（A6）。
- Open question: 旧方案的子目录名 `IaC` 是否继续适用，架构阶段提请 will 决定。
