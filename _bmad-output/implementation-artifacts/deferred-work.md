- source_spec: `_bmad-output/implementation-artifacts/spec-qwen3-tts-restrained-voice-mapping.md`
  summary: 为独占 GPU 的 Qwen3.6 停止路径补充失败恢复、正确 tags 和部署后状态验证。
  evidence: 本规格要求保留既有 1.7B/GPU 生命周期行为；审查发现该既有路径在后续部署失败时可能让 Qwen3.6 保持停止，需作为独立生命周期改动处理。
- source_spec: `_bmad-output/implementation-artifacts/spec-qwen3-tts-restrained-voice-mapping.md`
  summary: 为既有 1.7B Talker/Subtalker 采样及固定 seed 配置增加渲染级验证。
  evidence: 当前音频冒烟只验证响应可用，无法证明部署后的 sampling 字段未被误改；采样和 seed 属于本规格 Ask First 边界。
