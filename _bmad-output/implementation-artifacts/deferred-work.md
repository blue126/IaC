- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 将 Proxmox 节点和 VMID 直接传入动态 inventory，消除 Terraform 与 host_vars 的重复元数据。
  evidence: n8n 本次必须手工新增 `proxmox_node: pve0` 和 `proxmox_vmid: 106`；迁移或重建后容易失配并操作错误容器。
- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 把 llm-workstation 已有的"主机基线 + 服务部署"两层结构推广到其余节点。
  evidence: 19 个 deploy playbook 中 13 个开头手抄同一段 `common + tailscale + docker + <服务>`；新增 host_vars 本身不会触发 `install-tailscale.yml`，忘记补这几行不会报错，只是静默不做。`deploy-llm-workstation.yml`（主机基线）与 `deploy-qwen38.yml`/`deploy-qwen3-tts.yml`（服务）已是正确形态：Tailscale 属于主机，模型只是主机上的服务，两者不应混在一个 playbook 里。
  note: 原条目表述为"统一入口同时执行 common、Tailscale 和服务 role"，方向相反——那会把已分对的层次重新搅浑。另：先前统计"6 个 playbook 缺 common、8 个缺 tailscale"不可直接当作遗漏清单，其中 open-webui-gateway（网关无 Python）、anki-oci 与 unified-proxy（OCI 静态 inventory）、jenkins-agent（与 jenkins 同机）都是有意为之。可选做法：把基线并入 `site.yml`（爆炸半径从 16 台升到 16+15 台，且引入可能重启 LXC 的逻辑），或维持约定并在新节点检查中断言"在 tailscale 组却未连上"。
- source_spec: `terraform/README.md`
  summary: 把 pve1 上的 Proxmox Backup Server import 进 Terraform，使其重新进入动态 inventory。
  evidence: `a0e5692` 把 PBS 从 ESXi 迁到 pve1 并删除了 `terraform/esxi/pbs.tf`，提交信息明确记录"The backup server on pve1 has no Terraform definition yet"。因此 `ansible pbs --list-hosts` 匹配不到任何主机，而 `ansible/roles/pbs`、`roles/pbs-client`、`deploy-pbs.yml`、`setup-pbs-backup.yml` 四者仍在仓库中，目前是指向不存在目标的孤儿。补主机基线（common/tailscale）在 import 之前没有意义。
  note: import 的是一台在跑的生产备份机，plan 写错可能提议重建，需谨慎并单独授权。
- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 为包含 Proxmox snapshot 区段的 LXC 设计安全的 TUN 配置管理和重复执行验证。
  evidence: 当前简化的 `lineinfile` 适用于没有 snapshot 的 VMID 106，但不理解配置文件中的 snapshot 区段；缺少连续执行与重启后的自动验证。
- source_spec: `_bmad-output/implementation-artifacts/spec-oink-documentation-site.md`
  summary: 建立自动的 Markdown 断链检查，纳入 doc-accuracy 工作流。
  evidence: 一次性清理已完成：扫描 `docs/**/*.md` 得 68 处失效目标，逐条分类后实修 5 处真错误（minimax 两篇的互链写错目录、jenkins 学习笔记指向从未提交的 spec），另给 minimax 两篇补历史横幅。其余不应修改——历史文档指向已正当删除的代码（正文本身即记录）、未实现工作的 spec、以及把 Terraform provider 名 `ansible/ansible` 误判为路径这类扫描噪声。
  note: 缺的是防止再次发生的机制。手工扫描既会漏（第一次用较窄的正则只得 46 处）又会误报，需要能区分“真断链”与“历史记录中的已删路径”的检查，后者的判据大致是文档是否带历史横幅。
- source_spec: `_bmad-output/implementation-artifacts/spec-oink-doc-accuracy-integration-phase-1.md`
  summary: 保留 Ansible Vault 到私有 Notion Credentials DB 的单向密码同步，并以显式 credential allowlist、全量日志脱敏和 OINK/detector 隔离加固这个人类可读 GUI。
  evidence: 用户明确 Notion 是弥补 Ansible Vault 无 GUI 的授权 secret sink；该目标与只读仓库文件的 deterministic detector 可独立交付，且同 PR 会混合 secret 存储与文档验证两种 blast radius。
- source_spec: `ansible/roles/qwen3-tts`
  summary: 为每个 OpenAI voice 槽位分别建立并部署独立的 Base 参考 profile，让 llm-workstation 上可用的音色不止一个。
  evidence: 当前 `TTS_MODE=base` 下 shim 把 13 个 alias 全部改写成同一个 `audiobook_narrator_zh` profile，`voice` 参数实际不起作用；role 已经具备生成候选参考音频的 `candidate-pairing` 流程，缺的是把多个 profile 同时注册并按 alias 路由。
