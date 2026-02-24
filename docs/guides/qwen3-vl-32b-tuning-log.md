# Qwen3-VL-32B 性能调优实测记录

## 测试环境

- **引擎**：ik_llama.cpp commit `f7923739`
- **模型**：mradermacher/Huihui-Qwen3-VL-32B-Thinking-abliterated-GGUF (Q4_K_M, ~19.7GB)
- **Vision encoder**：mmproj-Q8_0
- **硬件**：2× RTX 3090 (24GB × 2)，384GB DDR4，2× Xeon E5-2686 v4
- **固定参数**：`-ngl 999 --parallel 1 --jinja --mmproj ...`
- **测试负载**：短 prompt（~18 tokens → 生成 ~300 tokens），长 prompt（~5018 tokens → 生成 100 tokens）
- **方法论**：每次只改变一个变量以隔离效果，每组 4 次 benchmark（1 冷启动 + 3 热），取热启动均值

### 与 M2.5 调优的关键差异

Qwen3-VL-32B 是 **Dense 模型**（非 MoE），模型完全放入双卡 VRAM。因此：
- 无需 `-ot` tensor override（没有 expert 层）
- CPU 线程影响应远小于 M2.5（Dense 模型计算主要在 GPU）
- 调优重点转向：split-mode、tensor-split 比例、KV cache 类型、Flash Attention 等 GPU 侧参数

---

## 基线配置

```
--split-mode graph --tensor-split 1,1
--cache-type-k q8_0 --cache-type-v q8_0
--ctx-size 32768 --threads 20 --threads-batch 36
```

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 176.8 | 37.01 | 1550.9 | 32.52 |
| #2 | 325.1 | 36.91 | 1553.6 | 32.58 |
| #3 | 317.9 | 36.87 | 1546.3 | 32.66 |
| #4 | 314.8 | 36.87 | 1546.5 | 32.73 |
| **#2-4 avg** | **319.3** | **36.88** | **1548.8** | **32.66** |

VRAM: CUDA0=18,246 MiB, CUDA1=13,482 MiB, RSS=1.04 GB

---

## Round 1: split-mode (graph vs layer)

变量：`--split-mode layer`（基线为 `graph`）

> 注：从本轮起使用 Ansible `llm-benchmark` 角色跑 benchmark，短 prompt 为 "Write a short poem about the sea."（max_tokens=300, temp=0），长 prompt 为 ~5000 tokens fox 重复文本（max_tokens=100, temp=0）。生成速度（gen tok/s）可与基线直接对比，prefill 因 prompt 不同仅在同批次内对比。

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 177.5 | 36.77 | 1547.8 | 32.64 |
| #2 | 198.8 | 36.74 | 1555.4 | 32.75 |
| #3 | 165.2 | 36.87 | 1530.6 | 32.49 |
| #4 | 188.8 | 36.64 | 1540.4 | 32.48 |
| **#2-4 avg** | **184.3** | **36.75** | **1542.1** | **32.57** |

VRAM: CUDA0=18,246 MiB, CUDA1=13,482 MiB, RSS=1.04 GB

**对比基线（graph）**：
- Short gen: 36.88 → 36.75 (−0.4%)
- Long gen: 32.66 → 32.57 (−0.3%)
- Long prefill: 1548.8 → 1542.1 (−0.4%)

**结论**：`split-mode layer` 对 Dense 模型无优势，生成速度略降。保持 `graph` 模式。

---

## Round 2: tensor-split 比例

变量：`--tensor-split`（基线 `1,1`）

### tensor-split 2,3

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 172.7 | 36.70 | 1478.5 | 32.44 |
| #2 | 314.1 | 36.61 | 1461.2 | 32.36 |
| #3 | 318.2 | 36.69 | 1468.6 | 32.55 |
| #4 | 329.3 | 36.62 | 1456.6 | 32.37 |
| **#2-4 avg** | **320.5** | **36.64** | **1462.1** | **32.43** |

VRAM: CUDA0=15,870 MiB, CUDA1=15,856 MiB

