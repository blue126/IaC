# Docker Sandboxes 迁移设计

> 本文记录迁移决策与历史实施边界。当前职责模型见
> [Docker Sandbox Agent Architecture](docker-sandbox-agent-architecture.md)。

## 1. 背景与目标

本项目当前使用根目录 `.devcontainer/` 提供 Terraform、Ansible、Python、Codex、Claude Code、OpenCode 和 Playwright 工具链。该方案依赖 devcontainer CLI、Docker Desktop bind mount、宿主机 MCP Gateway、宿主机可见 Chrome，以及为 OpenCode Desktop 维护的同路径双重挂载。

迁移目标是用 Docker Sandboxes（`sbx`）完全替换本地 devcontainer 开发环境，并保留以下能力：

- Codex、Claude Code 和 OpenCode 三种 agent 均可使用。
- 用户可以在 direct mode 与 clone mode 之间自行选择。
- 多个 agent 可以使用不同 sandbox 名称并行工作。
- Terraform、Ansible、Python 和 Playwright 工具链只维护一份项目定义。
- Playwright MCP 和 Chromium 运行在 sandbox microVM 内。
- OpenCode TUI 和 OpenCode Desktop 入口均可使用。
- 密钥、Vault 密码和 OCI API 私钥的边界明确且有文档说明。

本次迁移不退役或删除任何现存 VM。历史上用于配置独立 devcontainer VM 的 Ansible playbook 将会退役，但这不表示删除基础设施资源。

## 2. 已确认的设计决策

### 2.1 使用 `sbx run` 而不是 `.sbxenv.yaml`

用户需要在命令行中直接选择 agent、sandbox 名称和 direct/clone mode。`sbx v0.39.0` 的 `sbx env run` 不支持用 CLI 参数覆盖 `agent` 和 `name`，因此不使用 `.sbxenv.yaml` 作为主入口。

标准入口为：

```bash
sbx run --name iac-codex --no-share-skills codex . --kit ./.sandbox-kit
sbx run --name iac-claude claude . --kit ./.sandbox-kit
sbx run --name iac-opencode opencode . --kit ./.sandbox-kit
```

Clone mode 在创建 sandbox 时附加 `--clone`。并行任务使用不同 `--name`。

### 2.1.1 Git 与 host worktree 边界

Docker Sandboxes 的 direct mode 从 main checkout 启动时，sandbox 内 Git 可用。从宿主
linked worktree 启动时，agent 仍可编辑文件，但 Docker 只挂载 worktree，无法解析指向
外部 common Git directory 的 `.git` pointer；sandbox 内 Git 因而不可用，Git 由宿主机
管理，且不自动挂载 common Git directory。`--clone` 必须从 main checkout 创建，不能从
linked worktree 创建；agent 在 private clone 中可使用 Git。

