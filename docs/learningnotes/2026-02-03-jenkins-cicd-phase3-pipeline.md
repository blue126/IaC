# Jenkins CI/CD 学习笔记 - Phase 3: Pipeline 开发

> 日期：2026-02-03
> 主题：Jenkinsfile 编写、声明式 Pipeline、Terraform + Ansible 集成

## 概念解释

### 声明式 vs 脚本式 Pipeline

| 特性 | 声明式 (Declarative) | 脚本式 (Scripted) |
|------|---------------------|-------------------|
| 语法 | 结构化、固定格式 | 自由 Groovy 代码 |
| 学习曲线 | 低 | 高 |
| 灵活性 | 有限 | 完全自由 |
| 推荐场景 | 大多数情况 | 复杂逻辑需求 |

**本项目选择声明式**：结构清晰，易于维护和阅读。

### Pipeline 关键概念

```groovy
pipeline {
    agent any           // 在任意可用节点执行
    environment { }     // 环境变量定义
    options { }         // Pipeline 选项（超时、保留构建数等）
    stages {
        stage('Name') {
            steps { }   // 执行步骤
        }
    }
    post { }            // 构建后操作
}
```

### Credentials 在 Pipeline 中的使用

**方式 1：environment 块（推荐用于全局）**
```groovy
environment {
    TF_TOKEN_app_terraform_io = credentials('terraform-cloud-token')
}
```

**方式 2：withCredentials 块（推荐用于局部）**
```groovy
withCredentials([string(credentialsId: 'my-secret', variable: 'SECRET')]) {
    sh 'echo $SECRET'  // 只在这个块内可用
}
```

### Terraform Cloud 认证

Terraform CLI 通过环境变量 `TF_TOKEN_<hostname>` 自动认证：

```groovy
// 注意：点号要替换成下划线
TF_TOKEN_app_terraform_io = credentials('terraform-cloud-token')
```

对应的主机名是 `app.terraform.io`（HCP Terraform Cloud）。

## Pipeline 阶段设计

### 完整流程图

```
Checkout → Setup → Validate (并行) → Terraform Plan → 人工审批 → Terraform Apply → Refresh Inventory → 人工审批 → Ansible Deploy
                    ├── Terraform Validate
                    └── Ansible Lint
```

### 各阶段详解

| 阶段 | 目的 | 关键命令 |
|------|------|----------|
| **Checkout** | 拉取代码 | `checkout scm` |
| **Setup** | 准备环境 | 写 vault 密码文件、生成 tfvars |
| **Validate** | 语法检查 | `terraform validate`, `ansible-playbook --syntax-check` |
| **Terraform Plan** | 预览变更 | `terraform plan -out=tfplan` |
| **Approval** | 人工审批 | `input` 步骤 |
| **Terraform Apply** | 应用变更 | `terraform apply tfplan` |
| **Refresh Inventory** | 刷新 Ansible 动态库存 | `terraform state pull` |
| **Ansible Deploy** | 配置管理 | `ansible-playbook` |

### 并行执行

```groovy
stage('Validate') {
    parallel {
        stage('Terraform Validate') { ... }
        stage('Ansible Lint') { ... }
    }
}
```

**好处**：
- 缩短构建时间
- 快速发现问题（任一失败立即停止）

## 设计决策

### 为什么需要人工审批？

```groovy
stage('Approval - Terraform Apply') {
    steps {
        input message: 'Review the Terraform plan above. Proceed with apply?',
              ok: 'Apply'
    }
}
```

**原因**：
1. **安全**：避免误删生产资源
2. **审查**：Plan 输出需要人工确认
3. **可控**：允许在任何时候停止

**适用场景**：
- 生产环境（必须）
- 开发/学习环境（可选）

### 敏感文件的清理

```groovy
post {
    always {
        sh 'rm -f $ANSIBLE_VAULT_PASSWORD_FILE'
        sh 'rm -f terraform/proxmox/secrets.auto.tfvars'
    }
}
```

**放在 `always` 块**：无论成功失败都执行，确保敏感文件不残留。

### 为什么把 Vault 密码写成文件？

```groovy
withCredentials([string(credentialsId: 'ansible-vault-password', variable: 'VAULT_PASS')]) {
    sh '''
        echo "$VAULT_PASS" > $ANSIBLE_VAULT_PASSWORD_FILE
        chmod 600 $ANSIBLE_VAULT_PASSWORD_FILE
    '''
}
```

