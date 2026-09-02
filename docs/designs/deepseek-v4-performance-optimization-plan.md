# DeepSeek V4 Flash 本地推理性能优化全景计划

**创建日期**：2026-08-15；**最后更新**：2026-08-17
**状态**：执行中（Stage 1–3 已完成；mainline + DSpark 当前运行，部署与文档已提交）
**关联**：
- `docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`（部署与实验纪年）
- `_bmad-output/implementation-artifacts/spec-deepseek-v4-memory-prefill-experiments.md`（实验规范）
- `_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md`（研究基线）

---

## TL;DR

当前部署是 `mainline llama.cpp@10bf611e` + 0731 UD-Q3_K_M + Q8_0 DSpark + 双 3090 layer split + 全 CPU-MoE + 128K，`n_max=1`。相对历史 ik 基线，decode 约回退 5%，但 1K/8K cold TTFT 分别降至 7.76s/39.79s，prefill 提升到 152.64/233.66 tok/s。`n_max=2` 没有整体优势，已回调到 1；服务保持 mainline，不退回 ik。

优化不能靠单一杠杆解决，而是一个**分阶段、有依赖、有证据门**的组合：

1. **已落地杠杆**：0731 + DSpark + mainline，agentic 质量和 prefill/TTFT 是主要收益；官方 GPU-heavy 环境的 decode 加速未在本机 CPU-MoE 上兑现。
2. **下一软件杠杆**：在当前 GPU0 Gen3×16 / GPU1 Gen3×8 拓扑上探索 `--override-tensor` 精准放置；P2P/graph split 已确认物理阻塞并关闭。
3. **显存利用杠杆**：`--n-cpu-moe` 逐层 + `--override-tensor`，已测单层收益 2–3%，需与 PCIe 改善叠加才能放大（§8）。
4. **容量杠杆**：>128K context、KV 量化——是容量不是速度，独立轨道（§9）。
5. **可用性杠杆**：R6 的 34GiB prompt-cache 同步保存阻塞 /health，是独立正确性缺陷（§10）。
6. **模型杠杆**：UD-Q3_K_M 基座 + Q8_0 DSpark drafter——已决定，并入 Stage 2（§6）。
7. **运行时迁移杠杆**：SGLang-KT 当前在 3090 上不可行，作为天花板之后的备选（§11）。

**当前执行原则**：这是 homelab 快速验证；一次只改一个主变量，先 health/chat，再跑同 corpus 1K/8K 三样本与 control 对比，并检查 OOM/restart。未经用户要求不扩展成长 soak 或 production promotion 流程。

---

## 1. 现状基线（实测，2026-08-14/15）

| 指标 | 实测值 | 目标 | 判定 |
|---|---:|---:|---|
| API 契约 | 19/19 | 19/19 | ✅ |
| 128K recall | 通过（126,992 tokens） | 通过 | ✅ |
| decode 吞吐 | 1K 8.05 / 8K 7.68 tok/s | ≥10 tok/s | ❌ |
| 8K 冷 prefill TTFT | ~85–113 s | 越快越好（无固定阈值） | ❌ |
| 1K 冷 TTFT | ~22 s | 越快越好（无固定阈值） | ⚠️ |
| prefill 吞吐 | 1K 冷 ~71 / 8K 冷 ~89 tok/s | 越快越好 | ⚠️ |
| 空闲显存 | GPU0/1 各 ~11–12 GiB | 每卡峰值留 ≥2 GiB | 有富余 |
| 主机可用 RAM | ~150–186 GiB（视负载） | 无 swap/OOM | ✅ |
| P2P | 两方向均 `NS`，无 NVLink | 路线已关闭 | ❌ 物理阻塞 |
| PCIe | GPU0 Gen3 ×16 / GPU1 Gen3 ×8（维护后） | 两卡 Gen3 ×16 | ⚠️ GPU1 待维护 |

**已收敛、不再折腾的基线参数**（单变量实验结论）：`threads=32`、`numa=distribute`、`threads-batch=36`、`batch=4096`、`ubatch=2048`、pinned host memory=on、`cache-ram=8GiB`、全 CPU-MoE、`split-mode=layer`、`ctx=131072`。

---

## 2. 瓶颈诊断（为什么慢）

以下数字描述历史 ik 基线；mainline 已显著改善 prefill/TTFT，但全 CPU-MoE 下的 CPU 内存带宽/专家计算瓶颈仍存在：

