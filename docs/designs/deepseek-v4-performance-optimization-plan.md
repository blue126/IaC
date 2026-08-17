# DeepSeek V4 Flash 本地推理性能优化全景计划

**日期**：2026-08-15
**状态**：规划稿（未提交，未实施）
**关联**：
- `docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`（部署与实验纪年）
- `_bmad-output/implementation-artifacts/spec-deepseek-v4-memory-prefill-experiments.md`（实验规范）
- `_bmad-output/planning-artifacts/research/technical-deepseek-v4-gguf-memory-and-prefill-optimization-research-2026-08-14.md`（研究基线）

---

## TL;DR

当前部署（`ik_llama.cpp@981e5ea0` + `sokann/DeepSeek-V4-Flash-GGUF` + 双 3090 layer split + 全 CPU-MoE + 128K）**正确性已达标（19/19 契约、128K recall），但交互性能不达标**：decode ~8 tok/s（目标 ≥10），8K 冷 prefill TTFT ~85–113s。根因是**模型 145.6 GiB 远超 48GB 显存，稀疏专家几乎全在 CPU 内存，decode/prefill 都被 CPU 内存带宽与专家计算主导**，两张卡各闲置 ~11GiB 显存。

优化不能靠单一杠杆解决，而是一个**分阶段、有依赖、有证据门**的组合：

1. **decode 杠杆**：投机解码（**0731 + DSpark**）→ agentic 质量大幅提升 + decode ~1.8×（本机待测），是 decode 达标的主攻方向，需换模型 + 换 runtime（详见 §6）。
2. **prefill 杠杆**：PCIe ×8→×16 + ESXi P2P → 解锁 graph split → 再用 `--override-tensor` 精准放专家。这是 TTFT 达标的主攻方向（§7）。
3. **显存利用杠杆**：`--n-cpu-moe` 逐层 + `--override-tensor`，已测单层收益 2–3%，需与 PCIe 改善叠加才能放大（§8）。
4. **容量杠杆**：>128K context、KV 量化——是容量不是速度，独立轨道（§9）。
5. **可用性杠杆**：R6 的 34GiB prompt-cache 同步保存阻塞 /health，是独立正确性缺陷（§10）。
6. **模型杠杆**：Q3_K_M 降量化（省 CPU 带宽换 decode）——已决定，与 MTP 一并落地（§6）。
7. **运行时迁移杠杆**：SGLang-KT 当前在 3090 上不可行，作为天花板之后的备选（§11）。

**核心原则**（沿用仓库规范）：一次只改一个主变量、正确性先于性能、每个候选过 19 项契约 + 资源护栏、未达 ~10% 推广线不 promote、证据不可覆盖。

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
| P2P | 两方向均 `NS`，无 NVLink | 需 `P2P=Enabled` 才开放 graph | ❌ |
| PCIe | 两卡均 Gen3 ×8 | Gen3 ×16 | ❌ |

**已收敛、不再折腾的基线参数**（§9.1 单变量实验结论）：`threads=32`、`numa=distribute`、`threads-batch=36`、`batch=4096`、`ubatch=2048`、pinned host memory=on、`cache-ram=8GiB`、全 CPU-MoE、`split-mode=layer`、`ctx=131072`。

---

