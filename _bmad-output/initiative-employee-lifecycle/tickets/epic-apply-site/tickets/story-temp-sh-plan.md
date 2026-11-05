---
title: '退役 Temp.sh 交付'
type: 'chore'
ticket: '6'
created: '2026-11-01'
status: 'done'
baseline_revision: 'a1baac3f0be847f87ed7f5c6523955230bf6115c'
route: 'oneshot'
route_source: 'auto'
risk: 'low'
review: 'none'
review_source: 'auto'
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 活动文档与员工说明仍写 Temp.sh、三天、一步 POST 下载。

**Approach:** oci-hub 交付代码已在 3.4 改走 cc.willfan.me；本 story 只改活动文档与员工公开说明。

**Decision:** 2026-11-01 已退役的旧方案（existing profile）代码含 temp.sh 分支，但 admin-core.py、ansible/onboard.yml、README.md 有用户未提交改动，保持不动；带日期的部署记录与规划文档作为历史保留。

</frozen-after-approval>

## Implementation Notes

- IaC PR #206（a262e02）：employee-provision SKILL 与 operations、oci-hub-native-provisioning、oci-employee-vpn-hub 改为 cc.willfan.me 一次性链接、验证码两步下载、`wsctl reissue`。
- workspace-onboarding PR #3（用户批准推公开仓库）：README、AGENTS、download、三份系统手册、administrator 说明。该仓库测试 50 个，3 个 `out of pty devices` 错误在 main 上同样出现（沙箱）。
- 执行器 oci-hub 路径不再调用 temp.sh（deliver-temp.publish 对 oci-hub 走 apply-site）。
