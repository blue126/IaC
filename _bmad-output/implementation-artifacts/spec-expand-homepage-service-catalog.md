---
title: '扩展 Homepage 服务目录'
type: 'feature'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
baseline_commit: '9b7faaf65256f0193b34b1db172ff475139b566e'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Homepage 遗漏多个已有 Web 界面，分组未区分交互入口和后台端点；部分现有地址也已失效。

**Approach:** 扩展服务模板并同步布局：补齐主要 Web 入口，将非交互服务整理为状态卡，并修正过期信息。

## Boundaries & Constraints

**Always:** 使用 `Infrastructure`、`Applications`、`Operations`、`Service Health` 四组；新增 n8n、Open WebUI、PBS、Jenkins、Gitea、Anki Desktop；NetBox 使用现有 HTTPS 域名；Oracle Cloud 使用当前 inventory IP；地址和 Proxmox 元数据以仓库最新事实为准；模板保持合法 YAML/Jinja；验证不得输出凭据。

**Ask First:** 如事实冲突，或需要修改 Caddy、DNS、Vault、网络、服务部署及文件权限，暂停并征求决定。

**Never:** 不新增 vCenter；不改服务、反向代理、凭据或 Terraform；不把 RustDesk、unified-proxy、Anki Sync、LLM API 伪装成普通 UI；不自动部署或提交；不泄露敏感值。

</frozen-after-approval>

## Code Map

- `ansible/roles/homepage/templates/services.yaml.j2` -- 服务卡片、URL、探测及 Proxmox 元数据。
- `ansible/roles/homepage/templates/settings.yaml.j2` -- 四组布局。
- `ansible/inventory/host_vars/caddy.yml` -- HTTPS 反向代理事实。
- `ansible/inventory/host_vars/llm-server.yml` -- LLM 服务地址事实。
- `docs/incidents/2026-04-12-pve0-nvme-controller-hang.md` -- PBS 迁移事实。

## Tasks & Acceptance

**Execution:**
- [x] `ansible/roles/homepage/templates/services.yaml.j2` -- 重组四组，新增六个入口和后台状态卡，修正 NetBox/OCI。
- [x] `ansible/roles/homepage/templates/settings.yaml.j2` -- 补齐四组布局。

**Acceptance Criteria:**
- Given 模板被渲染，when Homepage 加载配置，then 四组顺序正确且均有布局定义。
- Given 六个交互服务，when 查看 Homepage，then 每项均有准确可用的入口。
- Given 旧配置，when 新模板生效，then NetBox 指向 `https://netbox.willfan.me`，OCI 不再引用 `152.67.113.23`。
- Given PBS 已迁移，when 显示运行归属，then 元数据为 pve1 / VMID 113 / QEMU。
- Given 四个后台端点，when 展示服务状态，then 位于 Service Health 且无误导性 UI 链接。
- Given 修改完成，when 本地验证，then syntax-check、Jinja 渲染和 YAML 解析通过且日志无凭据。

## Spec Change Log

## Design Notes

OCI 保留为基础设施状态项并移除过期 SSH 入口。Applications 放日常产品，Operations 放管理控制台，Service Health 放协议/API。PBS 归属采用最新事故记录，不采用旧 ESXi Terraform 定义。

## Verification

**Commands:**
- `cd ansible && ansible-playbook playbooks/deploy-homepage.yml --syntax-check` -- expected: 成功且不打印凭据。
- 使用非敏感 fixture 渲染两个模板并解析 YAML，断言分组顺序、六个入口、NetBox/OCI、PBS 元数据及四个无 `href` 状态卡 -- expected: 全部断言通过。
- `git diff --check` -- expected: no whitespace errors.

**Results (2026-08-13):**
- Ansible syntax-check passed; dynamic Terraform inventory emitted sandbox network warnings, but the playbook parsed successfully.
- Non-secret Jinja rendering, YAML parsing, and all acceptance assertions passed.
- `git diff --check` passed.

## Suggested Review Order

**服务目录结构**

- 从基础设施入口开始，核对修正地址与 PBS 最新归属。
  [`services.yaml.j2:15`](../../ansible/roles/homepage/templates/services.yaml.j2#L15)

- 检查六个新增交互入口及其 LAN/Proxmox 元数据。
  [`services.yaml.j2:71`](../../ansible/roles/homepage/templates/services.yaml.j2#L71)

- 运维控制台独立分组，避免与日常应用混杂。
  [`services.yaml.j2:95`](../../ansible/roles/homepage/templates/services.yaml.j2#L95)

**健康状态边界**

- 后台协议和 API 无普通入口，仅呈现状态信息。
  [`services.yaml.j2:140`](../../ansible/roles/homepage/templates/services.yaml.j2#L140)

**展示与后续工作**

- 四组布局与服务模板保持同名同序。
  [`settings.yaml.j2:14`](../../ansible/roles/homepage/templates/settings.yaml.j2#L14)

- 迁移后的 Terraform 与仓库一致性留作独立任务。
  [`deferred-work.md:1`](deferred-work.md#L1)
