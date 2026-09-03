---
title: 'Switch DeepSeek V4 to mainline DSpark'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
baseline_commit: '2d876ae3ef6d38b000d838077e306791f19960bf'
context:
  - '{project-root}/docs/designs/deepseek-v4-optimization-handoff.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

# Switch DeepSeek V4 to mainline DSpark

## Intent

**Problem:** homelab 当前仍运行 ik runtime；mainline llama.cpp、0731 UD-Q3_K_M 四分片和 Q8_0 DSpark 已准备完成，但尚未形成可重复的 Ansible 部署入口。

**Approach:** 新建轻量 `deepseek-v4-mainline` role 和部署 playbook，停止 ik 后让 mainline 直接接管 loopback backend `8082`，保持现有兼容代理 `8081` 与 Open WebUI 不变。DSpark `n_max=1/2` 已完成对比并采用整体表现更好的 `n_max=1`；只做启动所需的 pin 校验、健康检查和一次确定性 chat，失败时保留 mainline 现场继续排错，不自动恢复 ik。

## Boundaries & Constraints

**Always:** 固定 mainline HEAD `10bf611e533d81f739128304991c5e133c6aebd8`、binary SHA-256 `2e63f6a8aa2508d129aaef1d59769754e2ae37558b9eec3dbe8d0307ea4d7074`、runtime image digest与五个模型 SHA；容器内运行 binary，使用两张 GPU、`LD_LIBRARY_PATH=/build`、首分片自动加载其余分片、Q8_0 drafter、`--spec-type draft-dspark --spec-draft-n-max 2 --fit off`；模型只读挂载；切换前先验证全部 artifact；切换后的错误保留 mainline 现场并继续修复。

**Ask First:** 实际连接 guest 执行部署、修改任何 pin、改变 `n_max`、删除旧 ik runtime/模型或清理旧 service。

**Never:** 不把 ik role 改造成支持 mainline；不改兼容代理、Open WebUI、context、并发、PCIe/ESXi；不自动部署或 commit；不引入生产级 candidate、watchdog、soak、promotion/evidence 框架。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期行为 | 失败处理 |
|---|---|---|---|
| Artifact 合法 | HEAD、binary 与 5 模型 SHA 匹配 | 渲染并启动 mainline | — |
| Artifact 不符 | 任一 pin 不匹配 | 停止切换，不停止 ik | 报出不匹配文件 |
| mainline 启动成功 | `8082/health` 就绪 | `8081` health 与固定 chat 通过 | 保留 mainline |
| mainline 启动失败 | 容器退出、超时或 smoke 失败 | 保留 mainline 配置与现场 | 检查错误并继续修复，不自动回退 |

</frozen-after-approval>

## Code Map

- `ansible/roles/deepseek-v4-mainline/defaults/main.yml` — 固定 runtime/model pins、路径、端口和启动参数。
- `ansible/roles/deepseek-v4-mainline/tasks/main.yml` — artifact preflight、部署、失败回退和最小验证。
- `ansible/roles/deepseek-v4-mainline/templates/docker-compose.yml.j2` — mainline+DSpark 容器定义。
- `ansible/roles/deepseek-v4-mainline/templates/deepseek-v4-mainline.service.j2` — Compose systemd owner。
- `ansible/roles/deepseek-v4-mainline/handlers/main.yml` — systemd reload。
- `ansible/playbooks/deploy-deepseek-v4-mainline.yml` — Deploy + Verify 入口。
- `scripts/deepseek-v4-mainline-build.sh` — 修正 host/container 构建输出路径不一致。
- `docs/designs/deepseek-v4-optimization-handoff.md` — 改为快速切换的真实入口和验证步骤。

## Tasks & Acceptance

**Execution:**
- [x] 新建 mainline role defaults、Compose/systemd 模板和 playbook，不修改 ik role。
- [x] 在停止 ik 前校验 runtime HEAD/binary SHA与五个模型 SHA；渲染 mainline 配置。
- [x] 执行 ik→mainline 切换；失败时保留 mainline 现场继续排错。
- [x] 修正构建脚本路径分叉并同步交接文档。

**Acceptance Criteria:**
- Given artifact pin 不匹配，when 运行部署，then 在停止 ik 前失败。
- Given全部 pin 匹配，when部署，then只有 mainline 占用 backend `8082`，兼容代理仍提供 `8081`。
- Given mainline 就绪，when执行 Verify，then `/health` 与 `temperature=0, seed=42` 的固定 chat 成功。
- Given mainline 启动或验证失败，when任务停止，then不自动恢复 ik，并保留 mainline 现场供后续修复。

## Verification

**Commands:**
- `cd ansible && ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml --syntax-check` — playbook 语法通过。
- 经用户授权后运行部署；预期 mainline `8082/health`、稳定入口 `8081/health` 和固定 chat 通过，失败则 ik 自动恢复。

## Suggested Review Order

**切换入口与回退边界**

- 从唯一 playbook 入口理解快速部署与显式只读验证。
  [`deploy-deepseek-v4-mainline.yml:2`](../../ansible/playbooks/deploy-deepseek-v4-mainline.yml#L2)

- 所有 pin 在停止 ik 前锁定并逐项核验。
  [`main.yml:2`](../../ansible/roles/deepseek-v4-mainline/tasks/main.yml#L2)

- 目标机先解析 Compose，再进入带自动回退的 owner 切换。
  [`main.yml:169`](../../ansible/roles/deepseek-v4-mainline/tasks/main.yml#L169)

- block/rescue 管理 8082 释放、smoke 与 ik 恢复。
  [`main.yml:182`](../../ansible/roles/deepseek-v4-mainline/tasks/main.yml#L182)

- Verify 同时证明 Compose 容器、健康端点和精确 OK。
  [`verify.yml:23`](../../ansible/roles/deepseek-v4-mainline/tasks/verify.yml#L23)

**运行配置**

- Compose 固定多分片、Q8 drafter、双 GPU 与只读挂载。
  [`docker-compose.yml.j2:2`](../../ansible/roles/deepseek-v4-mainline/templates/docker-compose.yml.j2#L2)

- systemd 明确 mainline 与 ik owner 互斥。
  [`deepseek-v4-mainline.service.j2:1`](../../ansible/roles/deepseek-v4-mainline/templates/deepseek-v4-mainline.service.j2#L1)

**支持文件**

- 构建路径统一到 src/build，并使用固定容器工具链验证。
  [`deepseek-v4-mainline-build.sh:18`](../../scripts/deepseek-v4-mainline-build.sh#L18)

- 交接文档给出最短部署、验证与回退语义。
  [`deepseek-v4-optimization-handoff.md:119`](../../docs/designs/deepseek-v4-optimization-handoff.md#L119)
