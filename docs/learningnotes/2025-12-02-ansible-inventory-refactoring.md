# 学习笔记：Ansible Inventory 结构重构与最佳实践 (2025-12-02)

## 1. 背景与动机

在完成 Tailscale 部署重构后，我们发现 Ansible Inventory 结构存在以下问题：
1. **命名不一致**: 目录名 `pve-lxc` 与组变量文件 `pve_lxc.yml` 使用不同的分隔符
2. **组织混乱**: 同时使用单文件模式（`hosts.yml`）和目录模式（`pve-lxc/`）
3. **职责不清**: `hosts.yml` 既定义主机又定义组层级关系
4. **可扩展性差**: 所有 Proxmox 节点挤在一个文件里，难以单独管理

本文记录了如何将 Inventory 重构为清晰、一致、易维护的结构。

## 2. Ansible Inventory 的组织哲学

### 2.1 两种组织模式

Ansible 支持两种 Inventory 组织方式：

#### 单文件模式
```yaml
# inventory/hosts.yml
all:
  children:
    webservers:
      hosts:
        web1:
          ansible_host: 192.168.1.10
        web2:
          ansible_host: 192.168.1.11
```

**优点**: 简单直观，适合小规模环境  
**缺点**: 文件变大后难以维护，Git 冲突频繁

#### 目录模式（推荐）
```
inventory/
├── groups.yml              # 组层级定义
├── group_vars/             # 组变量
│   └── webservers.yml
├── host_vars/              # 主机变量
│   ├── web1.yml
│   └── web2.yml
└── webservers/             # 组成员定义
    └── hosts.yml
```

**优点**: 职责清晰，易扩展，Git 友好  
**缺点**: 文件数量多（但这不是真正的问题）

### 2.2 核心原则：单一职责

每个文件应该只负责一件事：
- `groups.yml`: **只**定义组之间的层级关系
- `group_vars/<组名>.yml`: **只**定义该组的变量
- `host_vars/<主机名>.yml`: **只**定义该主机的变量
- `<组名>/hosts.yml`: **只**列出该组的成员

## 3. 重构过程

### 3.1 问题诊断

**原始结构**:
```
inventory/
├── hosts.yml               # 混合：定义 proxmox_cluster 主机 + 组层级
├── tailscale.yml           # 单独定义 tailscale 组
├── pve-lxc/                # 命名不一致（使用连字符）
│   ├── anki.yml
│   └── homepage.yml
└── pve-vms/                # 命名不一致
    ├── immich.yml
    └── samba.yml
```

**问题**:
1. `hosts.yml` 职责过重
2. `pve-lxc` vs `pve_lxc.yml` 命名冲突
3. 组定义分散在多个文件

### 3.2 重构步骤

#### 步骤 1: 统一命名
```bash
mv inventory/pve-lxc inventory/pve_lxc
mv inventory/pve-vms inventory/pve_vms
```

**原则**: 目录名必须与 `group_vars` 文件名一致（都使用下划线）

#### 步骤 2: 拆分主机定义
将 `hosts.yml` 中的 Proxmox 节点拆分到独立的 `host_vars` 文件：

```yaml
# inventory/host_vars/pve0.yml
ansible_host: 192.168.1.50
ansible_user: root
ansible_ssh_pass: "Admin123..."
proxmox_api_host: "{{ ansible_host }}"
```

**好处**: 每个节点的配置独立，修改 pve0 不会影响 pve1 的 Git 历史

#### 步骤 3: 集中组定义
创建 `groups.yml` 统一管理所有组层级：

```yaml
# inventory/groups.yml
all:
  children:
    proxmox_cluster:
    pve_lxc:
      children:
        anki:
        homepage:
    pve_vms:
      children:
        immich:
        netbox:
        samba:
    tailscale:
      children:
        proxmox_cluster:
        pve_lxc:
        oci:
```

**好处**: 一眼看清整个基础设施的组织结构

#### 步骤 4: 创建组成员列表
```yaml
# inventory/proxmox_cluster/hosts.yml
proxmox_cluster:
  hosts:
    pve0:
    pve1:
    pve2:
```

**注意**: 这里只列出成员，不定义变量（变量在 `host_vars` 里）

### 3.3 最终结构