```
decode ~8 tok/s ← 每个 token 要读激活的 6 个专家权重（256 专家 MoE）
                  ← 专家在 CPU 内存 → CPU 内存带宽 + 专家计算主导
prefill 85–113s ← 同样被 CPU 专家带宽主导，冷前缀无 KV cache 命中
显存闲置 23GiB  ← 模型 145.6GiB 装不进 48GB，专家只能留在 CPU
```

四条独立的内存池（不可互相替代）：CPU 专家权重、host prompt-cache、GPU 权重/KV、GPU/host 计算 workspace。**在一个池子里的空闲不代表另一个池子能放下**。

因此优化的本质是**「把更多的活跃计算/权重移向快内存（GPU），并减少 CPU 侧的数据搬运」**，而不是「把 context 或并发调大」。

---

## 3. 优化杠杆全景（全部方向）

| # | 杠杆 | 作用维度 | 预期 | 成本/风险 | 依赖 | 状态 |
|---|---|---|---|---|---|---|
| D1 | 0731 + DSpark 投机解码 | decode | ~1.8×（GPU-heavy；本机实测未兑现） | 换模型+换 runtime，高 | 无 | **已部署；decode -5%左右，prefill/TTFT 显著改善** |
| D2 | `--n-cpu-moe` 41→40 逐层 | decode/PP | 每层 2–3% | 低 | 无 | 42 已测，未达标 |
| D3 | `--override-tensor` 精准放专家 | decode/PP | 可能 >整层 | 中（正则放错毁正确性） | help + GGUF/verbose 张量发现 | 未做 |
| D4 | `--fit` 自动放置 | decode/PP | — | — | — | **当前不做：DSpark 已验证必须 `--fit off`** |
| D5 | `--parallel 2` 并发 | 总吞吐 | 单用户无益 | 中（分薄 KV） | 多用户需求 | 暂缓 |
| P1 | PCIe 链路维护与基准验收 | prefill/H2D | 已形成当前拓扑基线 | 高（停机维护） | 无 | **完成：GPU0 ×16 / GPU1 ×8；1K/8K 已跑** |
| P2 | ESXi P2P 开启 | 跨卡 DMA | 前置条件 | 高（ESXi 配置） | 无 | **已启用参数，仍不可用**（物理拓扑：不同 root port） |
| P3 | graph split | prefill/分布 | 未量化 | 高（P2P+正确性） | P2 | **物理阻塞，降级** |
| P4 | `--override-tensor`（同 D3） | prefill | — | — | — | 未做 |
| C1 | context >128K（256/384K） | 容量 | 非速度 | 中 | 无 | 独立轨道 |
| C2 | KV 量化 | 容量 | 非速度 | 中（质量回归） | 无 | 低优先 |
| A1 | R6 prompt-cache 阻塞修复 | 可用性 | — | 低 | 无 | 进行中 |
| M1 | UD-Q3_K_M 基座 + Q8_0 drafter | decode/质量 | 本机 decode 未提升；prefill/TTFT 显著改善 | 高（换模型） | 与 D1 同批 | **已部署并基准验证** |
| R1 | 迁 SGLang-KT | 天花板 | 未量化 | 高 | 硬件升级 | 3090 阻塞 |

---

## 4. 依赖关系与解锁路径

```
                    ┌─ D1 DSpark ── 需 M1 换模型(UD-Q3_K_M + Q8_0 drafter) + mainline ─┐
                    │                                                                    │
decode 改善 ────────┼─ D2/D3 专家上 GPU ── 当前 ×16/×8 可测；GPU1 修到 ×16 后再复测 ───┤
                    │                                                                    │
                    └─ D5 并发（仅当多用户）                                            │
                                                                                         │
prefill 改善 ────── 当前拓扑基线已完成 ──► P4 override-tensor；P2/P3 已放弃            │
                                                                                         │
容量/质量 ───────── C1 context / C2 KV 量化（独立，不混入速度实验）                        │
                                                                                         │
可用性 ─────────── A1 R6 在 mainline 按需复现/判定                                      │
```

**关键路径判断**：
- D1 已落地，但 decode 目标未达；下一软件杠杆是 D3/P4 `override-tensor`。
- 当前 ×16/×8 拓扑的 control 已完成，可直接做单变量候选；GPU1 修到 ×16 后再复测胜出候选。P2P/graph 因物理拓扑不可用，已放弃。
- `override-tensor` 必须先核实 pinned mainline 的帮助文本，并从 GGUF 工具或 verbose 加载日志取得实际张量名；当前 binary 没有 `--dry-run`，不能照抄旧 ik 正则。

