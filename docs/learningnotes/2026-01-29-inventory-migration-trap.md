# 学习笔记：从静态 Inventory 迁移到动态 Inventory 的数据丢失陷阱

**日期**: 2026-01-29
**标签**: #Ansible #Terraform #Refactoring #DevOps

## 1. 核心问题复盘
在我们将基础设施代码 (IaC) 从 **Static Inventory** (静态 YAML 文件) 重构为 **Dynamic Inventory** (Terraform State) 的过程中，发生了一次意外的“配置丢失”。

### 1.1 发生了什么？
我们删除了 `ansible/inventory/pve_lxc/caddy.yml` 等文件，目的是让 Ansible 直接通过 `terraform.yml` 插件从 Terraform 读取主机列表。
结果导致 Caddy 上的 `homepage`, `netbox` 等反向代理配置丢失，仅剩新配置的 `rustdesk`。

### 1.2 为什么会丢失？
这是因为我们需要区分两个概念：**寻址 (Addressing)** 与 **配置 (Configuration)**。

*   **旧架构 (Static Inventory)**:
    静态文件通常**混合**了这两者：
    ```yaml
    # pve_lxc/caddy.yml
    caddy:
      hosts:
        caddy:
          ansible_host: 192.168.1.105  # <--- 寻址 (Infrastructure)
          caddy_reverse_proxies:       # <--- 配置 (Configuration)
            - subdomain: netbox ...
    ```

*   **新架构 (Dynamic Inventory)**:
    Terraform 只负责“寻址”：
    *   Terraform 告诉 Ansible: "Caddy 在 192.168.1.105"。
    *   **Terraform 不知道也不应该知道** `caddy_reverse_proxies` 是什么。

**陷阱**: 当我们认为“Terraform 已经接管了 Inventory”并删除旧 YAML 文件时，我们实际上**同时也删除了附着在文件里的业务配置数据**。

## 2. 正确的架构模式
为了避免这种情况，必须严格执行 **数据与逻辑分离**，以及 **基础设施与应用配置分离**。

### 2.1 推荐目录结构
```bash
ansible/
├── inventory/
│   ├── terraform.yml       # 1. 动态源：只负责“有哪些机器” (Infrastructure)
│   ├── group_vars/         # 2. 通用配置：比如所有 LXC 的默认 DNS
│   │   └── pve_lxc.yml
│   └── host_vars/          # 3. 专用配置：承载业务数据 (Configuration)
│       ├── caddy.yml       #    <--- 代理规则放这里！
│       ├── netbox.yml      #    <--- 数据库密码放这里！
│       └── ...
```

### 2.2 迁移黄金法则
> **"Don't delete the file, migrate the vars."**
> (不要直接删除文件，要先迁移变量。)

在删除静态 Inventory 文件之前，必须检查其中是否定义了 `ansible_host` 和 `ansible_user` 以外的变量。
如果有，必须将这些变量提取出来，放入 `host_vars/<hostname>.yml` 中。

## 3. 关于模板 (Templates) 的最佳实践
不要将业务配置写死在 J2 模板中。
*   ❌ **Bad**: 在 `Caddyfile.j2` 里写死 `reverse_proxy 192.168.1.102`。
*   ✅ **Good**: 在 `Caddyfile.j2` 里遍历变量 `{% for proxy in caddy_reverse_proxies %}`。

这保证了 Ansible Role 的**通用性**，配置数据则由 Inventory 层的 `host_vars` 注入。

## 4. 附：Passlib 是什么？
在 Ansible 中使用 `password_hash` 过滤器（例如生成 Caddy WebDAV 的 bcrypt/blowfish 密码哈希）时，Ansible 实际上是调用 Python 的 `passlib` 库来执行哈希计算。
如果控制节点（运行 Ansible 的机器）没有安装 `passlib`，任务就会失败。这是一个典型的**控制节点依赖 (Control Node Dependency)**。
