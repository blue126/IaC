---
title: '固定 LLM GPU 平台内核与 NVIDIA 运行时'
type: 'bugfix'
created: '2026-08-17'
status: 'done'
baseline_commit: 'a3d766b2d00ece89b79789b4535102d13dec7c59'
review_loop_iteration: 0
context:
  - '{project-root}/docs/designs/ansible-role-architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `unattended-upgrade` 在 2026-08-14 将 VM 内核从已验证的 `6.8.0-101` 推进到 `6.8.0-137`，但没有同步提供 NVIDIA 590 模块；2026-08-17 重启后 `nvidia.ko` 缺失，两张已透传的 3090 无法使用。

**Approach:** 在 `deepseek-v4-ik` 中增加显式 `platform` action，把 `6.8.0-101-generic + NVIDIA 590.48.01 Open` 作为不可拆分的版本束，独立管理包保护、GRUB、VM 重启门和验证。

## Boundaries & Constraints

**Always:** 精确验证内核、用户态驱动和预编译模块版本；platform 默认关闭并与其他 lifecycle action 互斥；保留其他 unattended security updates；确认目标包和 GRUB 项后才允许重启；重启后要求目标内核、`modinfo nvidia` 和两张 RTX 3090 均正确；保持幂等并保留现有改动。

**Ask First:** 升级到任何其他内核/NVIDIA 组合；删除已安装内核或驱动包；改为 DKMS；全局关闭 unattended-upgrades；重启 ESXi；提交 Git 改动。

**Never:** 调用或重新启用已退役 `llm-server` 主入口；让 experiment 或 production 隐式执行 platform action；混用 NVIDIA 590 用户态与 595 内核模块；自动 purge `6.8.0-137`；触碰无关 Anki/OCI/Caddy 改动；在平台校验失败时启动 DeepSeek 实验。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| 首次恢复 | 当前运行 `137`，完整 `101/590` 版本束已安装，显式批准 VM reboot | 固定包和 GRUB，VM 启动到 `101`，两卡可见 | 任一前置条件失败则不重启 |
| 未批准重启 | 当前内核不是目标且 reboot gate=false | 完成安全配置后明确报告需要 VM 重启 | fail closed，不触发 handler/reboot |
| 已达稳态 | 当前运行目标内核且包/GRUB/holds 正确 | 幂等完成，不重启 | 验证失败即停止 |
| 版本束缺失 | 精确包版本、GRUB 项或 NVIDIA 模块缺失 | 不改变启动目标 | 列出缺失项并失败 |

</frozen-after-approval>

## Code Map

- `ansible/roles/deepseek-v4-ik/defaults/main.yml` -- 版本束、platform action 和 reboot gate。
- `ansible/roles/deepseek-v4-ik/tasks/main.yml` -- platform 的 exactly-one lifecycle 门。
- `ansible/roles/deepseek-v4-ik/tasks/platform.yml` -- 前置验证、包保护、GRUB、VM reboot 和验收。
- `ansible/roles/deepseek-v4-ik/templates/99-deepseek-v4-kernel.cfg.j2` -- GRUB 默认项。
- `ansible/roles/deepseek-v4-ik/handlers/main.yml` -- `update-grub` handler。
- `ansible/playbooks/qualify-deepseek-v4-ik.yml` -- 显式 platform play。
- `ansible/inventory/host_vars/llm-server.yml` -- 主机精确版本束。
- `ansible/tests/deepseek-v4-ik/render.yml` -- action、互斥和非法组合测试。
- `ansible/tests/deepseek-v4/policy-test.py` -- 静态 fail-closed 策略测试。

## Tasks & Acceptance

**Execution:**
- [x] 扩展 `deepseek-v4-ik` 的 exactly-one lifecycle gate，新增独立 platform action；验证精确 Debian 包版本与目标内核模块，保护 kernel/NVIDIA tracking 包并仅排除该版本束的自动升级。
- [x] 渲染 GRUB drop-in；验证 menuentry 后执行 `update-grub`，仅在显式 gate=true 且当前内核不匹配时重启 VM。
- [x] 在现有 qualification playbook 中增加 platform play；Verify 检查内核、模块版本、两卡身份、holds 和自动升级排除规则。
- [x] 增加本地策略测试和 syntax-check；随后仅运行平台 playbook，恢复后执行现有双 GPU topology/P2P preflight。

**Acceptance Criteria:**
- Given VM 运行 `6.8.0-137` 且目标版本束完整，when 以显式 reboot gate 部署，then VM 启动到 `6.8.0-101-generic`、NVIDIA 驱动为 `590.48.01` 且发现两张 RTX 3090。
- Given 任一目标包、模块或 GRUB 项缺失，when 部署，then 在修改启动目标或重启前失败并报告准确缺口。
- Given 平台已处于目标状态，when 重跑 playbook，then 不发生额外重启且 Verify 全部通过。
- Given unattended-upgrades 保持启用，when 检查策略，then kernel/NVIDIA 版本束不会自动推进，其他安全更新未被全局禁用。
- Given GPU 恢复完成，when 运行 topology preflight，then 生成两卡链路宽度、拓扑和 P2P 的新证据后才恢复性能实验。

## Spec Change Log

- 2026-08-17：实现并实机验收 platform action；VM 恢复到目标 kernel/driver，双 GPU
  可见，幂等 verify 通过。Slot2/Slot4 topology 为 `PHB`，但 P2P 仍为 `NS`，因此 graph
  split 继续阻断。

## Design Notes

platform action 复用现有互斥与测试框架，但不会被其他 action 隐式调用。保留 `6.8.0-137` 作救援项，GRUB 默认固定到 `101`；未来升级须把内核、预编译 NVIDIA 模块和用户态驱动整体重验。生产路径不引入 DKMS。

## Verification

**Commands:**
- `cd ansible && ansible-playbook playbooks/qualify-deepseek-v4-ik.yml --syntax-check` -- 语法通过。
- `python3 ansible/tests/deepseek-v4/policy-test.py` -- 平台策略通过。
- `cd ansible && ansible-playbook -i 'localhost,' tests/deepseek-v4-ik/render.yml` -- action/互斥测试通过。
- `cd ansible && ansible-playbook playbooks/qualify-deepseek-v4-ik.yml --tags platform --check --diff` -- 预演无意外变更。
- `cd ansible && ansible-playbook playbooks/qualify-deepseek-v4-ik.yml --tags platform -e deepseek_v4_ik_platform_allow_reboot=true` -- 受控恢复 VM。
- `cd ansible && ansible-playbook playbooks/qualify-deepseek-v4-ik.yml --tags platform-verify` -- 内核、模块、两卡和 holds 正确。

**Live result:** 运行内核为 `6.8.0-101-generic`，NVIDIA module/userspace 为
`590.48.01`，两张精确 RTX 3090 可见，11 个精确包处于 hold；`platform-verify` 幂等
重跑为 `changed=0`。unattended-upgrades service/timer 保持启用。

## Suggested Review Order

1. [Platform lifecycle and verification](../../ansible/roles/deepseek-v4-ik/tasks/platform.yml)
2. [Exactly-one action gate](../../ansible/roles/deepseek-v4-ik/tasks/main.yml)
3. [Pinned platform defaults](../../ansible/roles/deepseek-v4-ik/defaults/main.yml)
4. [Qualification playbook](../../ansible/playbooks/qualify-deepseek-v4-ik.yml)
5. [Render and policy tests](../../ansible/tests/deepseek-v4-ik/render.yml)
