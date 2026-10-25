---
id: SPEC-proxmox-consolidation
companions:
  - brownfield.md
  - migration-plan.md
  - acceptance.md
  - ../../planning-artifacts/architecture/architecture-IaC-2026-10-25/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/architecture/architecture-IaC-2026-10-25/solution-design.md
  - ../../planning-artifacts/architecture/architecture-IaC-2026-10-25/runbook.md
  - ../../planning-artifacts/architecture/architecture-IaC-2026-10-25/validation-and-rollback.md
  - ../../planning-artifacts/architecture/architecture-IaC-2026-10-25/preflight-evidence.md
  - ../../../AGENTS.md
  - ../../../docs/architecture/proxmox-qdevice-architecture.md
sources: []
---

> 本 SPEC 与 companions 构成迁移契约，已吸收2026-10-25定稿方案；CAP-1至CAP-6及配套架构AD-1至AD-15保持稳定。本轮仅文档更新，未执行迁移，文档完成不代表现场准入通过。

# Proxmox 来宾整合与 VM108 迁移

## Why

操作者希望把pve1全部来宾集中至pve0，同时把平时不开机的VM108移至pve2，保留原有服务、Time Machine历史和失败后的恢复能力，并控制存储及内存压力。

## Capabilities

- **CAP-1**
  - **intent:** 操作者能在迁移前确认目标条件与完整恢复路径。
  - **success:** 节点、容量、身份、网络及备份准入证据齐全；PBS恢复能力及pve2接收能力接受用户确认，pve2可达性已现场核实；其余未满足条件停止，不以文档自检替代。
- **CAP-2**
  - **intent:** VM108在pve2按需使用。
  - **success:** 系统及containerlab功能通过验证，数据和网络身份保留；验证后关机且不自启，IaC不重新启动它，旧源不能自行成为另一活动副本。
- **CAP-3**
  - **intent:** pve1的全部八个来宾在pve0提供原有功能。
  - **success:** VM112–117、CT111/118的位置和状态符合migration-plan.md；逐业务验收通过，pve0原有业务无迁移引起的退化。
- **CAP-4**
  - **intent:** 两台Mac继续使用fileserver的既有Time Machine历史。
  - **success:** 两台Mac均识别旧历史、完成增量备份和代表性文件恢复；完整数据及元数据一致，报告760GiB、硬限额800GiB和系统可写余量核验通过。
- **CAP-5**
  - **intent:** 管理配置、运行位置和备份覆盖一致。
  - **success:** Terraform/state/provider、Ansible、NetBox及备份归属定向核对完成；完整及定向计划无意外创建、销毁、替换、回迁、启动或重启，迁后有验证通过的恢复点。
- **CAP-6**
  - **intent:** 操作者能验证整合稳定性并在失败时恢复服务。
  - **success:** 逐批及24–48小时真实并发观察通过；回退容量累计认领、可读恢复点和数据截止点明确，不丢弃目标新数据；验收通过后旧源副本可清理，无额外保留期，pve1暂时保持在线。

## Constraints

- 保留VMID/IP/MAC及单一权威数据谱系；正常路径保留源盘，旧源退注册后不得rescan或复用ID；冲突不得force覆盖。
- 全部来宾采用冷备份恢复；同ID内部API交接未经同版本/模块哈希演练及批准不得执行，不能以destroy替代。
- vmdata新增预算336GiB并保留128GiB余量，不依赖VM108源盘释放；CT111数据硬限额800GiB，Samba报告760GiB留40GiB差额，系统实际dataset可写余量至少64GiB；容量口径见migration-plan.md。
- 当前常开配置约69GiB超过pve0约62.6GiB；VM112/113计划约一周后退役，届时配置约61GiB，当前迁移仍包含两台；采用按实测受控超配；遵守runbook附录G的启动、压力停止和恢复线，Windows提前验证后关机，不承诺满配并发。
- 全量内容及ACL/xattr、UID/GID、链接、稀疏语义须核验；权限/读取/清单差异未解释不得开放写入，禁止原地缩源ext4或只改容量声明。
- 目标首次启动后默认按最新数据T1回退；恢复空间按node/pool累计，不能重复认领；无容量或可读恢复点时保全等待，不能直接启动旧源。
- 接受PBS与VM108共pve2故障域；恢复以可读且验证通过的点和数据截止点为界，不保证双机故障回退或RPO0。
- 保留pve1成员与QDevice；后续关机须另获授权并验证见证票及quorum，失败恢复pve1，不退群或降票。
- 基础设施、state、管理系统、备份保护/作业、清理及关机遵守AGENTS.md各自授权边界；凭据、原始配置及state仅保存在批准的私有位置。

## Non-goals

- 本轮迁移、备份/恢复、应用IaC、提交或推送；自动清理源盘、解除备份保护或关闭pve1。
- pve2加入集群、pve1退群、调整投票、新增HA或独立备份基础设施。
- 更换硬件、修改其他服务架构、批量接管手工来宾或升级provider。

## Success signal

VM108在pve2验证后关机；pve1八个来宾均由pve0承载并通过业务、Time Machine历史、完整性、容量及迁后备份验收。管理声明与现场一致，真实并发观察无迁移引起的持续压力，且恢复分支、可达性和数据损失边界可执行并有记录；当前仅规格对齐完成。

## Assumptions

- AD-3的内部API仅退配置交接能在相同版本/模块哈希的隔离演练中成立；失败必须修订方案，不能现场绕过。
- VM108按pve2-ssd/vmbr0接收方案及PBS既有传输媒介推进；接收能力和PBS恢复能力已由用户确认，助理不重复复核，也不冒称已亲自试恢复；无本地巨型暂存fallback。

## Open Questions

- 实施窗口、值守者及获准的生产负载停止顺序如何签入变更单？
- 现场核验与演练后，各node/pool的累计A/B/C回退认领如何分配，容量不足分支是否取得所需精确授权？
- 受保护T0/T1恢复点的保留与解除保护策略如何确定？源副本已选定验收后可清理，pve1暂不关机，两项不再作为迁移待决问题。
