---
id: 1
type: story
title: "RemoteCC IaC files live in the private remotecc repository"
parent: none
covers: []
sources: []
companions: []
after: []
assignee: ""
refined: false
hitl: true
risk: high
---

# RemoteCC IaC files live in the private remotecc repository

## Description

把 RemoteCC 的 Terraform、Ansible 文件和相关测试从公开仓库迁到私有 `remotecc` 仓库的 `IaC/` 子目录，让同一项功能不再跨两个仓库修改。**2026-11-06 暂缓，未开始。**

## Requirements

Verify: 执行器上 `wsctl` 只读检查和一次 dry run 通过；公开仓库不再含这些文件；公开仓库 CI 通过。

## References

- plan — remotecc/docs/2026-11-06-iac-migration-plan.md（私有仓库，含 Codex 审查记录）

## Notes

- Decision: 2026-11-06 用户决定暂缓，方案未批准。详细方案只放私有仓库，这张票不写细节。
- Decision: 2026-11-06 子目录名是 `IaC`，不用 `infra`。
- Open question: 恢复时要定方案“待你决定”里的三项，并重跑第 0 步基线。
- Assumption: 先记成一张 story；恢复时大概率要拆成 epic，因为方案有 9 步，超出一次 agent 会话。
- Risk high: 切换直接影响执行器上的 `wsctl`。标准之外还要确认 `terraform plan` 与基线一致。
- hitl: 提交、推送、线上 dry run 和开 PR 都要用户分别授权。