---

## 5. 分阶段路线图（带证据门）

| 阶段 | 内容 | 证据门（通过才进下一阶段） | 是否变服务 |
|---|---|---|---|
| **1** | 0731 模型下载、SHA-256、mainline 编译与硬件核验 | 5/5 SHA-256、runtime pin、容器内启动、PCIe/P2P 证据 | **已完成** |
| **2** | D1+M1：0731 + DSpark + mainline `draft-dspark` | 快速 health/chat + 1K/8K 三样本基准 | **已完成；mainline 当前运行** |
| **3** | 当前 GPU0 ×16 / GPU1 ×8 的 mainline 1K/8K 基准 | 同 corpus `n_max=1/2` 对照 | **已完成；采用 1** |
| **4** | D3：`--override-tensor` 精放（下一软件步骤） | help/list-devices + GGUF/verbose 日志核实；health/chat；1K/8K 三样本；无 OOM/restart | 是 |
| **H1** | GPU1 ×8 清洁、重插或交换测试（独立硬件轨道） | GPU1 Gen3 ×16，或确认卡 lane 损伤并接受 ×8 | 是（停机维护） |
| **5** | C1/C2：256K/384K 容量轨道 | 峰值分配 + recall，不影响 128K 交互基线 | 是 |
| **6** | R1：SGLang-KT 重评估 | 硬件升级或已知阻塞修复后的独立验证 | 是 |

> 当前 Stage 1–3 已完成。下一位 AI 从 Stage 4 的 `override-tensor` 发现步骤开始；H1 是独立维护窗口，不阻塞软件实验。P2P/graph split 已关闭，不再进入执行路线。

---

## 6. decode 杠杆详细方案

### D1 + M1：投机解码（0731 + DSpark，主攻）

**目标模型**：`unsloth/DeepSeek-V4-Flash-0731-GGUF` 的 UD-Q3_K_M 基座（4 分片，约 128GB）+ Q8_0 DSpark drafter（`dspark-DeepSeek-V4-Flash-0731-Q8_0.gguf`，10.9GB）。
**目标 runtime**：mainline llama.cpp（#25784/`596a579` 之后），flag `--spec-type draft-dspark --spec-draft-n-max N --fit off -fa on --jinja`。

**为什么必须换模型 + 换 runtime**（已核实）：
- 当前 `sokann` GGUF 实测 `block_count=43`、**0 个 MTP head 张量**（投机 head 被转换器剥掉）。
- pinned `ik@981e5ea0` 的 deepseek4 加载器只在「standalone companion」布局加载 nextn head，无法使用 rogerai 的「embedded」布局（源码 `create_deepseek4_tensors` 已核对）→ 必须离开 ik。
- 投机机制绑定版本：已定 **0731（DSpark）**——0731 只带 DSpark、无 NextN head（rohitraj 证实），故用 `draft-dspark`，不是 `draft-mtp`。

**三条 runtime 路径判定**：
| 路径 | 判定 | 理由 |
|---|---|---|
| B1 mainline #25784+ + v2 | ✅ **采用** | rogerai 官方 stock 路径；mainline 已含 `--cache-ram`/`--ctx-checkpoints`/`--cpu-moe`/`--n-cpu-moe`/`--numa`（Stage 0 已核对），迁移风险低 |
| B2 rogerai fork + v1 | 备选 | 可跑但小众，仅作 B1 fallback |
| B3 SGLang-KT | ❌ | 3090 跑不起来（issue #1999）+ DSpark 不支持（issue #2118） |

**实测结论/遗留**：(1) 0731 基座降量化 + DSpark 是组合变化，不能把全部差异归因给 speculation；(2) R6 是否在 mainline 的独立 `server_prompt_cache` 实现中复现仍未知；(3) `n_max=1/2` 已测，采用 1，不要重复。

**实测**：质量方向保留 0731；官方 ~1.8× decode 数据来自 GPU-heavy 硬件，本机 CPU-MoE 未兑现。实际主要收益是 prefill/TTFT，详见 §15.3。

### ✅ 已定：B（0731 + DSpark）—— 决策过程记录

