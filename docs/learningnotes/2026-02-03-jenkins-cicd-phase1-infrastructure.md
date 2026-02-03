# Jenkins CI/CD 学习笔记 - Phase 1: 基础设施部署

> 日期：2026-02-03
> 主题：在 Proxmox LXC 上部署 Jenkins + Terraform + Ansible

## 概念解释

### 为什么选择 LXC 而不是 Docker？

| 方案 | 优点 | 缺点 |
|------|------|------|
| **LXC** | 轻量、像轻量 VM、可以直接装所有工具 | 需要 Proxmox 支持 |
| **Docker** | 容器化、便携 | Jenkins 容器内还需装 Terraform/Ansible，"套娃"复杂 |
| **VM** | 完全隔离 | 资源开销大 |

**结论**：Jenkins 需要运行 `terraform` 和 `ansible-playbook` 命令，LXC 更像轻量 VM，管理更直观。

### Terraform lifecycle ignore_changes

```hcl
lifecycle {
  ignore_changes = [
    ssh_public_keys,  # 防止更新 SSH 密钥时销毁重建容器
  ]
}
```

**作用**：
- 已存在的资源：更新被忽略，不触发 destroy/recreate
- 新创建的资源：使用最新的变量值

**使用场景**：当某个属性的更改会导致资源重建，但你不希望这样时。

### Jenkins GPG Key 问题（Debian 12）

Debian 12 不再使用 `apt-key`，需要把 GPG key 放到 `/usr/share/keyrings/` 目录：

```bash
# 正确方式
gpg --batch --keyserver keyserver.ubuntu.com --recv-keys 7198F4B714ABFC68
gpg --batch --export 7198F4B714ABFC68 > /usr/share/keyrings/jenkins-keyring.gpg

# sources.list 中引用
deb [signed-by=/usr/share/keyrings/jenkins-keyring.gpg] https://pkg.jenkins.io/debian-stable binary/
```

### PEP 668 - Python 外部管理环境

Debian 12 禁止用 `pip` 直接安装系统级 Python 包，会报 `externally-managed-environment` 错误。

**解决方案**：
- 使用 `apt install ansible` 替代 `pip install ansible`
- 或者使用 `python3 -m venv` 创建虚拟环境

## 设计决策

### 为什么 VMID = IP 最后一位？

项目约定：VMID 107 → IP 192.168.1.107

**好处**：
- 便于记忆和管理
- 快速定位资源
- 避免 IP 冲突

### Ansible Host Groups 设计

```hcl
groups = ["pve_lxc", "jenkins"]
```

- `pve_lxc`：所有 LXC 共享的组，便于批量操作
- `jenkins`：专属组，playbook 用 `hosts: jenkins` 定位

## 踩坑记录

### 1. SSH 连接被拒绝

**问题**：新建 LXC 后 Ansible 无法 SSH 连接

**原因**：devcontainer 的 SSH 公钥不在 Terraform `sshkeys` 变量中

**解决**：
1. 把新公钥加到 `terraform.tfvars`
2. 因为会触发所有 LXC 重建，改用 `ignore_changes` + 手动注入公钥

### 2. Jenkins GPG Key 验证失败

**问题**：`NO_PUBKEY 7198F4B714ABFC68`

**原因**：Jenkins 更新了签名密钥，旧的 `jenkins.io-2023.key` 不包含新 key

**解决**：从 keyserver 直接获取最新的 key ID

### 3. Alpine 没有 bash

**问题**：`pct exec 105 -- bash -c '...'` 失败

**原因**：Alpine 系统只有 `sh`，没有 `bash`

**解决**：对 Alpine 使用 `sh -c` 替代 `bash -c`

### 4. Ansible 内置变量冲突

**问题**：`ansible_version.stdout_lines` 报错

**原因**：`ansible_version` 是 Ansible 内置 fact，不能作为 register 变量名

**解决**：改用 `ansible_version_output`

## 创建的文件

```
terraform/proxmox/jenkins.tf           # Jenkins LXC 定义
terraform/modules/proxmox-lxc/main.tf  # 添加 ssh_public_keys 到 ignore_changes
ansible/roles/jenkins/
├── defaults/main.yml                  # 默认变量
├── tasks/main.yml                     # 安装任务
└── handlers/main.yml                  # 服务处理器
ansible/playbooks/deploy-jenkins.yml   # 部署 + 验证 playbook
```

## Q&A 汇总

**Q: ignore_changes 会影响新建资源吗？**
A: 不会。ignore_changes 只影响已存在资源的更新，新建资源会使用完整的变量值。

**Q: 为什么用 apt 装 Ansible 而不是 pip？**
A: Debian 12 遵循 PEP 668，禁止 pip 直接安装系统级包。apt 是官方推荐方式。

**Q: Jenkins LTS vs Weekly 怎么选？**
A: 生产环境选 LTS（长期支持），学习/测试可选 Weekly（最新功能）。

## 部署结果

| 项目 | 值 |
|------|-----|
| Jenkins URL | http://192.168.1.107:8080 |
| Terraform | v1.14.4 |
| Ansible | core 2.14.18 |
| Java | OpenJDK 17.0.18 |