```
inventory/
├── groups.yml                    # 组层级关系（新增）
├── group_vars/                   # 组变量
│   ├── proxmox_cluster.yml
│   ├── pve_lxc.yml              # 与目录名一致
│   ├── pve_vms.yml              # 与目录名一致
│   ├── tailscale.yml
│   └── oci.yml
├── host_vars/                    # 主机变量（新增）
│   ├── pve0.yml
│   ├── pve1.yml
│   └── pve2.yml
├── proxmox_cluster/              # 组定义（新增）
│   └── hosts.yml
├── pve_lxc/                      # 重命名
│   ├── anki.yml
│   └── homepage.yml
├── pve_vms/                      # 重命名
│   ├── immich.yml
│   ├── netbox.yml
│   └── samba.yml
└── oci/
    └── hosts.yml
```

## 4. 关键概念辨析

### 4.1 `group_vars` vs `host_vars`

| 类型 | 用途 | 示例 |
|------|------|------|
| `group_vars` | 该组所有主机共享的变量 | `pve_lxc.yml`: `lxc_gateway: 192.168.1.1` |
| `host_vars` | 该主机特有的变量 | `pve0.yml`: `ansible_host: 192.168.1.50` |

**变量优先级**: `host_vars` > `group_vars` > `playbook vars`

### 4.2 目录名 vs 文件名

**错误示例**:
```
inventory/
├── group_vars/
│   └── pve_lxc.yml        # 使用下划线
└── pve-lxc/               # 使用连字符 ❌
```

**正确示例**:
```
inventory/
├── group_vars/
│   └── pve_lxc.yml        # 使用下划线
└── pve_lxc/               # 使用下划线 ✅
```

**原因**: Ansible 组名必须是合法的 Python 变量名（不能包含连字符）

### 4.3 何时合并，何时拆分？

**合并场景**:
- 配置简单且一致（如 3 个 Proxmox 节点的 API 配置）
- 主机数量少（< 5 个）

**拆分场景**:
- 配置复杂且差异大（如 Immich 有 10+ 个变量）
- 需要独立管理（如每个 VM 有不同的维护者）
- 希望 Git 历史清晰

**我们的选择**: 完全拆分，因为：
1. 环境规模可控（总共 < 15 台主机）
2. 每个服务配置差异大
3. Git 友好性优先

## 5. 验证与测试

### 5.1 验证组结构
```bash
ansible-inventory --graph
```

**预期输出**:
```
@all:
  |--@proxmox_cluster:
  |  |--pve0
  |  |--pve1
  |  |--pve2
  |--@tailscale:
  |  |--@proxmox_cluster:
  |  |--@pve_lxc:
  |  |--@oci:
```

### 5.2 验证变量继承
```bash
ansible pve0 -m debug -a "var=tailscale_auth_key"
```

**预期**: 能正确输出 `group_vars/tailscale.yml` 中的值

## 6. 文档更新清单

重构后需要更新的文档引用：
- ✅ `README.md`: 目录结构图
- ✅ `TAILSCALE_DEPLOYMENT.md`: `tailscale.yml` → `groups.yml`
- ✅ `HOMEPAGE_DASHBOARD_DEPLOYMENT.md`: `hosts.yml` → `groups.yml` (2处)
- ✅ `SAMBA_VM_DEPLOYMENT.md`: `hosts.yml` → `groups.yml`
- ✅ `2025-12-02-tailscale-integration-refactoring.md`: 学习笔记更新

## 7. 总结

### 核心收获
1. **一致性优先**: 目录名、文件名、组名必须统一
2. **单一职责**: 每个文件只做一件事
3. **完全拆分 > 部分拆分**: 在小规模环境中，完全拆分的清晰度优势远大于文件数量的劣势
4. **Git 友好性**: 独立文件 = 独立 commit = 清晰的变更历史

### 可复用的模式
```
inventory/
├── groups.yml              # 组层级（必需）
├── group_vars/             # 组变量（按需）
├── host_vars/              # 主机变量（按需）
└── <组名>/                 # 组成员定义（必需）
    └── hosts.yml
```

### 后续优化方向
- 考虑引入 Ansible Vault 加密 `ansible_ssh_pass`
- 将 `proxmox_api_*` 变量移到 `group_vars/proxmox_cluster.yml`（避免在每个 `host_vars` 重复）
- 探索动态 Inventory（从 Proxmox API 自动发现 VM/LXC）
