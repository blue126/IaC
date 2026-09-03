---
title: 'Qwen3-TTS 克制旁白音色映射与默认指令'
type: 'feature'
created: '2026-09-02'
status: 'done'
review_loop_iteration: 0
baseline_commit: '693117e5de1b0c556554d586c3b573e1b9616e25'
context:
  - '{project-root}/_bmad-output/planning-artifacts/research/technical-qwen3-tts-audiobook-sampling-parameters-2026-09-01/research.md'
  - '{project-root}/docs/designs/qwen3-tts-openai-api-integration.md'
---

> **溯源说明(迁移时补充)**
>
> 本规格撰写时的实现目标是 `ansible/roles/qwen3-tts`,部署在 llm-server
> (192.168.1.247)。该主机已退役。正文中的文件路径与行号指向
> `baseline_commit` 当时的旧 role,保持原样以保留记录。
>
> 实际在运行的同一份实现现位于 `ansible/roles/qwen3-tts-workstation`
> (llm-workstation, 192.168.1.191)。`qwen3-tts-shim.py` 与
> `qwen3-tts-profile-bootstrap.py` 两个文件在两个 role 之间字节一致;
> role 层面的差异是去掉了 qwen36 共存断言与停止逻辑,新主机上没有该服务。

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前 13 个 Speech Central/OpenAI voice 槽位只暴露 5 个本地 preset，且包含偏明亮、活泼的重复音色；1.7B 请求也没有统一的克制旁白 instruction，无法按研究结论有效试听更多候选。

**Approach:** 让全部 13 个槽位覆盖全部 9 个 Qwen3 CustomVoice preset，重复槽位优先分配给 Uncle_Fu、Dylan、Serena；shim 在客户端未提供或仅提供空白值时注入可配置的克制旁白 `instructions` 和 `language=Chinese`。

## Boundaries & Constraints

**Always:** 固定映射为 `alloy/onyx/cedar→Uncle_Fu`、`echo/ballad→Dylan`、`marin/sage→Serena`、`fable→Aiden`、`ash→Eric`、`verse→Ryan`、`coral→Vivian`、`nova→Sohee`、`shimmer→Ono_Anna`；未知 voice 仍回退 `alloy`；显式非空 `instructions` 和 `language` 原样保留；默认语言为 `Chinese`；默认指令为“平静、克制、自然地朗读，像成熟的有声书旁白。保持稳定音色、音高和语速，语调起伏小，句间停顿自然。不要角色表演，不要笑、哭腔、耳语、夸张重音或额外声音。”；Ryan、Vivian、Eric 等偏 expressive/bright/lively 的 preset 仅占一个扩展试听槽位，不列为沉稳优先候选；保留 1.7B、Talker/Subtalker `0.6/50`、现有 GPU/Compose/流式转发行为和同任务未提交改动。

**Ask First:** 修改模型、采样值、seed、CUDA Graph、并发、请求块长、默认语言或 instruction/language 覆盖语义；部署前必须单独确认。

**Never:** 把本地 preset 冒充不存在的 Kai；修改 Cloudflare Worker；把外语母语 preset 宣称为中文旁白优选；运行全量部署、性能基准或复杂机器听感评分。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Speech Central 试听 | 任一 13 个固定 alias，未带 instruction/language | 解析为精确映射，并转发默认 `instructions` 与 `language=Chinese` | 未知 alias 回退 Uncle_Fu |
| 显式控制 | 请求携带非空 `instructions` 或 `language` | 分别保留客户端值，不覆盖对应字段 | 空白值按缺省处理 |
| 原生 speaker | 请求直接使用 9 个规范 speaker 名 | 大小写规范化后透传 | 非规范值走未知回退 |

</frozen-after-approval>

## Code Map

