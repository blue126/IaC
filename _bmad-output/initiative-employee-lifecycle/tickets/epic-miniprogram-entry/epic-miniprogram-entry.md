---
type: epic
title: "员工在微信小程序与网站申请并查看状态"
parent: initiative-employee-lifecycle
covers: [R15, R16, R17, R20, R21]
sources: []
companions: []
after: [epic-executor-platform, epic-apply-site]
refined: true
risk: medium
---

# 员工在微信小程序与网站申请并查看状态

## Description

沿用 `remotecc/employee-miniprogram/` 现有前端，把 signup-api 改写为 uniCloud 支付宝云的云函数与云数据库；员工经微信登录提交申请、查看自己的状态与到期日；`wsctl request` 合并网站与小程序两个入口的申请，执行器向 uniCloud 推送状态副本。网站同样提供员工自助查看：经邮箱验证码登录后看到自己的状态与到期日（执行器向网站推送同一份状态副本）。网站与小程序使用同一套文案与视觉风格。小程序以个人主体备案。

## Outcome

国内员工在微信里完成申请并随时查看自己的到期日，不受网站可达性影响。

## Done when

- 小程序提交的申请与网站的申请出现在同一份 `wsctl request` 结果中，同一邮箱只算一条。
- 开户后员工在小程序里看到自己的状态与到期日，续费后随之更新。
- 关停 uniCloud 时网站入口与开户照常；关停网站时小程序入口照常。
- 小程序通过微信审核上线。
- 员工在网站经邮箱验证码登录后看到自己的状态与到期日，与小程序显示一致。
- 员工在本机用 `mosh <主机名>` 一条命令登录，看到的 hostname 不带 `oci-hub-` 前缀。
- 网站与小程序的规格说明、申请须知、状态与到期日表述及视觉风格一致（以同一份文案源为准）。

## Deferred

- 2026-11-02 用户决定暂不上线微信小程序：5.4 uniCloud 后端、5.5 小程序前端、5.6 两入口汇总与推送 uniCloud、5.7 uniCloud 到期提示、5.8 提审上线全部延后。本期 epic 只交付网站侧（5.1–5.3、5.12）及 5.10、5.11、5.13。上面 Done when 中关于小程序的四条随之延后：小程序申请并入 wsctl request、小程序显示状态、关停 uniCloud 互不影响、通过微信审核。

## Boundaries

- 小程序不提供设备包下载，不出现收费或付款字样。
- 云端不存私钥；唯一凭据为仅发信的 Resend 密钥。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R15, R16, R20)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-18, AD-19

## Notes

- Waits on epic-executor-platform because: 管理令牌只存放在执行器 VM。
- Waits on epic-apply-site because: 申请格式与 `wsctl request` 在 epic 3 定型，本 epic 加入第二个来源。
- Decision: 2026-11-02 视觉重新设计一套，两端共用设计 token；文案源为单一 JSON；网站会话 2 小时；小程序也用邮箱验证码，uniCloud 可持有仅发信 Resend 密钥（AD-18 放宽，AD-21）。
- Decision: 2026-11-02 uniCloud 支付宝云免费版服务空间 `remotecc-miniprogram` 已开通：SpaceId `env-00jy726lv4yv`，request 域名 `https://env-00jy726lv4yv.api-hz.cloudbasefunction.cn`，到期 2026-12-02 23:59:59（免费版按月到期，需续期；5.7 摘要提示）。AK/SK 不入文档。
- Open question: 个人主体是否需要认证费未核实；正式小程序 AppID 状态待确认。
- Dropped: 5.14，2026-11-04 用户决定 VM 系统 hostname 保持 `oci-hub-<员工ID>`，员工介意可自行修改。
- Decision: 2026-11-07 用户在 WILL-112 确认：5.9、5.10、5.15、5.16、5.18、5.25 记为 done，5.4–5.8 随小程序暂停。已知遗留：5.18 的 demo 以 VMID 503 开户没有成功的直接记录；5.24 的员工文档页 `usage/hapi` 等文档站接入后发布；5.25 中 502、505、506、507 的 `employee_acceptance` 仍为 pending。5.26 的描述和验收改为现行做法，保留批准这一步。
