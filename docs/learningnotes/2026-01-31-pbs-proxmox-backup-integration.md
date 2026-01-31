# 学习笔记：PBS 与 Proxmox 集群备份集成（IaC 方式）

**日期**: 2026-01-31
**标签**: #PBS #Proxmox #Backup #Ansible #IaC #ZFS

通过 Ansible 自动化配置 Proxmox 集群备份到 PBS（Proxmox Backup Server），过程中遇到了大量 CLI 差异、API 认证、Jinja2 陷阱等实战问题。

## 1. PBS CLI 命令与文档差异

**误区**: 以为 `proxmox-backup-manager user token` 是子命令前缀（类似 Proxmox VE 的风格）。
**事实**:
*   PBS 的 token 管理命令是 **独立的子命令**，不是嵌套的：
    *   `user list-tokens <userid>` （不是 `user token list`）
    *   `user generate-token <userid> <name>` （不是 `user token add`）
    *   `user delete-token <userid> <name>` （不是 `user token remove`）
*   `generate-token` 的输出不是纯 JSON，而是 `Result: { JSON }` 格式，需要先用 regex 去掉 `Result:` 前缀再解析。
*   `cert info --fingerprint` 不是一个独立的参数 —— 正确的做法是调用 `cert info` 然后从文本输出中用 regex 提取 `Fingerprint (sha256):` 行。

**教训**: PBS 和 PVE 虽然同属 Proxmox 家族，但 CLI 风格不统一。写自动化脚本前，一定要先手动测试实际命令输出格式。

## 2. PBS API Token 认证机制

### Token vs 用户的关系

```
backup@pbs (用户)
  └── backup@pbs!automation (API Token)
        └── 继承用户权限 + 可独立设置 ACL
```

*   Token 创建时必须其所属用户已存在，否则虽然命令不报错但认证会失败。
*   Token **默认不继承** 用户在某个 datastore 上的权限 —— 需要单独对 token 设置 ACL：
    ```bash
    proxmox-backup-manager acl update /datastore/backup-storage DatastoreAdmin --auth-id backup@pbs!automation
    ```
*   `DatastoreBackup` 角色不够让 Proxmox 检测到 datastore —— 需要 `DatastoreAdmin` 才能通过 `pvesm add` 的连通性验证。

### Token 值的生命周期

*   Token 值**只在创建时显示一次**，之后无法找回。
*   自动化中需要特别处理这个问题：
    *   首次运行：创建 token → 显示值 → 用户手动保存到 vault
    *   后续运行：通过 `--extra-vars` 或 vault 提供已保存的值
    *   未提供值时：明确 `fail` 并给出重建 token 的命令

## 3. Proxmox `pvesm` 存储管理的不可变参数

**误区**: 认为 `pvesm set` 可以像 `pvesm add` 一样更新所有参数。
**事实**: 对于 PBS 类型存储，以下参数在创建后**不可修改**：
*   `--server` — "can't change value of fixed parameter 'server'"
*   `--datastore` — "Unknown option: datastore"
*   `--password` — `pvesm set` 不支持此参数

**结论**: 如果需要修改这些参数，唯一的方法是删除后重建：
```bash
pvesm remove pbs-backup
# 然后重新运行 playbook
```

在 Ansible 中，当存储已存在时最合理的做法是只做验证（确认 active），不尝试更新。

## 4. PVE 9.x `pvesh` 备份任务 API

### 不支持 `--notification-policy`

虽然 PVE 文档提到 `--mailnotification` 已弃用，但 PVE 9.0.3 的 `pvesh` CLI 实际上两个都不支持：
*   `--mailnotification failure` → 可能在旧版本工作
*   `--notification-policy failure` → "Unknown option"

**解决方案**: 不传通知参数，使用 Proxmox UI 中的通知系统单独配置。

### `--comment` 参数的空格问题

`pvesh create /cluster/backup --comment "Managed by Ansible"` 中带空格的字符串在 Ansible `command` 模块中会被拆分为多个参数。使用连字符代替空格：`--comment Managed-by-Ansible`。