**B 的可行性已确认（2026-08-16 重新评估）**：mainline llama.cpp #25784（merge `596a579`）原生支持；`unsloth/DeepSeek-V4-Flash-0731-GGUF` 仓库**同时提供 0731 基座 GGUF + DSpark drafter**，单源即可落地。

**关键事实（rohitraj 实测 + unsloth 仓库核实）**：
- **0731 只带 DSpark、没有 NextN MTP head**——「on 0731 reaching for `draft-mtp` is reaching for a head that is not there」。所以 B 是 DSpark 专用，无法回退 `draft-mtp`。
- **DSpark 是独立小 drafter 模型**（`--model-draft`，仅 ~7–11GB / 81 张量），不是嵌在基座里。
- 调用：`--model <0731基座> --model-draft <drafter> --spec-type draft-dspark --spec-draft-n-max N --fit off -fa on --jinja`（`--fit off` 必需，PR 线程实测）。
- `--spec-draft-n-max` 默认 3、上限被 clamp 到 5（V4 drafter 训练块大小）；**可设 1–5 调档**——缓解了「长 draft 在 CPU-MoE 上亏」的担忧（可先测 n_max=1/2）。
- 质量提升确定：Terminal Bench 61.8→82.7、NL2Repo 39.4→54.2、**DeepSWE 7.3→54.4**（rohitraj 引官方+AA 数据）。

| | A：Preview + NextN-MTP | B：0731 + DSpark |
|---|---|---|
| agentic 质量 | 基线（Preview，已被 0731 取代） | **大幅更好**（DeepSWE 7.3→54.4） |
| 投机机制 | NextN 单 head（embedded） | DSpark（独立 drafter） |
| decode 加速 | 1.3–1.6×（外部数据） | 外部 GPU-heavy ~1.8×；**本机实测约比 ik 低 5%** |
| 模型下载 | rogerai Q3_K_M-MTP 143GB | unsloth 0731 基座 ~104–162GB + drafter ~7–11GB |
| runtime | mainline `draft-mtp` | mainline `draft-dspark` |
| 复杂度 | 已评估 | 已评估（同 mainline，多一个 drafter 文件） |

**基座量化档（unsloth）**：UD-IQ3_XXS ~104GB（最小可用）/ UD-Q3_K_M ~128GB / UD-Q4_K_XL ~155GB / UD-Q8_K_XL ~162GB；drafter 有 Q8_0（10.9GB）和 BF16（11.3GB）两档。

**决策结论**：B（0731 + DSpark）**可行且已采用**——质量提升确定且直接命中 coding 负载，速度不确定性用「n_max 从 1 起测」兜底。0731 是 DSpark-only，无 NextN 回退。

**已拍板：B。Stage 1 下载对象 = unsloth 0731 UD-Q3_K_M 基座 + Q8_0 DSpark drafter；5/5 SHA-256 已通过。**

### D2：`--n-cpu-moe` 逐层（补充）

- 已测 `--n-cpu-moe 42`：1K/8K decode 仅 +3.4%/+2.4%，8K 未达 8 tok/s 门槛，按「首个收益不显著即停」规则未继续。
- 若 GPU1 后续修复到 ×16，可选择性重测胜出候选；不要先重复已失败的 42 档。
- 每步至少要求：health/chat、峰值显存每卡留 ≥2GiB、无 OOM/restart；完整契约仅在用户要求资格验证时运行。

### D3：`--override-tensor`（下一软件实验）

- 研究结论：优先把 **shared expert、gate、up/down** 等高频张量放快内存，再放稀疏 `exps`。
- 当前 pinned binary 已确认语法：主模型 `-ot/--override-tensor <tensor name pattern>=<buffer type>,...`，drafter `-otd/--override-tensor-draft`；`--list-devices` 返回 `CUDA0`/`CUDA1`。
- 当前 binary 没有 `--dry-run`。须先通过 GGUF 检查工具或一次受控 `--verbose` 加载获取真实张量名，并实证 buffer type 写法；正则表达式放错张量会破坏正确性。
- 一次只加一条规则，rendered command 与当前 control 做 diff；先 health/chat，再跑 1K/8K 三样本并检查 OOM/restart。
- `--fit off` 是当前 DSpark 路线的已验证必需项，不把 `--fit` 作为下一实验变量。

---

## 7. prefill 杠杆详细方案（TTFT 达标主攻）

### P1：PCIe 链路维护 —— **物理操作与当前拓扑基准已完成（2026-08-17）**

