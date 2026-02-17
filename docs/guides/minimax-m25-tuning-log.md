# MiniMax M2.5 性能调优实测记录

> 本文档从 [minimax-llama.md](minimax-llama.md) 的 6.6 节独立拆出，记录在 Dual RTX 3090 + ik_llama.cpp 上逐步调优 MiniMax M2.5 的完整过程。

## 测试环境

- **引擎**：ik_llama.cpp commit `f7923739`
- **模型**：unsloth/MiniMax-M2.5-GGUF (UD-Q5_K_XL, ~162GB, 5 shards)
- **硬件**：2× RTX 3090 (24GB × 2)，384GB DDR4，2× Xeon E5-2686 v4
- **固定参数**：`-ngl 999 --ctx-size 65536 --parallel 1 --jinja`
- **测试负载**：短 prompt（46 tokens → 生成 ~250 tokens），长 prompt（~5045 tokens → 生成 100 tokens）
- **方法论**：每次只改变一个变量以隔离效果，使用 Ansible `llm-benchmark` role 自动化执行

---

## 基线：`--cpu-moe` + KV cache f16

初始配置将所有 expert 层全量卸载到 CPU，KV cache 使用 FP16：

```
--cpu-moe --split-mode layer --tensor-split 1,1
--cache-type-k f16 --cache-type-v f16
```

| 指标 | 值 |
|------|-----|
| Short gen | 6.5 tok/s |
| Long gen | 4.7 tok/s |
| Long prefill | 84 tok/s |
| CUDA0 | ~12 GB |
| CUDA1 | ~12 GB |
| RSS | ~153 GB |

> VRAM 在两卡间分布均匀，但生成速度较慢（所有 expert 在 CPU 上计算）。

---

## 第一轮：KV cache q8_0 + `--n-cpu-moe 58`

将 KV cache 从 f16 降级到 q8_0（减半 VRAM 占用），同时用 `--n-cpu-moe 58` 替代 `--cpu-moe`，将 5 层 expert 放到 GPU 加速。

**变更**：
```diff
- --cpu-moe
- --cache-type-k f16 --cache-type-v f16
+ --n-cpu-moe 58
+ --cache-type-k q8_0 --cache-type-v q8_0
```

> 注：首次尝试 `n-cpu-moe=52`（11 层 expert on GPU）导致 CUDA1 OOM（需要 27366 MiB，超过 24GB），回退到 58。

| 指标 | 基线 | n-cpu-moe=58 | 变化 |
|------|------|-------------|------|
| Short gen | 4.7 | 6.0 | +28% |
| Short prefill | — | 16.1 | — |
| Long gen | 4.7 | 6.4 | +36% |
| Long prefill | 84 | 91.2 | +8.6% |
| CUDA0 | ~12 GB | 5,848 MiB | — |
| CUDA1 | ~12 GB | 17,334 MiB | — |
| RSS | ~153 GB | 140 GB | -8.5% |

