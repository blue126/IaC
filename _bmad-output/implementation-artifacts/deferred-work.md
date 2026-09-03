- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 将 Proxmox 节点和 VMID 直接传入动态 inventory，消除 Terraform 与 host_vars 的重复元数据。
  evidence: n8n 本次必须手工新增 `proxmox_node: pve0` 和 `proxmox_vmid: 106`；迁移或重建后容易失配并操作错误容器。
- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 建立所有新节点都会执行 common、Tailscale 和服务 role 的统一部署入口。
  evidence: `deploy-n8n.yml` 只执行 n8n role，新增 host_vars 本身不会触发 `install-tailscale.yml`；同类遗漏会影响其他新节点。
- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 为包含 Proxmox snapshot 区段的 LXC 设计安全的 TUN 配置管理和重复执行验证。
  evidence: 当前简化的 `lineinfile` 适用于没有 snapshot 的 VMID 106，但不理解配置文件中的 snapshot 区段；缺少连续执行与重启后的自动验证。
- source_spec: `_bmad-output/implementation-artifacts/spec-oink-documentation-site.md`
  summary: 单独清理现有 Markdown 的断链、坏锚点和过期仓库文件引用。
  evidence: OINK 审查确认 `llm-server-deployment.md` 等既有文档含错误目标；本试点按人类确认保持 `docs/` byte-for-byte 不变，因此不在展示层变更中修复。
- source_spec: `_bmad-output/implementation-artifacts/spec-oink-doc-accuracy-integration-phase-1.md`
  summary: 保留 Ansible Vault 到私有 Notion Credentials DB 的单向密码同步，并以显式 credential allowlist、全量日志脱敏和 OINK/detector 隔离加固这个人类可读 GUI。
  evidence: 用户明确 Notion 是弥补 Ansible Vault 无 GUI 的授权 secret sink；该目标与只读仓库文件的 deterministic detector 可独立交付，且同 PR 会混合 secret 存储与文档验证两种 blast radius。
- source_spec: `ansible/roles/qwen3-tts`
  summary: 为每个 OpenAI voice 槽位分别建立并部署独立的 Base 参考 profile，让 llm-workstation 上可用的音色不止一个。
  evidence: 当前 `TTS_MODE=base` 下 shim 把 13 个 alias 全部改写成同一个 `audiobook_narrator_zh` profile，`voice` 参数实际不起作用；role 已经具备生成候选参考音频的 `candidate-pairing` 流程，缺的是把多个 profile 同时注册并按 alias 路由。
- source_spec: `_bmad-output/implementation-artifacts/spec-qwen3-tts-restrained-voice-mapping.md`
  summary: 为既有 1.7B Talker/Subtalker 采样及固定 seed 配置增加渲染级验证。
  evidence: 当前音频冒烟只验证响应可用，无法证明部署后的 sampling 字段未被误改；采样和 seed 属于本规格 Ask First 边界。原规格针对 llm-server 上已删除的同名 role，同样适用于当前的 `ansible/roles/qwen3-tts`。
- source_spec: `tools/check-doc-claims.py`
  summary: 让 claim 的 oracle 读取支持嵌套与按索引定位的 YAML 键，使 vLLM deploy-config 中的每 stage 取值可被校验。
  evidence: `_yaml_key_values` 只匹配顶层键（第 110 行显式跳过缩进行），且同名键出现多次会被判 `oracle_key_duplicate`；而 `gpu_memory_utilization`、`max_num_seqs`、`kv_cache_memory_bytes`、`silence_ban_frames` 全部位于 `stages:` 之下且每 stage 各一份。设计文档曾把 Talker 的 `gpu_memory_utilization` 写成 `0.17` 而配置早已是 `0.3`，正是该工具应当拦截却拦不到的一类漂移。改动会变更工具契约并影响既有 oracle 语义，需独立交付。
- source_spec: `docs/designs/qwen3-tts-openai-api-integration.md`
  summary: 在 shim 内按能量阈值裁剪 clip 首尾静音，消除连续朗读时每个接缝约 775 毫秒的死区。
  evidence: 实测 clip 头部约 400 毫秒、尾部约 350 毫秒为 RMS 仅峰值 0.13%–0.68% 的近似静音，语音段为 6%–23%，阈值分离干净；`silence_ban_frames` 经每组 15 样本对比证明无效（775 对 806 毫秒）。非 PCM 格式需要 shim 具备解码能力，属于新增依赖，需单独授权。
