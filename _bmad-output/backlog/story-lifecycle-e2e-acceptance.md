---
id: 7
type: story
title: "测试员工走完整生命周期，补齐未运行过的路径"
parent: none
covers: []
sources: []
companions: []
after: [6]
assignee: ""
refined: false
hitl: true
risk: high
---

# 测试员工走完整生命周期，补齐未运行过的路径

## Description

代码实现和测试都在，但下面这些路径线上没有完整跑过：initiative 的前两条缺口（全程在 Semaphore 和邮件中完成、Mac 关机一天），新上线的 `renew`、`retire`、`deliver` 模板，以及 D1 和 HAPI 上线后的退役。用一名测试员工走一遍，不碰真实员工。

## Requirements

Verify: 测试员工从网站申请、开户、下载设备包、登录 VM，全程只在 Semaphore 和邮件中完成；到期后隧道断开、VM 关机、HAPI 被拒绝，`wsctl renew` 模板续费后都恢复；两名可退役测试员工批量退役时，其中一人续费后整批被拒绝，重新计划后只退役另一人；退役后 Portal、Terraform、BWS、网站设备包、catalog、VM500 路由和令牌、Access 邮箱、PVE 放行、Hub 会话数据都没有该员工；两名测试员工互相进不了对方的 namespace；Mac 关机一天，提醒和摘要照常送达；在 wg-portal 手工停用后 `wsctl status` 立即反映。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R2, R5–R9, R12, R19)

## Notes

- Decision: 2026-11-07 用户在 WILL-112 同意开这张票。
- 涉及线上操作，要单独授权。
- 可和 10.4、10.6 的测试员工开户退役合并。
- 排序由 WILL-116 的切分决定。