### tensor-split 3,2

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 186.4 | 36.89 | 1531.2 | 32.49 |
| #2 | 325.4 | 36.71 | 1529.1 | 32.44 |
| #3 | 320.3 | 36.75 | 1541.9 | 32.47 |
| #4 | 318.0 | 36.48 | 1496.8 | 32.44 |
| **#2-4 avg** | **321.2** | **36.65** | **1522.6** | **32.45** |

VRAM: CUDA0=20,290 MiB, CUDA1=11,434 MiB

**对比基线（1,1）**：

| 配置 | Short gen (tok/s) | Long gen (tok/s) | Long prefill (tok/s) |
|------|-------------------|------------------|----------------------|
| **1,1（基线）** | **36.88** | **32.66** | **1548.8** |
| 2,3 | 36.64 (−0.7%) | 32.43 (−0.7%) | 1462.1 (−5.6%) |
| 3,2 | 36.65 (−0.6%) | 32.45 (−0.6%) | 1522.6 (−1.7%) |

**结论**：`1,1` 均分是最优配置。非均等分割均导致性能下降，VRAM 均衡（2,3）反而因 graph 调度与实际分配冲突而更慢。保持 `1,1`。

---

## Round 3: KV cache 类型 (f16 vs q8_0)

变量：`--cache-type-k f16 --cache-type-v f16`（基线为 `q8_0`）

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 221.0 | 37.67 | 1581.8 | 35.68 |
| #2 | 312.6 | 37.60 | 1559.9 | 35.62 |
| #3 | 316.6 | 37.63 | 1536.8 | 35.64 |
| #4 | 317.6 | 37.60 | 1549.3 | 35.63 |
| **#2-4 avg** | **315.6** | **37.61** | **1548.7** | **35.63** |

VRAM: CUDA0=20,208 MiB, CUDA1=15,324 MiB（较 q8_0 增加 ~3.8 GB）

**对比基线（q8_0）**：
- Short gen: 36.88 → 37.61 (**+2.0%**)
- Long gen: 32.66 → 35.63 (**+9.1%**) ← 显著提升！
- Long prefill: 1548.8 → 1548.7 (0.0%)
- VRAM 代价：+3.8 GB（48 GB 总容量内可接受）

**结论**：f16 KV cache 带来显著生成加速，尤其是长上下文场景 +9.1%。VRAM 增幅可接受。**采用 f16，后续轮次基于此配置继续测试。**

---

## Round 4: Flash Attention

变量：`--flash-attn off`（默认为 `on`）

此版 ik_llama.cpp (`f7923739`) 默认启用 Flash Attention（`--flash-attn on`）。然而：

1. 启动日志显示 `flash_attn = 1` 但随后 `warmup: flash attention is disabled` — **FA 在此模型/量化下实际不可用**
2. 显式设置 `--flash-attn off` 配合 f16 KV cache 会导致 `unable to load model` + SIGABRT 崩溃

**结论**：FA 对此模型无效（默认开启但实际被跳过）。不可关闭。此变量无可调空间，跳过。

---

## Round 5: threads / threads-batch

变量：`--threads`（基线 20，threads-batch 保持 36）

当前配置基于 Round 3 结论运行 f16 KV cache。

### threads=36, threads-batch=36

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 181.5 | 37.56 | 1492.0 | 35.51 |
| #2 | 327.2 | 37.34 | 1553.2 | 35.53 |
| #3 | 317.1 | 37.58 | 1548.2 | 35.58 |
| #4 | 316.6 | 37.57 | 1503.9 | 35.53 |
| **#2-4 avg** | **320.3** | **37.50** | **1535.1** | **35.55** |

### threads=10, threads-batch=36

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 164.3 | 37.57 | 1523.0 | 35.58 |
| #2 | 315.9 | 37.58 | 1544.3 | 35.60 |
| #3 | 315.8 | 37.53 | 1548.4 | 35.55 |
| #4 | 322.4 | 37.57 | 1533.3 | 35.56 |
| **#2-4 avg** | **318.1** | **37.56** | **1542.0** | **35.57** |

**对比（f16 KV cache 基准，threads=20）**：

