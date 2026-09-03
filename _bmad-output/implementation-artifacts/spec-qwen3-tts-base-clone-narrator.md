---
title: 'Qwen3-TTS Base 合成旁白克隆 profile'
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

**Problem:** 1.7B CustomVoice 即使使用克制 instruction，连续中文有声书朗读仍有明显主观音色/语势漂移，用户判断不可用；0.6B 仅作为最后回退选项。

**Approach:** 使用 VoiceDesign 创建一段非真人、沉稳中文旁白参考音频，再由 1.7B Base 将其持久化为固定 clone profile；Speech Central 继续使用既有 OpenAI endpoint 和任一硬编码 voice 槽位，但所有槽位统一请求该 profile。

## Boundaries & Constraints

**Always:** 采用 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` 仅生成合成参考音频；参考声描述为“成熟、沉稳、低起伏、自然的中文有声书旁白”，不得模拟真人或 Kai；必须由用户试听并明确确认该 WAV 后，才运行 `Qwen/Qwen3-TTS-12Hz-1.7B-Base` 并以准确转写创建 ICL profile `audiobook_narrator_zh`；将 profile 与参考 WAV 保存于现有持久化模型目录；Base 请求固定 `task_type=Base`、`voice=audiobook_narrator_zh`、`language=Chinese`，忽略客户端 alias 而保留 OpenAI API、`tts-1`、AAC/stream 兼容与 512 token 上限；以用户在 Speech Central 的连续试听判断效果。

**Ask First:** 修改 profile 文案/名称、使用真人或外部参考音频、改为 x-vector-only、改变 0.6/50、seed、并发、GPU、输出上限或将 0.6B 设为当前模型；部署每个会切换模型的阶段前单独确认。

**Never:** 序列化官方 Python `voice_clone_prompt` 对象；把 VoiceDesign 当作常驻生产 backend；以没有明确同意的真人声音克隆；暴露参考音频、转写或 profile 文件到 Git、公网或日志；在 VoiceDesign 与 Base 间并行占用同一 GPU。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 合成参考声 | 不存在参考 WAV | 临时 VoiceDesign 生成参考 WAV 并恢复当前 backend，等待用户试听确认 | 未确认不得创建 Base profile 或切换 Base |
| 合成 profile | 用户确认参考 WAV | Base 以准确转写注册 ICL profile，重启后仍可列出 | 任一步失败即停止切换并恢复上一个可用 backend |
| Speech Central 朗读 | 任一 13 个 alias，未携带 Base 字段 | shim 统一转发 Base task、固定 profile、Chinese；原 API 格式不变 | 未就绪 profile 返回明确 503，不回退到错误 speaker |
| 显式客户端 alias | `alloy`、`marin` 或未知值 | 产生同一固定 profile 请求，消除 alias 导致的身份差异 | alias 不作为 Base speaker 透传 |
| 重启后复用 | Base 容器重建 | profile 从持久目录恢复，仍可生成音频 | profile 缺失时 health/verify 失败而非静默随机生成 |

</frozen-after-approval>

## Code Map

- `ansible/roles/qwen3-tts/defaults/main.yml:2` -- 当前 CustomVoice、alias 和默认 instruction 边界；改为 Base/profile 与合成参考声配置。
- `ansible/roles/qwen3-tts/files/vllm-deploy-config.yaml:20` -- 保留单 GPU、`0.6/50` 与 512 输出限制，增加 Base persistent custom voice 路径。
- `ansible/roles/qwen3-tts/templates/docker-compose.yml.j2:3` -- 复用 server/shim/缓存/端口，增加受控的临时 VoiceDesign bootstrap 与 Base profile 持久存储。
- `ansible/roles/qwen3-tts/tasks/main.yml:2` -- 固定模型断言和最小 tagged 模型切换流程；必须让 profile 创建具备幂等性与失败恢复。
- `ansible/roles/qwen3-tts/files/qwen3-tts-shim.py:14,150` -- 保留 OpenAI 格式与音频兼容层，替换 CustomVoice alias→speaker 为 Base profile 注入。
- `ansible/roles/qwen3-tts/tasks/verify.yml:1` -- 在 `/v1/audio/voices`、Base profile、WAV/stream/AAC 及重启可用性上验证真实运行链路。
- `scripts/test-qwen3-tts-shim.py:134` -- 将精确 preset 映射测试改为所有 alias 的相同 Base 请求负载测试。

## Tasks & Acceptance

**Execution:**
- [x] 为合成参考声、ICL profile 和 Base 模型增加受控 defaults、Compose 持久卷与 tagged Ansible 生命周期。
- [x] 实现 VoiceDesign 一次性生成、Base profile 注册/恢复及失败时保留最后可用服务的流程。
- [x] 更新 shim、标准库测试和部署 verify，使全部 Speech Central alias 固定使用同一个 Base profile。
- [x] 更新运行文档，说明 synthetic reference、profile 资产边界、试听步骤与 0.6B 回退条件。

**Acceptance Criteria:**
- Given 没有 profile，when 运行获授权的 bootstrap，then 生成合成参考声并以准确转写创建 ICL `audiobook_narrator_zh`，重启后仍可在 voices endpoint 中找到它。
- Given 任意 Speech Central alias，when 调用 `/v1/audio/speech`，then shim 转发 Base task、同一 profile 与 Chinese，不再转发 CustomVoice speaker。
- Given profile 不存在或不可用，when 请求到达 shim，then 返回可诊断错误且不会用随机/预置音色生成。
- Given profile 存在，when `verify` 运行，then Base 语音、WAV、PCM stream 与 AAC→MP3 均成功；用户随后用固定文本连续试听判断稳定性。

## Spec Change Log

## Design Notes

vLLM-Omni 0.28.0 的公开持久化契约是 Base 的 `POST /v1/audio/voices`（参考音频加 `ref_text`）或离线 `custom_voice_dir`，而非官方 Python 的内存 `voice_clone_prompt`。本 PoC 应优先使用公开的持久化 profile 接口，并将 VoiceDesign 只作为生成非真人参考音频的一次性工具。

## Verification

**Commands:**
- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/test-qwen3-tts-shim.py` -- expected: all shim unit tests pass.
- `cd ansible && ansible-playbook playbooks/deploy-qwen3-tts.yml --syntax-check` -- expected: syntax check succeeds without deployment.
- `git diff --check` -- expected: no whitespace errors.

