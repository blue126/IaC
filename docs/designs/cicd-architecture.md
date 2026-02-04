# CI/CD 架构设计文档

> Homelab Infrastructure as Code 项目的持续集成/持续部署架构

## 概述

本项目采用 **Jenkins + Terraform + Ansible** 的 CI/CD 架构，实现从代码提交到基础设施部署的自动化流程。

## 痛点分析

### 引入 CI/CD 之前的问题

在引入 CI/CD 之前，部署流程完全手动，存在以下痛点：

#### 1. 两阶段手动执行

```
# 手动流程 (之前)
cd terraform/proxmox
terraform plan
terraform apply          # 等待完成...

cd ../../ansible
ansible-playbook playbooks/deploy-xxx.yml   # 又要等待...
```

**问题**:
- 需要手动切换目录、执行两次命令
- 容易忘记执行 Ansible 配置
- 基础设施创建了但服务没配置

#### 2. 验证步骤容易遗漏

**问题**:
- 忘记运行 `terraform validate`
- 忘记运行 `ansible-playbook --syntax-check`
- 代码有语法错误但直接 apply 导致失败

#### 3. 敏感信息管理分散

**之前的状态**:
- Terraform 变量手动复制粘贴
- 每次换环境要重新配置
- 敏感信息可能意外提交到 Git

#### 4. 缺乏变更审计

**问题**:
- 不知道谁在什么时候做了什么变更
- 没有变更前的审批机制
- 出问题难以追溯

#### 5. Inventory 同步问题

**问题**:
- Terraform 创建了新 VM，但 Ansible inventory 没更新
- 手动维护静态 inventory 容易出错
- IP 地址变更后 inventory 不同步

### CI/CD 解决方案

| 痛点 | 解决方案 |
|------|----------|
| 两阶段手动执行 | Pipeline 自动串联 Terraform → Ansible |
| 验证步骤遗漏 | Validate 阶段强制执行所有检查 |
| 敏感信息分散 | Ansible Vault 统一管理，动态注入 |
| 缺乏变更审计 | Jenkins 构建历史 + 人工审批节点 |
| Inventory 同步 | 动态 Inventory 从 Terraform State 生成 |

## 设计目标

1. **自动化** - Git push 触发自动验证和部署
2. **安全** - 敏感信息集中管理，构建过程中动态注入
3. **可审计** - 人工审批节点，完整的构建日志
4. **幂等性** - 多次执行结果一致
5. **学习导向** - 适合个人 homelab 学习实践

### 技术栈

| 组件 | 用途 | 版本 |
|------|------|------|
| Jenkins | CI/CD 引擎 | LTS |
| Terraform | 基础设施即代码 | 1.14.x |
| Ansible | 配置管理 | 2.19.x |
| HCP Terraform Cloud | 远程状态存储 | - |
| GitHub | 代码仓库 | - |

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GitHub Repository                               │
│                         (IaC - Infrastructure as Code)                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ Poll SCM (每5分钟)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Jenkins Server (LXC)                               │
│                          192.168.1.107:8080                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Jenkins Pipeline                             │    │
│  │  ┌──────────┐  ┌───────┐  ┌───────┐  ┌──────────┐  ┌────────┐      │    │
│  │  │ Checkout │→ │ Check │→ │ Setup │→ │ Validate │→ │  Plan  │      │    │
│  │  └──────────┘  └───┬───┘  └───────┘  └──────────┘  └────┬───┘      │    │
│  │                     │                                     │          │    │
│  │              非IaC变更?                                   ▼          │    │
│  │              跳过构建  ┌────────┐ ┌───────┐ ┌────────┐ ┌────────┐   │    │
│  │              (NOT_BUILT)│  Apply │←│Refresh│←│ Deploy │←│Approval│   │    │
│  │                        └────────┘ └───────┘ └────────┘ └────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐                         │
│  │    Terraform CLI     │  │     Ansible CLI      │                         │
│  │    (已安装)          │  │     (已安装)         │                         │
│  └──────────────────────┘  └──────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │
         │ API                          │ SSH
         ▼                              ▼
