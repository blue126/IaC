---
type: epic
title: "防火墙从主机对象派生，配对来自 D1，代码只走 role"
parent: initiative-employee-lifecycle
covers: [R22, R25, R26, R27]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: []
refined: true
risk: high
---

# 防火墙从主机对象派生，配对来自 D1，代码只走 role

## Description

取消员工层策略文件：PVE 规则从本机 SDN 和 VM 配置派生，OCI Hub 配对是来自 D1 的 nft set 元素。`boundary` 和 `executor` 在这里改名，代码下发收敛到两个 role。

## Outcome

主机上不再有员工数据副本，加人不用重写规则，只有一条路径下发防火墙代码。

## Requirements

- R1 (parent R22): `oci-hub`、`oci-hub-pve` role 不需要 `wsctl` 传入策略就能重跑，结果与线上一致。
- R2 (parent R25): PVE 防火墙从本机 SDN 和 VM 配置派生，不存在员工层文件；对象不符合 VMID 算法的 VM 被拒绝启动；切换前新渲染结果与线上规则一致。
- R3 (parent R26): OCI Hub 的设备与工作区配对来自 D1，是 nft set 的元素；开户、退役、改址后立即生效；set 未填入时设备与 VM 不通，读取失败时现有元素不变。
- R4 (parent R27): `firewall.py`（原 `boundary.py`）只由两个 role 下发，`wireguardusrmgr.py`（原 `executor.py`）改名同时完成；开户与退役流程不再复制代码。

## Constraints

- (AD-26) 切换前必须证明新渲染结果与线上规则一致，且现有 VM 全部符合 VMID 算法。
- (AD-27) 上线时先发布新 `wireguardusrmgr.py`，再切规则。
- (AD-30) 跑 role 前必须确认 `/srv/iac` 是最新的。

## Done when

- 两台主机上 `boundary.json` 已不存在，防火墙行为与切换前等价。
- 测试员工开户、退役后，配对和 VM 放行都正确变化，`wsctl` 不触发 Hub apply。
- D1 不可用时现有配对不变；Hub 重启后 set 为空时设备与 VM 不通。
- 搜索不到 role 以外下发 `firewall.py` 的路径。

## Boundaries

- 不把 PVE 规则改成 nft set（架构 Deferred）。
- `configure-oci-hub-mosh-boundary.yml` 的删除已由 WILL-118 单独执行。
- Touch point: 申请网站 Worker — 新增配对接口和令牌校验；owner: 本 epic。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R22, R25, R26, R27)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-2、AD-13、AD-26、AD-27、AD-30、AD-31

## Notes

- Decision: 2026-11-07 用户批准切分和 story 大纲。本 epic 的需求全部来自 initiative，不需要再补输入。
- Decision: 2026-11-07 tracer bullet 是 11.1：改名不改行为，但穿过公开代码、私有代码、两个 role 和两台主机，先证明这条路径通。改名按 AD-26 和 AD-27 在一个 story 里完成。
- Decision: 2026-11-07 用户同意收紧 AD-27：相同 generation 的配对内容必须相同。11.4 至 11.6 按收紧后的主干实现。
