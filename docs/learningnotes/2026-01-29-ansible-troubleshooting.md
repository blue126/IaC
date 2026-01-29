# 学习笔记：Ansible 踩坑记录 (Callback, Dependencies, Command Check)

**日期**: 2026-01-29
**标签**: #Ansible #Troubleshooting #DevOps #BestPractices

在本次部署中，我们遇到并解决了三个具有代表性的 Ansible 技术问题。

## 1. Ansible 输出格式的演变 (Stdout Callback)

**问题描述**: 我们希望 Ansible 的输出能像 YAML 一样整洁（处理多行字符串），而不是挤成一坨的 JSON。
**报错**: `The 'community.general.yaml' callback plugin has been removed.`

### 原因分析
在旧版本 Ansible 中，我们通常设置 `stdout_callback = yaml`。这实际上是调用了 `community.general` 集合里的插件。但从 Ansible Core 2.13 起，官方决定清理这些外部插件，转而增强内置的 `default` 插件。

### 解决方案
现代 Ansible (Core 2.13+) 的标准配置方式是：
1.  **使用默认插件**: `stdout_callback = default` (或者不写)。
2.  **在 `[defaults]` 区域配置参数**: 注意！虽然它是插件配置，但对于 `default` 插件，它的配置键直接位于 `[defaults]` 节下（这是最坑的地方）。

```ini
[defaults]
stdout_callback = default
callback_result_format = yaml  # <--- 正确位置：直接在 defaults 下
# bin_ansible_callbacks = True # 推荐开启，允许 ad-hoc 命令也使用此回调
```

**对比**: 普通插件通常使用 `[callback_<name>]` 节，但 `default` 是特例。

## 2. DevContainer 环境下的依赖缺失

**问题描述**:
1.  `deploy-caddy` 失败，提示缺 `passlib`。
2.  `install-tailscale` 失败，提示缺 `ansible.posix.sysctl`。

### 原因分析
我们的开发环境是 **DevContainer** (基于 Docker 的干净环境)。
*   **Passlib**: Ansible 的 `password_hash` 过滤器（用于生成 Caddy WebDAV 密码）依赖 Python 的 `passlib` 库。它不是 Ansible Core 的一部分。
*   **Ansible.Posix**: `sysctl` 模块被移出了 Ansible Core，放入了 `ansible.posix` 集合中。

### 教训
**Infrastructure as Code (IaC) 的环境必须是可复制的。**
我们不能假设环境里“正好有”这些包。必须显式声明：
*   Python 库 -> `requirements.txt`
*   Ansible 集合 -> `requirements.yml`

## 3. 优雅地检测命令是否存在

**问题描述**: 我们想检测机器上是否装了 Tailscale。
*   **错误做法**: `command: tailscale --version`
    *   后果: 如果没装，Ansible 会尝试执行二进制文件，结果系统报 "No such file or directory"，导致 Python 抛出异常 (Traceback)，非常难看且吓人。
*   **正确做法**: `shell: command -v tailscale`
    *   后果: 这是标准的 Shell 检测。如果没装，Shell 返回非零退出码 (RC=1)。Ansible 捕获这个退出码，配合 `ignore_errors: true`，可以优雅地跳过，没有任何报错杂音。

```yaml
- name: Check if Tailscale is installed
  shell: command -v tailscale
  register: check_result
  ignore_errors: true
  changed_when: false
```
