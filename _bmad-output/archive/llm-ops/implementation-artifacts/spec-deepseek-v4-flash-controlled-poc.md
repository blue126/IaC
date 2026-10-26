---
title: 'Prepare DeepSeek V4 Flash controlled PoC Phase 0'
type: 'feature'
created: '2026-08-13'
status: 'done'
review_loop_iteration: 0
baseline_commit: '04f404ed108cf6e34e9290dfe58aed1854630c2b'
context:
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/architecture.md'
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/implementation-phases.md'
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/acceptance-contract.md'
  - '{project-root}/_bmad-output/specs/spec-deepseek-v4-flash-controlled-poc/release-manifest.md'
  - '{project-root}/docs/designs/ansible-role-architecture.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 现有 `llm-server` 是会安装驱动、下载并启动 MiniMax/Qwen/GLM 的 GGUF 栈，无法安全承载 DeepSeek V4 Flash，也缺少固定发布集、完整 API fixture、证据门控和可恢复生命周期。

**Approach:** 仅实施 Phase 0：建立独立、默认离线且 fail-fast 的 DeepSeek role/playbook、受控生命周期、release manifest、Open WebUI bootstrap、contract/benchmark fixtures，并退役 legacy 的未来生产入口；不触碰 VM 或 guest。

## Boundaries & Constraints

**Always:** DeepSeek 使用独立路径、Compose project、unit 和端口；TP1 默认单卡、16K、并发 1、MTP off；模型只读挂载，容器非 privileged、默认 loopback/私网、有界日志；systemd 只编排和强制与精确 legacy units 互斥，Compose 独占容器 restart；model revision、image digest、entrypoint/parser 等未知值保持 `unresolved` 并阻止变更型标签；Open WebUI 仅在数据库不存在或为空时生成一次性 seed，已有数据库只备份和验证；所有脚本输出结构化、可审计 JSON。

**Ask First:** 任何 VM/ESXi/guest 访问、下载、服务启停、文件删除、驱动/Toolkit 变更、远端 check mode、模型盘/网络/API 认证决定，或发现必须修改 Terraform、Vault、Open WebUI 数据库 schema 和现有 `ik_llama.cpp` pin 时暂停。

**Never:** 不执行 Phase 1–5；不运行真实部署；不删除 guest 权重或 stale 配置；不把两张 3090 当作统一 48 GB；不使用 `main`/`latest` 或猜测 digest/revision/parser flags；不升级、覆盖或复用旧 ik_llama checkout；不自动提交或 push。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Offline render | fixture 提供完整固定发布集 | 渲染合法 Compose/unit/manifest；无网络或主机变更 | 任一浮动/空 pin 立即失败 |
| Production variables unresolved | 默认 inventory sentinel | syntax/self-test 可运行，任何变更型入口被阻止 | 列出未解析字段且不执行任务 |
| Fresh WebUI | DB 不存在或为空 | 只生成一次性 DeepSeek connection seed | seed 输入不完整则停止 |
| Existing WebUI | 非空 DB 已存在 | 创建备份计划并只读验证，不渲染覆盖连接 | DB/备份目标不可判定则停止 |
| Legacy artifacts remain | guest 仍有三个旧 unit/env/ot | 获批后的 lifecycle 精确 stop/disable 配置入口，不删除权重 | 非白名单目标或活动 owner 不明则停止 |
| Contract fixture failure | malformed SSE/DSML/tool output | runner 返回非零并写机器可读失败证据 | 不把畸形调用判为成功 |

</frozen-after-approval>

## Code Map

- `ansible/inventory/host_vars/llm-server.yml` -- 移除 legacy boot/download desired state，声明 DeepSeek 基线和 unresolved pins。
- `ansible/playbooks/deploy-llm-server.yml` -- 旧生产入口；改为明确退役且不得调用 legacy role。
- `ansible/playbooks/deploy-deepseek-v4.yml` -- 新 Deploy + Verify/benchmark 编排及窄标签边界。
- `ansible/roles/deepseek-v4/` -- validation、离线配置、manifest、WebUI bootstrap、preflight/artifact/lifecycle/verify/benchmark 实现。
- `ansible/roles/llm-benchmark/` -- 可复用资源与 JSON 报告骨架，扩展为固定 corpus 和通用时延指标。

## Tasks & Acceptance

**Execution:**
- [x] `ansible/inventory/host_vars/llm-server.yml`、`ansible/playbooks/deploy-llm-server.yml` -- 删除三旧模型/boot 目标并让旧入口无条件安全退出，确保未来运行不能下载或启动 legacy。
- [x] `ansible/roles/deepseek-v4/defaults/main.yml`、`tasks/{main,validate,config,webui,lifecycle,preflight,artifact,verify,benchmark}.yml` -- 实现 sentinel 校验、只读/变更边界、精确 legacy 白名单互斥及幂等标签；无 action 的默认路径只校验并明确停止。
- [x] `ansible/roles/deepseek-v4/templates/{docker-compose.yml.j2,deepseek-v4.service.j2,release-manifest.yml.j2,open-webui-seed.env.j2}` -- 渲染固定、隔离、最小权限的运行定义和 unresolved 阻断 manifest；数据库初始化后不再拥有 connection。
- [x] `ansible/roles/deepseek-v4/files/` -- 增加版本化 correctness corpus、OpenAI/SSE/reasoning/tool/continuation/malformed fixtures、JSON schema、preflight/contract/benchmark runner 与 canned-response self-test。
- [x] `ansible/roles/llm-benchmark/` -- 保留兼容默认值，增加 model/seed/重复采样、1K/8K×256 corpus、TTFT/E2E/median decode、资源与阈值 verdict 的结构化输出。
- [x] `ansible/playbooks/deploy-deepseek-v4.yml` -- 显式编排 role 和 Verify/benchmark plays；`config/preflight/artifact/lifecycle/verify/benchmark` 标签互不越权，未获 gate 的任务不在默认执行路径。
- [x] `ansible/tests/deepseek-v4/` -- 建立 localhost render、fresh/existing WebUI 分支、manifest/schema、policy 和 runner 自测，覆盖矩阵全部边界且只写临时目录。

