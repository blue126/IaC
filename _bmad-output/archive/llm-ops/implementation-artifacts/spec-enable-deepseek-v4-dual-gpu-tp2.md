---
title: 'Qualify DeepSeek V4 Flash dual-GPU TP2 profile'
type: 'feature'
created: '2026-08-14'
status: 'done'
review_loop_iteration: 0
baseline_commit: '0d6ad67bc93bc19ff27d9643b4acb197f2a909bb'
context:
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/architecture.md'
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/acceptance-contract.md'
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-deepseek-flash-v4-deployment-feasibility-research-2026-08-13.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 已部署的 DeepSeek V4 Flash 目前强制单张 RTX 3090、TP1，第二张卡未参与推理，实际交互首 token 延迟很高。双卡是既有架构规定的下一步单变量实验，但 GPU0↔GPU1 经 PCIe Host Bridge 连接且 P2P 显示不支持，不能假设 TP2 一定更快或稳定。

**Approach:** 增加一个默认仍为 TP1 的显式性能 profile，并实现受限的 TP2 profile：只允许两张已验证 GPU 同时暴露给容器、`TP=2`，其余正确性基线不变。以固定合同与基准采集 TP2 证据；若无法启动、正确性/稳定性失败或无至少 10% 用户体验/吞吐改善，自动恢复 TP1。

## Boundaries & Constraints

**Always:** 两张 24GB 卡保持独立显存，不增加 GPU experts、并发、context、MTP、镜像、模型 revision 或端口暴露；TP1 默认 profile 必须继续可渲染和可恢复；TP2 仅接受 GPU ordinals `["0", "1"]` 与 `TP=2`，TP1 仅接受 `["0"]` 与 `TP=1`；容器继续最小权限、只读模型卷、loopback 与 Open WebUI 网关 API；每轮保存 profile、拓扑、两卡资源、TTFT/E2E/decode、错误和 restart 证据。

**Ask First:** 需要改变 GPU passthrough、驱动/CUDA、模型/缓存精度、GPU expert offload、context、并发、MTP，或 TP2 未达晋级门槛但要保留 TP2。

**Never:** 不将 48GB 当作统一显存，不删除模型/Open WebUI 数据/旧权重，不修改现有 Open WebUI 连接与认证，不升级 runtime image，不重启 ESXi，不自动提交。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|---------------------------|----------------|
| TP1 默认 | profile `tp1` | 渲染 GPU 0、`CUDA_VISIBLE_DEVICES=0`、`TP=1` | 无效 profile 在任何远端变更前失败 |
| TP2 候选 | profile `tp2` | 渲染 GPU 0/1 两个 CDI device、`CUDA_VISIBLE_DEVICES=0,1`、`TP=2` | 任一 GPU 缺失或 profile/TP 不匹配即失败 |
| TP2 启动或验收失败 | API、合同或资源证据失败 | 保存失败证据，恢复已知 TP1 渲染并验证 API/WebUI | 不留下两个大模型 owner 或未就绪后端 |
| TP2 无收益 | 正确但 TTFT/吞吐未改善至少 10% | 记录 No-Go，恢复 TP1 | 不把无证据 TP2 留作默认 |

</frozen-after-approval>

## Code Map

- `ansible/inventory/host_vars/llm-server.yml` -- 选择经过审批的 TP2 profile，不改变不可变 release pins。
- `ansible/roles/deepseek-v4/defaults/main.yml` -- 定义默认 TP1 和两个严格 profile 的 GPU 列表。
- `ansible/roles/deepseek-v4/tasks/validate.yml` -- 在任何 gate 前验证 profile、TP 和 GPU ordinals 的精确对应关系。
- `ansible/roles/deepseek-v4/templates/docker-compose.yml.j2` -- 由列表生成 CUDA visible devices 与独立 CDI device 条目。
- `ansible/roles/deepseek-v4/templates/release-manifest.yml.j2` -- 保存 profile、TP 和 GPU 列表证据。
- `ansible/roles/deepseek-v4/tasks/{verify,benchmark}.yml`、`ansible/roles/llm-benchmark/` -- 记录 TP2 合同、时延、两卡利用率和明确 promotion verdict。
- `ansible/tests/deepseek-v4/` -- 离线渲染/策略测试覆盖 TP1、TP2 和非法 profile。

## Tasks & Acceptance

