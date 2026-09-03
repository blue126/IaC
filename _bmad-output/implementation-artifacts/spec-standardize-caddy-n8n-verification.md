---
title: 'Standardize Caddy and n8n verification plays'
type: 'bugfix'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'f9c5982fd607215058171990a34d423e50920f37'
context:
  - '{project-root}/docs/designs/ansible-role-architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `deploy-caddy.yml` 没有独立 Verify play，部署完成后直接显示成功但未检查 Caddy；`deploy-n8n.yml` 虽有 Verify play，却没有 `verify` tag，无法通过 `--tags verify` 单独运行。

**Approach:** 为 Caddy 增加最小、仅依赖目标机本地状态的 Verify play；为 n8n 现有 Verify play 添加 play-level `verify` tag，使两个 playbook 都符合仓库的 Deploy + Verify 约定。

## Boundaries & Constraints

**Always:** Verify 必须位于 Deploy play 之后，使相关 Handler 先在 play 边界执行；Caddy 验证应确认 WebDAV 监听端口可连接，并确认未认证 HTTP 请求返回预期的 `401` 与 Basic authentication challenge；输出必须明确说明这是受保护端点的预期负向认证结果，不得将其表述为普通 HTTP 健康请求成功；新增或修改的模块调用使用 FQCN；`--tags verify` 不应执行 bootstrap 或部署 role。

**Ask First:** 如果可靠验证必须依赖公网 DNS、TLS/ACME、外部反向代理上游、明文 WebDAV 凭据或修改服务配置，必须暂停并征求用户确认。

**Never:** 不得修改 Caddy/n8n role、Handler、模板、端口或认证设置；不得借机重构 n8n 现有验证任务；不得把公网域名或上游服务可用性作为 Caddy 部署的硬性成功条件；不得运行真实部署。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Full Caddy deploy | 不带 tag 执行 playbook | Deploy 和 post_tasks 完成，Handler 执行，然后 Verify 检查本机 WebDAV，并说明 401 是预期认证挑战 | 端口未监听、HTTP 状态不是 401 或缺少 Basic challenge 时失败 |
| Caddy verify only | `--tags verify` | 只执行 Caddy Verify play并输出认证挑战说明 | 不执行 SSH/Python bootstrap 或 caddy role |
| Full n8n deploy | 不带 tag 执行 playbook | 保持现有 Deploy + Verify 行为 | 现有验证语义不变 |
| n8n verify only | `--tags verify` | 只执行现有 n8n Verify tasks | 不执行 n8n role |

</frozen-after-approval>

## Code Map

- `ansible/playbooks/deploy-caddy.yml` -- Caddy bootstrap、Deploy 与待新增 Verify 编排。
- `ansible/playbooks/deploy-n8n.yml` -- 已有 Verify play，缺少 play-level tag。
- `ansible/roles/caddy/templates/Caddyfile.j2` -- WebDAV 8080 路由及 basic auth 语义，只读参考。
- `ansible/roles/caddy/defaults/main.yml` -- `caddy_webdav_port` 默认值，只读参考。

## Tasks & Acceptance

**Execution:**
- [x] `ansible/playbooks/deploy-caddy.yml` -- 在 Deploy play 后新增 `Verify Caddy Deployment` play，禁用 facts，添加 `verify` tag，等待 `caddy_webdav_port`，以未认证 GET 断言 HTTP 401 与 Basic challenge，并输出该负向测试的明确解释。
- [x] `ansible/playbooks/deploy-n8n.yml` -- 为现有 Verify play 添加 `tags: [verify]`，不改变其任务内容。

**Acceptance Criteria:**
- Given Caddy 部署产生 `Restart caddy` 通知，when Deploy play 完成，then Handler 在 Caddy Verify play 开始前执行。
- Given `--tags verify` 用于 Caddy，when 列出任务，then 只选择新增的端口和 HTTP 验证任务，不选择 bootstrap 或 role。
- Given WebDAV basic auth 正常启用，when Caddy Verify 未携带凭据请求本机端点，then HTTP 401 与 Basic challenge 被视为预期结果，输出明确说明它证明认证拦截生效，而不是普通健康请求成功。
- Given `--tags verify` 用于 n8n，when 列出任务，then 只选择现有 n8n Verify play 的全部任务，不选择 n8n role。
- Given 两个 playbook 修改完成，when 运行 syntax check 与 `git diff --check`，then 均成功。

## Spec Change Log

## Design Notes

Caddy Verify 使用本机 `http://localhost:{{ caddy_webdav_port }}/`，预期 `401` 和 `WWW-Authenticate: Basic`。这是未携带凭据时的预期负向认证测试：它证明 Caddy 监听、WebDAV 路由和 basic auth 拦截生效，但不宣称已完成一次成功的 WebDAV 业务访问。结果输出必须明确表达这一区别，同时避免把 DNS、证书签发或反向代理上游等外部系统纳入本次部署门槛。

## Verification

**Commands:**
- `ANSIBLE_LOCAL_TEMP=/tmp/ansible-caddy-n8n-verify ansible-playbook -i 'caddy,n8n,pve0,' playbooks/deploy-caddy.yml --syntax-check` -- 预期语法通过。
- `ANSIBLE_LOCAL_TEMP=/tmp/ansible-caddy-n8n-verify ansible-playbook -i 'caddy,n8n,pve0,' playbooks/deploy-n8n.yml --syntax-check` -- 预期语法通过。
- 对两个 playbook 分别运行 `--list-tasks --tags verify` -- Caddy 只列端口、认证挑战和结果说明任务，n8n 只列现有 Verify tasks。
- `git diff --check` -- 预期无空白错误。

## Suggested Review Order

**Caddy 验证边界**

- 独立 Verify play 确保 Handler 完成后再验证本机服务。
  [`deploy-caddy.yml:66`](../../ansible/playbooks/deploy-caddy.yml#L66)

- 无凭据请求禁用 netrc，并明确期待 HTTP 401。
  [`deploy-caddy.yml:78`](../../ansible/playbooks/deploy-caddy.yml#L78)

- Basic challenge 断言证明认证拦截配置已加载。
  [`deploy-caddy.yml:87`](../../ansible/playbooks/deploy-caddy.yml#L87)

- 输出区分负向认证测试与成功 WebDAV 业务访问。
  [`deploy-caddy.yml:95`](../../ansible/playbooks/deploy-caddy.yml#L95)

**n8n 验证入口**

- Play-level tag 使现有验证可通过 `--tags verify` 单独运行。
  [`deploy-n8n.yml:9`](../../ansible/playbooks/deploy-n8n.yml#L9)
