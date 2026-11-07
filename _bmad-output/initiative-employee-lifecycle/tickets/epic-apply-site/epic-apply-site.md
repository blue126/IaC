---
type: epic
title: "员工在 cc.willfan.me 申请并下载设备包"
parent: initiative-employee-lifecycle
covers: [R1, R2, R3, R10]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: [epic-executor-platform]
refined: true
risk: medium
---

# 员工在 cc.willfan.me 申请并下载设备包

## Description

Cloudflare Worker + D1 搭建 cc.willfan.me：规格介绍、申请表（Turnstile + IP 限频）、设备包下载页；wsctl request 拉取申请，provision --request 开户并上传设备包、发下载邮件；reissue 重发；Temp.sh 交付退役。

## Requirements

- R1 (parent R1, AD-13): `cc.willfan.me`（Worker 自定义域名，不用 `*.workers.dev`）移动端优先，展示与小程序一致的规格与说明（标准型：2 vCPU、8 GB 内存、20 GB 磁盘、5 GB/月流量；去掉"邀请码"一条），申请表字段为邮箱（必填）、姓名（必填）、手机号（选填）；提交写入 D1。
- R2 (parent R1, AD-13): 提交先校验 Turnstile，再按 IP 限频（每小时 3 次、每天 10 次，D1 计数）；Turnstile 无法加载时只靠限频。
- R3 (parent R1, AD-6, AD-19): `wsctl request` 用 Worker 管理令牌拉取未处理申请，落为 `employee-data/requests/oci-hub/site-<申请ID>.json`；`wsctl request --dismiss <ID>` 回写已处理。
- R4 (parent R2, AD-6): `wsctl provision --request <ID>` 的邮箱与姓名取自申请文件；开户完成后回写已处理。
- R5 (parent R3, AD-17): 执行器把设备包上传到 Worker（存 D1 BLOB），给员工发不带下载链接的开通邮件；员工登录“我的工作区”后下载，不限次数；设备包保存到退役或被同设备的新包替换为止；provision 不再调用 Temp.sh。
- R6 (parent R10, AD-17): `wsctl reissue` 生成新链接并重发邮件，旧链接立即失效。
- R7 (parent R3): Temp.sh 交付代码与文档退役。
- R8 (parent R1, Decision 2026-11-01): 申请前必须验证邮箱：页面获取 6 位验证码（10 分钟有效、最多试 5 次、同一邮箱 60 秒内只发一次），经 Resend 发出；提交时校验，验证码一次性。

## Outcome

员工在手机上完成申请与设备包下载，不再依赖 Temp.sh。

## Done when

- 手机浏览器提交的申请出现在 wsctl request 中，被刷时遭 Turnstile 或限频拒绝。
- 从申请开户后员工收到开通邮件，登录“我的工作区”后可下载设备包；退役后设备包被删除。
- reissue 生成新链接；provision 与 reissue 不再调用 Temp.sh。
- 网站与管理接口部署在 cc.willfan.me，从国内网络实测可打开。

## Boundaries

- 网站不提供登录与状态查询；不调用家中或 OCI。
- 不做提醒与摘要（epic 4）。

## References

- parent — _bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md, section Requirements (R1, R2, R3, R10)
- architecture — _bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md, AD-6, AD-13, AD-17

## Notes

- Decision: 2026-11-01 设备包存 D1 BLOB 而不开通 R2：包约 1.6 KB，D1 单值上限 2 MB、免费库 500 MB；Worker 内存取封装为 put/get/delete，日后需大文件时只改这三处换 R2（用户同意）。
- Decision: 2026-11-01 Cloudflare 资源经 SaaS MCP（Cloudflare API）创建与部署；Vault 中的 `vault_cloudflare_api_token` 只有 DNS 权限。执行器调用网站只用 Worker 自己的管理令牌（存 BWS `executor/apply-site-admin-token`）。
- Decision: 2026-11-01 文案与小程序一致，但不要邀请码与邮箱验证码；防刷靠 Turnstile + 限频，开户前管理员线下确认（按推荐，用户回复"同意"）。
- Decision: 2026-11-01 网站源码在私有 `remotecc/apply-site/`。
- Decision: 2026-11-01 用户要求申请前验证邮箱且用免费组件：选 Resend 免费版（每月 3000 封、每天 100 封），发信地址 noreply@cc.willfan.me，仅发信权限的 API Key 存 Worker secret `RESEND_API_KEY`；新增 story #8，排在 #3 之前。
- Decision: 2026-11-01 设备包链接改为 3 天内最多下载 3 次（用户），并且下载前须再验一次邮箱验证码，防止链接经 Agent 日志或转发泄露后被他人使用（用户选方案 A）。
- Decision: 2026-11-01 拆为 7 个 story；tracer 为 #1（页面 + 申请表 → D1 → wsctl request），保留 Refactor sweep。

- Waits on epic-executor-platform because: Cloudflare 管理令牌与邮件授权只存放在执行器 VM。
- Decision: 2026-11-07 用户在 WILL-112 要求更新文本：R5 和对应的 Done when 改为登录后下载，与 initiative R3 一致。
