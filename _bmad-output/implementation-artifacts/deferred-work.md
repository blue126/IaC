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
- source_spec: `ansible/roles/qwen3-tts-workstation`
  summary: 为每个 OpenAI voice 槽位分别建立并部署独立的 Base 参考 profile，让 llm-workstation 上可用的音色不止一个。
  evidence: 当前 `TTS_MODE=base` 下 shim 把 13 个 alias 全部改写成同一个 `audiobook_narrator_zh` profile，`voice` 参数实际不起作用；role 已经具备生成候选参考音频的 `candidate-pairing` 流程，缺的是把多个 profile 同时注册并按 alias 路由。
- source_spec: `_bmad-output/implementation-artifacts/spec-qwen3-tts-restrained-voice-mapping.md`
  summary: 为既有 1.7B Talker/Subtalker 采样及固定 seed 配置增加渲染级验证。
  evidence: 当前音频冒烟只验证响应可用，无法证明部署后的 sampling 字段未被误改；采样和 seed 属于本规格 Ask First 边界。原规格针对 llm-server 上的 `qwen3-tts`，同样适用于 `qwen3-tts-workstation`。
- source_spec: `tools/check-doc-claims.py`
  summary: 让 claim 的 oracle 读取支持嵌套与按索引定位的 YAML 键，使 vLLM deploy-config 中的每 stage 取值可被校验。
  evidence: `_yaml_key_values` 只匹配顶层键（第 110 行显式跳过缩进行），且同名键出现多次会被判 `oracle_key_duplicate`；而 `gpu_memory_utilization`、`max_num_seqs`、`kv_cache_memory_bytes`、`silence_ban_frames` 全部位于 `stages:` 之下且每 stage 各一份。设计文档曾把 Talker 的 `gpu_memory_utilization` 写成 `0.17` 而配置早已是 `0.3`，正是该工具应当拦截却拦不到的一类漂移。改动会变更工具契约并影响既有 oracle 语义，需独立交付。
- source_spec: `docs/designs/qwen3-tts-openai-api-integration.md`
  summary: 在 shim 内按能量阈值裁剪 clip 首尾静音，消除连续朗读时每个接缝约 775 毫秒的死区。
  evidence: 实测 clip 头部约 400 毫秒、尾部约 350 毫秒为 RMS 仅峰值 0.13%–0.68% 的近似静音，语音段为 6%–23%，阈值分离干净；`silence_ban_frames` 经每组 15 样本对比证明无效（775 对 806 毫秒）。非 PCM 格式需要 shim 具备解码能力，属于新增依赖，需单独授权。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 把 Phase 2 离线测试套件接入 `.github/workflows/doc-accuracy.yml`，与已自动化的 Phase 1 套件并列。
  evidence: 该 workflow 目前只有一个测试步骤，跑 `tests/doc-claims/doc-claims-test.py`；全仓检索 `doc-gardening` 只在本规格里作为手工命令出现。整套 fail-closed 保证（单文档 manifest、密钥脱敏、逐字 quote/hash 绑定）目前只在有人记得敲命令时才被验证。改动 Actions workflow 属于本规格 Ask First 边界，需单独授权。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 让 `validate-contract.py` 直接消费 `schemas/*.json`，取代手写校验，并给 `analysis-input-v1.json` 一个真实消费者。
  evidence: 同一份契约被编码两次——`contract.py` 的常量与手写检查，和四份 JSON schema。`analysis-input-v1.json` 无任何代码读取；`run-record-v1.json` 只被本次新增的等价性断言覆盖。等价性断言能挡住漂移，但两份实现的维护成本仍在。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 实现模型拒答识别，或从 `RUN_REASONS` 与 `CANDIDATE_REASONS` 中删除 `refusal` 与 `model_refusal`。
  evidence: 没有任何代码路径产生这两个值；`test_malformed_refusal_becomes_blocked_record_without_artifact` 断言的是 `validation_failed`。死枚举出现在模型可见的 schema 里，会诱导模型输出一个验证器随后拒绝的 reason。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 让 manifest 的 `hunks[].text` 直接承载 git 原始字节，而不是重建后的字符串。
  evidence: `_parse_hunks` 用 `"\n".join(current_lines) + "\n"` 重建 hunk 文本，丢弃原始行尾并无条件补尾换行，`\ No newline at end of file` 这类元数据行也会混入内容。整套设计以 sha256 作为溯源凭证，而这个哈希哈的是重建产物而非真实 diff。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 为 `contains_secret()` 补上本仓库实际使用的密钥形态，并把测试哨兵移出生产脱敏逻辑。
  evidence: 当前只有 `SECRET_SENTINEL`、PRIVATE KEY header、AKIA、GitHub PAT 四类模式。本仓库以 Ansible Vault 为唯一密钥来源，却没有 `$ANSIBLE_VAULT;1.1;AES256` header 与 `vault_*` 赋值的模式；同时把测试哨兵硬编码进生产脱敏逻辑，使仓库里长期存在一个会被自家工具判为含密的 fixture 文件。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 给离线 evaluator 补 `edit_proposal` 类型的黄金用例，并为 schema 加规模上界。
  evidence: `expectations.json` 的 10 个用例全是 `claim_candidates`，而提案是唯一会产生可应用文本改动的产物，其接受/拒绝行为从未被离线验证。schema 侧 `candidates` 无 `maxItems`、`quote`/`find`/`replace` 无 `maxLength`，模型返回超大数组或超长替换会被照单全收。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 让 `--confirm-live` 成为真正的人工确认，并与 `--live` 建立互斥校验。
  evidence: 同一条命令行上的一个 flag 不构成人工确认——脚本化调用可以一次性带上 `--live --confirm-live`。另外 `--confirm-live` 可在不带 `--live` 时静默传入，没有任何校验。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 补 `tools/doc-gardening/` 的使用文档，并把 `tools/` 与 `tests/` 加进 AGENTS.md 的 Repository Structure。
  evidence: 新增 5 个脚本、4 份 schema、2 份 prompt，没有 README，`docs/designs/` 下也没有对应设计文档；AGENTS.md 的目录树至今没有 `tools/` 和 `tests/` 两项，Key Commands 也没有任何 doc-gardening 条目。测试文件名 `doc-gardening-test.py` 不匹配 `unittest discover` 默认的 `test*.py`，怎么跑只能靠猜。
