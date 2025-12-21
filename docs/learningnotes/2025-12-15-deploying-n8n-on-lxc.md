# n8n Deployment on Proxmox LXC (npm method)

**日期**: 2025-12-15
**标签**: #n8n #lxc #proxmox #ansible #terraform #nodejs

## 背景
本次任务的目标是在 Proxmox VE 上部署 n8n 工作流自动化工具。选择了 LXC 容器作为运行环境，并使用 npm 方式安装 n8n。

## 核心概念

### LXC (Linux Containers)
一种轻量级的虚拟化技术，允许在单一 Linux 内核上运行多个隔离的 Linux 系统（容器）。相比 VM，LXC 启动更快，资源占用更少。

### TurnKey Linux Templates
Proxmox 支持使用 TurnKey Linux 模板快速创建特定用途的容器。
- **TurnKey Node.js**: 预装了 Node.js、NPM 和相关工具的 Debian 系统。
- **坑点**: TurnKey 模板通常将 Node.js 安装在 `/usr/local/bin`。如果后续尝试通过 `apt` 安装新版本 Node.js（安装在 `/usr/bin`），会因为 PATH 优先级问题导致系统继续使用旧版本。

### n8n
一个可扩展的工作流自动化工具。
- **安装方式**: Docker (官方推荐) vs npm (原生运行)。本次使用 npm 方式在 LXC 中原生运行。
- **依赖**: 需要 Node.js v18.17+ 或 v20.x。

## 实施步骤

### 1. 基础设施 (Terraform)
使用 `proxmox-lxc` 模块创建容器。
关键配置：
- **Template**: `local:vztmpl/debian-12-turnkey-nodejs_18.0-1_amd64.tar.gz`
- **Resource**: 2 vCPU, 2GB RAM (n8n 比较吃内存，建议 1GB 起步)

### 2. 配置管理 (Ansible)

#### Node.js 版本冲突解决
TurnKey 模板自带的 Node.js (v20.9.0) 版本较旧，不满足 n8n v20.19+ 的需求。
**解决方案**:
1.  强制删除手动安装的旧版本: `/usr/local/bin/node`, `/usr/local/bin/npm`。
2.  通过 NodeSource 仓库安装最新的 LTS 版本 (`apt install nodejs`)。

#### Ansible `file` 模块与循环
用于批量删除文件：
```yaml
- name: Remove manual Node.js installation
  file:
    path: "{{ item }}"
    state: absent
  with_items:
    - /usr/local/bin/node
    - ...
```

#### npm 全局安装
```yaml
- name: Install n8n globally
  npm:
    name: n8n
    global: yes
```

#### Systemd 服务
为了让 n8n 在后台运行并开机自启，创建了 `/etc/systemd/system/n8n.service`。
- **ExecStart**: 指向 `/usr/bin/n8n start`。
- **Environment**:
    - `N8N_SECURE_COOKIE=false`: 允许通过 IP (HTTP) 访问服务。
    - `N8N_ENCRYPTION_KEY`: **不设置**。让 n8n 自动生成并在 `/root/.n8n/config` 中管理密钥。如果在环境变量中设置了该值，必须确保在此后一直保持一致，否则会导致无法解密旧数据而启动失败。
- **User**: 使用 `root` (LXC 默认)。

## 遇到的问题与排查
1.  **Node.js 版本不更新**: `apt upgrade` 后 `node -v` 依然显示旧版本。
    - **原因**: `/usr/local/bin` 优先级高于 `/usr/bin`。
    - **解决**: 删除 `/usr/local/bin` 下的冲突文件。
2.  **服务启动失败 (203/EXEC)**: `ExecStart` 路径错误。
    - **排查**: 使用 `which n8n` 确认实际路径。
    - **解决**: 将服务文件中的路径从 `/usr/local/bin/n8n` 修正为 `/usr/bin/n8n`。
3.  **Ansible Debug 输出格式**:
    - **问题**: `msg` 传入列表时，通过 Python 列表格式打印 `['line1', 'line2']`。
    - **解决**: 使用 YAML 多行字符串语法 (`|`)。

## 参考资料
- [n8n npm Installation Guide](https://docs.n8n.io/hosting/installation/npm/)
- [Ansible npm Module](https://docs.ansible.com/ansible/latest/collections/community/general/npm_module.html)
