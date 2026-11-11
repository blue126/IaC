---
type: epic
title: 执行器切到独立项目
parent: initiative-remotecc-independence
covers: [R1, R2, R4, R5, R6, R13]
sources: []
companions: []
after: []
refined: false
risk: high
---

# 执行器切到独立项目

## Description

执行器上的 `wsctl` 和 Semaphore 入口改用独立项目，不再需要 IaC 代码根。切换按一次整体切换规划，切换步骤和回退由架构确定。

## Outcome

运维者修改和发布员工流程时不再需要公开 IaC，信号是切换后 plan 零差异和一次真实员工流程。

## Done when

- 切换后 plan 相对基线零差异，每台 VM 仍只由一份 state 管理。
- 一次获批 dry run 和一次真实员工流程通过，IaC 不提供文件时运行成功。
- R1 的三项代表性改动只在独立项目内完成和验证。
- 切换时的待批准项都有记录在案的结局。
- 回退步骤在切换前有演练或检查记录。
- 生产交付：执行器不再读取 `/srv/iac`。

## Boundaries

- 不做：`/srv/iac` 下线，另行授权（S10）。
- 不做：退役管理员公钥，切换期间仍走现有 SSH 通道（epic-admin-key-retirement）。
- Must not change: 员工、设备、密钥和交付身份。

## References

- parent — `_bmad-output/initiative-remotecc-independence/initiative-remotecc-independence.md`，Requirements
- shared decisions — `_bmad-output/initiative-remotecc-independence/shared-decisions.md`

## Notes

- Assumption: 切换是一次整体切换，架构改为分批时重切本 epic。
- Waits on epic-standalone-project because: 需要已到达执行器的独立项目、工具链和凭据路径，以及切换前 plan 基线。
