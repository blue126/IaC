---
type: epic
title: "执行器常驻 pve0，经 Semaphore 操作"
parent: initiative-employee-lifecycle
covers: [R12, R13]
sources: [_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md]
companions: [_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md]
after: []
risk: high
---

# 执行器常驻 pve0，经 Semaphore 操作

## Description

在 pve0 上用 Terraform 新建专用执行器 VM `ws-executor`，部署 wsctl 运行环境与 Semaphore，把 `employee-data` 迁入，执行器凭据改为运行时从 BWS 取出；`wsctl` 取代 `onboard.sh`，写命令改为交互确认（Semaphore 用 `--approve <SHA>`）。完成后 Mac 只作为浏览器和开发机。

## Outcome

管理员在浏览器里经 Semaphore 运行 wsctl，执行器不再依赖 Mac 在线。

## Requirements

- R1 (parent R12): pve0 上存在由 Terraform 创建的 `ws-executor` VM（VMID 115，192.168.1.115），只能从局域网与 Tailscale 访问，无公网入站。
- R2 (parent R12): Semaphore 以 root 运行在该 VM，管理员从浏览器登录后可运行调用 wsctl 的模板，并能配置定时任务。
- R3 (parent R12): 执行器凭据在运行时从 BWS default 项目取出、用完即删；VM 本地只常驻 BWS 机器账号 token 与加密的邮件 OAuth 缓存。
- R4 (parent R12): `employee-admin` 私有代码以 VM 上的裸仓库为远程，`git push` 即部署到运行目录。
- R5 (parent R12): `employee-data` 迁到 VM 后，VM 上 `wsctl status` 的结果与迁移前 Mac 上一致；完成后 Mac 上没有执行器凭据，无法执行写命令。
- R6 (parent R13): `wsctl` 取代 `onboard.sh` 且不再需要 `--profile`；`onboard.sh` 转发到 `wsctl`。
- R7 (parent R13, AD-1): 创建或删除资源的命令展示计划，确认后以同一 SHA 执行；`--approve <SHA>` 用于非交互调用；计划或输入变化即拒绝。

## Constraints

- (AD-1, AD-15) 同一时间只有一个执行器；迁移期间不得出现 Mac 与 VM 并发写。
- (AD-15) VM 无公网入站，所有连接由它主动发起。
- (AGENTS.md) 现行规则为"IaC 凭据以 Ansible Vault 为准、BWS 只放员工凭据"；本 epic 须同步修订该段，写明执行器凭据在 BWS default 项目。
- (initiative Decision 2026-10-31) 迁移期间允许员工掉线，不重发设备包。

## Done when

- Semaphore 中运行 `wsctl status` 的结果与迁移前 Mac 上一致。
- Semaphore 中经确认执行一次写命令（如 reissue）成功；计划变化时被拒绝。
- Mac 上已无执行器凭据，`onboard.sh` 转发到 `wsctl`。
- 从局域网外、非 Tailscale 来源实测无法连接 VM 的任何端口。

## Boundaries

- 不实现 renew、到期、网站、提醒、退役（属于 epic 2–4）。
- Must not change: 现有员工的设备身份与 BWS 中的员工私钥。

## References

- parent — `_bmad-output/initiative-employee-lifecycle/initiative-employee-lifecycle.md`, section Requirements (R12, R13)
- architecture — `_bmad-output/initiative-employee-lifecycle/architecture-employee-lifecycle/architecture-employee-lifecycle.md`, AD-1, AD-15

## Notes

- Decision: 2026-10-31 VM 为 Ubuntu cloud-init，使用 `proxmox-vm` 模块，2 核 4GB 32GB；VMID 115 / 192.168.1.115，plan 前复核未被占用。
- Decision: 2026-10-31 Semaphore 与 wsctl 以 root 运行；Semaphore 只能从局域网与 Tailscale 访问，接受"被攻破即 root"的风险。
- Decision: 2026-10-31 Semaphore 使用原生包与嵌入式数据库；v2.19 支持哪一种，实施时核实。
- Decision: 2026-10-31 执行器凭据放 BWS default 项目；BWS token 本地保留，由 Ansible 从 IaC Vault 部署；邮件 OAuth 缓存留本地加密。
- Decision: 2026-10-31 拆为 9 个 story；第一个 story（tracer bullet）为 #1"ws-executor VM 上线并只对局域网与 Tailscale 开放"；#2、#3 与 #1、#4 并行；保留收尾的 Refactor sweep（#9）。
- Unknown: settings 中 BWS 程序为 macOS 版（Linux 版此前已删除），`terraform_secret_vars_file` 仍指向旧 Sandbox 路径，迁移时须修正。