**Execution:**
- [x] `defaults/main.yml`、`validate.yml` -- 引入严格 profile 合同；保留 TP1 为默认，拒绝任意其他 TP/GPU 组合。
- [x] `host_vars/llm-server.yml`、`docker-compose.yml.j2`、`release-manifest.yml.j2` -- 将 GPU 标量改为列表，TP2 仅渲染 `0,1` 和两个 CDI device，记录实际候选。
- [x] `verify.yml`、`llm-benchmark` 相关任务 -- 在 TP2 运行后执行确定性 API/合同与固定 corpus 基准，采集两卡资源/重启数并写 promotion/no-go 证据。
- [x] `lifecycle` 或专用回退任务 -- 任一启动、合同、资源或收益门槛失败时，应用 TP1 profile、重建 inference 并重新证明 API/Open WebUI 可用。
- [x] `ansible/tests/deepseek-v4/` -- 添加 TP1/TP2 Compose 渲染与非法组合 fail-fast 测试。

**Acceptance Criteria:**
- Given 默认配置，when 本地渲染，then 仍只声明 GPU 0 与 TP1。
- Given TP2 profile，when 渲染并执行 Compose config，then 恰有两个 GPU CDI device、`CUDA_VISIBLE_DEVICES=0,1` 和 `TP=2`，且模型卷与 API 边界不变。
- Given TP2 部署，when 完成合同、确定性 chat 与 1K/8K 基准，then 两卡都有可审计资源记录、无 OOM/持续 swap/restart churn，且 API 与 Open WebUI 可用。
- Given TP2 不满足正确性、稳定性或相对 TP1 的 ≥10% 改善，when 判定 No-Go，then 自动恢复 TP1 并通过 API 与 Open WebUI smoke test。

## Spec Change Log

- TP2 运行中 SGLang 子进程退出、GPU1 释放且健康检查出现连接拒绝；固定 1K/8K 基准未能完成。按冻结的 No-Go 规则恢复 TP1，并验证 API 与 Open WebUI 连通。

## Design Notes

P2P `NS` 不等于 TP2 必然不可用，但代表跨卡通信必须经 PCIe Host Bridge；因此这是一项证据化实验而非最终设计假设。CPU-resident MoE 继续不变，避免将多变量调优误归因于 TP2。

## Verification

**Commands:**
- `ansible-playbook playbooks/deploy-deepseek-v4.yml --syntax-check` -- 通过。
- `python3 ansible/tests/deepseek-v4/policy-test.py` -- TP1/TP2 渲染与策略断言通过。
- `docker compose -f <rendered-tp2-compose> config --quiet` -- Compose 有效。
- `ansible-playbook playbooks/deploy-deepseek-v4.yml --tags verify -e 'deepseek_v4_gate=verify'` -- API、模型 identity、合同和 WebUI 可用。
- `ansible-playbook playbooks/deploy-deepseek-v4.yml --tags benchmark -e 'deepseek_v4_gate=benchmark'` -- 产生可比较的 TP2 性能与资源 verdict。

## Suggested Review Order

**Profile contract and activation boundary**

- Restricts GPU exposure and tensor parallelism to two audited combinations.
  [`validate.yml:2`](../../ansible/roles/deepseek-v4/tasks/validate.yml#L2)

- Requires every selected GPU before a guarded activation can proceed.
  [`activate.yml:29`](../../ansible/roles/deepseek-v4/tasks/activate.yml#L29)

- Waits for the activation process instead of returning background success.
  [`activate.yml:56`](../../ansible/roles/deepseek-v4/tasks/activate.yml#L56)

**Runtime rendering**

- Turns the validated GPU list into CUDA visibility and separate CDI reservations.
  [`docker-compose.yml.j2:25`](../../ansible/roles/deepseek-v4/templates/docker-compose.yml.j2#L25)

- Preserves TP1 as the default while declaring the explicit TP2 candidate.
  [`main.yml:42`](../../ansible/roles/deepseek-v4/defaults/main.yml#L42)

**Offline safety evidence**

- Renders TP2 Compose through Docker validation and rejects unknown profiles.
  [`render.yml:159`](../../ansible/tests/deepseek-v4/render.yml#L159)

- Asserts profile, device, privilege, and release-record policy invariants.
  [`policy-test.py:35`](../../ansible/tests/deepseek-v4/policy-test.py#L35)