**原因**：
- `get-secrets.sh` 脚本需要 Ansible 解密 Vault
- Ansible 的 `ansible.cfg` 指定 `vault_password_file`
- 密码需要以文件形式存在

### Poll SCM vs Webhook

| 方式 | 优点 | 缺点 |
|------|------|------|
| **Poll SCM** | 简单、无需公网暴露 | 有延迟（轮询间隔） |
| **Webhook** | 实时触发 | 需要公网可访问 |

**选择 Poll SCM**：Jenkins 在内网，无法接收 GitHub Webhook。

配置：`H/5 * * * *`（每 5 分钟检查一次）

## Pipeline Options 详解

```groovy
options {
    buildDiscarder(logRotator(numToKeepStr: '10'))  // 只保留最近 10 个构建
    timeout(time: 30, unit: 'MINUTES')              // 30 分钟超时
    disableConcurrentBuilds()                        // 禁止并发构建
    ansiColor('xterm')                               // 启用彩色输出
}
```

### 为什么禁止并发构建？

**问题场景**：
1. Build #1 执行 `terraform plan`
2. Build #2 也执行 `terraform plan`
3. Build #1 执行 `terraform apply`
4. Build #2 的 plan 已过期，apply 可能失败或产生意外结果

**解决**：`disableConcurrentBuilds()` 确保同一时间只有一个构建运行。

### AnsiColor 插件

```groovy
options {
    ansiColor('xterm')
}
```

**效果**：
- Terraform 的彩色输出正常显示
- Ansible 的 PLAY/TASK 高亮
- 错误信息红色、成功绿色

## 踩坑记录

### 1. 脚本路径硬编码

**问题**：`refresh-terraform-state.sh` 使用硬编码路径 `/workspaces/IaC/`

**表现**：在 Jenkins 中失败，因为工作目录是 `/var/lib/jenkins/workspace/IaC-Homelab-Pipeline/`

**解决**：
```bash
# 使用相对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/terraform/proxmox"
```

### 2. Credentials 类型不匹配

**问题**：`ansible-vault-password` 用 `file()` 类型但实际是 Secret text

**表现**：`withCredentials` 块报错

**解决**：确保 Credentials 类型与使用方式匹配
- Secret text → `string()`
- Secret file → `file()`

### 3. Ansible Galaxy Collections 未安装

**问题**：每次构建都安装 Galaxy collections，耗时长

**解决**：在 Jenkins role 中预装 collections
```yaml
- name: Install Ansible Galaxy collections
  command: ansible-galaxy collection install -r requirements.yml
  args:
    chdir: /opt/IaC/ansible
```

### 4. Terraform init 在并行中失败

**问题**：多个 stage 同时运行 `terraform init` 导致锁冲突

**原因**：共享同一个 `.terraform` 目录

**解决**：
- 在 Validate 阶段先完成 init
- 后续阶段复用初始化结果
- 或使用不同的工作目录

### 5. Ansible Galaxy Collections 缺失 (community.docker)

**问题**：Pipeline 在 Ansible Lint 阶段失败
```
couldn't resolve module/action 'community.docker.docker_compose_v2'
```

**原因**：Jenkins 上没有安装 Ansible Galaxy collections

**解决**：在 Jenkinsfile Setup 阶段条件安装 collections
```groovy
dir('ansible') {
    sh '''
        if [ ! -d "collections/ansible_collections/community/docker" ] || \
           [ ! -d "collections/ansible_collections/cloud/terraform" ]; then
            echo "Installing Ansible Galaxy collections..."
            ansible-galaxy collection install -r requirements.yml -p collections
        else
            echo "Ansible collections already installed, skipping..."
        fi
    '''
}
```

**关键点**：
- 使用条件判断避免每次都安装
- 安装到项目目录 `collections/` 而非系统目录
- 在 `ansible.cfg` 中配置 `collections_path = collections:~/.ansible/collections`

### 6. Terraform Inventory 路径问题

**问题**：Ansible 无法解析动态 inventory
```
No such file or directory: '/workspaces/IaC/terraform/proxmox'
```

