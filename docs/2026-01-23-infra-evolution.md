# 学习笔记：2026-01-23 自动化基础设施演进与最佳实践

## 1. 概览 (Overview)
本日工作重点在于将基础设施从“半手工/半自动化”状态迁移至“完全自动化”状态。核心成就包括全量迁移 Ansible Inventory 至 Terraform 管理，部署 DevContainer，解决 SSH 密钥注入的边界问题，并建立了基于 Role 的 Ansible 目录结构。

---

## 2. 详细工作记录

### 2.1 Ansible Inventory 架构重构 (Migration)
我们彻底改变了 Ansible 获取主机信息的方式，实现了 **单一事实来源 (Single Source of Truth, SSOT)**。

*   **旧架构**：混合模式。
    *   部分主机在 `inventory/pve_xxx` 的 YAML 文件中静态定义。
    *   部分主机通过 `terraform-inventory` 插件动态获取。
    *   存在问题：信息割裂，手动维护 hassle，容易出现 IP 变更后清单不更新的问题。
*   **新架构**：全动态模式。
    *   **核心机制**：移除所有静态的主机定义 YAML。Ansible 完全依赖 `terraform.tfstate` 文件。
    *   **注册方式**：在 Terraform 的 `.tf` 文件中，利用 `ansible_host` 资源将计算资源（VM/LXC）注册到 Inventory。
    *   **物理节点处理**：创建了 `terraform/proxmox/pve_cluster.tf`，专门用于注册物理节点（`pve0`, `pve1`, `pve2`），确保物理机也能被 Terraform 感知并在 Ansible 中管理。
    *   **清理工作**：
        *   归档 legacy 库存文件至 `ansible/legacy_inventory_backup`。
        *   **Redundant Group Cleanup**：移除了冗余的“单主机组”（如 `immich` 主机同时属于 `immich` 组），直接通过主机名管理，精简了 Inventory Graph。
        *   **Group Hierarchy**：保留 `groups.yml` 仅用于定义“组的组”（如 `tailscale` 包含 `pve_vms`），不再用于定义具体主机。

### 2.2 DevContainer 自动化部署
实现了开发环境的快速交付。
- **Terraform**：定义 VM 规格，通过 Cloud-Init 注入初始 User Data。
- **Ansible Playbook** (`deploy-devcontainer.yml`)：
    - 安装 Docker Engine & Compose。
    - 配置非 Root 用户（`ubuntu`）加入 Docker 组。

### 2.3 SSH 访问疑难排查 (Debugging)
**问题现象**：Ansible 可以连接 VM，但手动 SSH (`ssh ubuntu@ip`) 提示密码。
**根本原因**：
1.  **密钥类型混淆**：本地 `~/.ssh/id_rsa.pub` 文件名暗示是 RSA，但内容实际上是 `ssh-ed25519`。虽然 SSH 客户端能识别，但容易造成误解。
2.  **Cloud-Init 生命周期**：**关键点**。Terraform 更新了 `tfvars` 里的公钥配置，但对于**已运行**的虚拟机，Cloud-Init 默认只运行一次（First Boot）。因此，新的公钥虽然被挂载到了 ISO，但没有被写入 `authorized_keys`。
**解决方案**：
- 使用 Ansible 的 `authorized_key` 模块直接将正确的 ED25519 公钥强制写入运行中的 VM。这验证了 Ansible 在“配置强制（Configuration Enforcement）”方面的价值。

### 2.4 Ansible 代码结构优化 (Refactoring)
为了避免每个 Playbook 都重复写“安装 vim”、“配置 key”等任务，我们引入了模块化设计。

*   **Common Role (`roles/common`)**：
    *   **Vars**：集中管理所有管理员的 SSH 公钥列表。
    *   **Tasks**：
        1.  安装基准软件包 (`vim`, `curl`, `htop`, `git`, `net-tools`)。
        2.  循环注入所有管理员的 SSH Key。
        3.  配置 sudo 组免密权限 (`NOPASSWD`)。
*   **Master Playbook (`site.yml`)**：
    *   创建了全局入口文件。
    *   逻辑：`all` 主机应用 `common` -> 特定组应用特定 Role（如 `devcontainer`）。
    *   意义：确保未来任何新机器只要跑一次 `site.yml`，就自动具备运维基础环境。

---

## 3. 核心概念定义

### 3.1 Ansible Dynamic Inventory (动态清单)
一种机制，允许 Ansible 在运行时查询外部数据源（如 Cloud Provider API, Terraform State, CMDB）来构建主机列表，而不是读取静态文本文件。这对于云原生和频繁变动的环境至关重要。

### 3.2 Configuration Drift (配置漂移)
指服务器的实际配置与 IaC 代码中定义的期望配置随时间推移逐渐偏离的现象。
*   *例子*：Terraform 里定义了 Key A，但有人手动 SSH 上去加了 Key B。
*   *对策*：定期运行 Ansible Playbook 强制覆盖配置。

### 3.3 Bootstrap vs. Enforcement (引导与强制)
*   **Bootstrap (Terraform)**：负责“生”。创建资源，注入最基础的连接能力（如 CI User 的 SSH Key）。如果不做这步，Ansible 连都连不上。
*   **Enforcement (Ansible)**：负责“养”和“管”。确保软件安装正确、配置文件正确、用户权限正确。可以反复运行（幂等性）。

---

## 4. Q&A (Session Highlights)

**Q: 为什么 SSH key 都在 `terraform.tfvars` 里改了，apply 也成功了，虚拟机里还是没有？**
**A**: 因为 Cloud-Init 在虚拟机里通常只在**第一次启动**时运行。Terraform 的 `apply` 操作对于 VM 资源，如果只是修改元数据（Metadata/Cloud-init ISO），通常不会触发 VM 的销毁重建。因此，VM 内部的 Cloud-Init 进程看到“我以前跑过初始化了”，就跳过了新的配置读取。
> **教训**: Terraform 改配置不等于 VM 内部生效。对于运行中 VM 的状态修改，Ansible 是更合适的工具。

**Q: SSH Key 到底应该放在 Terraform 还是 Ansible？**
**A**: **混合模式是最佳实践**。
1.  **Terraform** 注入一个“救火/运维专用”的 Key（或 Ansible 自动化账号的 Key），保证机器一开机就能被管理。
2.  **Ansible** `common` Role 管理具体的开发人员 Key 列表。这样当团队成员变动时，改一下 Ansible 变量跑一遍即可，速度快且无需重启机器。

**Q: `site.yml` 是什么？必须叫这个名字吗？**
**A**: 它是 Ansible 项目的“总入口”剧本。名字不是强制的（你可以叫 `main.yml` 或 `deploy_all.yml`），但 `site.yml` 是社区约定俗成的标准命名。运维人员看到它就知道：“运行这个文件可以部署整个站点”。

**Q: 为什么要把 `groups.yml` 里的 `pve_vms` 删掉？**
**A**: 为了消除歧义和冗余。我们决定让 `pve_vms` 组完全由 Terraform 的动态插件生成，而不是在静态文件中再次定义。`groups.yml` 现在的职责变得很纯粹：只定义高层级的逻辑分组（如 `tailscale` 包含哪些子组），不再关心底层有哪些主机。

**Q: 为什么把单主机的组（Group）去掉？**
**A**: 之前的清单里，每个主机（如 `immich`）都自动生成了一个同名的组 `immich`。这在 `graph` 视图里非常乱。清理后，主机直接隶属于功能组（如 `pve_vms`），结构更扁平清晰。Ansible 原生支持直接指定 `hosts: hostname`，不需要专门给它套一个组。