- **结论**：链路速度无问题——空闲时 Gen1 是 ASPM 省电降速，**负载时两卡均协商到 Gen3**（负载采样 + ESXi `capList/16` 双重验证）；`lspci` 的 5GT/s×32 是 ESXi 直通占位值，不可信。
- **GPU0（03:00.0）：Gen3 ×16 ✅**——宽度 ×8→×16，维护成功（ESXi LnkSta 负载下 8GT/s ×16）。
- **GPU1（04:00.0）：Gen3 ×8 ⚠️**——槽能力 ×16，但 GPU1 在换槽后仍跟随该卡保持 ×8，问题已收敛到卡的金手指接触或 lane 损伤；维护时清洁/重插并做交换确认。
- 影响：GPU0 H2D 带宽翻倍（~7→~14 GB/s）；GPU1 不变。decode 为 CPU 带宽主导，PCIe 影响预计二阶。
- 当前 ×16/×8 拓扑的 mainline 1K/8K control 已完成（§15.3）；遗留仅是 GPU1 ×8 的独立硬件处理。

### P2：ESXi P2P 开启 —— **已实测不可用（2026-08-16）**

- ESXi 参数（`pciPassthru.allowP2P=true` + `relaxACSforP2P=true`）**已启用**，但 CUDA `cuDeviceCanAccessPeer()` **双向返回 0**；GPU 位于 **Slot 2 / Slot 4（不同 root port，不同 CPU 侧/NUMA）**。
- **结论：P2P 是物理拓扑限制，不是配置问题**。跨 root port 的 peer DMA 未被平台支持。此前「把第二张卡移到 CPU2 侧 ×16 插槽」的维护计划**不会修复 P2P**（换侧仍是不同 root port）。若想尝试 P2P，两卡须放同一 root port 组（同一 CPU 侧），本平台大概率无此插槽组合。
- P2 路线关闭；维护窗口仅保留 P1（PCIe ×16，改善 H2D）。

### P3：graph split A/B —— **物理阻塞，降级（2026-08-16 更新）**

- 前置（P2P=Enabled）**无法满足**：ESXi 参数已启用但 `cuDeviceCanAccessPeer()=0`，且两卡不同 root port。
- **graph split 从「待解锁」降级为「大概率永久阻塞」**，不投入；保留原风险记录（ik 源码警告 graph + partial offload 可能 incoherent output）。

---

## 8. 显存利用杠杆

- 当前约 16.7GiB 总空闲显存（实测 GPU0/1 约 7.3/9.4GiB），但**不能**假定都能放专家：须以张量发现、受控加载和峰值采样为准。
- D2/D3 都是这个池子的使用者，优先级：shared/gate/up-down 先于稀疏 exps。
- 每步护栏：每卡峰值留 ≥2GiB、无 swap、无 OOM、128K 启动不退化。

---

## 9. 容量杠杆（独立轨道，不混入速度实验）

- **C1 context >128K**：256K 能启动但 1K TTFT 升到 ~36s；512K 直接 CUDA OOM。这是容量 profile，不是速度优化，单独建。
- **C2 KV 量化**：当前 MLA 已压缩，128K KV 仅 5.5GiB，量化收益有限且质量有风险，仅当有明确容量需求才做。
- 二者都不得与 D/P 类实验同跑。

---

## 10. 可用性杠杆（A1，按需验证）

- **R6 缺陷**：127K→短请求切换时，pinned ik 同步保存 34.1GiB prompt-cache state（约 32 个 checkpoint，每个约 872.6 MiB，另有 KV 等其余 state），72s 阻塞 /health，相邻空洞 60.0001s 超界。
- **已批准的修复路径**：隔离的 `--ctx-checkpoints` 实验（显式 32 对照 → 8 → 仅 8 不达标才 4），每档 3 次长文 recall + 短请求 handoff + 独立 /health 探针。
- **checkpoint=8 实测（2026-08-16）**：同步保存时间显著改善（约 72s → 22–28s），**但仍出现 health timeout，可用性未解决**——属缓解而非修复：同步保存在任务队列执行的根本问题未变，只是 state 变小。若采纳，须配合「cache 策略跳过超大单条」或「保存异步化」，且不能靠放宽 health 门来「通过」。
- mainline 已直接用于 homelab。若实际使用仍出现长上下文切换时的 health 空洞，再在 mainline 上复现；不要假定 ik 的 `server_prompt_cache` 行为原样继承。

---