**Acceptance Criteria:**
- Given 干净本地 checkout 且不连接 inventory 主机，when 执行 syntax、render、fixture self-test 和 policy tests，then 全部通过且没有远端或外部状态变化。
- Given 默认 unresolved pins，when 选择 artifact/lifecycle/deploy 等变更型路径，then 在首个变更前失败并准确列出缺失发布字段。
- Given 渲染后的 Compose，when 执行 `docker compose config` 和策略检查，then digest、只读模型卷、loopback/私网、非 privileged、最小 capability 和日志上限均可判定。
- Given legacy inventory 与旧 playbook，when 静态审查生产路径，then MiniMax/Qwen/GLM 不可被选择、下载或启动，只有受 gate 保护的精确退役白名单可以引用其 unit。
- Given fresh 与 existing WebUI fixtures，when 分别渲染，then 仅 fresh 分支包含 seed，existing 分支只产生备份/验证计划且不包含连接覆盖值。
- Given canned API responses，when runner 覆盖同步、SSE、reasoning、单个/并行 tool、continuation 和 malformed 输出，then 合法案例产生版本化 JSON pass，畸形案例安全失败。

## Spec Change Log

## Design Notes

`deepseek-v4` 不依赖旧 `llm-server` role；后者保留为历史实现但失去生产入口。运行时 pins 由后续获批的 artifact gate 解析后写入 host vars，Phase 0 测试使用显式 fixture pins，不把研究时间点值伪装成晋级版本。systemd unit 不默认 enable/start，后续 lifecycle action 必须先停止三个精确 legacy units，再启动 Compose；任何额外匹配目标均失败。

## Verification

**Commands:**
- `cd ansible && ANSIBLE_LOCAL_TEMP=/tmp/ansible-local-deepseek ANSIBLE_REMOTE_TEMP=/tmp/ansible-remote-deepseek ansible-playbook -i 'llm-server,' playbooks/deploy-deepseek-v4.yml --syntax-check` -- expected: 无动态 inventory/远端连接且成功。
- `cd ansible && yamllint playbooks/deploy-deepseek-v4.yml roles/deepseek-v4 tests/deepseek-v4 && ansible-lint -x role-name,no-handler playbooks/deploy-deepseek-v4.yml roles/deepseek-v4` -- expected: 新增范围零错误；排除仓库命名约定冲突与既有 `disk.yml` 债务。
- `cd ansible && ansible-playbook -i 'localhost,' tests/deepseek-v4/render.yml --connection=local` -- expected: fresh/existing 与 unresolved/resolved fixtures 全部通过，只写 `/tmp`。
- `docker compose -f /tmp/deepseek-v4/fresh/docker-compose.yml config --quiet` -- expected: 离线 Compose 校验成功；工具缺失则如实记录未执行。
- `python3 ansible/roles/deepseek-v4/files/contract-runner.py --self-test && python3 ansible/tests/deepseek-v4/policy-test.py` -- expected: contract/schema 与 legacy/浮动依赖/权限策略全部通过。

## Suggested Review Order

**入口与门控**

- 从窄标签入口理解离线、验证和基准边界。
  [`deploy-deepseek-v4.yml:2`](../../ansible/playbooks/deploy-deepseek-v4.yml#L2)

- 未固定发布字段或审批门不匹配时先行失败。
  [`validate.yml:14`](../../ansible/roles/deepseek-v4/tasks/validate.yml#L14)

**运行与恢复边界**

- Compose 固定镜像、只读模型、单卡和私网权限边界。
  [`docker-compose.yml.j2:2`](../../ansible/roles/deepseek-v4/templates/docker-compose.yml.j2#L2)

- 切换前停止 writer 并生成可验证 SQLite 快照。
  [`lifecycle.yml:46`](../../ansible/roles/deepseek-v4/tasks/lifecycle.yml#L46)

- 启动或 UI 初始化失败时恢复到安全状态。
  [`lifecycle.yml:120`](../../ansible/roles/deepseek-v4/tasks/lifecycle.yml#L120)

- 发布清单集中记录兼容发布集和证据位置。
  [`release-manifest.yml.j2:2`](../../ansible/roles/deepseek-v4/templates/release-manifest.yml.j2#L2)

**客户端与 API 合同**

- 数据库初始化状态决定 seed 或数据库权威分支。
  [`webui.yml:10`](../../ansible/roles/deepseek-v4/tasks/webui.yml#L10)

- 严格验证 reasoning、SSE、工具参数与续接语义。
  [`contract-runner.py:222`](../../ansible/roles/deepseek-v4/files/contract-runner.py#L222)

- 实际 tokenizer usage 校准 1K/8K 性能输入。
  [`benchmark-runner.py:54`](../../ansible/roles/deepseek-v4/files/benchmark-runner.py#L54)

**Legacy 退役与验证**

- 旧 role 无条件失败，无法再次激活历史模型。
  [`main.yml:4`](../../ansible/roles/llm-server/tasks/main.yml#L4)

- localhost 双分支证明 seed 不覆盖既有数据库配置。
  [`render.yml:2`](../../ansible/tests/deepseek-v4/render.yml#L2)

- 策略测试静态锁定权限、pin、网络和退役不变量。
  [`policy-test.py:14`](../../ansible/tests/deepseek-v4/policy-test.py#L14)
