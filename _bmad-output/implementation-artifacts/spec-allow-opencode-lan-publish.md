---
title: 'Allow authenticated OpenCode LAN publishing'
type: 'chore'
created: '2026-09-04'
status: 'done'
review_loop_iteration: 0
baseline_commit: '3fdfde893302a101a437054c66338df34a37f7cc'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/README.md'
  - '{project-root}/docs/designs/docker-sandbox-agent-architecture.md'
  - '{project-root}/docs/designs/2026-08-28-docker-sandbox-migration.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** OpenCode Desktop 目前只能发布到宿主 loopback，导致同一 LAN 中仅有浏览器的客户端（例如手机）无法访问。该限制比实际安全需求更严格。

**Approach:** 保留 loopback 作为默认模式，同时允许用户明确选择宿主机某个具体 LAN IPv4 作为 `--publish` 地址。LAN 模式必须启用 OpenCode server 认证，并禁止宿主侧通配监听。

## Boundaries & Constraints

**Always:** 默认示例继续使用 `127.0.0.1`；LAN 模式使用属于宿主目标网卡的显式 IPv4，例如 `<LAN_IP>:4096:4096`；LAN 发布前启用 `OPENCODE_SERVER_PASSWORD`，凭据不得进入仓库或示例；启动前验证地址归属和端口空闲，启动后验证只监听所选地址；Sandbox 内 server 继续监听 `0.0.0.0:4096`；保持长期 attached session。

**Ask First:** 修改默认端口、认证机制，或把这项例外推广到 OpenCode Desktop 以外的 Sandbox 服务。

**Never:** 宿主 `--publish` 使用 `0.0.0.0`、省略宿主 IP、在 LAN 模式下关闭认证、把密码写入版本控制，或使用 `--detached` 启动 server。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 默认本机访问 | 未请求 LAN；4096 空闲 | 发布到 `127.0.0.1:4096` | 端口占用时停止并选择任务专用端口 |
| 手机 LAN 访问 | 用户选择有效 `<LAN_IP>` 且配置认证 | 发布到 `<LAN_IP>:4096`，手机浏览器使用认证访问 | 地址不属于本机、端口占用或未配置认证时不得启动 |
| 危险通配地址 | 宿主地址为 `0.0.0.0` 或被省略 | 拒绝该启动方式 | 改为显式 loopback 或具体 LAN IPv4 |

</frozen-after-approval>

## Code Map

- `AGENTS.md:158` -- 仓库权威运行规则；当前硬性要求 host loopback，需改为默认 loopback + 受控 LAN 例外。
- `README.md:139` -- 当前快速开始与 loopback-only 说明；需同步唯一受控 LAN 例外及安全操作流程。
- `docs/designs/docker-sandbox-agent-architecture.md:73` -- 当前 OpenCode Desktop 命令与安全说明；需加入 LAN 示例和验证边界。
- `docs/designs/docker-sandbox-agent-architecture.md:155` -- Playwright 通用 loopback 数据流；仅补充 OpenCode Desktop 例外引用，不泛化其他服务。
- `docs/designs/2026-08-28-docker-sandbox-migration.md:145` -- 迁移设计中的 loopback-only 决策、示例与生命周期说明。
- `docs/designs/2026-08-28-docker-sandbox-migration.md:319` -- OpenCode Desktop 验收清单；需覆盖受认证的 LAN 浏览器路径。

## Tasks & Acceptance

**Execution:**
- [x] `AGENTS.md` -- 将 OpenCode Desktop 规则改为默认 loopback、允许显式本地网卡 IPv4，并写明认证与禁止项。
- [x] `README.md` -- 同步模式专用名称、既有映射检查、可信 LAN 限制、认证与失败清理规则。
- [x] `docs/designs/docker-sandbox-agent-architecture.md` -- 同步运行示例、安全前置条件、监听验证和受控例外范围。
- [x] `docs/designs/2026-08-28-docker-sandbox-migration.md` -- 更新旧的 loopback-only 设计陈述及 LAN 验收步骤，避免文档冲突。

**Acceptance Criteria:**
- Given 未请求 LAN 访问，when Agent 读取运行规则，then 它仍优先发布到 `127.0.0.1`。
- Given 用户明确需要 LAN 浏览器访问，when Agent 启动 OpenCode Desktop，then 规则允许绑定具体 `<LAN_IP>`，同时要求认证、地址/端口预检和监听范围后检。
- Given 宿主发布地址是 `0.0.0.0` 或未指定，when Agent 评估命令，then 规则明确禁止执行。
- Given 四份文档被检索，when 比较 OpenCode Desktop 网络策略，then 不存在 loopback-only 与 LAN 例外互相矛盾的有效陈述。

## Spec Change Log

## Design Notes

这里区分两个监听层：Sandbox 内的 `serve --hostname 0.0.0.0` 仍是端口转发所需；安全限制针对宿主 `--publish` 地址。允许的是某个明确 LAN IPv4，而不是所有宿主接口。

## Verification

**Commands:**
- `rg -n "OpenCode Desktop|loopback|LAN_IP|0\\.0\\.0\\.0|OPENCODE_SERVER_PASSWORD" AGENTS.md docs/designs/docker-sandbox-agent-architecture.md docs/designs/2026-08-28-docker-sandbox-migration.md` -- expected: 三份文档表达一致，通配 host publish 被禁止。
- `git diff --check` -- expected: 无空白或补丁格式错误。

## Suggested Review Order

**权威策略**

- 从默认 loopback 到受控 LAN 例外的完整安全边界。
  [`AGENTS.md:158`](../../AGENTS.md#L158)

**运行行为**

- 模式专用名称防止重连时沿用错误端口映射。
  [`README.md:160`](../../README.md#L160)

- 手机 LAN 启动示例与认证、监听后检要求。
  [`README.md:166`](../../README.md#L166)

**架构依据**

- `--publish` 创建时固定，既有 Sandbox 必须先核对。
  [`docker-sandbox-agent-architecture.md:85`](../../docs/designs/docker-sandbox-agent-architecture.md#L85)

- 可信私有 LAN、强密码与通配地址禁令。
  [`docker-sandbox-agent-architecture.md:100`](../../docs/designs/docker-sandbox-agent-architecture.md#L100)

- 明文 HTTP 的信任边界及失败关闭行为。
  [`docker-sandbox-agent-architecture.md:107`](../../docs/designs/docker-sandbox-agent-architecture.md#L107)

**验收路径**

- loopback 与手机 LAN 两条可验证的验收流程。
  [`2026-08-28-docker-sandbox-migration.md:319`](../../docs/designs/2026-08-28-docker-sandbox-migration.md#L319)
