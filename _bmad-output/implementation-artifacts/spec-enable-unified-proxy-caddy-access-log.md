---
title: 'Enable unified-proxy Caddy access logging'
type: 'feature'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 1
baseline_commit: '90d58a906c87b8e73117846a6262c4e0dee8314b'
context:
  - '{project-root}/docs/designs/ansible-role-architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `proxy.willfan.me` 的 Caddy HTTP 边界没有独立 access log，无法区分请求未到达 Node、被 Caddy 拒绝或因上游不可用返回 502；默认 journald 已占用较多空间，不适合承载该流量日志。

**Approach:** 在现有 site block 中增加文件 access log 与 Caddy 内置轮转；先以 `caddy` 用户验证临时候选配置，成功后才原子部署到正式路径并再次验证，最后通过 systemd reload 加载，同时提供最小范围的 `caddy-config` 部署入口。

## Boundaries & Constraints

**Always:** access log 写入 `/var/log/caddy/access.log`，使用 `roll_size 50MiB` 与 `roll_keep 10`；必须先以 `caddy` 用户验证临时候选文件，成功后才原子部署到 `/etc/caddy/Caddyfile` 并再次以 `caddy` 用户验证最终路径；候选验证失败时正式配置不得改变，所有失败路径均须清理临时候选且不得 reload；Caddy 配置变更使用 graceful reload；生产应用只执行 `caddy-config` tag及关联 Verify，不更新 Node 源码；验证必须确认 Caddy active、health endpoint 可用、日志新增记录且 Authorization 被 `REDACTED`。

**Ask First:** 如果 Caddy 2.11.1 不接受日志语法、reload 不能创建日志 writer、日志目录权限与已核实环境不一致，或最小 tag 会选择任何 Node 源码/认证/环境任务，必须暂停并征求用户确认。

**Never:** 不得修改现有 `reverse_proxy` 或 `header` 块；不得改变 `proxy_domain`、`proxy_port`、日志目标路径或写入 journald；不得修改 unified-proxy 上游仓库；不得在配置校验前 reload/restart；不得用真实 API key测试日志脱敏；不得 push。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Valid config change | 新 access log 配置有效 | 候选验证成功，原子部署，最终验证成功，play 边界 reload，Verify 检查后端 | 任一步失败则部署失败并清理候选 |
| Invalid Caddyfile | 候选 `caddy validate` 非零 | 正式磁盘配置与运行中 Caddy均保持不变 | 立即中止、清理候选、不 reload |
| No config change | 渲染内容与正式配置一致 | 两次验证仍执行，复制任务 unchanged，Handler 不执行，Verify 正常运行 | validate/Verify 失败则报告失败 |
| Redaction check | 发送含虚构 Authorization 的 `/health` 请求 | 新日志记录包含 `REDACTED`，且不包含虚构 token | 明文 token 出现则验证失败并立即报告 |

</frozen-after-approval>

## Code Map

- `ansible/roles/unified-proxy/templates/Caddyfile.j2` -- `proxy.willfan.me` site 与待新增文件 access log。
- `ansible/roles/unified-proxy/tasks/main.yml` -- Caddyfile template、validate、服务状态及通知顺序。
- `ansible/roles/unified-proxy/handlers/main.yml` -- 待从 restart 改为 graceful reload 的 Caddy Handler。
- `ansible/playbooks/deploy-unified-proxy.yml` -- `caddy-config` 最小部署入口与独立 Verify play tag。

## Tasks & Acceptance

**Execution:**
- [x] `ansible/roles/unified-proxy/templates/Caddyfile.j2` -- 在现有 site block 添加固定文件日志及 Caddy 内置轮转，不改 reverse proxy/header。
- [x] `ansible/roles/unified-proxy/tasks/main.yml` -- 用带 `always` 清理的 block 渲染 caddy-owned 临时候选、以 `caddy` 用户验证、原子复制到正式路径并 notify `Reload Caddy`、再次以 `caddy` 用户验证最终路径；验证命令非零自然失败且 `changed_when: false`；为完整 Caddy 配置链添加 `caddy-config` tag。
- [x] `ansible/roles/unified-proxy/handlers/main.yml` -- 将 Caddy Handler 改名并改为 `ansible.builtin.systemd state: reloaded`，使用已核实的 unit `ExecReload` 零停机加载。
- [x] `ansible/playbooks/deploy-unified-proxy.yml` -- 增加 `caddy-config` usage，并让 Verify play响应该 tag，确保最小部署后仍验证后端健康。

**Acceptance Criteria:**
- Given access log 模板变更，when 列出 `--tags caddy-config` 任务，then 只选择 Caddy template/validate/start 与 Verify任务，不选择 code/auth/env 部署任务，且 template 的 notify 静态指向 `Reload Caddy`。
- Given Caddyfile 无效，when 候选验证失败，then 正式磁盘配置不变、临时候选被清理且 Caddy不会 reload。
- Given Caddyfile 有效，when Handler 执行，then systemd 使用 reload 而非 restart，现有连接不因服务停止而中断。
- Given生产部署完成，when 请求 `/health`，then响应为 ok/degraded，Caddy active，access log出现新记录。
- Given使用虚构 Authorization 值发起验证请求，when检查对应日志，then记录显示 `REDACTED` 且不包含该虚构值。
- Given本地修改完成，when运行 syntax check、tag task listing与 `git diff --check`，then全部成功。

