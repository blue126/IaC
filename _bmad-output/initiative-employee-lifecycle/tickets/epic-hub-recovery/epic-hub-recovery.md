---
type: epic
title: "OCI Hub 能恢复，公网 IP 变化时能全量切换"
parent: initiative-employee-lifecycle
covers: [R29, R30]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: []
refined: true
risk: high
---

# OCI Hub 能恢复，公网 IP 变化时能全量切换

## Description

在备份和配对都就绪后，补齐恢复需要的对账命令，用一次演练证明恢复路径，并做出 IP 预案缺的“全量切换 endpoint”。

## Outcome

OCI Hub 丢失不再是未验证的风险：恢复步骤演练过，IP 变了也有可执行的入口。

## Requirements

- R1 (parent R29): 管理员可在同一实例上替换启动卷恢复 OCI Hub；恢复期间 WireGuard 入站保持隔离，按 D1 双向对账全部通过后才解除；恢复报告列出回退的数据；演练证明替换后公网 IP 不变。
- R2 (parent R30): 公网 IP 变化时，管理员可按新 `endpoint` 批量重建设备包并批量重跑员工 VM 的 `oci-hub-spoke`。

## Constraints

- (AD-32) 同机的 Anki、unified-proxy、BookOrbit 会一起回退，恢复前确认空闲。
- (AD-15) 执行器不增加 OCI 凭据。

## Done when

- 恢复演练完成：公网 IP 不变，对账通过后才解除隔离，恢复报告列出回退数据。
- 用测试员工和测试 `endpoint` 跑一次全量切换，设备包和 VM 配置都指向新地址，不影响真实员工。
- 指向 OCI Hub 的 DNS 记录已列入执行器运行手册。

## Boundaries

- 不做保留公网 IP 和从零重建（架构 Deferred）。
- Touch point: 同机的 Anki、unified-proxy、BookOrbit — 恢复时一起回退；owner: 本 epic。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R29, R30)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-12、AD-32、配置总览的重建顺序
- oci-hub-ip-change — `docs/deployment/oci-hub-ip-change.md`

## Notes

- Decision: 2026-11-07 用户批准切分和 story 大纲。本 epic 的需求全部来自 initiative，不需要再补输入。
- Decision: 2026-11-07 tracer bullet 是 12.1：对账命令穿过 D1、`wsctl` 和 Hub 账本，演练要靠它。
