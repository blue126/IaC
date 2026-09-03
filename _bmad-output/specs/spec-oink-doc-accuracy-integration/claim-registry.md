# Phase 1 Claim Registry

此 registry 是 Phase 1 的闭集，不是自动发现机制。每条记录只允许一个 checked-in Markdown locator 和一个 checked-in YAML 标量 oracle；检测器不得从 runtime、Terraform state、Notion、Vault 或日志补全证据。

**权威来源是 `tools/check-doc-claims.py` 的 `CLAIMS`。** 下表是它的投影，`CLAIMS` 变动时必须同步重新导出。方向是单向的：代码变了改这张表，不是反过来。此前两者曾各自漂移到互不相符而两边都不显得错，正是因为没有声明方向。

## Status contract

| Status | Deterministic condition | Required report data |
|---|---|---|
| `verified` | locator 恰好匹配一次，oracle key 恰好解析为一个标量，规范化后相等 | document locator、oracle path/key、非敏感 expected/observed value、revision/digest |
| `contradiction` | 两端均可唯一解析，但规范化后不相等 | 同上，以及两端值 |
| `indeterminate` | source 缺失、不可解析、locator 缺失或多次匹配、key 缺失/重复/非标量 | failure reason、可用的 path/locator、revision/digest；不得编造值 |

规范化只移除 Markdown code fence/table 的表示层并解析 YAML scalar；不得改写端口数字、版本字符串、大小写或语义等价关系。对于本 registry，原始标量的 exact equality 是唯一的 `verified` 条件。

## Closed claims

闭集当前为 **6 条**。文档侧覆盖 `docs/deployment/` 与 `docs/designs/` 两类。

| ID | Document and stable locator | Oracle | Expected value | Reader |
|---|---|---|---|---|
| `service.netbox.port` | `docs/deployment/netbox-deployment.md` → `Configuration Variables` 表中 `netbox_port` 行 | `ansible/roles/netbox/defaults/main.yml` → `netbox_port` | `8080` | 表格 |
| `service.netbox.image` | `docs/deployment/netbox-deployment.md` → `Configuration Variables` 表中 `netbox_image` 行 | `ansible/roles/netbox/defaults/main.yml` → `netbox_image` | `netboxcommunity/netbox:v4.1.11` | 表格 |
| `service.qwen3-tts.vllm-image` | `docs/designs/qwen3-tts-openai-api-integration.md` → `关键配置值` 中 `qwen3_tts_vllm_image` | `ansible/roles/qwen3-tts-workstation/defaults/main.yml` → `qwen3_tts_vllm_image` | `vllm/vllm-omni:v0.28.0` | fenced YAML |
| `service.qwen3-tts.gpu-ordinal` | `docs/designs/qwen3-tts-openai-api-integration.md` → `关键配置值` 中 `qwen3_tts_gpu_ordinal` | `ansible/roles/qwen3-tts-workstation/defaults/main.yml` → `qwen3_tts_gpu_ordinal` | `1` | fenced YAML |
| `service.qwen3-tts.port` | `docs/designs/qwen3-tts-openai-api-integration.md` → `关键配置值` 中 `qwen3_tts_port` | `ansible/roles/qwen3-tts-workstation/defaults/main.yml` → `qwen3_tts_port` | `8100` | fenced YAML |
| `service.qwen3-tts.min-free-vram-mib` | `docs/designs/qwen3-tts-openai-api-integration.md` → `关键配置值` 中 `qwen3_tts_min_free_vram_mib` | `ansible/roles/qwen3-tts-workstation/defaults/main.yml` → `qwen3_tts_min_free_vram_mib` | `512` | fenced YAML |

每条 claim 的依赖项均为"该文档 + 该 defaults 文件"。

### 已退役

`service.llm-server.engine-version` 与 `service.llm-server.webui-port` 随 llm-server 多模型 role 一并删除（`f46ab45`）。四条 qwen3-tts claim 在 `a3818ec` 加入。

### 待同步

`ansible/roles/qwen3-tts-workstation/` → `ansible/roles/qwen3-tts/` 的 role 重命名已在 `claude/tts-drop-inert-seed` 上提交但尚未合并。本表记录的是 `origin/main` 的事实；该分支落地后，四条 qwen3-tts claim 的 oracle 路径随之改变。

## Required fixtures

The test suite must cover all of the following without contacting external services:

1. 每条 registry claim 的仓库 fixture 均评估为 `verified`。
2. A changed Markdown scalar evaluates to `contradiction` and identifies the document locator.
3. A changed YAML scalar evaluates to `contradiction` and identifies the oracle path/key.
4. A missing source, zero-match locator, multi-match locator, missing key, duplicate key, or non-scalar oracle evaluates to `indeterminate` with a specific reason.
5. Every serialised report uses only the values above and the structural fields in the status contract; it contains no secret-bearing field or unredacted input outside the registry.

## Excluded candidates

`docs/deployment/immich-deployment.md` is deliberately excluded: its stated port is not presently represented by a stable `immich_port` scalar in `ansible/roles/immich/defaults/main.yml`.

`ansible/roles/qwen3-tts-workstation/files/vllm-deploy-config.yaml` 中的 `gpu_memory_utilization`、`max_num_seqs`、`kv_cache_memory_bytes`、`silence_ban_frames` 同样排除：`_yaml_key_values` 直接跳过首字符为空白的行，而这些键位于 `stages:` 之下均为缩进行，因此根本不会被收集，实际结果是 `oracle_key_missing`——不是每 stage 重复导致的歧义，重复判定压根轮不到。这四项目前只能人工核对。

Credentials, tokens, passwords, free-form notes, domains, runtime states, Terraform resource specifications and any value sourced from a secret file are also excluded, even if they appear in documentation.
