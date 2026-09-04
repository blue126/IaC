# Docker Sandbox Agent Architecture

## 1. 目标

本设计定义 IaC 仓库中 Codex、Claude Code、OpenCode、BMad、Docker Sandbox、MCP 和项目指令的职责边界。目标是让三种 Agent 在 host checkout、linked worktree 和 clone-mode Sandbox 中获得一致的项目治理与环境约束，同时避免宿主个人配置污染 Sandbox，并让 BMad 成为唯一 workflow owner。

## 2. 职责模型

| 层 | 来源 | 职责 |
|---|---|---|
| Agent system capabilities | Agent-specific template | 各 Agent 的内建能力、认证和基础工具 |
| 项目 skills | `.agents/skills/` | BMad planning、implementation、review workflow |
| 跨 Agent 项目指令 | `AGENTS.md` | 仓库事实、技术规范、环境能力和安全边界 |
| Claude 项目入口 | `CLAUDE.md` | 使用 `@AGENTS.md` 导入跨 Agent 项目指令 |
| 宿主 MCP 注册表 | `sbx mcp` | 全局注册 Playwright 等宿主 MCP server |
| Sandbox 环境指令源 | `.sandbox-kit/files/home/.local/share/iac-agent/sandbox-rules.md` | direct/clone、Git、凭据和运行时隔离事实 |
| Sandbox Kit | `.sandbox-kit/` | Terraform、Ansible、Python、网络和环境指令安装器 |
| 设计文档 | `docs/designs/` | 原理、拓扑、迁移和故障排查；不注入 prompt |

`AGENTS.md` 不定义 task decomposition、checkpoint、实现顺序、验证策略或 Git/PR lifecycle。BMad workflow 决定这些步骤；workflow ownership 不等于授权，未明确批准的 commit、push、merge、deployment 或其他外部写入仍必须停止。

## 3. 指令加载与 managed block

| Agent | 项目指令 | Sandbox 全局指令 | 验证入口 |
|---|---|---|---|
| Codex | 仓库根 `AGENTS.md` | `/home/agent/.codex/AGENTS.md` | `codex debug prompt-input noop` |
| Claude Code | 根 `CLAUDE.md` 通过 `@AGENTS.md` 导入 | `/home/agent/.claude/CLAUDE.md` | 新 interactive session 的 `/context` |
| OpenCode | 仓库根 `AGENTS.md` | `/home/agent/.config/opencode/AGENTS.md` | 新 session 中确认 global 与 project sources |

Sandbox 规则只有一个版本控制源：

```text
.sandbox-kit/files/home/.local/share/iac-agent/sandbox-rules.md
  ↓ install-iac-agent-instructions
  ├── managed block → /home/agent/.codex/AGENTS.md
  ├── managed block → /home/agent/.claude/CLAUDE.md
  └── managed block → /home/agent/.config/opencode/AGENTS.md
```

安装器只替换以下 marker 之间的内容，保留目标文件中的全部既有非 managed 内容：

```text
<!-- BEGIN IAC SANDBOX RULES -->
<!-- END IAC SANDBOX RULES -->
```

安装前，三个目标文件必须同时通过 marker 数量与配对检查；任一文件畸形时不修改任何目标。安装器通过 `id -u agent` 和 `id -g agent` 解析所有者，在目标目录内准备临时文件后原子替换。规则 marker `iac-sandbox-v1.3.0` 与 Kit `1.3.0` 同步，用于识别旧 Sandbox。

Claude Code 不直接读取 `AGENTS.md`，因此根 `CLAUDE.md` 使用正式 `@AGENTS.md` import。OpenCode V2 自动发现 `AGENTS.md`；不要依赖尚未解析为 active instructions 的 `instructions` 配置数组。

## 4. 执行拓扑与启动入口

### Direct mode from a host linked worktree

- `.` 必须是已分配的 host task worktree；main checkout 只用于协调。
- 文件编辑与本地验证在 Sandbox 内进行，Git preflight、commit、push 和 PR 操作在对应宿主 worktree 中进行。
- Docker 可能无法解析指向外部 common Git directory 的 `.git` pointer；这是能力边界，不是迁移故障。

### Clone mode from the verified main checkout

- 使用 `--clone` 创建私有 Git clone，Git 操作在 Sandbox 内进行。
- gitignored Vault、Terraform secrets 和个人 BMad 配置默认不存在。
- 只从 `/run/sandbox/source` 复制任务明确需要的 secret 文件，且不输出、暂存或提交其内容。

将 `TASK` 替换为唯一 kebab-case 任务名。未指定 `--static-mcp` 时使用默认 dynamic MCP Gateway，Agent 按需从宿主全局注册表附加 `playwright`：