因此，当前 linked-worktree smoke 的 `No Git` 是预期 Docker 限制，并非迁移缺陷；正式
main checkout 验收后该现象不再出现。参见 [Docker host worktree Git 边界](https://docs.docker.com/ai/sandboxes/workflows/git/)
与 [Docker Sandboxes clone mode 限制](https://docs.docker.com/ai/sandboxes/usage/)。

### 2.2 单一共享 Kit

项目在根目录提供一个 Kit：

```text
.sandbox-kit/
├── spec.yaml
└── files/
    └── home/
        └── .local/
            └── bin/
                └── iac-playwright-mcp
```

Kit 使用 schema v2 和 `kind: mixin`，负责：

- 安装 Terraform CLI。
- 创建 sandbox 专用 Python 虚拟环境，并安装 `.sandbox-kit/spec.yaml` 中的
  literal Python package list；该列表镜像 `requirements.txt`，两者必须同步更新。
- 安装 `.sandbox-kit/spec.yaml` 中的 literal Ansible collection list；该列表镜像
  `ansible/requirements.yml`，两者必须同步更新。
- 安装项目需要的系统工具，例如 `jq`。
- 安装固定版本的 `@playwright/mcp` 和对应 Chromium。
- 定义 `PLAYWRIGHT_BROWSERS_PATH` 等必要环境变量。
- Kit 安装时查询 Playwright package 的 `chromium.executablePath()` 并创建稳定的 `/usr/local/bin/iac-chromium` symlink；统一包装命令 `iac-playwright-mcp` 使用该入口启动 `playwright-mcp --headless --isolated --executable-path <chromium>`。
- 声明安装和运行所需的网络权限。

Kit 不安装 Codex、Claude Code 或 OpenCode；三种 agent 继续使用 Docker 内置 agent template 和原生认证。

Kit install hook 发生在 workspace 文件可用之前，因此不会直接读取 `requirements.txt`
或 `ansible/requirements.yml`。新增或升级依赖时，必须同时更新对应清单和 Kit 中的
literal list。

Ansible collections 安装到 sandbox 的持久化 HOME，不写入项目 `ansible/collections/`。这可以避免两个 direct-mode agent 在创建环境时同时修改宿主工作区。

### 2.3 Sandbox 内 Playwright MCP

不使用宿主 `sbx mcp add playwright --command ...` 作为 Playwright 实现，因为该方式会在宿主机运行 MCP server 和浏览器，不属于 sandbox microVM 隔离边界。

三个 agent 都通过项目级配置启动同一个 sandbox-local stdio MCP 命令：

```text
.mcp.json              # Claude Code adapter
opencode.json          # OpenCode adapter
.codex/config.toml     # Codex adapter (trusted projects only)
```

三个项目配置都只负责将 `playwright` MCP 指向 `iac-playwright-mcp`。Playwright 版本、Chromium、参数和网络权限只在 `.sandbox-kit` 中维护。

Codex 会跳过 untrusted project 的 `.codex/config.toml`。当前设计保留项目 adapter，并把建立 project trust 与 `codex mcp list` 纳入每个新 Sandbox 的验收；不再为每次启动传递 CLI override。Codex Sandbox 同时使用 `--no-share-skills`，排除 Docker host-shared skills store。

运行时数据流为：

```text
Agent in sandbox
  → agent-specific project MCP adapter
  → iac-playwright-mcp (stdio)
  → headless Chromium in the same microVM
  → public web or sandbox-local service
```

使用 `--isolated` 避免并行 MCP 客户端争用持久化 browser profile。浏览器访问公网时受 Docker Sandbox 网络策略约束，访问 sandbox 内启动的前端服务时可以直接使用 `localhost`。

### 2.4 前端可视化

Sandbox 内 Chromium 使用 headless mode，用户不能直接看到 agent 操作的实时窗口。前端项目采用两条观察通道：

- Agent 通过 Playwright MCP 获得 snapshot、截图、console、network log 和 trace。
- 用户将 sandbox 内开发服务端口发布到宿主 loopback，并用宿主浏览器查看同一服务。

示例：

```bash
sbx run --name iac-frontend codex . \
  --no-share-skills \
  --kit ./.sandbox-kit \
  --publish 127.0.0.1:3000:3000
```

开发服务必须在 sandbox 内监听 `0.0.0.0:3000`。用户在 macOS 打开 `http://127.0.0.1:3000`。

第一版不引入 Xvfb、VNC 或 noVNC。只有当实际需要实时观看 agent 的同一浏览器会话时，才单独设计该能力。

## 3. OpenCode 运行模式

### 3.1 TUI

```bash
sbx run --name iac-opencode opencode . --kit ./.sandbox-kit
```

### 3.2 OpenCode Desktop

OpenCode Desktop 通过宿主 loopback 连接 sandbox 内的 standalone server：

```bash
sbx run \
  --name iac-opencode-desktop \
  --publish 127.0.0.1:4096:4096 \
  opencode . \
  --kit ./.sandbox-kit \
  -- serve --hostname 0.0.0.0 --port 4096
```

Desktop 连接 `http://127.0.0.1:4096`。宿主发布只绑定 loopback，不暴露到局域网。

`sbx run ... -- serve ...` 必须在长期 attached terminal/session 中持续运行。不要使用
`--detached`：它只创建/启动 microVM，不会启动 agent server。仅在该 session 保持运行时，
才从另一宿主终端执行 health check。

Docker Sandboxes 保留宿主 workspace 的绝对路径，因此不再需要 devcontainer 中为 OpenCode Desktop 实现的同路径双重 bind mount、symlink 和 host config rewrite。

OpenCode TUI 与 Desktop server 使用不同 sandbox 名称，允许并行运行且避免生命周期冲突。

## 4. 凭据与敏感文件

### 4.1 Agent 模型认证

Codex、Claude Code 和 OpenCode 使用 Docker Sandboxes 内置认证和宿主凭据代理。项目 Kit 不复制 `~/.codex`、`~/.claude`、OpenCode auth 或 API key。

### 4.2 SSH

Docker Sandboxes 自动转发宿主 `SSH_AUTH_SOCK`。私钥保留在宿主 SSH agent 中，sandbox 内进程只能请求签名，不能读取或复制私钥。Direct mode 会挂载整个仓库工作区（包括 gitignored 文件），所以仓库本地 `.ssh` 中禁止存放私钥；否则 sandbox 仍可直接读取它们。

迁移将移除以下硬编码私钥路径：

- `ansible/ansible.cfg` 中的 `private_key_file`。
- `ansible/inventory/oci/hosts.yml` 中的 `ansible_ssh_private_key_file`。
- Terraform 或 Ansible host metadata 中专门写死为 `~/.ssh/id_ed25519` 的字段。

宿主启动 sandbox 前应使用 `ssh-add -L` 验证密钥已加载。移除显式路径不会破坏普通宿主环境，OpenSSH 仍会使用默认 identity discovery 和 SSH agent。

### 4.3 Ansible Vault

Direct mode 继续使用宿主 workspace 中 gitignored 的 `ansible/.vault_pass`。

Clone mode 的私有 clone 不会自动包含未跟踪的 `.vault_pass` 和生成的 `*.auto.tfvars`。宿主仓库仍以只读形式出现在 `/run/sandbox/source`。第一版文档提供手工复制步骤，不用启动脚本自动复制敏感文件。

### 4.4 OCI API 私钥

OCI Terraform provider 需要在每个 API 请求发出前使用 RSA 私钥生成 OCI request signature。Docker HTTP 凭据代理不能用固定 token 替代该签名，OCI provider 也不支持通过 SSH agent 调用这把 API 私钥。

日常 sandbox 不挂载 OCI 私钥。只有运行 OCI Terraform 时才显式增加只读 workspace：

```bash
test -d "${HOME}/.oci" || { echo 'OCI credentials directory is missing; stop and ask the user to restore or provide approved OCI credentials.' >&2; exit 1; }
sbx run --name iac-oci --no-share-skills codex . "${HOME}/.oci:ro" --kit ./.sandbox-kit
```

执行 OCI 命令前必须先确认 `test -d "${HOME}/.oci"` 成功；目录不存在时停止或跳过 OCI sandbox 创建，并请求用户恢复或提供已批准的 OCI credentials。不得自动创建空目录，也不得搜索替代私钥位置；目录存在后才使用带引号的 `"${HOME}/.oci:ro"`。Docker Sandboxes 在 microVM 中保留额外 workspace 的宿主绝对路径，因此 Terraform `private_key_path` 可以继续指向该文件。只读挂载可防止 sandbox 修改私钥，但 sandbox 内进程在该次运行中仍可以读取它；`README.md` 和 `AGENTS.md` 必须明确说明这一边界。

## 5. 文档与 agent 指令

### 5.1 必须更新

- `README.md`：用 Docker Sandboxes 替换 devcontainer 快速开始，记录三种 agent、direct/clone mode、端口发布、SSH、Vault、OCI 和 Kit 重建要求。
- `AGENTS.md`：将 Dev Container/OpenCode 路径映射说明替换为 Docker Sandboxes 环境规则，并明确 OCI 私钥挂载边界。
- `CLAUDE.md`：删除独立和过时规则，仅保留对 `AGENTS.md` 的权威指针，避免两套指令漂移。
- 当前仍有效的 troubleshooting、deployment、architecture 和 agent setup 文档。

`CLAUDE.md` 的目标内容为：

```markdown
# Claude Code Instructions

Read and follow [AGENTS.md](./AGENTS.md) as the authoritative project instructions.
```

### 5.2 保留历史原文

以下目录中的 devcontainer 描述是当时事实，不做机械替换：

- `docs/incidents/`
- `docs/learningnotes/`
- `docs/archive/`

若历史文档中的命令容易被误当成当前操作指南，可增加简短历史状态说明，但不改写原事件。

## 6. 退役范围

Docker Sandbox 验证通过后删除：

- 整个 `.devcontainer/`。
- `.gitignore` 中的 `.devcontainer/.generated/`。
- `ansible/playbooks/deploy-devcontainer.yml`。
- `ansible/playbooks/site.yml` 中对 `deploy-devcontainer.yml` 的 import 和条件。
- 项目 `.mcp.json` 中指向 `host.docker.internal:8931` 的旧 Playwright HTTP 配置；该文件会改为 sandbox-local stdio 配置，不是整体删除。

不删除任何 Terraform VM 资源或当前 inventory host。已有搜索未发现 Terraform 或当前 inventory 中仍定义名为 `devcontainer` 的主机。

## 7. 错误处理与操作约束

- **SSH agent 未加载 key**：sandbox 可启动，但 Ansible SSH 验证失败。用 `ssh-add -L` 在宿主和 sandbox 内分别检查。
- **Kit 网络策略缺失**：安装阶段应硬失败并显示受阻域名，不允许半完成 sandbox。
- **Kit 已变更**：现有 sandbox 不会自动重放全部创建步骤。需要删除并重建，或在官方支持的有限字段范围内使用 `sbx kit add`。
- **Clone mode 缺少未跟踪 Vault 或生成的 Terraform secret 文件**：从 `/run/sandbox/source` 手工复制所需文件到 private clone，不自动传播；绝不复制 SSH 私钥。
- **OCI key 未挂载**：OCI provider 在计划前失败；不尝试从其他位置搜索或复制私钥。
- **OpenCode 4096 端口冲突**：sandbox 创建失败，不默认换用不可预测端口。
- **Playwright profile 竞争**：统一使用 `--isolated`。
- **Workflow ownership**：BMad 控制 planning、checkpoint、验证与 Git/PR lifecycle；`AGENTS.md` 只保留不可协商的安全边界。

## 8. 验证设计

### 8.1 阶段一：建立新环境，保留回退

在 `.devcontainer/` 仍然存在时完成新 Kit、三个 agent 的项目 MCP adapters、SSH 路径修改和文档草案。

静态验证：

```bash
sbx kit validate .sandbox-kit
terraform fmt -check -recursive
git diff --check
```

解析 `.codex/config.toml`、`.mcp.json` 和 `opencode.json`；在 trusted Codex Sandbox 内以 `codex mcp list` 验证 required local Playwright adapter。

为三种 agent 分别创建名称唯一的临时 smoke sandbox，验证：

- `terraform version`。
- `ansible --version`。
- Python 虚拟环境及 `requirements.txt`。
- Ansible collections 可发现。
- `iac-playwright-mcp` 可启动。
- Chromium 可以在 microVM 内启动并访问测试页面。
- Codex、Claude Code 和 OpenCode 能发现 Playwright MCP。
- `ssh-add -L` 可见转发的宿主公钥，不验证或输出私钥。

项目验证：

- 在 `ansible/` 目录运行 `ansible-playbook playbooks/site.yml --syntax-check`。
- Terraform 各环境运行 `terraform init -backend=false` 和 `terraform validate`。
- 不运行 Terraform `plan` 或 `apply`。
- 不运行任何 Ansible 部署。

OCI 验证使用 `"${HOME}/.oci:ro"` 额外 workspace，只检查私钥路径可读和 Terraform 可初始化/验证，不输出密钥内容，不执行计划或变更。

OpenCode Desktop 验收：

- 启动 `iac-opencode-desktop` server sandbox。
- 从宿主检查 `http://127.0.0.1:4096/global/health`。
- 用 Desktop GUI 确认连接和项目路径。

阶段一完成后停止，汇报证据并等待用户批准最终切换。

### 8.2 阶段二：删除旧环境

用户批准后：

1. 删除 `.devcontainer/` 和对应 `.gitignore` 规则。
2. 退役 `deploy-devcontainer.yml` 和 `site.yml` import。
3. 完成当前有效文档更新。
4. 搜索剩余 `devcontainer`、`.devcontainer` 和 `/workspaces/IaC` 引用，按当前文档与历史文档的边界分类处理。
5. 重新运行 Kit validate、Terraform fmt check、Ansible syntax check 和 `git diff --check`。

完成后汇总所有改动、剩余已知风险和验证证据，不自动提交。

## 9. 实施边界

- 本次不创建启动 wrapper script；重复的 `sbx run` 参数先在 README 中明确记录。
- 本次不引入 `.sbxenv.yaml`。
- 本次不引入 noVNC、持久化可见 browser profile 或宿主 Chrome extension 连接。
- 本次不部署、修改或删除任何 homelab VM。
- 本次不把 Docker Desktop MCP Toolkit 配置自动迁移到 `sbx mcp`；未来对 Notion、GitHub 等宿主管理的外部 MCP 单独设计。
- 本次不自动提交 Git commit。

## 10. 主要参考资料

- [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/)
- [Docker Sandboxes Usage](https://docs.docker.com/ai/sandboxes/usage/)
- [Docker Sandboxes Credentials](https://docs.docker.com/ai/sandboxes/configuration/credentials/)
- [Docker Sandboxes Kits](https://docs.docker.com/ai/sandboxes/customize/kits/)
- [Docker Sandboxes Kit Reference](https://docs.docker.com/ai/sandboxes/customize/kit-reference/)
- [Docker Sandboxes MCP Gateway](https://docs.docker.com/ai/sandboxes/mcp-gateway/)
- [Docker Sandboxes OpenCode](https://docs.docker.com/ai/sandboxes/agents/opencode/)
- [OpenAI Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [OpenCode MCP Servers](https://opencode.ai/docs/mcp-servers/)
- [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [OCI Request Signatures](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/signingrequests.htm)
- [OCI Terraform Provider Configuration](https://docs.oracle.com/en-us/iaas/Content/dev/terraform/configuring.htm)