| 配置 | Short gen (tok/s) | Long gen (tok/s) |
|------|-------------------|------------------|
| **threads=20（当前）** | **37.61** | **35.63** |
| threads=36 | 37.50 (−0.3%) | 35.55 (−0.2%) |
| threads=10 | 37.56 (−0.1%) | 35.57 (−0.2%) |

**结论**：Dense 模型在双 GPU 上运行，CPU 线程数对性能影响极小（<0.3%）。保持 `threads=20` 不变。

---

## Round 6: ctx-size

变量：`--ctx-size`（基线 32768）

### ctx-size=8192

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 180.5 | 37.70 | 1588.4 | 35.64 |
| #2 | 317.9 | 37.65 | 1546.9 | 35.70 |
| #3 | 323.5 | 37.70 | 1556.8 | 35.67 |
| #4 | 333.1 | 37.71 | 1555.7 | 35.71 |
| **#2-4 avg** | **324.8** | **37.69** | **1553.1** | **35.69** |

VRAM: CUDA0=16,944 MiB, CUDA1=12,348 MiB（较 ctx=32768+f16 节省 ~6.2 GB）

**对比（f16, ctx=32768）**：
- Short gen: 37.61 → 37.69 (+0.2%)
- Long gen: 35.63 → 35.69 (+0.2%)
- VRAM: 35.5 GB → 29.3 GB (−6.2 GB)

**结论**：ctx-size 对生成速度影响极小（<0.3%）。缩小 ctx 可节省 VRAM，但牺牲最大上下文长度。保持 `32768` 以支持长对话/长文档场景。

---

## Round 7: parallel（1 vs 2）

变量：`--parallel 2`（基线为 1）

> 注：parallel=2 时 ctx-size 被 2 个 slot 均分，每 slot 实际可用 16384 tokens。Benchmark 单请求串行运行，仅测量并发开启时对单请求性能的影响。Run 2-4 的 prefill 数值因 prompt cache 命中而失真，仅 Run 1 的 prefill 可信。

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 170.6 | 37.58 | 1558.4 | 34.96 |
| #2 | (cached) | 34.82 | (cached) | 35.07 |
| #3 | (cached) | 34.78 | (cached) | 35.06 |
| #4 | (cached) | 34.80 | (cached) | 35.04 |
| **#2-4 avg** | — | **34.80** | — | **35.06** |

VRAM: CUDA0=20,208 MiB, CUDA1=15,324 MiB（与 parallel=1 相同）

**对比 parallel=1（f16）**：
- Short gen: 37.61 → 34.80 (**−7.5%**)
- Long gen: 35.63 → 35.06 (−1.6%)
- 每 slot 最大上下文：32768 → 16384（减半）

**结论**：parallel=2 允许 2 个并发请求，但单请求短文本生成速度下降 7.5%，且每请求最大上下文减半。对于单用户场景，保持 `parallel=1` 更优。如需多用户并发，可考虑 parallel=2 并增大 ctx-size 以补偿。

---

## 补充测试: 64K 上下文可行性 (ctx=65536 + q8_0 + parallel=2)

用户需求：能否扩展到 64K 上下文并支持 2 路并发？

**VRAM 分析**：
- f16 + ctx=65536 需要 ~51.3 GB → **超出** 48 GB 总容量
- q8_0 + ctx=65536 需要 ~35.5 GB → 可行
- parallel=2 时每 slot 分得 65536/2 = **32768 tokens**（等于当前最优配置的总上下文）

**配置**：`--cache-type-k q8_0 --cache-type-v q8_0 --ctx-size 65536 --parallel 2`，其余参数不变。

**VRAM 实测**：CUDA0=20,620 MiB, CUDA1=15,592 MiB（总计 ~36.2 GB，48 GB 内余量 ~12 GB）

> 注：Warm runs 的 prefill 数据因 parallel=2 的 slot prompt cache 机制而严重失真（~23-28 tok/s vs cold run 1555 tok/s），仅 Run 1 prefill 可信。