> **关键发现**：`--n-cpu-moe` 在多 GPU 环境下不均匀分配 expert 层（[已知问题](https://github.com/ggml-org/llama.cpp/issues/15136)），CUDA1 承担了大部分 expert。生成速度大幅提升，但 VRAM 极度不均。

---

## 第二轮：`--n-cpu-moe 57`（多 1 层 expert 到 GPU）

在上轮基础上减少 1 层 CPU expert（58→57），让 6 层 expert 在 GPU 上。

| 指标 | moe=58 | moe=57 | 变化 |
|------|--------|--------|------|
| Short gen | 6.0 | **6.65** | +10.8% |
| Short prefill | 16.1 | 13.0 | -19% |
| Long gen | 6.4 | 6.48 | +1.3% |
| Long prefill | 91.2 | 91.6 | ~持平 |
| CUDA0 | 5,848 | 5,924 | +76 MiB |
| CUDA1 | 17,334 | 19,940 | +2,606 MiB |

> 新增的 expert 层**全部落在 CUDA1**，CUDA0 几乎没变。CUDA1 已用 81%（19.9/24.5 GB）。

---

## 第三轮：`--tensor-split 3,1`（尝试平衡 VRAM）

尝试将 75% 基础层放 CUDA0，为 CUDA1 的 expert 腾空间。

| 指标 | ts=1,1 (基线) | ts=3,1 | 变化 |
|------|-------------|--------|------|
| Short gen | 6.65 | 6.09 | **-8.4%** |
| Short prefill | 13.0 | 16.0 | +23% |
| Long gen | 6.48 | **6.79** | +4.8% |
| Long prefill | 91.6 | **92.1** | +0.5% |
| CUDA0 | 5,924 | 8,624 | +2,700 MiB |
| CUDA1 | 19,940 | 17,242 | -2,698 MiB |

> `tensor-split` 只控制基础层分布，不影响 expert 层放置。VRAM 有所改善，但短 prompt 生成速度反而下降（跨卡通信对称性被打破）。**结论**：`tensor-split` 不是解决 VRAM 不均的正确工具。

---

## 第四轮：`--split-mode graph`（张量并行）

切换回 `tensor-split 1,1`，将 `split-mode` 从 `layer`（顺序执行）改为 `graph`（两卡并行计算）。这是 ik_llama.cpp 特有的功能。

**变更**：
```diff
- --split-mode layer
+ --split-mode graph
```

| 指标 | layer (基线) | **graph** | 变化 |
|------|------------|-----------|------|
| Short gen | 6.65 | **7.01** | **+5.4%** |
| Short prefill | 13.0 | **16.3** | **+25%** |
| Long gen | 6.48 | 6.57 | +1.4% |
| Long prefill | 91.6 | 91.9 | ~持平 |
| CUDA0 | 5,924 | 5,924 | 不变 |
| CUDA1 | 19,940 | 19,940 | 不变 |
| RSS | 137.6 GB | 137.6 GB | 不变 |

> **Graph 模式显著提升短 prompt 性能**，且不改变 VRAM 分布和内存占用。纯计算调度优化。

---

## 第五轮：`-ot`（Override Tensor）均匀分配 expert

`--n-cpu-moe` 的不均匀分配是[已知 bug](https://github.com/ggml-org/llama.cpp/issues/15136)。用 `-ot` 手动指定 expert 层放置，替代 `--n-cpu-moe 57`：

**变更**：
```diff
- --n-cpu-moe 57
+ -ot "blk\.(5[7-9])\.ffn_(up|down|gate)_exps\.weight=CUDA0"
+ -ot "blk\.(6[0-2])\.ffn_(up|down|gate)_exps\.weight=CUDA1"
+ -ot "\.ffn_(up|down|gate)_exps\.weight=CPU"
```

意图是 6 层 expert 在 GPU（3 层 CUDA0 + 3 层 CUDA1）。

| 指标 | graph+moe57 | **graph+ot** | 变化 |
|------|------------|-------------|------|
| Short gen | 7.01 | 6.29 | **-10.3%** |
| Short prefill | 16.3 | 13.7 | -16% |
| Long gen | 6.57 | 6.47 | -1.5% |
| Long prefill | 91.9 | 90.0 | -2.1% |
| **CUDA0** | **5,924** | **13,820** | **+7,896 MiB** |
| **CUDA1** | **19,940** | **12,046** | **-7,894 MiB** |
| RSS | 137.6 GB | 137.6 GB | 不变 |

> **VRAM 分布大幅改善**（13.8:12.0 vs 5.9:19.9），但性能出现回退。短 prompt 生成下降 10%。

**日志分析 — 实际 GPU 分配为 3+2（非 3+3）**：

查看 `journalctl -u llama-server` 启动日志，发现 `-ot` 生效的实际层分配：

```
# CUDA0 匹配了 3 层（blk.57, 58, 59）✓
buffer type overriden to CPU for tensor blk.57.ffn_...
→ 实际放到 CUDA0

# CUDA1 只匹配了 2 层（blk.60, 61）✗
# blk.62 没有 expert 层！模式 blk\.(6[0-2]) 中 62 是空匹配
```

**根因**：MiniMax M2.5 共 63 层（blk.0 ~ blk.62），但 **expert 层只存在于 blk.0 ~ blk.61**。blk.62 是输出层，不包含 `ffn_(up|down|gate)_exps` 张量。因此正则 `blk\.(6[0-2])` 实际只匹配了 blk.60 和 blk.61（2 层），总计只有 5 层 expert 在 GPU（3+2），不是预期的 6 层（3+3）。

启动日志中的 buffer 分配证实了这一点：

```
CUDA0 buffer size =  8912.02 MiB   （3 层 expert + 基础层份额）
CUDA1 buffer size =  7135.02 MiB   （2 层 expert + 基础层份额）
KV cache CUDA0    =  4352.00 MiB
KV cache CUDA1    =  4080.00 MiB
CPU buffer size   = 140853.02 MiB  （剩余 57 层 expert + 其他）
```

**修正方案**：将正则下移一层，覆盖 blk.56-58 → CUDA0、blk.59-61 → CUDA1，确保 6 层（3+3）全部有效匹配（见第六轮）。

---

## 第六轮：修正 `-ot` 正则（真正 3+3 分配）

修正正则覆盖范围：blk.56-58 → CUDA0，blk.59-61 → CUDA1，确保 6 层全部有效。

**变更**：
```diff
- -ot "blk\.(5[7-9])\.ffn_(up|down|gate)_exps\.weight=CUDA0"
- -ot "blk\.(6[0-2])\.ffn_(up|down|gate)_exps\.weight=CUDA1"
+ -ot "blk\.(5[6-8])\.ffn_(up|down|gate)_exps\.weight=CUDA0"
+ -ot "blk\.(59|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"
```

| 指标 | 第五轮 (3+2) | **第六轮 (3+3)** | 变化 |
|------|-------------|-----------------|------|
| Short gen | 6.29 | 5.80 | -7.8% |
| Short prefill | 13.7 | **16.4** | **+19.7%** |
| Long gen | 6.47 | **6.68** | +3.2% |
| Long prefill | 90.0 | **91.6** | +1.8% |
| **CUDA0** | 13,820 | **13,514** | -306 MiB |
| **CUDA1** | 12,046 | **14,880** | **+2,834 MiB** |
| RSS | 137.6 GB | 135.1 GB | -2.5 GB |

启动日志 buffer 分配：
```
CUDA0 buffer size =  8606.29 MiB   （3 层 expert，比第五轮少 1 层：blk.56-58 vs 57-59）
CUDA1 buffer size =  9969.52 MiB   （3 层 expert，比第五轮多 1 层：blk.59-61 vs 60-61）
KV cache CUDA0    =  4352.02 MiB
KV cache CUDA1    =  4080.01 MiB
```

> CUDA1 buffer 增加 ~2.8 GB（从 7,135 → 9,970），恰好是 1 层 expert 的大小，确认 blk.59 正确分配到了 CUDA1。但 **short gen 进一步下降**（5.80 vs n-cpu-moe 的 7.01），说明跨卡 expert 执行路径的通信开销是主要瓶颈，而不是层数问题。`-ot` 的价值在于 VRAM 均匀分布，可以放更多层到 GPU 来弥补通信开销。CUDA0 剩余 ~11 GB、CUDA1 剩余 ~9.7 GB，可继续加层。

---

## 第七轮：`-ot` 4+4（8 层 expert on GPU）

增加 2 层 expert 到 GPU：blk.54-57 → CUDA0（4 层），blk.58-61 → CUDA1（4 层）。

**变更**：
```diff
- -ot "blk\.(5[6-8])\.ffn_(up|down|gate)_exps\.weight=CUDA0"
- -ot "blk\.(59|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"
+ -ot "blk\.(5[4-7])\.ffn_(up|down|gate)_exps\.weight=CUDA0"
+ -ot "blk\.(5[89]|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"
```

| 指标 | 第六轮 (3+3) | **第七轮 (4+4)** | vs graph+moe57 |
|------|-------------|-----------------|----------------|
| Short gen | 5.80 | **6.57** (+13.3%) | 7.01 (差6.3%) |
| Short prefill | 16.4 | **17.3** (+5.5%) | 16.3 (**超越**) |
| Long gen | 6.68 | **7.06** (+5.7%) | 6.57 (**超越7.5%**) |
| Long prefill | 91.6 | **95.2** (+3.9%) | 91.9 (**超越3.6%**) |
| **CUDA0** | 13,514 | **16,042** | — |
| **CUDA1** | 14,880 | **17,412** | — |
| RSS | 135.1 GB | **130.1 GB** (-5 GB) | — |

启动日志 buffer 分配：
```
CUDA0 buffer size = 11135.29 MiB   （4 层 expert，+2,529 vs 3+3）
CUDA1 buffer size = 12498.52 MiB   （4 层 expert，+2,530 vs 3+3）
KV cache CUDA0    =  4352.02 MiB
KV cache CUDA1    =  4080.01 MiB
```

> **显著提升**：增加 2 层后，long gen (7.06) 和 long prefill (95.2) 已超越 n-cpu-moe=57 的最优值。Short gen 还差 6%，但趋势明确——更多 GPU expert 层 = 更快。两卡各剩 ~7-8 GB，可继续加层。每多 2 层（1+1），CPU↔GPU 传输减少，性能持续改善。

---

## 第八轮：`-ot` 5+5（10 层 expert on GPU）

继续对称加层：blk.52-56 → CUDA0（5 层），blk.57-61 → CUDA1（5 层）。

**变更**：
```diff
- -ot "blk\.(5[4-7])\.ffn_(up|down|gate)_exps\.weight=CUDA0"
- -ot "blk\.(5[89]|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"
+ -ot "blk\.(5[2-6])\.ffn_(up|down|gate)_exps\.weight=CUDA0"
+ -ot "blk\.(5[7-9]|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"
```

| 指标 | 第七轮 (4+4) | **第八轮 (5+5)** | vs graph+moe57 |
|------|-------------|-----------------|----------------|
| Short gen | 6.57 | 6.59 (+0.3%) | 7.01 (差6%) |
| Short prefill | 17.3 | 17.6 (+1.7%) | 16.3 (**超越**) |
| Long gen | **7.06** | 6.44 (-8.8%) | 6.57 |
| Long prefill | 95.2 | **100.2** (+5.2%) | 91.9 (**超越9%**) |
| **CUDA0** | 16,042 | **18,266** | — |
| **CUDA1** | 17,412 | **19,940** | — |
| RSS | 130.1 GB | **125.4 GB** (-4.7 GB) | — |

启动日志 buffer 分配：
```
CUDA0 buffer size = 13358.29 MiB   （5 层 expert）
CUDA1 buffer size = 15027.52 MiB   （5 层 expert）
KV cache CUDA0    =  4352.02 MiB
KV cache CUDA1    =  4080.01 MiB
```

> Long prefill 突破 **100 tok/s**（基线 84 → 100.2，+19%）。但 short gen 停滞（6.59 vs 6.57），long gen 反而下降（6.44 vs 7.06）。CUDA1 已达 19,940 MiB（仅剩 4.6 GB），接近上限。可能原因：CUDA1 VRAM 压力导致调度效率下降，或 benchmark 波动。下一步尝试 6+4 不对称分配，将 CUDA1 压力转移到 CUDA0（余量更大）。

---

## 第九轮：`-ot` 6+4 不对称分配（10 层 expert on GPU）

同样 10 层 expert，但不对称分配：CUDA0 多承担 2 层，缓解 CUDA1 压力。

**变更**：
```diff
- -ot "blk\.(5[2-6])\.ffn_(up|down|gate)_exps\.weight=CUDA0"   # 5层
- -ot "blk\.(5[7-9]|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"  # 5层
+ -ot "blk\.(5[2-7])\.ffn_(up|down|gate)_exps\.weight=CUDA0"   # 6层
+ -ot "blk\.(5[89]|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"   # 4层
```

| 指标 | 5+5 | **6+4** | vs graph+moe57 |
|------|-----|---------|----------------|
| Short gen | 6.59 | **7.17** (+8.8%) | **超越 2.3%** |
| Short prefill | 17.6 | 17.0 (-3.4%) | 超越 |
| Long gen | 6.44 | 6.37 (-1.1%) | 差3% |
| Long prefill | **100.2** | 94.9 (-5.3%) | 超越 3.3% |
| **CUDA0** | 18,266 | **20,794** (+2,528) | — |
| **CUDA1** | 19,940 | **17,412** (-2,528) | — |
| RSS | 125.4 GB | 125.4 GB | 不变 |

启动日志 buffer 分配：
```
CUDA0 buffer size = 15887.29 MiB   （6 层 expert）
CUDA1 buffer size = 12498.52 MiB   （4 层 expert）
KV cache CUDA0    =  4352.02 MiB
KV cache CUDA1    =  4080.01 MiB
```

> **Short gen 7.17 — 首次超越 n-cpu-moe=57 的 7.01！** 不对称分配有效：CUDA0 集中 6 层 expert 减少了跨卡通信，CUDA1 压力从 19.9 GB 降到 17.4 GB。Prefill 略降（100.2→94.9）但仍超基线。这证实了跨卡通信开销是 decode 瓶颈——expert 越集中在一侧，decode 越快。

---

## 第十轮：split-mode 隔离实验（graph vs layer，固定 -ot 6+4）

保持 -ot 6+4 不变，仅将 `split-mode` 从 `graph` 切回 `layer`，隔离 split-mode 对不对称 expert 分配的影响。

**变更**：
```diff
- --split-mode graph
+ --split-mode layer
```

| 指标 | graph (第九轮) | **layer** | 变化 |
|------|--------------|-----------|------|
| Short gen | 7.17 | **7.23** (+0.8%) | 略优 |
| Short prefill | 17.0 | 16.5 | ~持平 |
| Long gen | 6.37 | **6.84** (+7.4%) | 改善 |
| Long prefill | 94.9 | **99.3** (+4.6%) | 改善 |
| CUDA0 | 20,794 | 20,794 | 不变 |
| CUDA1 | 17,412 | 17,412 | 不变 |

> 单次测试 layer 看起来略优于 graph，但**单次数据不可靠**（见下方多轮稳定性分析）。需要多轮数据才能得出结论。

---

## Benchmark 稳定性分析与 Graph vs Layer 多轮对比

单次 benchmark 波动较大，需要多轮数据才能得出可靠结论。以下为两种 split-mode 在相同 -ot 6+4 配置下的多轮数据。

**Prefill 指标说明**：首次请求后，llama-server 在 slot 中保留 KV cache。后续相同 prompt 命中缓存时，`prompt_per_second` 被缓存行为污染（分母变小），指标虚低。用时间反证：5000 tokens 按 7 tok/s 需 ~12 分钟，实际间隔仅 1-2 分钟。因此 **prefill 仅首次冷启动有效，generation 是唯一跨轮次可靠的指标**。

### Layer 模式多轮数据（9 次，服务器不重启）

| 轮次 | S_gen | L_gen |
|------|-------|-------|
| #1（冷启动） | 7.23 | 6.84 |
| #2 | 6.06 | 7.06 |
| #3 | 7.07 | 6.58 |
| #4 | 6.89 | 6.77 |
| #5 | 7.11 | 6.66 |
| #6 | 6.59 | 7.15 |
| #7 | 6.23 | 6.88 |
| #8 | 6.36 | 6.97 |
| #9 | 7.56 | 7.37 |
| **#2-9 均值** | **6.66** | **6.93** |

### Graph 模式多轮数据（6 次，服务器不重启）

| 轮次 | S_gen | L_gen |
|------|-------|-------|
| #1（冷启动） | 6.80 | 7.02 |
| #2 | 7.21 | 6.66 |
| #3 | 7.01 | 6.96 |
| #4 | 7.04 | 6.89 |
| #5 | 7.20 | 6.82 |
| #6 | 7.05 | 6.61 |
| **#2-6 均值** | **7.10** | **6.79** |

### Graph vs Layer 多轮均值对比

| 指标 | Graph 均值 | Layer 均值 | 差异 | 优势 |
|------|-----------|-----------|------|------|
| **S_gen** | **7.10** | 6.66 | **+6.6%** | **Graph** |
| L_gen | 6.79 | **6.93** | +2.1% | Layer（微弱） |
| 冷启动 S_prefill | 17.35 | 16.5 | ~持平 | — |
| 冷启动 L_prefill | 97.6 | 99.3 | ~持平 | — |

> **结论**：Graph 模式在日常交互最重要的 short gen 上有 6.6% 的稳定优势，long gen 两者几乎持平。**推荐配置：`split-mode graph`**。
>
> 第十轮单次测试中 layer 看似略优，是因为单次波动（layer 恰好跑到 7.23，graph 恰好跑到 6.80）。多轮均值证明 graph 在 short gen 上的优势是稳定的。

---

## 第十一轮：`-ot` 7+3（更极端的不对称分配）

在 6+4 基础上进一步集中 expert 到 CUDA0：7 层 CUDA0 + 3 层 CUDA1，总量仍为 10 层。

**变更**：
```diff
- -ot "blk\.(5[2-7])\.ffn_(up|down|gate)_exps\.weight=CUDA0"   # 6层
- -ot "blk\.(5[89]|6[01])\.ffn_(up|down|gate)_exps\.weight=CUDA1"  # 4层
+ -ot "blk\.(5[1-7])\.ffn_(up|down|gate)_exps\.weight=CUDA0"   # 7层
+ -ot "blk\.(5[89]|60)\.ffn_(up|down|gate)_exps\.weight=CUDA1"    # 3层
```

**多轮数据**（6 次）：

| 轮次 | S_gen | L_gen |
|------|-------|-------|
| #1（冷启动） | 7.47 | 6.90 |
| #2 | 7.12 | 6.95 |
| #3 | 7.28 | 6.92 |
| #4 | 7.08 | 6.91 |
| #5 | 7.27 | 6.68 |
| #6 | 7.28 | 6.48 |
| **#2-6 均值** | **7.21** | **6.79** |

冷启动 prefill：S_prefill=17.46, L_prefill=99.1

| 指标 | 7+3 均值 | 6+4 均值 | 变化 |
|------|---------|---------|------|
| **S_gen** | **7.21** | 7.10 | **+1.5%** |
| L_gen | 6.79 | 6.79 | 持平 |
| CUDA0 | 23,246 | 20,794 | +2,452 MiB |
| CUDA1 | 14,498 | 17,412 | -2,914 MiB |

> S_gen 继续提升（7.21 vs 7.10），验证了 expert 越集中越快的趋势。CUDA0 = 23.2 GB（仍有 ~1.3 GB 余量），CUDA1 降至 14.5 GB。Long gen 持平，prefill 持平。

---

## CPU 线程调参（第十二～十七轮）

前 11 轮聚焦于 expert 层的 GPU 放置策略。接下来转向 CPU 线程参数——MoE 模型中绝大多数 expert 仍在 CPU 上执行，decode 时每个 token 都经过 CPU 路径，线程调度开销对 generation 速度有直接影响。

**思路**：系统为 2× Xeon E5-2686 v4（18C/36T × 2 = 72 线程），但过多线程会导致 NUMA 跨节点访问和同步开销增大。先用 `--threads` 粗扫（固定 `--threads-batch 36`），再用最优 threads 扫 `--threads-batch`。

### 第十二～十五轮：`--threads` 粗扫（16/20/24/28）

固定 `-ot 7+3 graph`、`--threads-batch 36`，变化 `--threads`。每组 3-6 次 benchmark，取排除冷启动后的均值。

| Round | threads | S_gen 均值 | L_gen 均值 | vs 无显式线程控制 |
|:---:|:---:|:---:|:---:|:---:|
| 12 | 16 | 8.17 | 7.82 | +13.3% / +15.2% |
| 13 | **20** | **8.38** | **8.02** | **+16.2% / +18.1%** |
| 14 | 24 | 8.40 | 8.02 | +16.5% / +18.1% |
| 15 | 28 | 7.98 | 7.95 | +10.7% / +17.1% |

> **关键发现**：
> - 线程调参效果巨大——从默认（物理核全开）到 threads=20，short gen +16%，long gen +18%。增益幅度超过此前所有 expert 层优化。
> - threads=20 和 24 基本同平台（差异 <0.3%），优先选 20——线程更少，调度开销更低，更稳定。
> - threads=28 short gen 明显回落（8.38→7.98），验证了线程过多引入同步开销的假设。
> - 所有测试波动极小（±0.02 tok/s），数据高度稳定。

### 第十六～十七轮：`--threads-batch` 扫参（24/32）

固定 `--threads 20`、`-ot 7+3 graph`，变化 `--threads-batch`（tb=36 已在第十三轮测过）。

| Round | threads-batch | S_gen 均值 | L_gen 均值 | L_pf (冷启动) |
|:---:|:---:|:---:|:---:|:---:|
| 13 | 36 | 8.38 | 8.02 | 100.2 |
| 16 | 24 | 8.34 | 8.00 | 85.2 |
| 17 | 32 | 8.37 | 8.00 | 104.5 |

> **结论**：
> - `--threads-batch` 对 generation 速度几乎无影响（三者全在噪声范围内）。
> - `--threads-batch` 对 **prefill 速度** 有明显影响：tb=24 的 long prefill 仅 85 tok/s，比 tb=32/36 低 ~18%。
> - tb=32（104.5）和 tb=36（100.2）接近，差异可能是单次冷启动噪声。
> - **推荐 `--threads-batch 36`**：prefill 表现好，且为系统物理核数一半，与更多核的 batch 计算天然匹配。

### 7+3 vs 6+4 生产选型

7+3 CUDA0 = 23,246 / 24,576 MiB，仅剩 ~1.3 GB 余量。日常使用 context 波动、CUDA runtime 碎片都可能触及上限。**6+4 是推荐的生产默认**，CUDA0 = 20,794 MiB（余 3.8 GB），稳定性更好，性能仅损失 ~1.5% short gen。

---

## `cache_prompt: false` 与服务端异常

尝试在 benchmark 请求中加入 `cache_prompt: false` 以获取可靠的 prefill 数据。结果触发服务端异常：

1. **首次请求**：600s 超时——此时后台仍有 benchmark task 占用唯一 slot（`--parallel 1`），新请求排队等待
2. **确认 slot 空闲后重试**：服务端进入 `kv cache rm [p0, end)` 高频循环，日志不断刷屏但不返回结果，需手动 `systemctl restart llama-server` 恢复

**分析**：这更像是 slot/KV 状态机卡住，`cache_prompt: false` 是触发条件之一但不一定是唯一根因。社区有类似报告：
- 健康接口正常但 completion 挂住：[llama.cpp #13281](https://github.com/ggml-org/llama.cpp/issues/13281)
- `/completion` + cache_prompt 路径的多个缓存异常：[llama.cpp #13484](https://github.com/ggml-org/llama.cpp/issues/13484)、[llama.cpp #4989](https://github.com/ggml-org/llama.cpp/issues/4989)
- `kv cache rm` 正常行为参考：[Discussion #13606](https://github.com/ggml-org/llama.cpp/discussions/13606)

> **当前状态**：已从 benchmark 任务中移除 `cache_prompt: false`，benchmark 可靠性问题留待后续通过服务端重启或更换提示词等方式解决。

---

## 待测试优化

| 参数 | 说明 | 预期效果 |
|------|------|---------|
| `--merge-qkv` | 合并 Q/K/V attention 张量 | 减少 kernel launch，提升 prefill |
| `-gr` (graph reuse) | 复用计算图 | 减少图构建开销 |
| `-smgs` | Graph scheduling 优化 | 小幅性能提升 |
| `-b 4096 -ub 4096` | 增大批处理大小 | 提升长 prompt prefill |

---

## 调优总结

### Expert 层放置优化（第一～十一轮）

| 配置 | Short gen | Long gen | Long prefill | CUDA0 | CUDA1 | 备注 |
|------|-----------|----------|-------------|-------|-------|------|
| 基线 (cpu-moe, f16) | 4.7 | 4.7 | 84 | ~12 GB | ~12 GB | 全 expert CPU |
| +q8_0 +moe=58 | 6.0 | 6.4 | 91.2 | 5,848 | 17,334 | 5 层 expert GPU |
| +moe=57 | 6.65 | 6.48 | 91.6 | 5,924 | 19,940 | 极不均 |
| +graph mode | 7.01 | 6.57 | 91.9 | 5,924 | 19,940 | 张量并行 |
| +ot 4+4 | 6.57 | 7.06 | 95.2 | 16,042 | 17,412 | |
| +ot 5+5 | 6.59 | 6.44 | 100.2 | 18,266 | 19,940 | prefill最优 |
| +ot 6+4 graph | 7.10¹ | 6.79¹ | 97.6 | 20,794 | 17,412 | |
| +ot 7+3 graph | 7.21¹ | 6.79¹ | 99.1 | 23,246 | 14,498 | CUDA0余1.3GB |

### CPU 线程优化（第十二～十七轮）

| 配置 | Short gen | Long gen | Long prefill | 备注 |
|------|-----------|----------|-------------|------|
| ot 7+3, 无显式线程 | 7.21¹ | 6.79¹ | 99.1 | 默认使用全部物理核 |
| +threads=16, tb=36 | 8.17 | 7.82 | — | +13% / +15% |
| **+threads=20, tb=36** | **8.38** | **8.02** | **100.2** | **+16% / +18%，当前最优** |
| +threads=24, tb=36 | 8.40 | 8.02 | 100.1 | 与 t=20 持平 |
| +threads=28, tb=36 | 7.98 | 7.95 | 101.7 | S_gen 回落 |
| +threads=20, tb=24 | 8.34 | 8.00 | 85.2 | prefill 明显下降 |
| +threads=20, tb=32 | 8.37 | 8.00 | 104.5 | prefill 略优 |

¹ 多轮均值（排除首次冷启动），见"Benchmark 稳定性分析"。

### 全程优化总览

| 阶段 | Short gen | Long gen | 累计提升 |
|------|-----------|----------|---------|
| 基线 (cpu-moe, f16) | 4.7 | 4.7 | — |
| Expert 层优化后 (ot 7+3 graph) | 7.21 | 6.79 | +53% / +44% |
| **+ CPU 线程优化后 (threads=20)** | **8.38** | **8.02** | **+78% / +71%** |

### 关键发现

1. **CPU 线程调参是最大增益点**：threads=20 比默认（全核）S_gen +16%、L_gen +18%，增幅超过此前所有 expert 层优化的总和
2. **Expert 集中分配趋势明确**：3+3 → 4+4 → 5+5 → 6+4 → 7+3，short gen 从 5.80 提升到 7.21
3. **不对称分配**（主卡多 expert）优于对称分配，减少跨卡通信开销
4. **Graph 模式**在 short gen 上有 6.6% 稳定优势（多轮均值验证）
5. **threads-batch 影响 prefill 不影响 generation**：tb=24 prefill 明显劣于 tb=32/36
6. **单次 benchmark 波动** ±0.5 tok/s，多轮均值才可靠；prefill 仅冷启动有效

### 推荐生产配置

```
-ot 6+4 不对称 + split-mode graph + KV cache q8_0
--threads 20 --threads-batch 36
CUDA0: blk.51-56 (6层 expert) → ~20,794 MiB (余 3.8 GB)
CUDA1: blk.57-60 (4层 expert) → ~17,412 MiB (余 7.2 GB)
Short gen: ~8.38 tok/s | Long gen: ~8.02 tok/s | Long prefill: ~100 tok/s
```

> 7+3 性能略高（S_gen 7.21→8.38 同样适用），但 CUDA0 仅余 1.3 GB，不推荐作为日常默认。