**原因**：`terraform.yml` 和 `terraform-esxi.yml` 使用了硬编码的绝对路径

**错误配置**：
```yaml
plugin: cloud.terraform.terraform_provider
project_path: /workspaces/IaC/terraform/proxmox
state_file: /workspaces/IaC/terraform/proxmox/terraform.tfstate
```

**正确配置**：
```yaml
plugin: cloud.terraform.terraform_provider
project_path: terraform/proxmox
```

**关键点**：
- 使用相对路径，相对于运行 ansible 命令的目录
- 只需要 `project_path`，不需要 `state_file`（插件会自动找）
- **必须从项目根目录运行 Ansible**，而不是 `ansible/` 目录

**Jenkinsfile 调整**：
```groovy
environment {
    ANSIBLE_CONFIG = "${WORKSPACE}/ansible/ansible.cfg"
    ANSIBLE_VAULT_PASSWORD_FILE = "${WORKSPACE}/ansible/.vault_pass"
}

// 从项目根目录运行，不用 dir('ansible')
sh 'ansible-playbook ansible/playbooks/deploy-jenkins.yml --tags verify'
```

### 7. Ansible 版本过低

**问题**：Jenkins 上的 Ansible 2.14.18 不支持新版 collections
```
Collection cloud.terraform does not support Ansible version 2.14.18
Collection ansible.posix does not support Ansible version 2.14.18
```

**原因**：Debian apt 仓库的 Ansible 版本太旧

**解决**：修改 Jenkins role，使用 pipx 安装最新版 Ansible
```yaml
- name: Remove old apt-installed Ansible if present
  apt:
    name:
      - ansible
      - ansible-core
    state: absent

- name: Install pipx
  apt:
    name: pipx
    state: present

- name: Install Ansible via pipx
  command: pipx install --include-deps ansible
  args:
    creates: /usr/local/bin/ansible
  environment:
    PIPX_HOME: /opt/pipx
    PIPX_BIN_DIR: /usr/local/bin
```

**结果**：Ansible 2.14.18 → 2.19.6

## 创建的文件

```
Jenkinsfile                    # Pipeline 定义
scripts/refresh-terraform-state.sh  # 修复路径问题
```

## Q&A 汇总

**Q: `checkout scm` 和 `git clone` 有什么区别？**
A: `checkout scm` 是 Jenkins 内置步骤，自动使用 Job 配置的 SCM（包括凭据），无需手动配置。

**Q: 为什么用 `terraform plan -out=tfplan`？**
A: 保存 plan 结果到文件，确保 `apply` 时执行的是你审批过的计划，而非重新计算的计划。

**Q: input 步骤会阻塞 executor 吗？**
A: 是的。如果 executor 资源紧张，可以用 `agent none` + 指定 agent 的方式释放资源。

**Q: 如何跳过审批？**
A: 
1. 删除 `input` 步骤（不推荐生产环境）
2. 设置超时自动通过：`timeout(time: 5, unit: 'MINUTES') { input ... }`

**Q: post 块的执行顺序是什么？**
A: `always` → `success`/`failure`/`unstable` → `cleanup`

## 其他发现

### Proxmox Terraform Provider 的 tags drift 问题

**问题**：每次 `terraform plan` 都显示 tags 变化
```
- tags = " " -> null
```

**原因**：telmate/proxmox provider 的 bug
- Proxmox API 返回 `" "`（空格）表示空 tags
- 但 provider 不接受 `" "` 作为输入值（验证失败）
- 导致永久性 drift

**解决**：在 `lifecycle` 中忽略 tags
```hcl
lifecycle {
  ignore_changes = [
    tags,
  ]
}
```

**更好的方案**：迁移到 **bpg/proxmox** provider
- 更活跃的开发
- 更少的 drift 问题
- 更好的 Proxmox 8.x 支持
- 更智能的 in-place 更新

## 进阶：未来改进方向

1. **通知集成**：失败时发送 Slack/邮件通知
2. **分支策略**：master 走完整流程，feature 分支只验证
3. **Artifact 归档**：保存 terraform plan 输出
4. **动态 Playbook 选择**：根据变更的文件决定运行哪些 playbook
5. **环境分离**：dev/staging/prod 不同的审批策略
6. **迁移到 bpg/proxmox provider**：解决 telmate provider 的各种 drift 问题
