# 学习笔记：Tailscale 在 Proxmox LXC 与混合云环境中的深度集成 (2025-12-02)

## 1. 背景
在将 OCI (Oracle Cloud) 实例纳入 Homelab 管理并集成 Homepage 监控的过程中，我们深度重构了 Tailscale 的部署方案。本文记录了在 Proxmox LXC 容器中运行 Tailscale 的特殊挑战、Ansible 代码重构的思考，以及对 Terraform 管理 Tailnet 的架构探讨。

## 2. LXC 容器运行 Tailscale 的核心挑战

在非特权 (Unprivileged) LXC 容器中运行 Tailscale 需要解决两个核心问题：设备访问与 DNS 解析。

### 2.1 `/dev/net/tun` 设备透传
Tailscale 依赖 `tun` 设备创建虚拟网卡。默认情况下，非特权 LXC 容器无法访问宿主机的此设备。

*   **症状**: `tailscale up` 报错，提示无法创建网络接口。
*   **解决方案**: 修改宿主机上的容器配置文件 (`/etc/pve/lxc/<vmid>.conf`)。
    ```bash
    lxc.cgroup2.devices.allow: c 10:200 rwm
    lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
    ```
*   **Ansible 实现**: 使用 `delegate_to: {{ proxmox_node }}` 将任务委托给宿主机执行。
*   **注意**: 修改配置文件后，**必须重启容器**才能生效。

### 2.2 DNS 解析死锁 (The DNS Deadlock)
这是一个经典的“鸡生蛋”问题。

*   **场景**: Proxmox 宿主机安装了 Tailscale 并开启了 MagicDNS (如 `100.100.100.100`)。
*   **问题**: Proxmox 会自动将宿主机的 `/etc/resolv.conf` 同步给 LXC 容器。
*   **死锁**:
    1.  容器启动，DNS 指向 MagicDNS IP。
    2.  容器内的 Tailscale 还没启动，无法连接 MagicDNS IP。
    3.  Ansible 尝试 `apt install tailscale` 或 `curl` 下载脚本。
    4.  **失败**: DNS 解析超时，因为网络不通。
*   **解决方案**:
    1.  **禁止覆写**: 创建 `/etc/.pve-ignore.resolv.conf` 告诉 Proxmox "不要碰我的 DNS"。
    2.  **临时修复**: 强制将 `/etc/resolv.conf` 指向公共 DNS (如 `8.8.8.8`)。

## 3. Ansible 重构：从 Playbook 到 Role

初期的实现将 LXC 的特殊处理逻辑写在 Playbook 的 `pre_tasks` 中，导致逻辑分散且难以复用。我们进行了以下重构：

### 3.1 逻辑封装 (Encapsulation)
将所有 LXC 相关的逻辑（透传、DNS、重启）全部移入 `roles/tailscale/tasks/main.yml`。

*   **优势**: Playbook 变得极其简洁，只需调用 Role。
*   **技术点**: 在 Role 内部使用 `delegate_to` 操作宿主机，保持了 Role 的自包含性。

### 3.2 统一 Inventory 与变量
*   **旧状**: `tailscale_auth_key` 分散在多个 `group_vars` 文件中，容易导致不一致。
*   **新状**:
    *   创建 `inventory/groups.yml` 定义 `tailscale` 组。
    *   创建 `inventory/group_vars/tailscale.yml` 集中管理 Auth Key。

## 4. 架构探讨：Terraform vs Ansible

我们探讨了 "是否应该用 Terraform 管理 Tailscale (Tailnet)" 的问题。

### 4.1 控制平面 (Control Plane) -> Terraform
Tailscale 的**策略与配置**非常适合 Terraform：
*   **ACLs**: 将 JSON 规则代码化，实现 GitOps。
*   **Auth Keys**: 自动生成 Reusable Key，无需手动复制粘贴。
*   **DNS Settings**: 全局 DNS 配置。

### 4.2 数据平面 (Data Plane) -> Ansible
Tailscale 的**客户端落地**依然离不开 Ansible：
*   **软件安装**: `apt` / `curl`。
*   **系统配置**: 开启 `ip_forward`，处理 LXC 透传。
*   **服务启动**: `systemctl`。

### 4.3 最佳实践架构
**混合模式**:
1.  **Terraform**: 定义 ACLs，生成 Auth Key 并 Output。
2.  **Ansible**: 读取 Terraform Output 的 Key，在各节点执行安装和接入。

## 5. 总结
*   **LXC 并不简单**: 它是轻量级虚拟化，但在网络和设备隔离上需要特殊处理。
*   **Ansible Role 应当自包含**: 即使涉及宿主机操作，也应封装在 Role 内部，对使用者透明。
*   **IaC 工具各司其职**: Terraform 管资源与策略 (State)，Ansible 管配置与部署 (Process)。
