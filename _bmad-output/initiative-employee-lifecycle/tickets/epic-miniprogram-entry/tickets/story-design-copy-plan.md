---
title: '新视觉设计与统一文案源'
type: 'feature'
ticket: '1'
created: '2026-11-02'
status: 'done'
route: 'full'
risk: 'low'
review: 'human'
---

## Intent

网站与小程序共用一套新视觉（参考 pay.sh 风格：近黑底、细线网格、等宽标签、荧光绿强调、直角卡片、终端感；只借鉴风格，不用其品牌与素材）和一份 JSON 文案源。

## Deliverables

- 设计稿（Design 画布，私有）：https://claude.ai/artifact/VJh5cnQE3hABAyy6G8ozUD
  - 设计规范（颜色 token、字体层级、状态标签、按钮/输入/键值卡片）
  - 手机端：规格与申请须知、提交申请、我的工作区、设备包下载
  - 网站桌面首页
  - 每张有深色/浅色开关（Tweaks）
- 画布源文件：`remotecc/design/canvas/project/`
- 文案源：`remotecc/design/text.json`（沿用现网站文案，补充"我的工作区"与跨入口提示）
- 设计 token：`remotecc/design/tokens.json`

## Assumptions（待管理员审定）

- 品牌字标：`Remote/CC`（2026-11-02 管理员在画布评论中确定）；中文名"远程工作区"不变。
- 配色参照 pay.sh：主按钮为中性色（primary），强调色 #A2EF5C 只用于小标签、状态点与终端提示符；深色为主，保留浅色模式（2026-11-02 用户确认）。
- 字体：Geist / Geist Mono 自托管；中文走系统黑体，不加载网络中文字体（用户确认）。
- 状态中文名：正常 / 申请中 / 已到期 / 已暂停 / 长期有效（用户确认）。
- 页面名统一为"我的工作区"；管理员联系邮箱 red_of_blue@hotmail.com；网站不出现小程序引导；登录后可在"我的工作区"下载设备包（AD-17）。
- 状态码：ACTIVE / PENDING / EXPIRED / PAUSED / NO_EXPIRY，中文分别为正常 / 申请中 / 已到期 / 已暂停 / 长期有效。
- 首页英雄标题"一台属于你的命令行 Linux。"为新增文案。
- 小程序不展示设备包下载页（AD-18）；下载页只在网站。
- 设计源统一放在 `remotecc/design/`（text.json 文案、tokens.json 样式值、canvas/ 画布），独立本地 git（已初始化，未提交）；网站与小程序构建时从这里读取（2026-11-02 用户决定）。

## Review

- [ ] 管理员审定设计稿与文案
