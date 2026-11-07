---
type: epic
title: "VM 记录归 D1，VNet 与 VM 同由 Terraform 管理"
parent: initiative-employee-lifecycle
covers: [R23, R24]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: []
refined: true
risk: high
---

# VM 记录归 D1，VNet 与 VM 同由 Terraform 管理

## Description

把 roster 并入 D1 的 VM 记录，var-file 改为每次运行时生成，再把 PVE SDN 交给 Terraform，让 VM、VNet、子网走同一份输入。`pve-sdn.py` 随之退役。

## Outcome

VM 事实只有一份，开户或退役中断后不会留下半套资源。

## Requirements

- R1 (parent R23): VM 记录存于 D1，开户时先于 Terraform 写入，退役时先于 Terraform 删除；var-file 每次运行时生成，roster 文件退役；读取失败时不生成 var-file；切换前后完整 plan 没有意外差异。
- R2 (parent R24): 员工 VM 的 VNet 和子网与 VM 由同一份 Terraform 输入创建和删除，`pve-sdn.py` 退役；导入现有对象后 plan 没有差异。

## Constraints

- (AD-28) 迁移时冻结 roster 写入，原样导入，核对完整 plan 后一次切换。
- (AD-29) provider 版本钉在 1.0 以下；Terraform 运行前做 SDN pending 预检。
- (AD-10) VM 记录的条件删除是退役提交点。

## Done when

- roster 文件已不存在，`terraform/remotecc` 的完整 plan 没有变化。
- 测试员工开户和退役各跑通，VNet 随 VM 建删。
- 退役中断后，下一次 plan 继续销毁，VM 不会被建回。

## Boundaries

- 不改防火墙，归 epic-firewall-derivation；本 epic 提供全部 VM 记录查询给配对接口。
- Touch point: `terraform/proxmox` 和共享模块 `proxmox-vm` 只核实升级影响。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R23, R24)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-2、AD-10、AD-26（VMID 算法）、AD-28、AD-29

## Notes

- Decision: 2026-11-07 用户批准切分和 story 大纲。本 epic 的需求全部来自 initiative，不需要再补输入。
- Decision: 2026-11-07 tracer bullet 是 10.1：VM 记录打通 D1、Worker 和 `wsctl`；10.5 provider 升级是最不确定的一步，排第二；它和 10.3 都动 plan 基线，所以 10.3 等它完成。
- Decision: 2026-11-07 10.3 切换后冻结开户和退役，到 10.4 完成为止，两者之间没有可用的写入路径。