## 2. 瓶颈诊断（为什么慢）

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
| D1 | 投机解码 MTP（NextN） | decode | 1.3–1.6× | 换模型+换 runtime，高 | 无 | **待实施** |
| D2 | `--n-cpu-moe` 41→40 逐层 | decode/PP | 每层 2–3% | 低 | 无 | 42 已测，未达标 |
| D3 | `--override-tensor` 精准放专家 | decode/PP | 可能 >整层 | 中（正则放错毁正确性） | dry-run | 未做 |
| D4 | `--fit`/`--fit-margin` 自动放置 | decode/PP | 未测 | 低 | 无 | 未做 |
| D5 | `--parallel 2` 并发 | 总吞吐 | 单用户无益 | 中（分薄 KV） | 多用户需求 | 暂缓 |
| P1 | PCIe ×8→×16 维护窗口 | prefill/H2D | 未量化 | 高（停机维护） | 无 | 待排 |
| P2 | ESXi P2P 开启 | 跨卡 DMA | 前置条件 | 高（ESXi 配置） | 无 | **已启用参数，仍不可用**（物理拓扑：不同 root port） |
| P3 | graph split | prefill/分布 | 未量化 | 高（P2P+正确性） | P2 | **物理阻塞，降级** |
| P4 | `--override-tensor`（同 D3） | prefill | — | — | — | 未做 |
| C1 | context >128K（256/384K） | 容量 | 非速度 | 中 | 无 | 独立轨道 |
| C2 | KV 量化 | 容量 | 非速度 | 中（质量回归） | 无 | 低优先 |
| A1 | R6 prompt-cache 阻塞修复 | 可用性 | — | 低 | 无 | 进行中 |
| M1 | 模型降量化 Q3_K_M | decode | ~13%（rogerai 4×Blackwell 实测 Q3_K_M vs Q8，本机待测） | 低 | 与 D1 同批 | **已决定** |
| M2 | 升级 0731（DSpark） | decode/**质量** | DSpark ~1.8×（本机待测）；agentic 质量大幅提升 | 高（另下模型） | 无 | **已定（并入 D1）** |
| R1 | 迁 SGLang-KT | 天花板 | 未量化 | 高 | 硬件升级 | 3090 阻塞 |

---

## 4. 依赖关系与解锁路径

```
                    ┌─ D1 MTP ──── 需 M1 换模型(Q3_K_M-MTP) + R 换 runtime(mainline) ──┐
                    │                                                                    │
decode 达标 ────────┼─ D2/D3 专家上 GPU ── 需 P1 PCIe×16 改善 H2D 才能放大 ──────────────┤
                    │                                                                    │
                    └─ D5 并发（仅当多用户）                                            │
                                                                                         │
prefill 达标 ────── P1 PCIe×16（H2D）──► P4 override-tensor；P2/P3(graph) 物理阻塞已放弃 │
                                                                                         │
容量/质量 ───────── C1 context / C2 KV 量化（独立，不混入速度实验）                        │
                                                                                         │
可用性 ─────────── A1 R6 checkpoint/cache 修复（独立，任何 runtime 变更前先修复）          │
```

**关键路径判断**：
- **decode 达标**的主路径是 **D1（MTP）**，因为它是唯一有量级（1.3–1.6×）的 decode 杠杆；D2/D3 是百分比级补充。
- **prefill 达标**的主路径：**P1（PCIe ×16，改善 H2D）→ P4（override-tensor）**；P2/P3（P2P/graph）因物理拓扑不可用，**已放弃**（2026-08-16 实测 `cuDeviceCanAccessPeer()=0`、不同 root port）。
- D2/D3（专家上 GPU）只有在 PCIe ×16 改善 H2D 之后才能体现出应有收益——当前 ×8 拓扑下「GPU 专家放置会回退」（host_vars 注释已印证）。

---

## 5. 分阶段路线图（带证据门）

| 阶段 | 内容 | 证据门（通过才进下一阶段） | 是否变服务 |
|---|---|---|---|
| **0** | 冻结基线 + 观测 | 现有 19 项契约 + 128K + 资源采样基线可复现 | 否 |
| **1** | A1：修复 R6 checkpoint/cache 阻塞 | 128K→短请求切换时 /health 不再超时（相邻空洞 ≤60s）+ 一小时 soak | 是（候选） |
| **2** | D1+M1：0731 + DSpark + mainline `draft-dspark` | decode 中位 ≥10 tok/s（目标）、19 契约、128K recall、无 swap/OOM/restart | 是（隔离候选） |
| **3** | P1：PCIe ×8→×16 维护窗口（目标：H2D/专家 offload 改善；**不以解锁 graph 为目标**） | 两端 `LnkSta` 均 Gen3 ×16；同 corpus 重跑 1K/8K 基准 | 是（停机） |
| **4** | ~~P2/P3：ESXi P2P + graph split~~ → **已实测物理不可用，放弃**（`cuDeviceCanAccessPeer()=0`，Slot 2/4 不同 root port） | — | 否（跳过） |
| **6** | D3/D4：`--override-tensor`/`--fit` 精放 | 全契约 + 显存余量 + 收益归因 | 是（候选） |
| **7** | C1/C2：容量轨道 | 峰值分配 + recall，不影响 128K 交互基线 | 否→是 |
| **8** | M2/R1：0731 升级 / SGLang-KT | 独立 release 证据 | 是 |

> 顺序依据：先修正确性（A1），再做有量级的 decode 杠杆（D1+M1，因为它不依赖硬件变更），然后才进硬件维护窗口（P1/P2/P3，成本最高），最后做百分比级微调（D2/D3/D4）和容量/运行时轨道。

---

## 6. decode 杠杆详细方案

### D1 + M1：投机解码（0731 + DSpark，主攻）

**目标模型**：`unsloth/DeepSeek-V4-Flash-0731-GGUF` 基座（量化档待定，~104–162GB）+ 同仓库 DSpark drafter（`dspark-DeepSeek-V4-Flash-0731-Q8_0.gguf`，10.9GB）。
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

**已知风险**：(1) 0731 基座降量化 + 加 DSpark 同时改变多个变量，归因需补对照；(2) R6 的 34GiB 阻塞在 mainline 是否复现需 Stage 2 实测（mainline 是另一套 `server_prompt_cache`）；(3) DSpark 在本机 CPU-MoE 的净收益待测，先测 n_max=1/2 兜底。

**预期**：质量（agentic）确定大幅提升；decode 官方 ~1.8×（GPU 上），本机 CPU-MoE 待测（可能 1.2–1.6×，n_max 从 1 起测）。**不是**简单照搬官方数字（那是 GPU-heavy 硬件）。

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
| decode 加速 | 1.3–1.6×（n_max=1，适合 spill） | ~1.8×（GPU 上）；**本机 CPU-MoE 待测**，n_max 可降 |
| 模型下载 | rogerai Q3_K_M-MTP 143GB | unsloth 0731 基座 ~104–162GB + drafter ~7–11GB |
| runtime | mainline `draft-mtp` | mainline `draft-dspark` |
| 复杂度 | 已评估 | 已评估（同 mainline，多一个 drafter 文件） |

**基座量化档（unsloth）**：UD-IQ3_XXS ~104GB（最小可用）/ UD-Q3_K_M ~128GB / UD-Q4_K_XL ~155GB / UD-Q8_K_XL ~162GB；drafter 有 Q8_0（10.9GB）和 BF16（11.3GB）两档。

**修订建议**：B（0731 + DSpark）现在**可行且更优**——质量提升确定且直接命中 coding 负载，下载量相当（甚至更小），速度不确定性用「n_max 从 1 起测」来兜底。**倾向改选 B**，前提是你接受「0731 是 DSpark-only、无 NextN 回退」。

**已拍板：B。Stage 1 下载对象 = unsloth 0731 基座 + DSpark drafter（基座量化档待定）。**

### D2：`--n-cpu-moe` 逐层（补充）

- 已测 `--n-cpu-moe 42`：1K/8K decode 仅 +3.4%/+2.4%，8K 未达 8 tok/s 门槛，按「首个收益不显著即停」规则未继续。
- 若 PCIe ×16（P3 阶段后）改善 H2D，可重测 41/40 看收益是否累积（spec 已留此口子）。
- 每步强制：峰值显存每卡留 ≥2GiB、全契约、无 OOM。

### D3/D4：`--override-tensor` / `--fit`（微调）

- 研究结论：优先把 **shared expert、gate、up/down** 等高频张量放快内存，再放稀疏 `exps`。
- 用 `--dry-run` 先抓实际张量布局；正则表达式放错张量会毁正确性，须二次评审。
- `--fit` 在 ik fork 默认关，可用 `--fit-margin`/`--gpu-fit-margin` 评估；显式放置更易审计。

---

## 7. prefill 杠杆详细方案（TTFT 达标主攻）

### P1：PCIe ×16 维护窗口 —— **已完成并复核（2026-08-16）**

- **结论**：链路速度无问题——空闲时 Gen1 是 ASPM 省电降速，**负载时两卡均协商到 Gen3**（负载采样 + ESXi `capList/16` 双重验证）；`lspci` 的 5GT/s×32 是 ESXi 直通占位值，不可信。
- **GPU0（03:00.0）：Gen3 ×16 ✅**——宽度 ×8→×16，维护成功（ESXi LnkSta 负载下 8GT/s ×16）。
- **GPU1（04:00.0）：Gen3 ×8 ⚠️**——宽度未达 ×16（ESXi LnkCap 显示槽能力 ×16，但只协商 ×8）。待查：BIOS bifurcation（是否 ×8×8）、riser、插拔接触。
- 影响：GPU0 H2D 带宽翻倍（~7→~14 GB/s）；GPU1 不变。decode 为 CPU 带宽主导，PCIe 影响预计二阶。
- 遗留：1K/8K 基准重跑（P1 验收门），须同 corpus。

### P2：ESXi P2P 开启 —— **已实测不可用（2026-08-16）**

- ESXi 参数（`pciPassthru.allowP2P=true` + `relaxACSforP2P=true`）**已启用**，但 CUDA `cuDeviceCanAccessPeer()` **双向返回 0**；GPU 位于 **Slot 2 / Slot 4（不同 root port，不同 CPU 侧/NUMA）**。
- **结论：P2P 是物理拓扑限制，不是配置问题**。跨 root port 的 peer DMA 未被平台支持。此前「把第二张卡移到 CPU2 侧 ×16 插槽」的维护计划**不会修复 P2P**（换侧仍是不同 root port）。若想尝试 P2P，两卡须放同一 root port 组（同一 CPU 侧），本平台大概率无此插槽组合。
- P2 路线关闭；维护窗口仅保留 P1（PCIe ×16，改善 H2D）。

### P3：graph split A/B —— **物理阻塞，降级（2026-08-16 更新）**

- 前置（P2P=Enabled）**无法满足**：ESXi 参数已启用但 `cuDeviceCanAccessPeer()=0`，且两卡不同 root port。
- **graph split 从「待解锁」降级为「大概率永久阻塞」**，不投入；保留原风险记录（ik 源码警告 graph + partial offload 可能 incoherent output）。

---

## 8. 显存利用杠杆

- 当前 23GiB 显存富余，但**不能**假定都能放专家：需以 `--dry-run` + 峰值采样为准。
- D2/D3 都是这个池子的使用者，优先级：shared/gate/up-down 先于稀疏 exps。
- 每步护栏：每卡峰值留 ≥2GiB、无 swap、无 OOM、128K 启动不退化。

---

## 9. 容量杠杆（独立轨道，不混入速度实验）

- **C1 context >128K**：256K 能启动但 1K TTFT 升到 ~36s；512K 直接 CUDA OOM。这是容量 profile，不是速度优化，单独建。
- **C2 KV 量化**：当前 MLA 已压缩，128K KV 仅 5.5GiB，量化收益有限且质量有风险，仅当有明确容量需求才做。
- 二者都不得与 D/P 类实验同跑。

---

## 10. 可用性杠杆（A1，优先于一切 runtime 变更）

- **R6 缺陷**：127K→短请求切换时，pinned ik 同步保存 34.1GiB prompt-cache state（约 32 个 checkpoint，每个约 872.6 MiB，另有 KV 等其余 state），72s 阻塞 /health，相邻空洞 60.0001s 超界。
- **已批准的修复路径**：隔离的 `--ctx-checkpoints` 实验（显式 32 对照 → 8 → 仅 8 不达标才 4），每档 3 次长文 recall + 短请求 handoff + 独立 /health 探针。
- **checkpoint=8 实测（2026-08-16）**：同步保存时间显著改善（约 72s → 22–28s），**但仍出现 health timeout，可用性未解决**——属缓解而非修复：同步保存在任务队列执行的根本问题未变，只是 state 变小。若采纳，须配合「cache 策略跳过超大单条」或「保存异步化」，且不能靠放宽 health 门来「通过」。
- 任何 runtime 迁移（D1）**之前**先在新 runtime 上复现/修复此缺陷，否则会把可用性问题一起带过去。

---

## 11. 运行时迁移杠杆（R1，长期）

- SGLang-KT 是 DeepSeek V4 官方路径、MTP/DSpark 原生，但当前在 **3090（SM_86）上不可行**（issue #1999：MXFP4 需 AVX512、fp8 kernel 在 SM_86 断言失败），且 DSpark 未支持（issue #2118）。
- 触发条件：硬件升级（AVX512 CPU / Blackwell GPU）或 sglang-kt 修好 3090 路径后，作为独立 release 重新评估。
- 在 ik/mainline 的本地天花板被实测确认之前，不启动。

---

## 12. 验收标准与成功指标（汇总）

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
- [ ] mainline `draft-dspark` 的 n_max 在本机 CPU-MoE 下取几（1–5，默认 3；建议从 1/2 起测）。
- [x] 0731（DSpark）已并入 D1 主线。

---

## 14. 关键引用

- 当前模型 base：`sokann/DeepSeek-V4-Flash-GGUF`（base_model: `deepseek-ai/DeepSeek-V4-Flash`）
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
- 脚本：`scripts/deepseek-v4-mainline-build.sh`（自动检测 host nvcc；否则在 pinned runtime image 内编译，与 `prepare.yml` 同模式）。
- 构建参数：`-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86`，target `llama-server`。
- 状态：**已完成**（容器内编译，git HEAD = pin 一致）；二进制 `/opt/deepseek-v4-mainline/src/build/bin/llama-server`，容器内 `--gpus all` 运行验证通过。注意：构建 rpath 为容器路径，部署须在容器内运行或显式 `LD_LIBRARY_PATH`；mainline 默认启用 NCCL（本机 layer split 用不到，可选 `-DGGML_NCCL=OFF` 重建消除依赖）。
- 备注：rohitraj 提到多卡需编译期调高 `GGML_SCHED_MAX_SPLIT_INPUTS`；本机当前 layer split 非 graph split，先不调，graph 实验启用时再评估。
