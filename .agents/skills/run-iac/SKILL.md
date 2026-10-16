---
name: run-iac
description: Guide IaC tasks into the repository Docker Sandbox. Use when asked to enter, start, or reuse an IaC Sandbox to run Terraform, Ansible, or repository commands. Covers direct and clone modes, credential and network boundaries, and safe plan handling; it does not define service-specific deployment steps.
---

# 在 Docker Sandbox 中运行 IaC 任务

本技能说明如何选择、进入和使用本仓库的 Docker Sandbox。具体任务的实现、验证范围和部署授权仍按用户请求及仓库 `AGENTS.md` 执行。先读 `AGENTS.md` 中的 Docker Sandbox 和凭据规则，再运行命令；不要复制旧项目或任务的 Sandbox 配置。

## 选择运行位置

先在当前 shell 检查环境：

```bash
if [[ -n "${SANDBOX_ID:-}" ]]; then
  printf 'sandbox: %s\n' "$SANDBOX_NAME"
else
  printf 'host\n'
fi
```

- 如果已经在分配给本任务的 Sandbox 中，确认 `pwd` 指向本任务工作树后直接执行命令，不要再创建嵌套 Sandbox。
- 如果从宿主机开始，先确认当前目录是分配的 task worktree，分支不是 `main` 或 `master`。TASK 使用唯一的小写 kebab-case 名称。
- 当前任务应从 task worktree 使用 direct mode。仅当 Git 必须在 Sandbox 内管理时，才从已核实的 main checkout 使用 clone mode；不要从 linked worktree 创建 clone mode。
- 开始前用 `sbx ls` 检查是否已有同名 Sandbox。只复用确认属于本任务、工作树和模式匹配的实例；对已存在实例核对其 Sandbox 名称、工作目录及端口设置，不要假定 `sbx run` 会更新旧设置。

## 进入 Sandbox

创建新的 Codex direct-mode Sandbox 时，从 task worktree 的仓库根目录运行：

```bash
sbx run --name iac-codex-TASK-direct-v130 codex . --kit ./.sandbox-kit
```

将 `TASK` 替换为唯一任务名，并使用仓库 `AGENTS.md` 指定的 Kit 版本后缀。若用户只需要在已有 Sandbox 中执行一次命令，从宿主机运行：

```bash
sbx exec --workdir "$PWD" SANDBOX_NAME bash -lc 'terraform -chdir=terraform/proxmox validate'
```

把 `SANDBOX_NAME` 和命令替换为本次任务的实际值。Ansible 命令从 `ansible/` 运行；Terraform 命令从相应的 `terraform/<environment>/` root 运行。不要在宿主机安装或运行仓库要求放在 Sandbox 内的 Terraform、Ansible 工具链。

在 Sandbox 内确认身份、目录和工具版本：

```bash
test -n "${SANDBOX_ID:-}"
pwd
terraform version
ansible-playbook --version
```

如果 `sbx exec` 无输出地挂起，先确认是否有交互式 `sbx` TUI 正占用同一实例；关闭 TUI 后再试，不要把它误判成超时或 stdin 故障。

## Homelab 网络

Sandbox 网络策略默认拒绝未匹配的访问。`.sandbox-kit/spec.yaml` 中的依赖下载 allowlist 不代表可以访问 homelab。本项目 homelab 网段为 `192.168.1.0/24`；规则只加到获准的本任务 Sandbox，不修改全局策略。

仅当任务需要访问 homelab，且该网络访问已获用户授权时，为**本任务 Sandbox**添加该网段规则：

```bash
sbx policy allow network --sandbox SANDBOX_NAME '192.168.1.0/24'
sbx policy check network --sandbox SANDBOX_NAME TARGET_HOST:PORT
```

将 `SANDBOX_NAME` 和 `TARGET_HOST:PORT` 替换成实际值。`sbx policy check` 必须返回 `allowed: true` 后才能进行相应的网络操作。遇到 HTTP 403 时先检查 Sandbox policy 和代理路径；不要仅凭状态码认定 API 凭据权限错误，也不要随意清除代理变量或尝试绕过 Sandbox 网络策略。

## 凭据

严格遵循仓库 `AGENTS.md` 的凭据装载规则。只挂载当前任务确实需要且已获准使用的凭据目录，并设为只读；OCI 凭据仅按 OCI 专项规则处理。不要把 Vault 密码、Terraform token、私钥或凭据文件复制到仓库、命令行参数、日志或终端输出。检查凭据时只输出是否可读或是否非空，不打印值。

Terraform 使用 HCP backend 时，确认 Sandbox 通过批准的只读凭据挂载取得 HCP CLI 认证，并检查当前 workspace 与 Terraform root。不要因为认证失败而执行 `terraform login`、替换 workspace 或重建 backend。

## 计划与写入

- `terraform plan`、`terraform apply` 和 Ansible 部署按用户授权及仓库规则执行。计划出现未预期资源、更新、替换或删除时停止，不要继续 apply。
- 定向导入计划应核对目标地址、import ID、资源身份、磁盘容量和所有 action；导入计划不得夹带其他资源变化。
- 若 saved plan 放在 `/dev/shm`，不要假设它会跨多个 `sbx exec` 调用保留。把 plan 与 apply 放在同一次 Sandbox 调用中，或存到 Sandbox 内权限为 `0600` 的持久路径；apply 前再次核验保存的计划。
- 导入后可运行全 workspace plan 做只读漂移审阅。该计划可能包含与本任务无关的变更；逐项审阅，绝不因为一个定向导入成功就 apply 全量计划。

## 收尾

报告 Sandbox 名称与模式、实际执行位置、验证结果、网络规则范围和未解决的计划差异。不要停止、删除或清理其他任务的 Sandbox、缓存、卷、计划文件或凭据；清理已创建资源时按仓库授权边界确认准确目标。