┌─────────────────────┐    ┌─────────────────────────────────────────────────┐
│  HCP Terraform      │    │              Proxmox Cluster                     │
│  Cloud              │    │  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│  ┌───────────────┐  │    │  │  pve0   │  │  pve1   │  │  pve2   │          │
│  │ Remote State  │  │    │  │         │  │         │  │         │          │
│  │ (tfstate)     │  │    │  │ VMs:    │  │         │  │         │          │
│  └───────────────┘  │    │  │ -immich │  │         │  │         │          │
│                     │    │  │ -netbox │  │         │  │         │          │
│  ┌───────────────┐  │    │  │ -rustdsk│  │         │  │         │          │
│  │ Plan/Apply    │  │    │  │         │  │         │  │         │          │
│  │ Execution     │  │    │  │ LXCs:   │  │         │  │         │          │
│  └───────────────┘  │    │  │ -anki   │  │         │  │         │          │
└─────────────────────┘    │  │ -caddy  │  │         │  │         │          │
                           │  │ -homepg │  │         │  │         │          │
                           │  │ -jenkins│  │         │  │         │          │
                           │  │ -n8n    │  │         │  │         │          │
                           │  └─────────┘  └─────────┘  └─────────┘          │
                           └─────────────────────────────────────────────────┘
```

### 组件说明

#### Jenkins Server

- **部署方式**: Proxmox LXC 容器 (Debian 12)
- **资源配置**: 2 核 CPU, 2GB 内存, 16GB 存储
- **网络**: 192.168.1.107 (静态 IP)
- **VMID**: 107 (与 IP 最后一位对应)

**预装工具**:
- Jenkins LTS
- OpenJDK 17
- Terraform CLI
- Ansible (via pipx)
- Ansible Galaxy Collections

#### HCP Terraform Cloud

- **用途**: 远程状态存储和锁定
- **组织**: homelab-roseville
- **工作区**: 按环境/用途划分
- **认证**: API Token (存储在 Jenkins Credentials)

## Pipeline 详细设计

### 流程图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           Pipeline Stages                                   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────┐                                                              │
│  │ Checkout │  从 GitHub 拉取最新代码                                       │
│  └────┬─────┘                                                              │
│       │                                                                    │
│       ▼                                                                    │
│  ┌──────────────┐  检查变更文件路径                                         │
│  │Check Changes │  terraform/ ansible/ scripts/ Jenkinsfile → 继续         │
│  │              │  docs/ 等其他路径 → 跳过构建 (NOT_BUILT)                  │
│  └──────┬───────┘                                                          │
│         │                                                                  │
│         ▼ (仅当有 IaC 变更)                                                │
│  ┌──────────┐  1. 写入 Vault 密码文件                                       │
│  │  Setup   │  2. 执行 get-secrets.sh 生成 tfvars                          │
│  │          │  3. 条件安装 Ansible Galaxy Collections                       │
│  └────┬─────┘                                                              │
│       │                                                                    │
│       ▼                                                                    │
│  ┌──────────────────────────────────────┐                                  │
│  │           Validate (并行)            │                                  │
│  │  ┌─────────────────┐ ┌─────────────┐ │                                  │
│  │  │Terraform Validate│ │ Ansible Lint│ │                                  │
│  │  │ - init          │ │ - syntax    │ │                                  │
│  │  │ - validate      │ │   check     │ │                                  │
│  │  │ - fmt check     │ │             │ │                                  │
│  │  └─────────────────┘ └─────────────┘ │                                  │
│  └────────────┬─────────────────────────┘                                  │
│               │                                                            │
│               ▼                                                            │
│  ┌────────────────┐                                                        │
│  │ Terraform Plan │  生成执行计划，保存到 tfplan 文件                        │
│  └───────┬────────┘                                                        │
│          │                                                                 │
│          ▼                                                                 │
│  ┌────────────────┐                                                        │
│  │   Approval 1   │  人工审批: 确认 Terraform Plan                          │
│  │  (Manual Gate) │                                                        │
│  └───────┬────────┘                                                        │
│          │                                                                 │
│          ▼                                                                 │
│  ┌─────────────────┐                                                       │
│  │ Terraform Apply │  执行基础设施变更                                       │
│  └───────┬─────────┘                                                       │
│          │                                                                 │
│          ▼                                                                 │
│  ┌───────────────────┐                                                     │
│  │ Refresh Inventory │  从 Terraform Cloud 拉取最新 state                   │
│  │                   │  更新 Ansible 动态 Inventory                         │
│  └───────┬───────────┘                                                     │
│          │                                                                 │
│          ▼                                                                 │
│  ┌────────────────┐                                                        │
│  │   Approval 2   │  人工审批: 确认进行 Ansible 部署                         │
│  │  (Manual Gate) │                                                        │
│  └───────┬────────┘                                                        │
│          │                                                                 │
│          ▼                                                                 │
│  ┌────────────────┐                                                        │
│  │ Ansible Deploy │  执行配置管理和应用部署                                  │
│  └───────┬────────┘                                                        │
│          │                                                                 │
│          ▼                                                                 │
│  ┌────────────────┐                                                        │
│  │    Cleanup     │  清理敏感文件 (vault密码, tfvars)                        │
│  │   (post块)     │                                                        │
│  └────────────────┘                                                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 阶段详解

#### 1. Checkout

```groovy
stage('Checkout') {
    steps {
        checkout scm
    }
}
```

- 使用 Jenkins 内置 SCM 配置
- 自动使用 Deploy Key 认证
- 拉取触发构建的 commit

#### 2. Check Changes (路径过滤)

```groovy
stage('Check Changes') {
    steps {
        script {
            def changes = sh(script: 'git diff --name-only HEAD~1 HEAD', returnStdout: true).trim()
            def buildPaths = ['terraform/', 'ansible/', 'scripts/', 'Jenkinsfile']
            env.SHOULD_BUILD = 'false'
            for (path in buildPaths) {
                if (changes.split('\n').any { it.startsWith(path) }) {
                    env.SHOULD_BUILD = 'true'
                    break
                }
            }
        }
    }
}
```

检查本次 commit 变更的文件路径，只有以下路径的变更才触发构建：

| 路径 | 触发构建 | 原因 |
|------|----------|------|
| `terraform/**` | ✓ | 基础设施变更 |
| `ansible/**` | ✓ | 配置管理变更 |
| `scripts/**` | ✓ | 辅助脚本变更 |
| `Jenkinsfile` | ✓ | Pipeline 本身变更 |
| `docs/**` | ✗ | 文档变更，无需部署 |
| `.github/**` | ✗ | 仓库配置，无需部署 |
| `AGENTS.md` 等 | ✗ | 项目说明，无需部署 |

不触发构建时，后续所有阶段通过 `when { environment name: 'SHOULD_BUILD', value: 'true' }` 条件跳过，构建状态标记为 `NOT_BUILT`。

#### 3. Setup (条件执行)

```groovy
stage('Setup') {
    steps {
        // 1. 写入 Vault 密码
        withCredentials([string(credentialsId: 'ansible-vault-password', variable: 'VAULT_PASS')]) {
            sh '''
                echo "$VAULT_PASS" > $ANSIBLE_VAULT_PASSWORD_FILE
                chmod 600 $ANSIBLE_VAULT_PASSWORD_FILE
            '''
        }
        // 2. 生成 Terraform secrets
        sh './scripts/get-secrets.sh'
        // 3. 条件安装 Collections
        dir('ansible') {
            sh '''
                if [ ! -d "collections/..." ]; then
                    ansible-galaxy collection install -r requirements.yml -p collections
                fi
            '''
        }
    }
}
```

**关键操作**:
1. 从 Jenkins Credentials 获取 Vault 密码，写入临时文件
2. 执行 `get-secrets.sh` 解密 Vault，生成 `secrets.auto.tfvars`
3. 检查并安装 Ansible Galaxy Collections (仅首次)

#### 4. Validate (并行)

```groovy
stage('Validate') {
    parallel {
        stage('Terraform Validate') {
            steps {
                dir('terraform/proxmox') {
                    sh 'terraform init -input=false'
                    sh 'terraform validate'
                    sh 'terraform fmt -check -recursive || echo "Warning"'
                }
            }
        }
        stage('Ansible Lint') {
            steps {
                sh 'ansible-playbook ansible/playbooks/*.yml --syntax-check'
            }
        }
    }
}
```

**并行执行**:
- Terraform: 初始化、语法验证、格式检查
- Ansible: 所有 playbook 语法检查

#### 5. Terraform Plan

```groovy
stage('Terraform Plan') {
    steps {
        dir('terraform/proxmox') {
            sh 'terraform plan -out=tfplan -input=false'
        }
    }
}
```

- 生成执行计划
- 保存到 `tfplan` 文件确保 apply 执行的是审批过的计划

#### 6. Approval Gates

```groovy
stage('Approval - Terraform Apply') {
    steps {
        input message: 'Review the Terraform plan above. Proceed with apply?',
              ok: 'Apply'
    }
}
```

**两个审批点**:
1. **Terraform Apply 前** - 审核基础设施变更
2. **Ansible Deploy 前** - 确认进行配置部署

#### 7. Terraform Apply

```groovy
stage('Terraform Apply') {
    steps {
        dir('terraform/proxmox') {
            sh 'terraform apply -input=false tfplan'
        }
    }
}
```

- 执行之前保存的 plan
- 创建/更新/删除基础设施资源

#### 8. Refresh Inventory

```groovy
stage('Refresh Inventory') {
    steps {
        sh './scripts/refresh_terraform_state.sh'
    }
}
```

- 从 Terraform Cloud 拉取最新 state
- 保存到本地供 Ansible 动态 inventory 使用

#### 9. Ansible Deploy

```groovy
stage('Ansible Deploy') {
    steps {
        sh 'ansible-playbook ansible/playbooks/deploy-jenkins.yml --tags verify'
    }
}
```

- 执行配置管理
- 部署应用和服务

#### 10. Cleanup (post)

```groovy
post {
    always {
        sh 'rm -f $ANSIBLE_VAULT_PASSWORD_FILE'
        sh 'rm -f terraform/proxmox/secrets.auto.tfvars'
        sh 'rm -f terraform/oci/secrets.auto.tfvars'
    }
}
```

- 无论成功失败都执行
- 清理敏感文件

## 凭据管理

### Jenkins Credentials

| Credential ID | 类型 | 用途 |
|---------------|------|------|
| `github-ssh-key` | SSH Private Key | GitHub Deploy Key，克隆仓库 |
| `terraform-cloud-token` | Secret Text | HCP Terraform Cloud API Token |
| `ansible-vault-password` | Secret Text | Ansible Vault 解密密码 |

### 凭据流转图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Credentials Flow                                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  Jenkins Credentials │
│  (安全存储)          │
└──────────┬───────────┘
           │
           ├─────────────────────────────────────────────────────┐
           │                                                     │
           ▼                                                     ▼
┌──────────────────────┐                          ┌──────────────────────────┐
│ ansible-vault-password│                          │ terraform-cloud-token    │
│                      │                          │                          │
│ 写入临时文件:        │                          │ 设为环境变量:            │
│ $WORKSPACE/ansible/  │                          │ TF_TOKEN_app_terraform_io│
│ .vault_pass          │                          │                          │
└──────────┬───────────┘                          └────────────┬─────────────┘
           │                                                   │
           ▼                                                   │
┌──────────────────────┐                                       │
│   get-secrets.sh     │                                       │
│                      │                                       │
│ 解密 Ansible Vault   │                                       │
│ 生成 secrets.auto.   │                                       │
│ tfvars               │                                       │
└──────────┬───────────┘                                       │
           │                                                   │
           ▼                                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          Terraform                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ 读取变量:                                                           │ │
│  │ - terraform.auto.tfvars (非敏感, 已提交)                             │ │
│  │ - secrets.auto.tfvars (敏感, 动态生成)                               │ │
│  │                                                                      │ │
│  │ 认证 Terraform Cloud:                                                │ │
│  │ - 使用 TF_TOKEN_app_terraform_io 环境变量                            │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                       Pipeline 结束时清理                                 │
│  - rm -f $ANSIBLE_VAULT_PASSWORD_FILE                                    │
│  - rm -f terraform/proxmox/secrets.auto.tfvars                           │
│  - rm -f terraform/oci/secrets.auto.tfvars                               │
└──────────────────────────────────────────────────────────────────────────┘
```

### 敏感信息存储位置

| 信息类型 | 存储位置 | 访问方式 |
|----------|----------|----------|
| Proxmox API 凭据 | Ansible Vault | get-secrets.sh 提取 |
| Tailscale Auth Key | Ansible Vault | Ansible 直接使用 |
| Terraform Cloud Token | Jenkins Credentials | 环境变量注入 |
| GitHub Deploy Key | Jenkins Credentials + GitHub | SSH 认证 |
| Vault 密码 | Jenkins Credentials | 临时文件 |

## 动态 Inventory

### 架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Ansible Dynamic Inventory                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  HCP Terraform Cloud │
│  ┌────────────────┐  │
│  │  Remote State  │  │
│  │  (tfstate)     │  │
│  └───────┬────────┘  │
└──────────┼───────────┘
           │
           │ terraform state pull
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  terraform/proxmox/terraform.tfstate (本地缓存)                          │
│                                                                          │
│  包含 ansible_host 资源:                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ resource "ansible_host" "jenkins" {                                │ │
│  │   name   = "jenkins"                                               │ │
│  │   groups = ["pve_lxc", "jenkins"]                                  │ │
│  │   variables = { ansible_host = "192.168.1.107" }                   │ │
│  │ }                                                                  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
           │
           │ cloud.terraform.terraform_provider plugin
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ansible/inventory/terraform.yml                                         │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ plugin: cloud.terraform.terraform_provider                         │ │
│  │ project_path: terraform/proxmox                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
           │
           │ ansible-inventory --list
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Generated Inventory                                                     │
│                                                                          │
│  @all:                                                                   │
│    |--@pve_lxc:                                                          │
│    |  |--anki     (192.168.1.100)                                        │
│    |  |--caddy    (192.168.1.105)                                        │
│    |  |--homepage (192.168.1.103)                                        │
│    |  |--jenkins  (192.168.1.107)                                        │
│    |  |--n8n      (192.168.1.106)                                        │
│    |--@pve_vms:                                                          │
│    |  |--immich   (192.168.1.101)                                        │
│    |  |--netbox   (192.168.1.104)                                        │
│    |  |--rustdesk (192.168.1.102)                                        │
│    |--@jenkins:                                                          │
│    |  |--jenkins                                                         │
│    |--@proxmox_cluster:                                                  │
│    |  |--pve0, pve1, pve2                                                │
└──────────────────────────────────────────────────────────────────────────┘
```

### Inventory 文件结构

```
ansible/inventory/
├── terraform.yml           # Proxmox 动态 inventory (Terraform state)
├── terraform-esxi.yml      # ESXi 动态 inventory
├── group_vars/
│   ├── all/
│   │   ├── main.yml       # 全局变量
│   │   └── vault.yml      # 加密的敏感变量
│   ├── pve_lxc.yml        # LXC 组变量
│   └── pve_vms.yml        # VM 组变量
└── host_vars/
    ├── homepage.yml       # 主机特定变量
    └── ...
```

## 触发机制

### Poll SCM

```groovy
// Jenkins Job 配置
triggers {
    pollSCM('H/5 * * * *')  // 每 5 分钟检查一次
}
```

**选择 Poll SCM 而非 Webhook 的原因**:
- Jenkins 部署在内网，无法接收外部 Webhook
- 不需要暴露 Jenkins 到公网
- 5 分钟延迟对于 homelab 场景可接受

### 触发条件

| 条件 | 是否触发 |
|------|----------|
| Push to master | 是 |
| Push to feature branch | 否 (可配置) |
| PR merge | 是 |
| 手动 Build Now | 是 |

## 安全设计

### 最小权限原则

| 组件 | 权限范围 |
|------|----------|
| GitHub Deploy Key | 仅限 IaC 仓库，只读或读写 |
| Terraform Cloud Token | 限定 workspace |
| Proxmox API Token | 限定必要的 VM/LXC 操作权限 |
| Ansible SSH Key | 仅限目标主机 |

### 敏感信息保护

1. **不提交敏感信息到 Git**
   - `secrets.auto.tfvars` 在 `.gitignore`
   - `.vault_pass` 在 `.gitignore`
   - 使用 Ansible Vault 加密

2. **构建时动态生成**
   - Vault 密码从 Jenkins Credentials 注入
   - tfvars 由 get-secrets.sh 动态生成

3. **构建后清理**
   - post.always 块清理所有敏感文件
   - 即使构建失败也会执行

### 审批机制

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         Approval Flow                                       │
└────────────────────────────────────────────────────────────────────────────┘

  Terraform Plan
       │
       ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                      Plan Output (Console)                              │
  │  ┌───────────────────────────────────────────────────────────────────┐ │
  │  │ # module.jenkins.proxmox_lxc.lxc will be created                  │ │
  │  │ + resource "proxmox_lxc" "lxc" {                                  │ │
  │  │     + hostname = "jenkins"                                        │ │
  │  │     + memory   = 2048                                             │ │
  │  │     ...                                                           │ │
  │  │ }                                                                 │ │
  │  │                                                                   │ │
  │  │ Plan: 1 to add, 0 to change, 0 to destroy.                       │ │
  │  └───────────────────────────────────────────────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                      Manual Approval                                    │
  │  ┌───────────────────────────────────────────────────────────────────┐ │
  │  │ Review the Terraform plan above. Proceed with apply?              │ │
  │  │                                                                   │ │
  │  │                    [Apply]  [Abort]                               │ │
  │  └───────────────────────────────────────────────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────────────┘
       │
       ├──────────────── Abort ──────────────► Pipeline 终止
       │
       ▼ Apply
  Terraform Apply
```

## 错误处理

### 失败场景处理

| 阶段 | 失败原因 | 处理方式 |
|------|----------|----------|
| Checkout | 网络问题/认证失败 | 自动重试，检查 Deploy Key |
| Setup | Vault 密码错误 | Pipeline 失败，检查 Credentials |
| Validate | 语法错误 | Pipeline 失败，修复代码后重新触发 |
| Plan | Provider 配置错误 | Pipeline 失败，检查 tfvars |
| Apply | 资源冲突/API 错误 | Pipeline 失败，需人工干预 |
| Ansible | SSH 连接失败 | Pipeline 失败，检查网络/密钥 |

### 回滚策略

1. **Terraform 回滚**
   - Revert Git commit
   - 重新运行 Pipeline
   - Terraform 会自动计算差异并回滚

2. **Ansible 回滚**
   - 大部分操作幂等，重新运行即可
   - 复杂回滚需要专门的回滚 playbook

## 监控与日志

### Jenkins 日志

- 每个构建保留完整 console output
- 保留最近 10 个构建 (`buildDiscarder`)
- 支持 AnsiColor 彩色输出

### 构建超时

```groovy
options {
    timeout(time: 30, unit: 'MINUTES')
}
```

- 防止构建无限等待
- 审批步骤不受超时限制

## 当前局限性

### 1. 全量部署问题

**现状**: Ansible Deploy 阶段目前只运行单个 playbook 验证

**问题**: 
- 无法根据代码变更智能选择要运行的 playbook
- 全量运行所有 playbook 耗时长
- 无关服务也会被重新配置

### 2. 审批阻塞

**现状**: 两个人工审批节点

**问题**:
- 审批期间占用 Jenkins executor
- 无人审批时 Pipeline 一直等待
- 不适合频繁部署场景

### 3. 单一环境

**现状**: 只有 production 环境

**问题**:
- 无法在 staging 环境先验证
- 变更直接影响生产服务
- 缺乏蓝绿部署能力

### 4. 缺乏通知

**现状**: 只有 Jenkins Web UI 查看结果

**问题**:
- 构建失败无主动通知
- 需要人工检查构建状态
- 容易错过失败的部署

### 5. Terraform Provider 限制

**现状**: 使用 telmate/proxmox provider

**问题**:
- 存在 tags drift 等 bug
- 小改动容易触发资源重建
- 维护不够活跃

## 未来改进

### 短期改进 (1-2 周)

#### 1. 构建通知

**目标**: 构建完成/失败时自动通知

**方案**: 
```groovy
post {
    failure {
        // 发送 Telegram/Slack 通知
        sh 'curl -X POST ...'
    }
}
```

**优先级**: 高 - 解决无人值守时的感知问题

#### 2. Terraform Provider 迁移

**目标**: 从 telmate/proxmox 迁移到 bpg/proxmox

**收益**:
- 解决 tags drift 问题
- 更好的 in-place 更新
- 更活跃的社区支持

**详细计划**: 见 `docs/improvement/proxmox-provider-migration.md`

**优先级**: 高 - 影响日常使用体验

#### 3. Plan 输出归档

**目标**: 保存每次构建的 Terraform plan 输出

**方案**:
```groovy
stage('Terraform Plan') {
    steps {
        sh 'terraform plan -out=tfplan | tee plan-output.txt'
        archiveArtifacts artifacts: 'plan-output.txt'
    }
}
```

**优先级**: 中 - 便于审计和回顾

### 中期改进 (1-3 月)

#### 1. 智能 Playbook 选择

**目标**: 根据 Git 变更自动选择要运行的 playbook

**方案**:
```groovy
stage('Detect Changes') {
    steps {
        script {
            def changes = sh(script: 'git diff --name-only HEAD~1', returnStdout: true)
            if (changes.contains('ansible/roles/jenkins/')) {
                env.RUN_JENKINS = 'true'
            }
            if (changes.contains('ansible/roles/netbox/')) {
                env.RUN_NETBOX = 'true'
            }
        }
    }
}

stage('Ansible Deploy') {
    steps {
        script {
            if (env.RUN_JENKINS == 'true') {
                sh 'ansible-playbook ansible/playbooks/deploy-jenkins.yml'
            }
            if (env.RUN_NETBOX == 'true') {
                sh 'ansible-playbook ansible/playbooks/deploy-netbox.yml'
            }
        }
    }
}
```

**优先级**: 中 - 减少不必要的部署时间

#### 2. 分支策略

**目标**: 不同分支不同的 Pipeline 行为

**方案**:
| 分支 | Validate | Plan | Apply | Ansible |
|------|----------|------|-------|---------|
| feature/* | ✓ | ✓ | ✗ | ✗ |
| develop | ✓ | ✓ | ✓ (自动) | ✓ (staging) |
| master | ✓ | ✓ | ✓ (审批) | ✓ (production) |

```groovy
stage('Terraform Apply') {
    when {
        anyOf {
            branch 'master'
            branch 'develop'
        }
    }
    steps {
        // ...
    }
}
```

**优先级**: 中 - 需要先建立 staging 环境

#### 3. 审批超时自动处理

**目标**: 审批超时后自动取消或自动通过

**方案**:
```groovy
stage('Approval') {
    options {
        timeout(time: 4, unit: 'HOURS')
    }
    steps {
        script {
            try {
                input message: 'Proceed?'
            } catch (err) {
                // 超时处理
                currentBuild.result = 'ABORTED'
            }
        }
    }
}
```

**优先级**: 低 - homelab 场景不紧急

#### 4. 并行 Ansible 执行

**目标**: 多个独立服务并行部署

**方案**:
```groovy
stage('Ansible Deploy') {
    parallel {
        stage('Deploy Jenkins') {
            steps { sh 'ansible-playbook deploy-jenkins.yml' }
        }
        stage('Deploy Netbox') {
            steps { sh 'ansible-playbook deploy-netbox.yml' }
        }
    }
}
```

**优先级**: 低 - 当前服务数量不多

### 长期改进 (3-6 月)

#### 1. GitOps 架构

**目标**: 引入 GitOps 工具实现声明式部署

**候选方案**:
- **ArgoCD**: Kubernetes 原生，功能强大
- **Flux**: 轻量，与 Git 集成好

**考虑因素**:
- 需要先有 Kubernetes 集群
- 学习曲线较陡
- 可能过度工程化 for homelab

**优先级**: 低 - 需要评估是否必要

#### 2. 基础设施测试

**目标**: 自动化测试基础设施配置

**方案**:
- **Terratest**: Go 语言编写 Terraform 测试
- **InSpec**: 基础设施合规测试
- **Molecule**: Ansible role 测试

```go
// Terratest 示例
func TestProxmoxVM(t *testing.T) {
    terraformOptions := &terraform.Options{
        TerraformDir: "../terraform/proxmox",
    }
    
    defer terraform.Destroy(t, terraformOptions)
    terraform.InitAndApply(t, terraformOptions)
    
    // 验证 VM 创建成功
    vmIP := terraform.Output(t, terraformOptions, "vm_ip")
    assert.NotEmpty(t, vmIP)
}
```

**优先级**: 低 - 当前规模不需要

#### 3. 多集群支持

**目标**: 支持部署到多个 Proxmox 集群

**场景**:
- 主集群 (pve0, pve1, pve2)
- 备份集群 (远程站点)
- 测试集群

**方案**:
- Terraform workspaces
- 多个 provider 配置
- 环境变量切换

**优先级**: 低 - 取决于硬件扩展计划

#### 4. 自动回滚

**目标**: 部署失败时自动回滚到上一个稳定版本

**方案**:
```groovy
post {
    failure {
        script {
            // 获取上一个成功的 commit
            def lastGoodCommit = sh(script: 'git rev-parse HEAD~1', returnStdout: true)
            // 触发回滚 Pipeline
            build job: 'IaC-Rollback', parameters: [string(name: 'COMMIT', value: lastGoodCommit)]
        }
    }
}
```

**优先级**: 低 - 需要更成熟的发布流程

## 改进路线图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Improvement Roadmap                                  │
└─────────────────────────────────────────────────────────────────────────────┘

2026 Q1 (短期)
├── [高] 构建通知 (Telegram/Slack)
├── [高] Proxmox Provider 迁移 (telmate → bpg)
└── [中] Plan 输出归档

2026 Q2 (中期)
├── [中] 智能 Playbook 选择
├── [中] 分支策略 (feature/develop/master)
├── [低] 审批超时处理
└── [低] 并行 Ansible 执行

2026 Q3-Q4 (长期)
├── [评估] GitOps 架构
├── [评估] 基础设施测试
├── [评估] 多集群支持
└── [评估] 自动回滚

注: 优先级可能根据实际需求调整
```

## 附录

### 相关文件

```
Jenkinsfile                           # Pipeline 定义
terraform/proxmox/jenkins.tf          # Jenkins LXC 定义
ansible/roles/jenkins/                # Jenkins 配置 role
ansible/playbooks/deploy-jenkins.yml  # Jenkins 部署 playbook
scripts/get-secrets.sh                # 从 Vault 提取 secrets
scripts/refresh_terraform_state.sh    # 刷新 Terraform state
```

### 参考文档

- [Jenkins Pipeline 语法](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Terraform Cloud 文档](https://developer.hashicorp.com/terraform/cloud-docs)
- [Ansible Vault 文档](https://docs.ansible.com/ansible/latest/vault_guide/)
- [cloud.terraform Collection](https://galaxy.ansible.com/cloud/terraform)