## 11. 运行时迁移杠杆（R1，长期）

- SGLang-KT 是 DeepSeek V4 官方路径、MTP/DSpark 原生，但当前在 **3090（SM_86）上不可行**（issue #1999：MXFP4 需 AVX512、fp8 kernel 在 SM_86 断言失败），且 DSpark 未支持（issue #2118）。
- 触发条件：硬件升级（AVX512 CPU / Blackwell GPU）或 sglang-kt 修好 3090 路径后，作为独立 release 重新评估。
- 在 ik/mainline 的本地天花板被实测确认之前，不启动。

---

## 12. 验收标准与成功指标（汇总）

下表是需要完整资格验证时的标准，不是下一轮快速 `override-tensor` 实验的默认工作量。快速实验按 §TL;DR 的最小 health/chat + 1K/8K 三样本执行；只有用户明确要求长期采用或完整验证时才扩展到 19 契约、128K 和 soak。

| 目标 | KPI | 证据 |
|---|---|---|
| decode 达标 | decode 中位 ≥10 tok/s | 同 corpus 三样本中位 |
| prefill 达标 | 8K 冷 TTFT 下降（越快越好，无固定阈值） | cold-prefill 中位 |
| 正确性 | 19/19 契约 + 128K recall | 版本化契约 JSON |
| 稳定性 | 无 OOM/持续 swap/意外 restart | cgroup/host/资源采样 |
| 可用性 | /health 相邻空洞 ≤60s | soak 探针 |
| 归因 | 每候选单变量 + 显式 control | manifest + rendered-command diff |
| 推广门槛 | 声明指标 ≥~10% 收益 | control/candidate 对比 + verdict |

---

## 13. 未决项与决策点

- [x] 0731 基座 + DSpark drafter 下载：**已完成**（unsloth，`/data/models/DeepSeek-V4-Flash-0731-GGUF/`）；mainline 编译**已完成**。
- [x] prefill TTFT 目标：**无固定数值，越快越好**（用户已确认）；候选较 control 需实际下降（参考 ~10% 推广线）且无回归。
- [x] **方向性决策：已定 B（0731 + DSpark）**（§6）。基座量化档：**UD-Q3_K_M**（已下载）；drafter：**Q8_0**（已下载）。
- [x] PCIe/P2P：P1 已复核（GPU0 Gen3×16 ✅ / GPU1 Gen3×8 ⚠️）；P2P 物理不可用 → P2/P3 放弃。
- [x] mainline `draft-dspark` 的 n_max 已实测 1/2：2 仅改善 1K decode（+2.3%），8K decode 回退（-2.6%），没有整体优于 1；采用 1。
- [x] 0731（DSpark）已并入 D1 主线。

---

## 14. 关键引用

- 历史 ik 基线模型：`sokann/DeepSeek-V4-Flash-GGUF`；当前模型：`unsloth/DeepSeek-V4-Flash-0731-GGUF` 的 UD-Q3_K_M + Q8_0 drafter
- MTP GGUF：https://huggingface.co/rogerai-fyi/DeepSeek-V4-Flash-MTP-GGUF
- mainline DSpark/MTP 合并：https://github.com/ggml-org/llama.cpp/pull/25784
- DSpark 实测（1.83×）：https://rohitraj.tech/ar/notes/deepseek-dspark-speculative-decoding-llamacpp-2026
- KTransformers 3090 阻塞：https://github.com/kvcache-ai/ktransformers/issues/1999
- sglang-kt DSpark 缺失：https://github.com/kvcache-ai/ktransformers/issues/2118
- KTransformers V4 Flash 指南：https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/DeepSeek-V4-Flash.md
- ik MTP 参数：https://github.com/ikawrakow/ik_llama.cpp/blob/981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8/docs/parameters.md
- Broadcom VMDirectPath P2P：https://knowledge.broadcom.com/external/article/312208/vsphere-vmdirectpath-io-and-dynamic-dire.html

---

## 15. Stage 1 执行清单与状态（0731 + DSpark，2026-08-16）

