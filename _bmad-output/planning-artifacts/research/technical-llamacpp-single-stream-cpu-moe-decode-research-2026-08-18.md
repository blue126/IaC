---
stepsCompleted: [1, 2, 3]
inputDocuments: []
workflowType: 'research'
lastStep: 1
research_type: 'technical'
research_topic: 'llama.cpp 单流 CPU MoE decode 固定开销优化'
research_goals: '减少逐层 CPU 与 GPU 往返及同步开销，评估流水化、异构专家部署和更高产出的投机解码方案，并给出预期量级与验证方法'
user_name: 'Will'
date: '2026-08-18'
web_research_enabled: true
source_verification: true
---

# Research Report: llama.cpp 单流 CPU MoE decode 固定开销优化

**Date:** 2026-08-18
**Author:** Will
**Research Type:** Technical

---

## Research Overview

[Research overview and methodology will be appended here]

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technical Research Scope Confirmation

**Research Topic:** llama.cpp 单流 CPU MoE decode 固定开销优化
**Research Goals:** 减少逐层 CPU 与 GPU 往返及同步开销，评估流水化、异构专家部署和更高产出的投机解码方案，并给出预期量级与验证方法。

**Technical Research Scope:**

- Architecture Analysis - CPU MoE/GPU attention 异构执行与逐层依赖
- Implementation Approaches - 调度器、CUDA 后端、异步流水与专家缓存
- Technology Stack - llama.cpp 固定提交及当前主线、CUDA、DSpark
- Integration Patterns - CPU/GPU buffer、NUMA、PCIe 与投机解码接口
- Performance Considerations - 单流延迟、同步次数、前向产出及可验证收益

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-08-18

## Technology Stack Analysis

### Programming Languages and Execution Layers

本问题的关键栈不是单纯的 CUDA kernel，而是三层协作：llama.cpp 的 C/C++ 模型图构建、ggml 的跨 backend 调度器、以及 CUDA 与 x86 CPU backend。CPU MoE 的核心算子是 `MUL_MAT_ID`；CUDA 侧承载 attention、非专家权重和部分专家。当前主线要求 C++17，并通过 CMake 选择 CUDA、OpenMP 等 backend。

固定提交 `10bf611e` 必须与当前主线分开判断：网页索引无法解析该短哈希，因此后续所有“该提交已有”的判断须以本机 `llama-server --version`、构建日志的 `USE_GRAPHS` 和源码 grep 为准；当前主线事实只用于指出可升级能力。