| Agent | Direct mode from task worktree | Clone mode from main checkout |
|---|---|---|
| Codex | `sbx run --name iac-codex-TASK-direct-v130 codex . --kit ./.sandbox-kit` | `sbx run --clone --name iac-codex-TASK-clone-v130 codex . --kit ./.sandbox-kit` |
| Claude Code | `sbx run --name iac-claude-TASK-direct-v130 claude . --kit ./.sandbox-kit` | `sbx run --clone --name iac-claude-TASK-clone-v130 claude . --kit ./.sandbox-kit` |
| OpenCode | `sbx run --name iac-opencode-TASK-direct-v130 opencode . --kit ./.sandbox-kit` | `sbx run --clone --name iac-opencode-TASK-clone-v130 opencode . --kit ./.sandbox-kit` |

OpenCode Desktop 使用长期 attached session：

```bash
sbx run --name iac-opencode-desktop-TASK-loopback-v130 \
  --publish 127.0.0.1:4096:4096 \
  opencode . --kit ./.sandbox-kit \
  -- serve --hostname 0.0.0.0 --port 4096
```

默认模式继续把宿主端口绑定到 `127.0.0.1`。不要使用 `--detached`；它只创建或启动
microVM，不启动 agent server。

loopback 与 LAN 必须使用不同的 Sandbox 名称：分别为
`iac-opencode-desktop-TASK-loopback-v130` 与 `iac-opencode-desktop-TASK-lan-v130`。
`--publish` 仅在 Sandbox 首次创建时生效，重连时传入的新值会被忽略。因此启动任一模式
前，若同名 Sandbox 已存在，必须先运行 `sbx ports <name>`，确认现有映射与所需地址、
端口完全一致；不一致时停止，不能假定 `sbx run` 已切换发布模式。

只有用户明确要求从可信、隔离的私有 LAN 进行浏览器访问时，才允许使用受控例外：

```bash
sbx run --name iac-opencode-desktop-TASK-lan-v130 \
  --publish <LAN_IP>:4096:4096 \
  opencode . --kit ./.sandbox-kit \
  -- serve --hostname 0.0.0.0 --port 4096
```

`<LAN_IP>` 必须是所选物理 LAN 网卡实际拥有的具体私有 IPv4。公网、VPN、bridge、IPv4
通配 `0.0.0.0`、IPv6 通配 `::` 和省略宿主地址都不是有效目标。启动前必须确认三项条件：
该地址属于目标网卡、该地址的 TCP 4096 端口空闲，以及 OpenCode server 进程环境中已
通过未纳入版本控制的运行时渠道注入非空且至少 20 字符的强随机
`OPENCODE_SERVER_PASSWORD`。密码不得写入仓库、命令示例、命令参数或 shell 历史。
任一检查失败都不得启动；端口占用时必须停止并询问用户，不得自动改用其他端口。

LAN 模式的明文 HTTP 仅允许在可信隔离 LAN 内使用；其他网络路径必须提供 TLS 或可信
VPN。启动后，从另一宿主终端检查 TCP 4096 的监听地址只等于所选 `<LAN_IP>`，不能是
`0.0.0.0`、`::`、`*` 或其他接口地址；随后验证未认证访问失败、认证访问成功。任一后检
失败时立即终止长期 attached session，并确认宿主端口已经关闭。这里有两个独立监听层：
Sandbox 内 `serve --hostname 0.0.0.0` 是端口转发所需，宿主 `--publish` 则必须是显式
loopback 或具体 LAN IPv4。省略宿主 IP 和宿主 `0.0.0.0` 在所有模式下都禁止。

此 LAN 例外仅适用于 OpenCode Desktop，不改变其他 Sandbox 服务的 loopback-only 策略，
也不允许关闭认证。

## 5. Project-specific credential handling

本节描述 IaC 仓库的项目凭据策略，不定义 Docker Sandbox topology，也不定义 Codex、Claude Code 或 OpenCode runtime。

### Shared repository credentials

- SSH：使用宿主转发的 SSH agent；运行 Ansible 前验证 `ssh-add -L`。仓库不得保存 SSH 私钥。
- Vault：direct mode 使用工作区现有 gitignored 文件；clone mode 仅按任务需要从 `/run/sandbox/source` 复制。
- BMad：团队 runtime 纳入 Git，`config.user.toml` 与 `*.user.toml` 永不跟踪。

### OCI tasks only

OCI credential injection 是本项目访问 Oracle Cloud 的任务级需求，不是通用 Sandbox 模式。只有任务明确需要 OCI 时，才在宿主运行 `test -d "${HOME}/.oci"`。检查成功后，把 `"${HOME}/.oci:ro"` 作为额外只读 workspace 传给所选 direct/clone 与 Agent 入口；目录缺失时停止，不创建空目录、搜索替代私钥或使用可写挂载。