**Manual checks:**
- 在 Speech Central 以同一段文本连续播放三个 alias，确认三个请求听起来属于同一目标身份；记录漂移、情绪夸张和超时。
- 重启 Base backend 后重复一次短句，确认 profile 未丢失且声音未退回 preset。

## Suggested Review Order

**受控模型切换与恢复**

- Bootstrap 串行切换模型，并在失败时恢复已配置服务。
  [`main.yml:214`](../../ansible/roles/qwen3-tts/tasks/main.yml#L214)

- 合成参考音频与公开 ICL 注册接口均为幂等实现。
  [`qwen3-tts-profile-bootstrap.py:36`](../../ansible/roles/qwen3-tts/files/qwen3-tts-profile-bootstrap.py#L36)

**稳定的公开语音接口**

- 所有客户端 alias 固定注入同一 Base profile。
  [`qwen3-tts-shim.py:110`](../../ansible/roles/qwen3-tts/files/qwen3-tts-shim.py#L110)

- 缺失 profile 时 health 与 speech 都明确返回不可用。
  [`qwen3-tts-shim.py:175`](../../ansible/roles/qwen3-tts/files/qwen3-tts-shim.py#L175)

**持久性与回归验证**

- 持久 profile 和临时 VoiceDesign 服务隔离在 Compose 配置中。
  [`docker-compose.yml.j2:3`](../../ansible/roles/qwen3-tts/templates/docker-compose.yml.j2#L3)

- 验证覆盖 profile、音频格式以及重启后的实际合成。
  [`verify.yml:40`](../../ansible/roles/qwen3-tts/tasks/verify.yml#L40)

- 标准库测试锁定 alias 独立的 Base 请求负载。
  [`test-qwen3-tts-shim.py:134`](../../scripts/test-qwen3-tts-shim.py#L134)