- source_spec: `_bmad-output/implementation-artifacts/spec-qwen3-tts-restrained-voice-mapping.md`
  summary: 为既有 1.7B Talker/Subtalker 采样配置增加渲染级验证。
  evidence: 当前音频冒烟只断言返回字节是合法 WAV（`fail_msg: ... invalid RIFF/WAVE header`），证明不了部署后 `temperature`/`top_k`/`repetition_penalty` 及 subtalker 采样字段未被误改或被新版 vLLM-Omni 静默忽略——服务照常 200、WAV 头合法、verify 全绿，而音色开始漂移。原规格针对 llm-server 上已删除的同名 role，同样适用于当前的 `ansible/roles/qwen3-tts`。
  note: 原条目设想用固定 seed 的确定性做验证（合成两次断言字节一致），该路径在当前配置下不可行：实测同一文本三次渲染为 6.16s/6.56s/6.80s（10.4% 跨度），显式传相同 per-request seed 两次同样不一致。原因不是 seed 失效——仓库自己的源码核验（`research/.../digests/timbre-prosody-vllm-omni-r2-1.md`）已 verified 两点：seed 同时进入 Stage 0 Talker 与残差 MTP/Subtalker；而 FULL CUDA graph 重放单一捕获的 RNG 流，使逐请求 seed 不可复现。要拿到 bit-exact 需把 Stage 0 改为 eager 或纯 PIECEWISE，代价是 talker_mtp 每步 9ms→39ms。因此可行的替代是断言渲染音频的统计特征（时长落在实测区间、RMS 包络、基频中位数），而非字节相等。
- source_spec: `tools/check-doc-claims.py`
  summary: 让 claim 的 oracle 读取支持嵌套与按索引定位的 YAML 键，使 vLLM deploy-config 中的每 stage 取值可被校验。
  evidence: `_yaml_key_values` 只匹配顶层键（第 110 行显式跳过缩进行），且同名键出现多次会被判 `oracle_key_duplicate`；而 `gpu_memory_utilization`、`max_num_seqs`、`kv_cache_memory_bytes`、`silence_ban_frames` 全部位于 `stages:` 之下且每 stage 各一份。设计文档曾把 Talker 的 `gpu_memory_utilization` 写成 `0.17` 而配置早已是 `0.3`，正是该工具应当拦截却拦不到的一类漂移。改动会变更工具契约并影响既有 oracle 语义，需独立交付。
- source_spec: `docs/designs/qwen3-tts-openai-api-integration.md`
  summary: 在 shim 内按能量阈值裁剪 clip 首尾静音，消除连续朗读时每个接缝约 775 毫秒的死区。
  evidence: 实测 clip 头部约 400 毫秒、尾部约 350 毫秒为 RMS 仅峰值 0.13%–0.68% 的近似静音，语音段为 6%–23%，阈值分离干净；`silence_ban_frames` 经每组 15 样本对比证明无效（775 对 806 毫秒）。非 PCM 格式需要 shim 具备解码能力，属于新增依赖，需单独授权。
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
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 让 `validate_manifest_repository()` 从指定 revision 重建 diff，逐项比对 hunks 与 span-to-hunk 关系，而不是只核对文件哈希与 span quote。
  evidence: 当前校验只确认 manifest 自洽——篡改者改掉 hunk 文本后重算 hunk SHA 与 `manifest_sha256` 即可通过，任意内容因此可以进入交给 live 模型的封闭输入。Codex 在 PR #18 判为 P1 并复现过。这是"manifest 只做到自洽、从未从仓库重新推导"的一半。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 让 `_redacted_evidence()` 按目标 revision 重新读取 oracle 文件，核对路径、内容哈希与 claim 结果，而不是只做 `oracle_sha256` 的格式校验。
  evidence: `require_sha256` 只验证形如 64 位十六进制，从不打开那个 oracle 文件。Phase 1 report 生成后修改 oracle（例如把 `netbox_port` 改成 9999），builder 仍返回 0 并把旧 evidence 记为 `verified`，候选分析因此建立在过期证据上。本仓库的 edge-case-hunter 与 Codex 各自独立发现；前者曾在评审中提出 `manifest_oracle_stale` 守卫而未被采纳，此处补记。这是上一条的另一半。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 让 artifact 与 run record 原子发布——写入 run-scoped 临时路径后共同提交，任一失败即清除或隔离 artifact。
  evidence: 固定输出路径下，本轮验证失败不会使上一轮的旧 artifact 失效；反之若 artifact 写入成功而 run record 写入失败，会在 exit 2 后留下一个无 provenance 的新 artifact。两种情况下消费者都可能读到一个并不属于当前成功运行的合法 JSON。Codex 在 PR #18 判为 P2。
- source_spec: `_bmad-output/implementation-artifacts/spec-doc-gardening-phase-2.md`
  summary: 在 `validate_run_record()` 中校验 status、reason、live、runtime、model 与 artifact 是否存在之间的允许组合，而不只是逐个查枚举。
  evidence: 目前 `status=completed` 配 `reason=timeout`、`live=false` 配 `reason=live_completed`、以及 blocked record 携带 artifact 都能通过。该 validator 是审计记录的确定性信任边界，自相矛盾的记录不应通过。Codex 在 PR #18 判为 P2。
