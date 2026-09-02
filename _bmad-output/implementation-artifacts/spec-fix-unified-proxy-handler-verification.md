---
title: 'Fix unified-proxy handler verification flow'
type: 'bugfix'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'fceb73e9cc39b75fb907bfe532690a3f1f429864'
context:
  - '{project-root}/docs/designs/ansible-role-architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `unified-proxy` 在 role 内先执行健康检查、后执行被 `notify` 延迟的重启 Handler，导致已有服务更新时可能验证旧进程；同时 `--tags config` 会跳过注册 `env_file` 的 stat 任务并引用未定义变量，而且名称不能清楚表达该 tag 只管理环境文件。

**Approach:** 将 role 内验证移动到独立 Verify play，使 Deploy play 的 Handler 在 play 边界先执行；把 `config` tag 重命名为 `env`，并让 `.env` 的前置检查及写入任务使用同一 tag。

## Boundaries & Constraints

**Always:** 保持完整部署以及 `code`、`auth`、`env` 增量部署在 Handler 执行后验证新进程；保留 `--tags verify` 作为只读健康检查入口；使用 FQCN 编写新增或修改的 Ansible 模块调用；保留现有 Handler 定义顺序和幂等行为。

**Ask First:** 如果实现需要改变 `.env` 的所有权模型、服务端口、Caddy 验证范围、上游源码部署方式或依赖安装流程，必须暂停并征求用户确认。

**Never:** 不得让现有 `.env` 中的 `PROXY_API_KEY` 随 Vault 值自动轮换；不得将首次创建模板改为持续覆盖整个 `.env`；不得修改 Caddy、`auth.json` 校验、npm 依赖安装或其他已暂缓问题；不得运行真实部署。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Full deploy | 不带 tag 执行 playbook | Deploy 完成，Handler 在 play 边界执行，然后 Verify 检查当前进程 | 新进程未就绪时 Verify play 失败 |
| Code update | `--tags code` | 只运行代码路径、被通知的 Handler 和 Verify play | 重启后端口或健康检查失败则部署失败 |
| Auth update | `--tags auth` | 更新 `auth.json`、必要时重启，然后验证 | 无效运行状态由 Verify 捕获 |
| Environment update | `--tags env` | stat、首次模板和非敏感 lineinfile 均被选择，然后验证 | 不出现 `env_file` 未定义；现有 API key 不变化 |
| Verify only | `--tags verify` | 跳过 Deploy，仅执行 readiness 与 HTTP health check | 服务不可用时返回非零 |
| Existing environment | `.env` 已存在且 Vault API key 改变 | 仅维护 HOST、PORT、PROXY_AUTH_FILE | 保留远程 `PROXY_API_KEY` 原值 |

</frozen-after-approval>

## Code Map

- `ansible/roles/unified-proxy/tasks/main.yml` -- `.env` tag 选择与当前 role 内验证任务所在地。
- `ansible/playbooks/deploy-unified-proxy.yml` -- Deploy/Verify play 编排及使用示例。
- `ansible/roles/unified-proxy/handlers/main.yml` -- 现有 reload/restart 顺序，只读参考，不修改。
- `ansible/roles/unified-proxy/templates/env.j2` -- 首次创建 `.env` 时写入 API key，只读参考，不修改。

## Tasks & Acceptance

**Execution:**
- [x] `ansible/roles/unified-proxy/tasks/main.yml` -- 将 `config` tag 改为 `env`，给 stat 前置任务添加相同 tag，并删除 role 尾部验证任务，使 tag 路径自包含且不在 Handler 前验证。
- [x] `ansible/playbooks/deploy-unified-proxy.yml` -- 更新 usage 示例；新增独立 Verify play，继承 `verify`、`code`、`auth`、`env` tags，并承接 wait、HTTP health 和结果输出任务。

**Acceptance Criteria:**
- Given 完整部署产生 Handler 通知，when Deploy play 完成，then Handler 在 Verify play 开始前执行。
- Given 分别使用 `--tags code`、`--tags auth` 或 `--tags env`，when 列出任务，then 对应部署任务和 Verify play 均被选择。
- Given 使用 `--tags env`，when `.env` 已存在，then stat 先执行、首次模板跳过、非敏感键可幂等更新，且 API key 不被覆盖。
- Given 使用 `--tags verify`，when 列出任务，then Deploy role 没有业务任务，只有独立 Verify play 的健康检查任务。
- Given playbook 修改完成，when 运行 syntax check 和 `git diff --check`，then 两者均成功。

## Spec Change Log

## Design Notes

Verify play 使用 `tags: [verify, code, auth, env]`。Ansible 在 Deploy play 的 roles/tasks 阶段结束时自动同步 Handler，因此无需在 role 中额外 `flush_handlers`；增量 tag 运行也会先完成相应部署及 Handler，再进入下一 play 验证。

## Verification

**Commands:**
- `ANSIBLE_LOCAL_TEMP=/tmp/ansible-unified-proxy ansible-playbook -i localhost, playbooks/deploy-unified-proxy.yml --syntax-check` -- 预期语法通过，仅允许临时 inventory 不匹配目标 host 的警告。
- `ANSIBLE_LOCAL_TEMP=/tmp/ansible-unified-proxy ansible-playbook -i localhost, playbooks/deploy-unified-proxy.yml --list-tasks --tags code` -- 预期代码任务与 Verify 任务被选择。
- 对 `auth`、`env`、`verify` 重复上述 `--list-tasks` -- 预期每条路径符合 I/O 矩阵。
- `git diff --check` -- 预期无空白错误。

## Suggested Review Order

**部署与验证边界**

- 独立 Verify play 保证先应用 Handler，再检查新进程。
  [`deploy-unified-proxy.yml:26`](../../ansible/playbooks/deploy-unified-proxy.yml#L26)

- 增量 tag 继承让代码、认证和环境更新自动验证。
  [`deploy-unified-proxy.yml:29`](../../ansible/playbooks/deploy-unified-proxy.yml#L29)

**环境配置路径**

- stat 与写入任务统一使用 env tag，消除未定义变量。
  [`main.yml:157`](../../ansible/roles/unified-proxy/tasks/main.yml#L157)

- 非密钥字段继续独立维护，保留 API key 不轮换设计。
  [`main.yml:175`](../../ansible/roles/unified-proxy/tasks/main.yml#L175)
