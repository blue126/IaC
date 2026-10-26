# llm-ops 迁出项目的 BMAD 产物（归档）

本目录保存 deepseek-v4 与 qwen3-tts 两个项目在本仓库期间产生的 BMAD spec 与调研报告。两个项目的代码、部署与后续工作已迁到 [`blue126/llm-ops`](https://github.com/blue126/llm-ops)，本仓库只收基础设施（见 `AGENTS.md`）。

- 归档日期：2026-10-26。
- 目录结构保持原样：`implementation-artifacts/`、`planning-artifacts/research/`、`specs/` 与 `_bmad-output/` 下的原位置一一对应。
- 这些文件只作历史参考，不再更新；新的工作在 llm-ops 里进行。
- `deferred-work.md` 是只增不改的清单，里面仍按旧路径引用部分 qwen3-tts spec。`scripts/sync-deferred-work.py` 按条目文本识别条目，旧路径只会计入 `stale source specs`，不影响同步。