- `ansible/roles/qwen3-tts/defaults/main.yml:18` -- 13 槽位映射及新的默认 instruction/language 变量。
- `ansible/roles/qwen3-tts/files/qwen3-tts-shim.py:14,65,133` -- 内置映射、环境变量加载和请求级缺省 instruction/language 注入。
- `ansible/roles/qwen3-tts/templates/docker-compose.yml.j2:55` -- 将两个默认值传入 shim 容器；沿用 `config` 最小部署路径。
- `ansible/roles/qwen3-tts/tasks/main.yml:2` -- 固定边界断言覆盖完整映射与 instruction 类型。
- `scripts/test-qwen3-tts-shim.py:111` -- 精确映射、9 个原生 speaker、两个字段的缺省/空白注入和显式保留测试。
- `ansible/roles/qwen3-tts/tasks/verify.yml:96` -- 女声冒烟改用 Serena 槽位；继续验证真实音频。
- `docs/designs/qwen3-tts-openai-api-integration.md:48`、`_bmad-output/specs/spec-qwen3-tts-speech-central-shim/voice-mapping.md:3` -- 同步运行契约、母语限制和试听优先级。

## Tasks & Acceptance

**Execution:**
- [x] 更新 role、Compose 与 shim，使精确映射和可配置默认 instruction/language 生效且仅缺省注入。
- [x] 扩展标准库测试和 Ansible 边界/冒烟检查，防止映射、回退或显式 instruction/language 回归。
- [x] 更新设计文档与映射 companion，标明优先试听及外语母语 preset 风险。

**Acceptance Criteria:**
- Given 13 个 Speech Central alias，when 本地解析，then 全部命中预定 speaker、覆盖 9 个唯一 preset，且默认回退仍为 Uncle_Fu。
- Given 请求未带或仅带空白 `instructions`，when shim 转发，then 上游收到固定默认指令；Given 非空值，then 上游收到原值。
- Given 请求未带或仅带空白 `language`，when shim 转发，then 上游收到 `Chinese`；Given 非空值，then 上游收到原值。
- Given 仅配置类变更，when 本地验证通过并获部署授权，then 只运行 `--tags config` 后再运行 `--tags verify`，不重启 backend。

## Spec Change Log

## Verification

**Commands:**
- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/test-qwen3-tts-shim.py` -- expected: all shim unit tests pass.
- `cd ansible && ansible-playbook playbooks/deploy-qwen3-tts.yml --syntax-check` -- expected: syntax check succeeds without deployment.
- `git diff --check` -- expected: no new whitespace errors.

**Manual checks:**
- Voice A/B：固定文本、设备和 `0.6/50`，先试听 `alloy/onyx/cedar`、`echo/ballad`、`marin/sage`，再试听其余单槽位 preset；以实际中文听感判断。
- Instruction A/B：在胜出 voice 上，通过 `config` 最小部署依次比较空默认值与长版默认指令；若长版反而做作，再比较短版“沉稳、自然、均匀的有声书旁白。”。
- 重复稳定性：对胜出的 voice/instruction 使用同一文本连续生成三次，记录身份跳变、夸张情绪、正文外声音和固定位置伪影；不要求逐字节相同。

## Suggested Review Order

**请求契约与音色解析**

- 精确映射、回退与仅缺省注入集中在同一个边界。
  [`qwen3-tts-shim.py:14`](../../ansible/roles/qwen3-tts/files/qwen3-tts-shim.py#L14)

- 固定 role 默认值防止部署时静默改变旁白策略。
  [`main.yml:18`](../../ansible/roles/qwen3-tts/defaults/main.yml#L18)

- 容器将可配置默认值明确传给本地 shim。
  [`docker-compose.yml.j2:55`](../../ansible/roles/qwen3-tts/templates/docker-compose.yml.j2#L55)

**部署边界与运行验证**

- Ansible 断言锁定全槽位映射和精确默认 instruction。
  [`main.yml:2`](../../ansible/roles/qwen3-tts/tasks/main.yml#L2)

- 女声冒烟切换到优先试听的 Serena 槽位。
  [`verify.yml:96`](../../ansible/roles/qwen3-tts/tasks/verify.yml#L96)

**用户试听与回归保护**

- 标准库测试覆盖所有 alias、原生 speaker 与独立字段覆盖语义。
  [`test-qwen3-tts-shim.py:134`](../../scripts/test-qwen3-tts-shim.py#L134)

- 运行文档说明候选优先级、母语风险和默认控制面。
  [`qwen3-tts-openai-api-integration.md:49`](../../docs/designs/qwen3-tts-openai-api-integration.md#L49)

- 映射 companion 保留 Speech Central 槽位的试听用途。
  [`voice-mapping.md:1`](../specs/spec-qwen3-tts-speech-central-shim/voice-mapping.md#L1)
