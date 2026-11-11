---
type: epic
title: "静态配置和 Hub 服务配置归 IaC"
parent: initiative-employee-lifecycle
covers: [R22]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: []
refined: true
risk: high
---

# 静态配置和 Hub 服务配置归 IaC

## Description

把只存在于线上文件和 settings 的静态网络参数、Hub 服务配置收进 IaC 和 Vault。本 epic 交付 R22 的静态输入；role 不靠 `wsctl` 传入策略就能重跑，由 epic-firewall-derivation 完成。

## Outcome

静态拓扑和 Hub 服务配置有了版本记录，线上文件丢失时能重新生成。

## Requirements

- R1 (parent R22): 静态网络参数只在一份不含插值的变量文件里，settings 不再保存，`wsctl` 只读；`endpoint` 是一个只含 IPv4 的变量。
- R2 (parent R22): `portal.yaml` 和 `executor.json` 由 `oci-hub` role 生成，Portal 的 4 个密钥和配对只读令牌在 Vault。
- R3 (AD-30): `iac.git` 部署钩子持 `wsctl` 运行锁，运行中不换代码，计划摘要包含 IaC commit。

## Constraints

- (AD-25) 值进公开仓库前逐项判断，不宜公开的放 Vault，`wsctl` 不依赖 Vault 里的值。
- (AD-31) 密钥迁入 Vault 属凭据改动，需单独授权。
- (AD-30) 跑 role 前必须确认执行器 `/srv/iac` 是最新的。

## Done when

- `wsctl` 读到的每项静态参数等于线上值，settings 里已没有这些字段。
- `oci-hub` role 的 `--check --diff` 对 `portal.yaml`、`executor.json` 没有差异。
- 开户运行中推送 IaC 代码会等待运行结束。

## Boundaries

- 文件改名和 `pairs_*` 字段归 epic-firewall-derivation，这里沿用 `executor.json` 和现有字段。
- 不改防火墙规则本身。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R22)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-2、AD-25、AD-30、AD-31、配置总览

## Notes

- Decision: 2026-11-07 用户批准切分和 story 大纲。本 epic 的需求全部来自 initiative，不需要再补输入。
- Decision: 2026-11-07 tracer bullet 是 9.1：变量文件打通 Git、role 和 `wsctl` 三处读取，后面所有 epic 都要用。