### 15.1 下载清单（unsloth/DeepSeek-V4-Flash-0731-GGUF）

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `UD-Q3_K_M/DeepSeek-V4-Flash-0731-UD-Q3_K_M-00001-of-00004.gguf` | 0.01 GB | `36e02d6d87c9fbfe0dd4e8fd0d03cef2aa2c509248802a9d1772159112db3734` |
| `UD-Q3_K_M/DeepSeek-V4-Flash-0731-UD-Q3_K_M-00002-of-00004.gguf` | 49.22 GB | `b210930a3dc8ad13b55f6a0eb79b58abb0752ac446cb53aebcdc744c6834a7ad` |
| `UD-Q3_K_M/DeepSeek-V4-Flash-0731-UD-Q3_K_M-00003-of-00004.gguf` | 49.53 GB | `ac71bc6fd30c0af3eb702cea5bc94be570b9fed4857d63bf7180ec668683612c` |
| `UD-Q3_K_M/DeepSeek-V4-Flash-0731-UD-Q3_K_M-00004-of-00004.gguf` | 29.32 GB | `28b764750db8c4539df530292cd5950c6d161d81b20673b736ff4f8ca4ffa7ae` |
| `dspark-DeepSeek-V4-Flash-0731-Q8_0.gguf` | 10.90 GB | `2c7ac54b0b64a99df1f139a9f1371a00198265e1d6a614b77597d20a655a4249` |
| **合计** | **138.97 GB** | — |

- 目标目录：guest `/data/models/DeepSeek-V4-Flash-0731-GGUF/`（隔离，不影响现有模型）。
- 工具：guest host `hf download`（resumable，断网后重跑同命令自动续传；`/tmp/0731-download.log`）。
- 校验：`hf download` 下载时自动核对 LFS 校验；完成后用上表 SHA-256 复核。
- 状态：**已完成**（5/5 文件就位，**SHA-256 复核 5/5 全部通过**，与上表清单一致；断网一次由 `hf download` 续传成功）。未认证请求受 HF 限速（可选设 `HF_TOKEN` 加速）。

### 15.2 mainline 编译清单

- **Pin**：`ggml-org/llama.cpp@10bf611e533d81f739128304991c5e133c6aebd8`（2026-08-16 master HEAD，≥ `596a579`/PR #25784，含 `draft-dspark`）。
- 目录：guest `/opt/deepseek-v4-mainline/{src,build}`（隔离，不动 `/opt/deepseek-v4-ik`）。
- 脚本：`scripts/llama-cpp-mainline-build.sh`（固定在 pinned runtime image 内编译并校验 binary SHA-256）。
- 构建参数：`-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86`，target `llama-server`。
- 状态：**已完成**（容器内编译，git HEAD = pin 一致）；二进制 `/opt/deepseek-v4-mainline/src/build/bin/llama-server`，容器内 `--gpus all` 运行验证通过。注意：构建 rpath 为容器路径，部署须在容器内运行或显式 `LD_LIBRARY_PATH`；mainline 默认启用 NCCL（本机 layer split 用不到，可选 `-DGGML_NCCL=OFF` 重建消除依赖）。
- 备注：rohitraj 提到多卡 graph split 可能需调高 `GGML_SCHED_MAX_SPLIT_INPUTS`；本机使用 layer split，且 graph 路线已关闭，因此不调整。

### 15.3 mainline + DSpark 快速部署与基准（2026-08-17）

- 服务：`deepseek-v4-mainline.service` active + enabled；ik inactive；稳定 API `8081` health/chat 通过。
- 1K：decode 7.58 tok/s，TTFT 7.76s，prefill 152.64 tok/s。
- 8K：decode 7.31 tok/s，TTFT 39.79s，prefill 233.66 tok/s。
- 相比 ik：decode 约回退 5%，但 TTFT 下降约 53–65%，prefill 提升至约 2.15–2.63×。
- 资源：0 restart、无 swap、GPU0/1 空闲显存约 7.3/9.4GiB、available RAM 约 207GiB。
- 证据：guest `/tmp/mainline-dspark-1k.json`、`/tmp/mainline-dspark-8k.json`。

`n_max=2` 追加基准：

- 1K：decode 7.75 tok/s，TTFT 7.68s，prefill 154.27 tok/s；对 `n_max=1` 分别为 +2.3%、-1.1%、+1.1%。
- 8K：decode 7.11 tok/s，TTFT 40.12s，prefill 231.79 tok/s；对 `n_max=1` 分别为 -2.6%、+0.8%、-0.8%。
- 结论：`n_max=2` 没有整体性能优势，运行参数回调为 1；不退回 ik runtime。
- 证据：guest `/tmp/mainline-dspark-nmax2-1k.json`、`/tmp/mainline-dspark-nmax2-8k.json`。
