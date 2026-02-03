# Jenkins CI/CD 学习笔记 - Phase 2: Jenkins 配置

> 日期：2026-02-03
> 主题：Jenkins 插件安装、凭据配置、GitHub SSH 连接

## 概念解释

### Jenkins 凭据类型

| 类型 | 用途 | 示例 |
|------|------|------|
| **SSH Username with private key** | SSH 连接认证 | GitHub Deploy Key |
| **Secret text** | 单个密钥/Token | Terraform Cloud Token |
| **Secret file** | 文件形式的密钥 | Ansible Vault 密码文件 |
| **Username with password** | 用户名密码对 | 基础 HTTP 认证 |

### GitHub Deploy Key vs Personal Access Token (PAT)

| 特性 | Deploy Key | PAT |
|------|------------|-----|
| 作用范围 | 单个仓库 | 用户所有仓库 |
| 权限 | 可设只读或读写 | 按 scope 配置 |
| 过期 | 永不过期 | 可设过期时间 |
| 安全性 | 更好（范围小） | 泄露影响大 |

**选择 Deploy Key 的原因**：
- 只需访问一个仓库
- 永不过期，无需维护
- 最小权限原则

### Terraform Cloud Token

HCP Terraform Cloud 的 API Token 用于：
- 远程执行 `terraform plan/apply`
- 访问远程状态 (`terraform state pull`)
- 不需要本地存储 `.tfstate` 文件

生成路径：`Terraform Cloud → User Settings → Tokens → Create an API token`

## 配置步骤详解

### 1. 安装 Jenkins 插件

在 `Manage Jenkins → Plugins → Available plugins` 中安装：

- **Terraform** - 提供 Terraform 构建步骤
- **Ansible** - 提供 Ansible 构建步骤
- **AnsiColor** - 终端彩色输出支持

### 2. 配置 GitHub SSH 凭据

**步骤 1：在 Jenkins LXC 上生成 SSH 密钥对**

```bash
# 切换到 jenkins 用户
sudo -u jenkins ssh-keygen -t ed25519 -C "jenkins@homelab" -f /var/lib/jenkins/.ssh/id_ed25519 -N ""
```

**步骤 2：配置 SSH known_hosts**

```bash
# 预先信任 GitHub 主机
sudo -u jenkins ssh-keyscan github.com >> /var/lib/jenkins/.ssh/known_hosts
```

**步骤 3：添加 Deploy Key 到 GitHub**

1. 复制公钥内容：`cat /var/lib/jenkins/.ssh/id_ed25519.pub`
2. GitHub 仓库 → Settings → Deploy keys → Add deploy key
3. 粘贴公钥，勾选 "Allow write access"（如需推送）

**步骤 4：在 Jenkins 添加凭据**

1. `Manage Jenkins → Credentials → System → Global credentials`
2. Add Credentials:
   - Kind: `SSH Username with private key`
   - ID: `github-ssh-key`
   - Username: `git`
   - Private Key: 直接输入私钥内容

### 3. 配置 Terraform Cloud Token

1. Add Credentials:
   - Kind: `Secret text`
   - ID: `terraform-cloud-token`
   - Secret: 从 Terraform Cloud 复制的 Token

### 4. 配置 Ansible Vault 密码

1. Add Credentials:
   - Kind: `Secret file`
   - ID: `ansible-vault-password`
   - File: 上传包含 vault 密码的文件

## 设计决策

### 为什么用 Secret file 存 Vault 密码？

Ansible 的 `--vault-password-file` 参数需要文件路径，不能直接传入字符串。

使用 Jenkins 的 Secret file：
```groovy
withCredentials([file(credentialsId: 'ansible-vault-password', variable: 'VAULT_PASS')]) {
    sh "ansible-playbook --vault-password-file ${VAULT_PASS} playbook.yml"
}
```

Jenkins 会创建临时文件，执行后自动删除。

### SSH Key 放 Jenkins 服务器 vs 放 Jenkins Credentials

| 方案 | 优点 | 缺点 |
|------|------|------|
| **服务器 .ssh 目录** | Git 命令直接可用 | 需手动管理 |
| **Jenkins Credentials** | UI 管理、可追踪 | 需 `sshagent` 包装 |
| **两者都配** | 灵活、备份 | 需同步维护 |

**选择两者都配**：
- 服务器 .ssh：让 `git clone` 在任何地方都能工作
- Credentials：Pipeline 中使用 `sshagent` 步骤，更规范

## 踩坑记录

### 1. Host key verification failed

**问题**：Pipeline 克隆仓库时报 `Host key verification failed`

**原因**：jenkins 用户的 `~/.ssh/known_hosts` 没有 GitHub 的主机密钥

**解决**：
```bash
sudo -u jenkins ssh-keyscan github.com >> /var/lib/jenkins/.ssh/known_hosts
```

### 2. Permission denied (publickey)

**问题**：SSH 连接 GitHub 失败

**排查步骤**：
```bash
# 测试 SSH 连接
sudo -u jenkins ssh -T git@github.com

# 检查 key 权限
ls -la /var/lib/jenkins/.ssh/
# 应该是：id_ed25519 (600), id_ed25519.pub (644)
```

**常见原因**：
1. Deploy Key 没添加到 GitHub 仓库
2. 私钥权限不是 600
3. 使用了错误的用户执行命令

### 3. Credentials 在 Pipeline 中不生效

**问题**：`withCredentials` 块中变量为空

**原因**：Credentials ID 拼写错误或作用域不对

**检查**：
- ID 是否完全匹配（区分大小写）
- Credentials 是否在 Global scope

## 创建的凭据清单

| Credentials ID | 类型 | 用途 |
|----------------|------|------|
| `github-ssh-key` | SSH private key | 克隆 GitHub 仓库 |
| `terraform-cloud-token` | Secret text | Terraform Cloud API 认证 |
| `ansible-vault-password` | Secret file | 解密 Ansible Vault |

## Q&A 汇总

**Q: Deploy Key 和 SSH Key 有什么区别？**
A: Deploy Key 是 GitHub 特有概念，本质就是 SSH 公钥，但绑定到特定仓库而非用户账户。

**Q: 为什么 Git 用户名是 "git" 而不是 GitHub 用户名？**
A: SSH 方式连接 GitHub 时，用户名固定是 `git`，身份识别通过 SSH 密钥完成。

**Q: Terraform Cloud Token 会过期吗？**
A: User Token 默认不过期，但可以设置过期时间。Team Token 和 Organization Token 有不同策略。

**Q: 如何轮换 Jenkins 中的凭据？**
A: `Manage Jenkins → Credentials → 选择凭据 → Update`，Pipeline 会自动使用新值，无需修改代码。
