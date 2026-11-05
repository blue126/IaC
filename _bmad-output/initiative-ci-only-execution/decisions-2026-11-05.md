# CI-only 执行：用户决策记录（2026-11-05）

本文件是 Sofia 编写 initiative 和 `bmad-architecture` 更新 `docs/architecture/ci-only-execution-architecture.md` 的输入。
SPEC 副本来自 worktree `t_cc49477a`，内容未改；其 companion 路径 `docs/designs/...` 已过时，现行路径是 `docs/architecture/ci-only-execution-architecture.md`。

## 已批准

1. **Git 权威：** 放弃 Gitea 权威，保留 GitHub。重写 AD-2、AD-3、AD-11、AD-12 和 CAP-1、CAP-5、CAP-6。Cloudflare webhook 隧道保留，公网入口风险需要在架构中重新回答。
2. **范围：** 只覆盖 `terraform/proxmox`、`terraform/oci` 和 Ansible。RemoteCC（`terraform/remotecc`，`wsctl`，`remotecc-ops`）写成 AD-1 的正式例外。删除 ESXi。NetBox（CAP-5、CAP-7）推迟。
3. **本地执行：** AD-1 改成移交后才生效的目标状态；移交前本地执行和合并前 dry run 照旧。
4. **审批人：** 同一名运维者可以完成 Terraform 和 Ansible 两次审批，靠两条独立审批记录保证可追溯。关闭 SPEC 的开放问题。
5. **路线：** 第一个 epic 是 peer 生产落地（`docs/planning/jenkins-peer-agent-recovery.md` 的 S1–S8）。

## 已确认的补充决策

- Gitea 继续运行，只退出 IaC 权威，n8n job 仍用它做只读 SCM。
- GitHub Actions 不持有基础设施凭据，webhook 只能请求执行，不能选择代码或命令。
- 移交后允许本地只读 plan，不允许写。
- 同意解除 Jenkins 流水线冻结；本地证据显示 `IaC-Homelab-Pipeline` 已在 2026-10-27 解冻，无需动作，线上现状待登录确认。
- 给 `/github-webhook/` 加 HMAC secret 并由 Jenkins 校验，列入第一个 epic，排在最前面。

## 授权边界

以上决策不授权部署。CT110 部署、真实密钥使用、controller 归零、提交、推送都要单独授权。