## 5. Ansible Jinja2 陷阱：`>-` 与 `None`

**Bug**: 用 `>-`（折叠块标量）配合 `default(None)` 会产生字符串 `"None"` 而不是 Python 的 `None`。

```yaml
# 错误写法 - pbs_existing_job 会变成字符串 "None"
pbs_existing_job: >-
  {{ list | first | default(None) }}

# 然后 is none 测试会失败
when: pbs_existing_job is none    # 永远是 false！
```

**原因**: `>-` 会将整个表达式的输出当作字符串处理，`None` 被序列化为字面量 `"None"`。

**正确写法**:
```yaml
# 方案1: 用引号包裹（不使用 >-），default 用 false
pbs_existing_job: "{{ list | first | default(false) }}"

# 方案2: 使用独立的布尔变量
pbs_existing_job: "{{ list | first | default({}) }}"
pbs_job_exists: "{{ (list | length) > 0 }}"
```

另一个相关陷阱：Ansible 新版本不允许 dict 类型直接用于 `when` 条件（"Conditional result was derived from value of type 'dict'"）。必须用显式的布尔变量。

## 6. 跨 Play 变量传递：`delegate_facts` 模式

Playbook 中需要在 PBS 主机获取信息（token、指纹），然后在 Proxmox 主机使用。Ansible 的做法是：

```yaml
# Play 1: 在 PBS 上运行
- name: Export facts to localhost
  set_fact:
    pbs_fingerprint: "{{ pbs_fingerprint }}"
  delegate_to: localhost
  delegate_facts: true

# Play 2: 在 Proxmox 上运行
- hosts: pve0
  vars:
    pbs_fingerprint: "{{ hostvars['localhost']['pbs_fingerprint'] }}"
```

**注意事项**:
*   依赖隐式的 `localhost` 在 inventory 中存在
*   使用 `--limit` 筛选主机时可能破坏这个模式
*   `| default(omit)` 通过 `delegate_facts` 传递时，可能变成 omit 占位符字符串

## 7. `include_tasks` vs `roles` 的变量作用域

**问题**: 在 playbook 中通过 `include_tasks` 引入角色内的 task 文件时，角色的 `defaults/main.yml` **不会自动加载**。

```yaml
# 这样不会加载 pbs_client/defaults/main.yml 中的变量！
tasks:
  - include_tasks: ../roles/pbs_client/tasks/pbs-token.yml
```

**解决方案**: 显式加载变量文件：
```yaml
vars_files:
  - ../roles/pbs_client/defaults/main.yml
tasks:
  - include_tasks: ../roles/pbs_client/tasks/pbs-token.yml
```

而如果通过 `roles:` 引入，defaults 会自动加载 —— 这是 Ansible role 机制的一部分。

---

## 架构决策总结

| 决策 | 选择 | 原因 |
|------|------|------|
| PBS 认证方式 | API Token | 比密码更安全，可独立撤销 |
| 备份模式 | Snapshot | 无需停机，对运行中的 VM/LXC 影响最小 |
| 存储更新策略 | 只创建不更新 | PBS 存储参数大部分不可变 |
| 备份任务管理 | 创建 + 幂等更新 | `pvesh set` 支持重新设置 schedule/retention |
| 跨主机变量 | `delegate_facts` | Ansible 原生方式，无需额外中间文件 |
| Token 值管理 | 显示 + 手动保存 | Token 只显示一次的 PBS 限制 |

## 最终部署配置

```
PBS (192.168.1.249:8007)
  ├── 用户: backup@pbs
  ├── Token: backup@pbs!automation (DatastoreAdmin on backup-storage)
  ├── Datastore: backup-storage (ZFS mirror, 7.27TB)
  └── 证书指纹: 29:50:02:f3:83:57:33:da:...

Proxmox (pve0, 192.168.1.50)
  ├── 存储后端: pbs-backup (PBS 类型, active)
  └── 备份任务: 每天 02:00, snapshot+zstd
       ├── VMID: 100-106 (7 个工作负载)
       └── 保留: 7日 + 4周 + 6月
```