| Run | Short prefill (tok/s) | Short gen (tok/s) | Long prefill (tok/s) | Long gen (tok/s) |
|-----|-----------------------|-------------------|----------------------|------------------|
| #1 (cold) | 175.2 | 36.85 | 1555.2 | 31.76 |
| #2 | (cached) | 31.56 | (cached) | 31.84 |
| #3 | (cached) | 31.51 | (cached) | 31.84 |
| #4 | (cached) | 31.32 | (cached) | 31.53 |
| **#2-4 avg** | — | **31.46** | — | **31.74** |

**对比最佳配置（f16, ctx=32768, parallel=1）**：

| 指标 | 最佳配置 | 64K+q8_0+parallel=2 | 变化 |
|------|----------|---------------------|------|
| Short gen (tok/s) | 37.61 | 31.46 | **−16.4%** |
| Long gen (tok/s) | 35.63 | 31.74 | **−10.9%** |
| VRAM 总用量 | 35.5 GB | 36.2 GB | +0.7 GB |
| 最大上下文/用户 | 32768 | 32768 | 相同 |
| 并发请求 | 1 | 2 | +1 |

**结论**：64K + q8_0 + parallel=2 **技术上完全可行**，VRAM 充裕（余量 ~12 GB）。每用户实际可用上下文与当前最优配置相同（32K tokens），且支持 2 路并发。代价是生成速度下降 10-16%，来源于三个因素叠加：
1. q8_0 反量化开销（约 −2% 短 / −9% 长）
2. parallel=2 slot 调度开销（约 −7.5% 短 / −1.6% 长）
3. 更大的 KV cache 内存管理开销

适用场景：多用户共享推理服务时，此配置以 ~15% 性能换取 2 路并发，且每用户仍享有完整 32K 上下文。

---

## 总结与最佳配置

### 各轮结果汇总

| 轮次 | 变量 | 测试值 | Short gen 变化 | Long gen 变化 | 结论 |
|------|------|--------|---------------|---------------|------|
| R1 | split-mode | layer | −0.4% | −0.3% | 无提升，保持 graph |
| R2 | tensor-split | 2,3 / 3,2 | −0.6~0.7% | −0.6~0.7% | 1,1 最优 |
| R3 | **KV cache** | **f16** | **+2.0%** | **+9.1%** | **显著提升，采用** |
| R4 | flash-attn | off | N/A（崩溃） | N/A | 默认启用但实际不可用 |
| R5 | threads | 36 / 10 | <0.3% | <0.2% | 无显著差异 |
| R6 | ctx-size | 8192 | +0.2% | +0.2% | 影响极小，保持 32768 |
| R7 | parallel | 2 | −7.5% | −1.6% | 单用户保持 1 |
| 补充 | 64K+q8_0+p=2 | ctx=65536 | −16.4% | −10.9% | 可行，多用户适用 |

### 最佳配置（已应用）

```
--split-mode graph --tensor-split 1,1
--cache-type-k f16 --cache-type-v f16    ← 唯一变更（q8_0 → f16）
--ctx-size 32768 --threads 20 --threads-batch 36
--parallel 1
```

### 性能对比（基线 vs 最佳）

| 指标 | 基线 (q8_0) | 最佳 (f16) | 提升 |
|------|-------------|------------|------|
| Short gen (tok/s) | 36.88 | 37.61 | **+2.0%** |
| Long gen (tok/s) | 32.66 | 35.63 | **+9.1%** |
| Long prefill (tok/s) | 1548.8 | 1548.7 | 0.0% |
| VRAM 总用量 | 31.7 GB | 35.5 GB | +3.8 GB |

### 关键发现

1. **KV cache 类型是 Dense 模型在双 GPU 上唯一有效的调优变量**。f16 消除了 q8_0 的反量化开销，在长上下文场景提升最为显著（+9.1%）。
2. **Dense 模型在双 GPU 上几乎无 CPU 侧调优空间**——split-mode、tensor-split、threads 等变量影响均 <1%，与 MoE 模型（M2.5 调优中 CPU 线程带来 +16%）形成鲜明对比。
3. **Flash Attention 名义启用但实际不生效**，疑为 ik_llama.cpp 对此架构/量化的兼容性限制。
4. **parallel=2 的代价不可忽视**（短文本 −7.5%），建议单用户场景保持 parallel=1。
