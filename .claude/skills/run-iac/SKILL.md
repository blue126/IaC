---
name: run-iac
description: Run, start, and smoke-test the IaC Docker Sandbox with the repository .sandbox-kit. Use when asked to launch an IaC sandbox, verify Terraform/Ansible tooling, or 开启/验证 IaC Sandbox. Creates an isolated CLI environment; does not deploy infrastructure or start an interactive coding agent.
---

# 运行 IaC Sandbox

从**宿主任务 worktree**运行 `.claude/skills/run-iac/driver.sh`，由它创建专用 Sandbox，并通过 `sbx exec` 驱动同目录的 `smoke.sh`。以下路径均相对仓库根目录。项目没有统一的应用 GUI；此入口验证真实 Terraform/Ansible CLI，不启动交互 Agent，不需要截图。

## Run（Agent 与人工共用入口）

**先获得用户对创建 Sandbox、在其中执行 Kit 依赖安装的明确授权。** 参数只是防误触确认，不能代替用户授权。

```bash
bash .claude/skills/run-iac/driver.sh --allow-sandbox-install
```

Driver 自动生成包含任务标识与 Kit 版本的唯一名称，依次执行：

1. 确认宿主 linked worktree、非 `main`/`master` 分支及 Kit `1.3.0`。
2. 校验 Kit；用 `sbx create --kit` 创建全新 Claude 模板 Sandbox，不复用旧实例，不发布端口。
3. 在 Sandbox 的临时目录生成独立 `ansible.cfg`；验证 Terraform、Ansible、pip、Python imports 和全部 7 个必需 collections。
4. 执行 Terraform console 的本地表达式，再对 **Sandbox localhost** 执行 Ansible ping。
5. 输出 `IAC_SANDBOX_SMOKE_OK`，停止本次创建的 Sandbox。失败时保留非零退出码，也尝试停止已成功创建的实例。

成功标准：看到 `ping: pong` 对应的 JSON 输出、成功 marker、停止确认，且 driver 退出码为 `0`。仅有 `Created sandbox` 不算验证成功。

Sandbox、临时配置和检查结果保留以便诊断；脚本打印准确位置。不会自动删除 Sandbox、临时文件或旧实例，清理需另获目标明确的授权。每次完整运行都会新建一个 Sandbox；本次依赖安装实测约 2–4 分钟，网络下载时间可能变化。

## 前置条件与范围

- 已安装、已登录且 daemon 可用的 Docker Sandboxes；宿主有 Git、Bash、Python 3。本次验证环境为 **macOS arm64 + sbx v0.39.0**，guest 为 Linux arm64。没有验证从零安装宿主工具；缺少前置工具时停止并请求安装授权，不猜测安装命令。
- 当前目录必须是获分配的独立任务 worktree，分支唯一；driver 不创建分支、不提交、不推送。宿主 main checkout 只用于协调。
- 保留仓库 `.sandbox-kit`，由 Kit 安装依赖；不在宿主安装 Terraform/Ansible。Kit 版本变化后需重新验证 driver 与命名。
- 此 smoke 不读取项目 inventory，不解密 Vault，不运行 Terraform init/plan/apply，不部署任何远端主机。不需要 OCI 挂载、生产凭据或 SSH 私钥。
- 这是工具运行验证，不是所有 Agent 的交互会话、MCP 或 clone-mode 验收，也不覆盖 OpenCode Desktop。

## Test（宿主，无真实安装或 Sandbox 创建）

Driver 边界测试覆盖：缺少授权参数、嵌套 Sandbox、创建失败、exec 失败、stop 失败和成功流程；使用假的 `sbx`，不操作现有实例。

```bash
python3 .claude/skills/run-iac/test-driver.py
```

APT 测试读取 Kit 的实际 hook，用假的 apt-get/sleep 验证一次成功、短暂故障恢复及 update/install 重试耗尽；不会安装宿主软件。

```bash
python3 .sandbox-kit/tests/test-apt-retry.py
```

## 实测故障与处理

- **创建时报 apt lists lock 被占用**：sbx v0.39.0 内置模板会后台更新 APT 索引。项目 Kit 已对 update/install 增加最多 6 次重试、失败间隔 5 秒，并为 install 设置 dpkg 锁等待。耗尽重试仍失败；不删锁、不杀进程。另一次实测出现下载归档 rename 失败，不能断言它与后台 update 同源。
- **后续 ensurepip 缺失、ansible-galaxy 不存在**：首先检查此前的系统包 hook 是否失败，不要只绕过 Python 安装报错。
- **Unsupported configuration file extension for /dev/null**：Ansible 2.20.8 不接受这个配置路径。smoke 改为临时目录中真正的 `.cfg` 文件，避免加载项目 Vault 配置。
- **创建成功但 smoke 失败**：查看 driver 的实际退出码；已验证失败退出码会保留，任务 Sandbox 会停止并保留供诊断。不要把安装日志的最后一条成功信息当成整体成功。

验证记录：2026-09-06，Terraform 1.14.9、Ansible core 2.20.8、Python 3.14.4；真实 Terraform 本地表达式及 Ansible localhost ping 均通过。