## Spec Change Log

- **Iteration 1 — candidate-first validation:** 独立审查发现“先覆盖正式 Caddyfile、再验证”会在失败时留下无效磁盘配置，且 root validation 可能创建 root-owned access log。实施方式改为 caddy-owned 临时候选 → `become_user: caddy` 验证 → 原子部署 → 最终路径复验 → `always` 清理。避免下一次重启读取坏配置及日志文件所有权错误。KEEP：固定文件日志与 50MiB/10 轮转、现有 reverse_proxy/header 不变、graceful reload、`caddy-config` 最小部署、生产脱敏验证。

## Design Notes

配置先渲染到 `tempfile` 动态创建的临时候选路径，由 `caddy` 用户运行 `caddy validate`，避免验证过程以 root provision 文件日志并产生错误所有权。候选通过后由 `copy remote_src` 原子更新正式配置并排队 Handler，再以同一运行用户验证最终路径。整个序列放在带 `always` 清理的 block 中；候选验证失败时正式文件不变，临时文件仍会删除。选择 reload 是因为 unit 已提供 `ExecReload=/usr/bin/caddy reload ... --force`，Caddy会原子加载有效配置而不停止服务。

本次是首次新增文件日志 writer，reload 应创建并启用它。未来若只修改同一路径 writer 的 roll参数，应重新核对 Caddy对 writer重用的行为，必要时安排受控 restart。

## Verification

**Commands:**
- `ANSIBLE_LOCAL_TEMP=/tmp/ansible-unified-proxy-log ansible-playbook -i localhost, playbooks/deploy-unified-proxy.yml --syntax-check` -- 预期语法通过。
- `ANSIBLE_LOCAL_TEMP=/tmp/ansible-unified-proxy-log ansible-playbook -i localhost, playbooks/deploy-unified-proxy.yml --list-tasks --tags caddy-config` -- 预期只列 Caddy配置链与 Verify。
- `git diff --check` -- 预期无空白错误。
- `ansible-playbook playbooks/deploy-unified-proxy.yml --tags caddy-config` -- 审查通过并再次确认后才执行生产最小部署。

**Production checks:**
- 在目标机运行 `caddy validate --config /etc/caddy/Caddyfile` 与 `systemctl is-active caddy`。
- 请求 `https://proxy.willfan.me/health` 并确认状态为 ok/degraded。
- 使用不含真实密钥的虚构 Authorization header再请求一次，读取新增 access log；确认匹配记录包含 `REDACTED` 且不包含虚构 token。
- 检查 `/var/log/caddy/access.log` 存在、由 Caddy写入，并查看最后两行。

## Deployment Result

- `2026-08-12` 首次 `--tags caddy-config` 成功验证、部署并 reload Caddy；随后 Verify 暴露第二个 play 无法继承 role defaults，`proxy_port` 未定义。
- Verify 把 role defaults 加载进 `unified_proxy_defaults` 命名空间，并优先使用 inventory 中的 `proxy_port`、未定义时才回退到 default，保留正常变量优先级；本地 syntax、tag listing 与 diff check 重新通过。
- 第二次最小部署全部通过，正式配置 unchanged，后端 health 返回 `status: ok`。
- 正式 `caddy validate` 返回 `Valid configuration`，`systemctl is-active caddy` 返回 `active`。
- `/var/log/caddy/access.log` 存在，属主 `caddy:caddy`、权限 `0600`；公开 HTTPS 测试请求记录状态 200，Authorization 为 `REDACTED`，未出现虚构 token 明文。
- Caddy 输出非阻断的 `caddy fmt` 格式警告；未为纯格式调整改动既有 reverse_proxy/header 块。
- 最终 `--tags verify` 通过，`ok=5, changed=0`，确认变量回退修复未产生部署副作用。

## Suggested Review Order

**安全部署路径**

- 先验证动态候选，再原子部署并确保失败清理。
  [`main.yml:207`](../../ansible/roles/unified-proxy/tasks/main.yml#L207)

- 仅内容变化时执行零停机 reload。
  [`main.yml:12`](../../ansible/roles/unified-proxy/handlers/main.yml#L12)

**日志行为**

- 文件日志使用 Caddy 内置 50MiB/10 轮转。
  [`Caddyfile.j2:2`](../../ansible/roles/unified-proxy/templates/Caddyfile.j2#L2)

**最小部署入口**

- 专用 tag 避免更新 Node 源码和凭据。
  [`deploy-unified-proxy.yml:12`](../../ansible/playbooks/deploy-unified-proxy.yml#L12)

- 配置应用后复用独立后端健康检查。
  [`deploy-unified-proxy.yml:27`](../../ansible/playbooks/deploy-unified-proxy.yml#L27)
