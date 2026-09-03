---
title: 'Qwen3-TTS VoiceDesign 与 Base clone 配对候选试听'
type: 'feature'
created: '2026-09-02'
status: 'in-progress'
review_loop_iteration: 0
baseline_commit: '693117e5de1b0c556554d586c3b573e1b9616e25'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/spec-qwen3-tts-base-clone-narrator.md'
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

**Problem:** 当前 `audiobook_narrator_zh` 已可用且漂移较小，但其 Base clone 输出与对应 VoiceDesign 参考声主观上不像同一人。单独更换 WAV 不能证明能改善这一模型间复刻偏差。

**Approach:** 生成三种成熟、沉稳中文旁白 VoiceDesign 候选；每一候选均以准确转写注册临时 Base profile，并以同一句固定探针文本合成 clone WAV。用户按“参考声与该候选 clone 是否像同一人”试听选择；当前生产 profile 和 Speech Central 设置保持不变。

## Boundaries & Constraints

**Always:** 候选为非真人合成声音；三组使用同一参考文本、相同长度、中文和固定探针文本；描述只在低沉共鸣、厚实质感、轻微自然沙哑三项间变化；一次仅运行 VoiceDesign 或 Base，独占现有 GPU；候选 WAV、临时 profile 和 clone WAV 均保存在现有持久模型目录并拉取到本机试听；候选 profile 使用独立名称，绝不覆盖 `audiobook_narrator_zh`。

**Ask First:** 将任一候选提升为生产 profile、替换当前参考 WAV、改变模型/采样参数/GPU/输出上限、清理候选资产，或让 Speech Central 指向候选 profile。

**Never:** 将多个 WAV 组合后上传为一个 profile；使用真人/外部参考音频；并行运行 VoiceDesign 与 Base；在 Git、日志或公网暴露候选音频；以候选失败为由中断当前生产 Base 服务。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 生成候选 | 三个固定描述、无候选 WAV | VoiceDesign 依次产出三个有效 WAV | 无效 WAV 时停止该候选，保留生产 profile |
| clone 配对 | 已确认有效候选 WAV 与准确转写 | Base 注册同名临时 profile，并输出固定探针 WAV | profile/合成失败时记录候选失败，继续安全地恢复生产服务 |
| 用户试听 | 3 组 reference + clone 文件 | 每组文件名称一一对应，可作主观身份相似度比较 | 未获得明确选择时不切换生产 profile |
| 生产保护 | 已运行 `audiobook_narrator_zh` | 原 profile、shim endpoint 与 Speech Central 映射不变 | 流程结束时恢复并验证原服务 |

</frozen-after-approval>

## Code Map

- `ansible/roles/qwen3-tts/defaults/main.yml` -- 保存当前 production profile 与 VoiceDesign prompt；新增候选矩阵及固定探针文本的唯一配置来源。
- `ansible/roles/qwen3-tts/files/qwen3-tts-profile-bootstrap.py` -- 已能生成单一参考与上传 profile；应复用 WAV 检验、multipart 上传和 `ref_text`，扩展为显式候选参数与 probe 合成，而非改变默认 production 行为。
- `ansible/roles/qwen3-tts/templates/docker-compose.yml.j2` -- `voice-design` 与 `profile-bootstrap` 已共享 profiles 卷；不改变公开端口或生产 shim 配置。
- `ansible/roles/qwen3-tts/tasks/main.yml` -- 已有串行 VoiceDesign/Base 启动和健康等待；新增独立、never 默认执行的 candidate-pairing tag，结束后恢复 Base + shim。
- `ansible/roles/qwen3-tts/tasks/verify.yml` -- 生产验证的边界；候选流程仅复用其 WAV 有效性约定，不修改用户现有服务契约。

## Tasks & Acceptance

**Execution:**
- [ ] `defaults/main.yml` -- 定义三个稳定候选及固定 probe 文本 -- 令试听对比可重现。
- [ ] `qwen3-tts-profile-bootstrap.py` -- 支持候选 reference、profile 上传及 probe WAV 生成 -- 用相同准确转写建立真正的 Base ICL 对。
- [ ] `tasks/main.yml` -- 增加串行、可失败恢复、默认不执行的 pairing 部署路径 -- 保证单 GPU 和生产服务保护。
- [ ] `scripts/test-qwen3-tts-shim.py` 或新的标准库测试 -- 覆盖候选命名/请求负载和不覆盖生产 profile -- 防止错误选择 profile。
- [ ] `docs/designs/qwen3-tts-openai-api-integration.md` -- 说明候选听评步骤与人工提升门槛 -- 保留操作知识。

**Acceptance Criteria:**
- Given 当前 production Base profile 可用，when 运行候选 pairing tag，then 产出三组各自命名的有效参考及 Base clone WAV，且生产 profile 文件不变。
- Given 每个候选 reference，when 注册与合成，then 使用同一候选名和准确参考转写，probe 输出为非空 RIFF/WAVE 音频。
- Given 一个候选失败，when 流程结束，then 当前 `audiobook_narrator_zh` 的 Base + shim 被恢复且 `/health` 可用。
- Given 用户未明确选定候选，when 候选资产完成，then Speech Central 仍请求 `audiobook_narrator_zh`。

## Spec Change Log

## Design Notes

Qwen 官方推荐 VoiceDesign 后以生成的短参考声创建可复用 Base clone prompt；vLLM 的持久 profile 接口每次上传一个 `audio_sample`，其中 `ref_text` 启用质量更高的 ICL。候选筛选的判据因此是每个 reference 与它的 Base 输出之间的相似性，而不是 reference 自身的偏好。

## Verification

**Commands:**
- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/test-qwen3-tts-shim.py` -- expected: existing shim contract remains valid.
- `cd ansible && ansible-playbook playbooks/deploy-qwen3-tts.yml --syntax-check` -- expected: candidate lifecycle syntax is valid.
- `git diff --check` -- expected: no whitespace errors.

**Manual checks:**
- 听每一组 reference 与同组 clone 的固定探针；仅在用户选择后才提升候选。