## 6. 并行任务与运行时隔离

- 每个任务使用独立 branch、worktree 和 Agent session。
- Worker 不修改其他任务 worktree，也不合并其他任务 branch。本地 integration 仅在明确指派时进行，并使用专用 integration worktree。
- Worktree 只隔离文件和 Git 状态。同一 Sandbox 内仍共享 Docker daemon、network、ports、volumes、`/tmp` 和服务状态。
- 共享 Sandbox 时使用不同的 Compose project name、host port、volume、temporary path 和 service identifier。
- 需要运行时强隔离时，为每个任务创建名称唯一的独立 Sandbox。

## 7. Host-managed Playwright MCP

Playwright 由宿主 `sbx mcp` 注册，三种 Agent 都通过 Sandbox MCP Gateway 使用同一个 server。项目不再包含 Agent-specific MCP adapter。

### 数据流

```text
Codex
  → Sandbox MCP gateway
  → host-managed playwright MCP
  → visible Chromium on macOS
  → published Sandbox service port or public web
```

宿主只需运行一次 `sbx mcp add playwright ...` 完成全局注册。所有未指定 `--static-mcp` 的 Sandbox 默认进入 dynamic mode，并由 Agent 通过 Gateway 的发现与附加工具按需启用。宿主直接进入仓库运行 Codex 时，不会再尝试启动 sandbox-only 命令。

宿主 Playwright 访问 Sandbox 内服务时，服务必须监听 `0.0.0.0`，并通过 `--publish 127.0.0.1:<host>:<sandbox>` 发布。浏览器访问发布后的 loopback 地址，用户可以实时观察同一个窗口。第 4 节中受认证的 OpenCode Desktop LAN 发布是唯一例外；不得据此把其他服务发布到 LAN。

## 8. 现有 Sandbox 迁移

Sandbox Kit 更新不会自动应用到现有 microVM。先运行 `sbx ls`；若固定名称已存在，使用包含任务名和 Kit 版本的新名称创建测试 Sandbox。验证指令、skills、trust 和 MCP 后，再单独请求删除或替换旧实例。不得自动删除旧实例或其内部 session/state。

## 9. 验收

### Local pre-commit checks

| 对象 | 检查 | 期望结果 |
|---|---|---|
| Installer shell | `bash -n` | 安装器与测试脚本语法有效 |
| Managed block behavior | `.sandbox-kit/tests/test-install-agent-instructions.sh` | 保留 vendor 内容；幂等更新；旧 marker 被替换；畸形 marker 时三个文件均不变 |
| Patch | `git diff --check` | 无空白错误 |
| Kit | `sbx kit validate ./.sandbox-kit` | schema 有效 |
| Kit contents | `sbx kit inspect ./.sandbox-kit --json` | 版本为 `1.3.0`，包含 installer 与 `sandbox-rules.md` |

### Fresh-Sandbox integration checks

创建 Sandbox 会执行 Kit 的 apt 和 pip 安装，因此必须获得单独授权。不得用 local `kit validate` 冒充 integration smoke。

| Agent | 检查 | 期望结果 |
|---|---|---|
| Shared | 在全新、名称唯一的 Sandbox 中检查三个目标文件的 owner、mode、既有内容与 `iac-sandbox-v1.3.0` marker | owner 是实际 `agent` UID/GID，mode `0644`，非 managed 内容保留，marker 唯一 |
| Codex | `codex debug prompt-input noop` 和 MCP gateway tool list | global/project 指令均加载；Playwright 来自宿主 gateway |
| Claude Code | 新 interactive session 中运行 `/context` | global `CLAUDE.md`、project `CLAUDE.md` 和导入的 `AGENTS.md` 可见 |
| OpenCode | 启动新 session 并检查 global/project instruction sources | 两层 `AGENTS.md` 均加载；旧 session 不用于更新验收 |
| Direct worktree | 从 host linked worktree 启动 | 文件可编辑和验证；Sandbox 内 Git 不作为成功条件 |
| Clone mode | 从 verified main checkout 使用 `--clone` 启动 | Sandbox 内 Git 可用；gitignored secrets 默认不存在 |

## 10. 参考

- [Codex AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codex config basics](https://learn.chatgpt.com/docs/config-file/config-basic)
- [Codex config reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Claude Code memory and CLAUDE.md](https://code.claude.com/docs/en/memory)
- [OpenCode V2 instructions](https://opencode.ai/v2/docs/instructions)
- [Docker Sandboxes usage](https://docs.docker.com/ai/sandboxes/usage/)
- [Docker Sandbox MCP gateway](https://docs.docker.com/ai/sandboxes/mcp-gateway/)
- [Docker host worktree Git boundary](https://docs.docker.com/ai/sandboxes/workflows/git/)