来源：[llama.cpp CMake options](https://github.com/ggml-org/llama.cpp/blob/master/ggml/CMakeLists.txt)、[llama.cpp repository](https://github.com/ggml-org/llama.cpp)

### Runtime Frameworks and Libraries

ggml backend scheduler 会把一张 forward graph 按 CPU/CUDA backend 切成多个 split，并为跨 backend tensor 建立 copy/event。当前主线公开了 split 数量、异步 graph compute 和 synchronize API；`GGML_SCHED_MAX_SPLIT_INPUTS` 是 split 输入容量，不是减少 split 的调优参数。CUDA Graphs 是正式 CMake 选项 `GGML_CUDA_GRAPHS`，解决 CUDA 子图内部的 kernel launch gap，但不会消除 CPU MoE 与 GPU 子图间的数据依赖和 backend join。

来源：[ggml backend scheduler source](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-backend.cpp)、[backend API](https://github.com/ggml-org/llama.cpp/blob/master/ggml/include/ggml-backend.h)、[CUDA Graphs design/measurements](https://github.com/ggml-org/llama.cpp/issues/6763)

### Model and Memory Storage

模型载体为 GGUF；CPU 专家权重位于 CUDA host buffer 时已具备 pinned-memory DMA 条件。`--ubatch-size` 定义一次物理处理的最大 token 数，主要影响 prompt processing 与 compute-buffer 容量；单 token或小型 speculative verification batch 不会因为把上限从 2048 调高而获得更多并行度，但降低它可能释放显存供完整专家层或专家 cache 使用。

本问题最相关的新存储层是非主线的持久 VRAM expert-slot cache：CPU 继续计算 cache miss，GPU 同时计算 cache hit，从而利用空闲 GPU，而不是每 token 把所有选中专家经 PCIe 同步搬运。`moe-cache-v2-pr` 已在 43×256、top-6、2×3090 的 DeepSeek-V4 类配置上给出容量/命中率/吞吐 sweep，但尚未进入 mainline。

来源：[ubatch documentation](https://github.com/ggml-org/llama.cpp/tools/completion/README.md)、[MoE expert cache RFC and measurements](https://github.com/ggml-org/llama.cpp/discussions/24528)

### Development and Measurement Tools

首要观测工具应是 `LLAMA_LOG_VERBOSITY=4 GGML_SCHED_DEBUG=2`，它能列出每个 graph split、backend 和跨 backend 输入；这是判断某个 tensor override 是否真的减少同步点的直接证据。第二层使用 Nsight Systems 统计 CUDA API、memcpy、event/stream synchronize 和 GPU idle gap；CPU 侧用 `perf stat` 观察 context switch、CPU migration，并用严格 affinity/polling A/B 区分线程唤醒成本与算子成本。

来源：[official scheduler debug guidance](https://github.com/ggml-org/llama.cpp/discussions/16449)、[server CPU scheduling options](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

### Deployment and Device Topology

`--split-mode layer` 是按连续层分配 GPU 的 pipeline-parallel 路径。无 P2P 时，两 GPU 间 tensor 需经 host staging；当前主线的 tensor-parallel 路径明确不支持 DeepSeek2/MoE 类架构，因而不是该模型的替代方案。主模型和 drafter 可以用独立 device list（`--device` 与 `--device-draft`），这使“drafter 权重在 CUDA0、compute buffer 却在 CUDA1”成为必须单独核验的潜在跨 root-port 路径。

来源：[official multi-GPU guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/multi-gpu.md)、[draft device option](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

### Technology Adoption and Version Trends

截至 2026-08-18，当前主线 `common/speculative.cpp` 已列出 `draft-simple`、`draft-eagle3`、`draft-mtp`、`draft-dflash`、`draft-dspark` 及多种 n-gram 实现；这不代表固定提交全部具备，也不代表 server 已有动态树验证。树状分支采样明确存在于独立 speculative example，而主线 server 的统一 speculative implementation 是另一条代码路径。Medusa 没有同等级的官方 server/GGUF 集成证据。

权重软件预取仍是开放 PR：它要求 pinned、非 mmap 权重并使用下一层 double buffer；公开结果显示它更适合大 ubatch/prefill，不能自动解决 decode 时尚未知道下一层 top-k expert ID 的问题。专家 cache RFC 则专门针对 ubatch=1 decode。

来源：[current speculative implementation](https://github.com/ggml-org/llama.cpp/blob/master/common/speculative.cpp)、[tree speculative example](https://github.com/ggml-org/llama.cpp/blob/master/examples/speculative/speculative.cpp)、[speculative decoding guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md)、[weight-prefetch PR #21067](https://github.com/ggml-org/llama.cpp/pull/21067)

### Confidence and Research Gaps

- 高置信：主线构建选项、scheduler API、现有 speculative type、layer split 限制和 expert-cache 实测数据，均来自官方仓库源码或官方讨论。
- 中置信：expert cache 在本机的收益方向。硬件/模型几乎同型，但显存被 10.2 GiB GPU drafter 占用，会显著改变可用 cache 容量和 device binding。
- 待本机验证：`10bf611e` 的 CUDA Graphs 默认值、DSpark 具体实现版本、实际 TG graph split 数、drafter compute buffer 所属 backend 的原因。

### User-Verified Corrections

- 后续对 DeepSeek-V4-Flash + 投机解码的 expert-cache 收益采用用户直接核对原文后的口径：同源实测 `+37%～+55%`，独立 3090 验证 `+21%～+39%`；不使用 `+16.4%` 推导投机场景。
- 用户已在 pinned commit `10bf611e` 确认：`GGML_SCHED_MAX_SPLIT_INPUTS=30` 是 `new_cap` 使用的容量常量；该基线没有 expert/MoE cache；存在 CPU `MUL_MAT_ID` 同步时 CUDA Graph 整体禁用。

## Integration Patterns Analysis

### Expert Cache Source and Reproducible Baseline

可落地实现不在主线 PR，而在 `leloch/llama.cpp` fork 的 `moe-cache-v2-pr` 分支。当前核验的分支 HEAD 是 `e3096b046bb809f7f80bc47801f6579aed1cbc60`；v2 核心提交是 `f2d7f930356b2208ba5e7686a91b3443aed0cf02`，其唯一上游父提交是 `15586e2d7165570fb3aa7c26e0d442e289ef69de`。完整功能栈共 29 个提交。核心提交一次改动 28 个文件、约 `+6814/-279`，后续还有容量、DSpark device placement、scratch、admission、并行 fill 和 kernel 边界等修复。因此推荐直接构建固定 HEAD，不推荐只 cherry-pick 核心提交。

```bash
git clone --branch moe-cache-v2-pr --single-branch \
  https://github.com/leloch/llama.cpp.git llama.cpp-moe-cache
cd llama.cpp-moe-cache
git checkout e3096b046bb809f7f80bc47801f6579aed1cbc60
```

如果维护自己的、以精确上游基线为起点的分支，可使用完整提交区间：

```bash
git remote add leloch https://github.com/leloch/llama.cpp.git
git fetch leloch moe-cache-v2-pr
git checkout -b moe-cache-test 15586e2d7165570fb3aa7c26e0d442e289ef69de
git cherry-pick \
  f2d7f930356b2208ba5e7686a91b3443aed0cf02^..e3096b046bb809f7f80bc47801f6579aed1cbc60
```

来源：[v2 分支提交历史](https://github.com/leloch/llama.cpp/commits/moe-cache-v2-pr/)、[核心提交](https://github.com/leloch/llama.cpp/commit/f2d7f930356b2208ba5e7686a91b3443aed0cf02)、[当前 HEAD](https://github.com/leloch/llama.cpp/commit/e3096b046bb809f7f80bc47801f6579aed1cbc60)

### Compatibility with `10bf611e`

`10bf611e` 不应视为可直接 cherry-pick 的目标。原因不是单一冲突，而是 v2 同时依赖 scheduler-owned session、backend write invalidation、fit API、CUDA registry、context/CLI 参数和 server draft-device placement。最接近且已由提交图证明的可用基线是 `15586e2d7165570fb3aa7c26e0d442e289ef69de`，推荐让 expert-cache 二进制与现有 `10bf611e` 二进制并存，以同一 GGUF 和参数启动在不同端口做 A/B。只有确有必须保留的本地 DeepSeek-V4 改动时，才把这些改动 forward-port 到 v2 HEAD；不要反向把整个 cache runtime 塞回旧 pin。

可先在本机确认两者提交关系：

```bash
git merge-base --is-ancestor \
  15586e2d7165570fb3aa7c26e0d442e289ef69de 10bf611e
echo $?
```

返回 `0` 只证明祖先关系，不证明可干净移植；仍应以完整 v2 HEAD 为测试对象。

### Build and Runtime Integration

没有独立的 MoE-cache CMake 开关；它随 CUDA backend 编译。3090 可使用普通 Release CUDA 构建，`CMAKE_CUDA_ARCHITECTURES=86` 只是缩短/收窄构建目标，不是启用 cache 的必要条件。

```bash
cmake -S . -B build \
  -DGGML_CUDA=ON \
  -DGGML_OPENMP=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES=86
cmake --build build --config Release -j 36
```

运行时 `--moe-cache` 的语义为：`auto` 保留 weight repacking；`on` 使用自动预算并关闭 repacking；`off`/`0` 完全关闭；正整数 `N` 表示每张设备的 VRAM 上限（MiB），同时关闭 repacking。环境变量等价项是 `LLAMA_ARG_MOE_CACHE`。

`--cpu-moe` 与 cache 是互补关系：CPU-resident expert 是 cache provider。`-ot` 已静态放到 CUDA 的 expert tensor 不进入 cache，继续按正常 CUDA tensor 执行。因此现有 `-ot` 可保留，cache 只作用于剩余 CPU expert。

基于目前每卡约 4.2--4.7 GiB 的表面空闲量，先从每卡 2048 MiB 开始，再测试 3072 MiB；不要一步压满，需给 CUDA scratch、speculative verification batch 和波动留至少约 1 GiB。受两卡不对称显存占用影响，实际可分配容量应以启动日志的 granted/active cache 为准，而不是请求值。

```bash
# A: hard-off control and restore the CPU repack path
./build/bin/llama-server <现有参数> --moe-cache off --repack on

# B: conservative fixed cache, per device
./build/bin/llama-server <现有参数> --moe-cache 2048

# C: larger fixed cache, only after B is stable
./build/bin/llama-server <现有参数> --moe-cache 3072
```

来源：[核心提交中的 CLI/parser 语义](https://github.com/leloch/llama.cpp/commit/f2d7f930356b2208ba5e7686a91b3443aed0cf02)

### Correctness Risks and Rollback

- 结果目标是质量等价而非 bit-identical；CPU/CUDA 舍入可能在近似并列 token 上改变 greedy 选择。必须分别做固定 seed/greedy token 对比、perplexity、长上下文检索和正常生成检查。
- 早期 v2 核心之后修复了 cache 容量、DSpark 自动 device、shared-draft device placement、scratch 预算和 MMV 尾行越界；本机 drafter 权重与 compute buffer 分居两卡，因此不得停在 `f2d7f930`，应至少使用完整 HEAD `e3096b046`。
- cache 有 admission 和 warm-up；只测三次冷短样本可能把 fill 成本误判为稳态性能。每个配置应重启 server，跑相同冷样本后再跑至少 512-token 稳态段，并记录 hit/miss/fill/eviction、实际池容量、OOM/fallback 和 committed tok/s。
- 显式 `on` 或数值预算会关闭 weight repacking，cache miss 的 CPU 路径可能因此变慢。必须同时测 `auto`、`off` 和固定预算；不能只比较固定 cache 与旧二进制。
- 一级回退是同一 v2 二进制加 `--moe-cache off --repack on`；二级回退是切回原始 `10bf611e` 二进制。该功能不修改 GGUF 或持久 KV 格式，因此双二进制回退不需要数据迁移。

建议回退阈值：出现 CUDA error/OOM、输出质量检查失败、cache 命中长期为零、稳态吞吐未超过 `off` 至少 5%，或 P95 首 token/请求延迟明显恶化，即回退并保留日志。

来源：[v2 核心的并发、失效、OOM/fallback 与质量说明](https://github.com/leloch/llama.cpp/commit/f2d7f930356b2208ba5e7686a91b3443aed0cf02)、[后续修复历史](https://github.com/leloch/llama.cpp/commits/moe-cache-v2-pr/)

### `llama-server` Tree and Multi-Candidate Status

当前主线 `llama-server` 没有可直接启用的通用树状、多候选或 Medusa 路径。`--spec-draft-p-split` 虽仍在公共参数中，但 server 使用的 `common/speculative.cpp` 没有消费它；树分支逻辑只存在独立 `examples/speculative/speculative.cpp`，其中 `n_parallel` 控制分支数并复制 sequence/KV。它不能只靠参数套到 DSpark：DSpark server path 是单候选 token block，不是 top-k tree。

当前可执行的 server 级替代是让 `ngram-mod` 优先、DSpark 兜底：

```bash
--spec-type ngram-mod,draft-dspark \
--spec-draft-n-max 2 \
--spec-ngram-mod-n-match 24 \
--spec-ngram-mod-n-min 48 \
--spec-ngram-mod-n-max 64
```

官方文档规定 draftless implementation 优先于 draft model；因此重复文本、代码改写、总结等命中时可提交长 n-gram block，未命中时继续使用已验证最优的 DSpark `n_max=2`。普通开放式生成的收益可能接近零，必须按业务 corpus 测量。每组应重启 server，避免共享 n-gram pool 污染冷样本，并记录各 speculative implementation 的 calls、generated/accepted tokens 与 target decode 次数。

来源：[官方 speculative guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md)、[server speculative implementation](https://github.com/ggml-org/llama.cpp/blob/master/common/speculative.cpp)、[独立 tree example](https://github.com/ggml-org/llama.cpp/blob/master/examples/speculative/speculative.cpp)、[tree speculative PR #3624](https://github.com/ggml-org/llama.cpp/pull/3624)

## Architectural Patterns and Design

### Runtime Observability Pattern

在 `e3096b046` 中，累计 cache 统计由 cache session teardown 输出；没有已实现的周期性 dump、信号触发或 `llama-server` HTTP/Prometheus 暴露。加载期提前出现的统计来自短生命周期 session，不代表基准期间的活动 target session。可执行的无代码路径是在完成 warmup 与测量后向 server 发送可优雅退出的 `SIGINT`/`SIGTERM`，等待 context 析构，再从日志读取最后一组 `[moe-cache] CUDA* hits=...`。若要在线观测，应在正常线程中调用 stats formatter；不能直接在 POSIX signal handler 中取得 cache mutex 或写复杂日志。

来源：[MoE cache convergence 文档提交](https://github.com/leloch/llama.cpp/commit/fd612c0584f190eee60c79ed3495759a358c8c9e)、[v2 提交历史](https://github.com/leloch/llama.cpp/commits/moe-cache-v2-pr/)

### Capacity-Control Pattern

`GGML_CUDA_MOE_CACHE_RESERVE_MB` 精确控制每张设备留在 cache 外的 VRAM，默认 3072 MiB。当前分支没有公开的 `min-slab` CLI/环境变量；1024 MiB 是 `auto` 模式内部的设备资格门槛。最干净的新对照应固定 drafter 在 CUDA0，同时把 reserve 调到 2560 或 2048 MiB，使 CUDA0 的 `free-reserve` 越过 1024 MiB；不要再依赖自动移动 drafter 来改变容量。

来源：[环境控制表及默认值](https://github.com/leloch/llama.cpp/commit/c0d7d916b28accf869d8303f2d8622802c9248dd)、[automatic slab floor 提交](https://github.com/leloch/llama.cpp/commit/a68d9dad63a2351b653c3a57b7c7d75c17b7db99)

### Hybrid Execution Semantics

`cpu-overlap` 统计的是全命中节点中被策略重新留给 CPU 的 routed rows，不是所有 CPU/GPU 并行执行。普通 partial-hit 节点已经由 CPU 计算 miss rows、CUDA 计算 hit rows，但不会因此增加该字段。全命中时才调用 adaptive policy：自动预算为每 token 8 MiB expert weights，并受 token 数、routing width、节点四分之一 rows 限制。`max-batch=8` 是 eligible node 的 token 上限；DSpark `n_max=2` 产生的 2--3 token verification batch 小于此上限，top-6 对应 12--18 routed rows，也低于 64-row 上限。

来源：[adaptive CPU overlap 实现提交](https://github.com/leloch/llama.cpp/commit/f0bd8b1b5d2c70a26e3071f95842b06ba9011255)、[eligibility 与 batch 限制](https://github.com/leloch/llama.cpp/commit/c0d7d916b28accf869d8303f2d8622802c9248dd)

### Experimental Design Pattern

当前 2x2 可以分离“自动 drafter placement”与“cache treatment”的表面效应，但不足以形成部署结论。`drafter 不钉` 的最终设备 placement 可能受 cache reservation 反向影响，因此必须比较四格的 resolved weight/compute-buffer placement，而不能只比较 CLI。三次同进程连续 1024-token 测量属于相关重复，不是三个独立样本；应增加独立 server restart 的 AB/BA blocks。还必须记录每格 DSpark accepted/generated tokens 和 mean accepted length，避免 cache 数值差异改变生成轨迹后间接改变投机收益。

干净的机制 A/B 是固定 `--spec-draft-device CUDA0`、撤掉 `-ot`、两臂使用相同 `GGML_CUDA_MOE_CACHE_RESERVE_MB=2560`，只切 `--moe-cache off` 与 `auto`。最终部署比较还要把生产最优基线“cache off + 原 `-ot`”加入，因为撤掉 `-ot` 是使用 cache 的机会成本，而不是可忽略的 nuisance variable。

### Coverage and Convergence Pattern

现有 pools 合计 14,310 MiB，只覆盖约 12.5% 的 112 GiB expert bytes。按日志逐类型计算，IQ3 slots/entries 为 `2632/21504=12.24%`，MXFP4 为 `1471/11520=12.77%`；`coverage=partial` 表示每种 shape 都必须依赖 admission/eviction，不能保证任一层全部 experts 常驻。若 routing 接近均匀，命中率会接近该容量比例并大概率无法偿还 dispatch/sync 成本；只有明显热集偏斜才能得到远高于 12.5% 的 residency hit rate。

上游验证使用过 512 warmup + 512 measured tokens，并在混合串行 workload 的首轮约 1943 tokens 内收敛，第二轮吞吐仅差 0.06%。因此本机 512 warmup + 3x1024 对固定分布原则上足够；是否真正稳态仍必须由 teardown 的 `used/capacity`、`filled`、`evictions`、hit rate 和每 1024 token 吞吐斜率共同确认。

来源：[workload convergence](https://github.com/leloch/llama.cpp/commit/fd612c0584f190eee60c79ed3495759a358c8c9e)、[RFC 与工作集建议](https://github.com/ggml-org/llama.cpp/discussions/24528)

### Deployment Decision Rule

在取得活动 session 的最终统计前，`-20.5%` 不能被判定为容量不足的必然结果。若最终 hit rate 很低且 `used` 已满、evictions 持续增长，则 12.5% partial coverage 是主因，降低 reserve 最多再增加少量 GiB，通常不足以扭转 20.5% 回退。若 hit rate已高、failures 为零、吞吐仍回退约 20%，则问题是该双路 Xeon/无 P2P/双 3090 上的 per-node dispatch/collect 成本，继续调容量没有意义，应结束该路线。
