---
name: employee-claude-workspace
type: architecture-spine
purpose: build-substrate
altitude: feature
scope: 员工远程 Claude Code 工作环境第一阶段
status: draft
created: 2026-10-21
updated: 2026-10-26
binds: [CAP-1, CAP-2, CAP-3, CAP-4, CAP-5, CAP-6]
sources: [SPEC.md]
companions: []
---

# Architecture Spine — 员工远程 Claude Code 工作环境

下述早期架构示意保留为规划记录；新增的“已部署实现”部分依据当前 Terraform/Ansible 代码记录资源边界。尚未核验的权限收紧与模块迁移不属于已完成决策。

## 已部署实现的 Terraform 边界（2026-10-26 核对）

- **VM 结构**：通用 `terraform/modules/proxmox-vm/` 按模板名称克隆、配置单网卡和标准 Cloud-Init。员工网关需要多张按永久槽位排列的隔离网卡；个人 VM 需要专属 bridge、vendor-data、pre-start hook、边界就绪前停机以及 `prevent_destroy`。当前在 `terraform/proxmox/employee-access.tf`、`employee-workspace.tf` 中直接声明 VM 资源，以保留这些约束。模板与 hook 文件也分别由员工专属资源管理。
- **连接和权限**：员工资源统一使用已有的 `proxmox.pve2`（独立 pve2 的 API token；SSH 通过 agent），原 `proxmox.employee` 的 `root@pam` 别名已移除。迁移前核对了 token 在节点、snippets 存储及 VM 路径的权限和 SSH 连通性；定向计划显示零资源变更，应用后六个员工 Proxmox 资源在 state 中均改绑 `proxmox.pve2`。这项 provider 收敛不改变 VM 模块选择，也不另建 Terraform state。
- **变更边界**：把已有 VM 改为模块调用会改变 Terraform 资源地址；provider 绑定现已通过零资源变更计划迁至 `proxmox.pve2`。未来若把已有 VM 改为模块调用，仍须核对 state、迁移路径及定向计划，证明员工 VM 与磁盘没有重建或删除。
