# Hindsight 多语言重排模型评估（2026-10）

pve1 LXC 118 上的 Hindsight 0.10.2 原来用英文重排模型 `cross-encoder/ms-marco-MiniLM-L-6-v2`，中文查询的召回排序很差。本文记录这次对多语言重排模型（以及嵌入模型）的对比测试、结论、上线变更和回滚办法。服务本身的部署与运维见 [hindsight-memory-architecture.md](./hindsight-memory-architecture.md) 和 [hindsight-operations.md](../guides/hindsight-operations.md)。

**证据口径**：下面的数字来自 2026-10-10 在 LXC 118 里用一次性容器做的实测（实测记录），以及切换后对线上 API 的验证（2026-10-10 13:55 UTC 之后）。相关性标注由执行评估的 agent 一人完成，在运行任何模型之前定好。本文不包含记忆原文、记忆 ID 或 key。

## 结论

- **已上线**：重排模型换成 `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`（2026-10-10 13:55 UTC，用户同意）。中文查询 nDCG@5 从 0.20 升到 0.79，第一条结果相关从 5/20 升到 19/20；英文从 0.59 升到 0.79。代价是线上重排从约 2.5 秒增加到约 3.7 秒（召回端到端最长约 4.8 秒），容器内存从约 0.9 GiB 升到约 1.6 GiB。
- **质量最好的 `BAAI/bge-reranker-v2-m3` 不可用**：比 mmarco 再好一点（中文 +0.07、英文 +0.04，置信区间不含 0），但在 i5-8500 上每次重排约 42 秒，远超 Hermes 的 8 秒上限；只重排前 30 个候选也要约 8.7 秒，而且质量反而不如 mmarco。
- **嵌入模型不换**：相关记忆已经全部（中文 100%、英文 97.5%）出现在候选集里，问题在重排。换嵌入要把所有库重新嵌入，而且同为 384 维时 Hindsight 不会察觉模型变了。
- **iGPU（UHD 630）不值得用**：理论算力和 CPU 相当，Hindsight 也没有能用它的提供方，见[iGPU](#igpuuhd-630)。

## 问题现象

对 `coding-agent::IaC` 做中文召回（`budget: low`、`types: ["observation"]`、`trace: true`）时，约 140 个候选里有约 90 个的 `rerank_score` 都在 1.1 左右，排第一的常与问题无关；英文查询分数分层清楚。

原因：MiniLM-L6 给大约一半的中文候选打出很高的 logit（经 sigmoid 归一化后 > 0.9 的占 42.5%，英文查询只有 0.3%）。Hindsight 的最终分数是 `归一化CE × 新近度加成 × 时间加成 × 确认次数加成`，CE 都接近 1 时，排序实际由新近度和确认次数决定，与问题内容无关。多语言模型的分数分布正常（> 0.9 的约 1%）。

## 测试方法

- **查询集**：两个库，`coding-agent::IaC`（168 条观察）和 `coding-agent::hermes`（141 条观察，中、英、俄文混合）。共 20 个话题，每个话题一条中文问法、一条英文问法，合计 40 条查询。其中 6 个话题的相关记忆主要是英文，用来测“中文问、英文答”。话题包括 N100 网关的角色、网关上的重排模型、pve0 系统盘故障、网关容器备份、BookOrbit 部署、控制台 502、阅读器选购要求、HF 离线模式、DeepSeek V4 调优、提交规则、Qwen3-TTS 静音、Hermes 记忆库划分，以及 hermes 库里的 VAD 静音、TTS 选择、T7910 定时开机、天气插件、auth.json 备份、开发团队 profile、homelab-admin、ASR 跨境建连。
- **标注**：每个话题把直接回答问题的记忆标为 2、相关的标为 1，在运行任何模型之前定好；事后检查各模型前 5 名里未标注的记忆，没有发现明显漏标。
- **候选**：每条查询先对线上 API 做一次真实召回，取 trace 里的全部候选（约 130~150 个，`budget: low` 时约占库的 86%（IaC）和 95%（hermes）），再按 Hindsight `engine/search/reranking.py` 的格式拼出重排输入（`[Date: …] context: text`）。各模型对同一批候选打分。
- **复现校验**：用同样的代码路径（`LocalSTCrossEncoder`：分桶批处理、batch 32、权重对齐）重算 MiniLM-L6，与线上 trace 的分数最大差 4e-6（两个库共 5,602 对）；切换后线上 mmarco 分数与测试结果最大差 7e-6。
- **评分**：用 Hindsight 的最终排序（CE 乘以线上 trace 里的各项加成）计算 nDCG@5、nDCG@10、MRR、第一条相关数，以及与 mmarco 的逐条配对比较（bootstrap 95% 置信区间）。
- **环境**：一次性容器，镜像同为 `ghcr.io/vectorize-io/hindsight:0.10.2`，`--network host --cpus 4 --oom-score-adj 1000`，模型下载到单独的临时缓存，不写 `/opt/hindsight/hf-cache`。内存上限原定 1 GiB，但多语言模型加载就超限（import 约 410 MB + fp32 权重 + 权重对齐副本），经用户同意先放宽到 2 GiB，测 bge-reranker-v2-m3 时放宽到 4 GiB（LXC 实际可用约 3 GiB）。耗时是 4 线程实测；“线上估算”按 MiniLM-L6 的线上 6 线程与测试 4 线程之比（0.83）折算。

## 结果

### 总表（两个库，各 20 条查询）

| 重排模型 | 参数 | 中文 nDCG@5 | 中文第一条相关 | 英文 nDCG@5 | 英文第一条相关 | 4 线程重排中位数 | 线上估算 | 峰值 RSS |
|---|---|---|---|---|---|---|---|---|
| ms-marco-MiniLM-L-6-v2（原线上） | 23M | 0.20 | 5/20 | 0.59 | 14/20 | 3.1 s | 2.6 s | 1.0 GB |
| **mmarco-mMiniLMv2-L12-H384-v1（已上线）** | 118M | **0.79** | **19/20** | **0.79** | **19/20** | 4.7 s | **3.9 s** | 1.7 GB |
| jina-reranker-v2-base-multilingual（强制 fp32） | 278M | 0.79 | 19/20 | 0.78 | 18/20 | 12.5 s | 10.4 s | 2.2 GB |
| bge-reranker-base | 278M | 0.85 | 20/20 | 0.78 | 19/20 | 14.7 s | 12.3 s | 2.1 GB |
| bge-reranker-v2-m3 | 568M | 0.86 | 20/20 | 0.83 | 19/20 | 51.0 s | 42.5 s | 2.8 GB |
| FlashRank `ms-marco-MultiBERT-L-12`（int8 ONNX） | — | 0.14 | 3/20 | 0.28 | 6/20 | 22.7 s | 19 s | 2.1 GB |

峰值 RSS 是测试进程的，包含 torch 等库本身（约 0.4 GB）。

### 按问法与库细分（nDCG@5）

| 分组 | MiniLM-L6 | mmarco | jina fp32 | bge-base | bge-v2-m3 |
|---|---|---|---|---|---|
| 中文问 → 中文记忆（14） | 0.27 | 0.77 | 0.76 | 0.85 | 0.85 |
| 中文问 → 英文记忆（6） | 0.05 | 0.84 | 0.84 | 0.84 | 0.90 |
| 英文问 → 中文记忆（14） | 0.47 | 0.78 | 0.74 | 0.75 | 0.82 |
| 英文问 → 英文记忆（6） | 0.86 | 0.82 | 0.88 | 0.84 | 0.86 |
| IaC 库中文（12） | 0.13 | 0.80 | 0.77 | 0.84 | 0.85 |
| hermes 库中文（8） | 0.31 | 0.78 | 0.81 | 0.85 | 0.88 |
| IaC 库英文（12） | 0.58 | 0.77 | 0.78 | 0.80 | 0.82 |
| hermes 库英文（8） | 0.61 | 0.83 | 0.78 | 0.74 | 0.85 |

只有“英文问、英文答”这一组 MiniLM-L6 本来就好，mmarco 略低（0.82 对 0.86）。

### 与 mmarco 逐条比较（nDCG@5，胜/平/负，均值差的 95% 置信区间）

| 模型 | 中文 | 英文 |
|---|---|---|
| MiniLM-L6 | 0/0/20，−0.59 [−0.71, −0.46] | 2/4/14，−0.20 [−0.33, −0.09] |
| jina fp32 | 6/7/7，−0.01 [−0.04, +0.03] | 4/8/8，−0.01 [−0.06, +0.04] |
| bge-reranker-base | 12/6/2，+0.05 [+0.00, +0.12] | 6/7/7，−0.02 [−0.08, +0.04] |
| bge-reranker-v2-m3 | 14/4/2，+0.07 [+0.02, +0.14] | 5/11/4，+0.04 [+0.01, +0.08] |

### 限制重排候选数（`HINDSIGHT_API_RERANKER_MAX_CANDIDATES_LOW`）

nDCG@5 中文/英文，以及按候选数线性折算的线上重排耗时：

| 模型 | 30 | 50 | 100 | 不限（约 140） |
|---|---|---|---|---|
| MiniLM-L6 | 0.22/0.60，0.5 s | 0.21/0.59，0.9 s | 0.20/0.59，1.8 s | 0.20/0.59，2.6 s |
| mmarco | 0.68/0.76，0.8 s | 0.72/0.76，1.4 s | 0.75/0.78，2.7 s | 0.79/0.79，3.9 s |
| jina fp32 | 0.69/0.78，2.1 s | 0.71/0.77，3.6 s | 0.75/0.78，7.1 s | 0.79/0.78，10.4 s |
| bge-reranker-base | 0.71/0.75，2.5 s | 0.74/0.74，4.2 s | 0.81/0.77，8.3 s | 0.84/0.78，12.3 s |
| bge-reranker-v2-m3 | 0.72/0.78，8.7 s | 0.76/0.78，14.6 s | 0.82/0.81，29.1 s | 0.86/0.83，42.5 s |

在 8 秒以内的组合里，不限候选的 mmarco 质量最高。限制候选数会漏掉 RRF 排名靠后的相关记忆（前 30 个候选只覆盖 71% 的中文标 2 记忆，前 100 个覆盖 93%），所以目前不设上限；只有召回明显变慢时才考虑设 100。

### 淘汰原因

- **jina-reranker-v2-base-multilingual**：它的 `config.json` 写的是 `torch_dtype: bfloat16`，transformers 5 默认 `dtype="auto"` 会照此加载；这颗 CPU 不支持 bf16 计算，按 Hindsight 的默认加载方式每条查询约 180 秒（只测了 2 条就停止）。强制 fp32 需要改 Hindsight 代码或另做本地副本，且仍要约 10 秒，质量与 mmarco 相同；还需要 `HINDSIGHT_API_RERANKER_LOCAL_TRUST_REMOTE_CODE=true`。
- **bge-reranker-base**：中文略好于 mmarco（置信区间下限贴着 0），但慢 3 倍以上。
- **bge-reranker-v2-m3**：质量最好，但 CPU 上太慢。
- **FlashRank `ms-marco-MultiBERT-L-12`**：分数同样大量饱和（约 30% 的候选 > 0.9），质量最差，而且很慢。

## 嵌入模型

只看语义检索这一路（全库余弦排序）：

| 嵌入模型 | 中文 nDCG@10 | 英文 nDCG@10 | 中文标 2 记忆 recall@20 | 英文 recall@20 | 文档编码速度（4 线程） |
|---|---|---|---|---|---|
| BAAI/bge-small-en-v1.5（现用） | 0.54 | 0.71 | 0.71 | 0.87 | 30 条/秒 |
| intfloat/multilingual-e5-small | 0.59 | 0.56 | 0.74 | 0.84 | 38 条/秒 |
| paraphrase-multilingual-MiniLM-L12-v2 | 0.67 | 0.72 | 0.86 | 0.88 | 58 条/秒 |

- `budget: low` 的候选集已经覆盖约 86%~95% 的库，标 2 的记忆在候选里的比例中文 100%、英文 97.5%，所以现在换嵌入对最终结果帮助有限。库变大（几千条以上）后，嵌入质量才会成为瓶颈。
- multilingual-e5-small 需要 `query: ` / `passage: ` 前缀，但它的 sentence-transformers 配置没有声明提示词，Hindsight 的本地嵌入就不会加前缀，所以英文反而变差。
- paraphrase-multilingual-MiniLM-L12-v2 的最大长度只有 128 个 token，较长的中文观察会被截断。
- **风险**：三者都是 384 维，与现用模型相同，Hindsight 不会因为维度变化触发重建；换模型后必须显式把所有库重新嵌入，否则新旧向量混在一起，检索结果悄悄变差。

## iGPU（UHD 630）

pve1 的 i5-8500 有 UHD 630（`00:02.0`，i915 已加载，`/dev/dri/renderD128` 存在），目前没有直通给 LXC 118。结论是不值得用，原因（分析，未实测）：

- 算力：UHD 630 是 Gen9.5、24 个 EU，fp32 约 0.4 TFLOPS、fp16 约 0.8 TFLOPS；CPU 6 核 AVX2 FMA 约 0.5~0.6 TFLOPS。即使 fp16 跑满也只快 1.5~2 倍，而且和 CPU 共用内存带宽。bge-reranker-v2-m3 即使快 2 倍也要约 20 秒。
- 软件：镜像里是 CPU 版 PyTorch；PyTorch 的 Intel GPU（XPU）后端不支持 Gen9 核显。能用它的只有 OpenVINO，而 Hindsight 没有 OpenVINO 提供方，得另起一个 OpenVINO 重排服务，再通过 `tei` 或 Cohere 兼容接口接入，还要把 `/dev/dri` 直通进非特权 LXC、安装只对 Gen9 保留旧版支持的 Intel compute runtime。
- 要用 bge-reranker-v2-m3 这一级的模型，现实的办法是放到独立 GPU 上（例如 llm-workstation 上的 TEI 服务，Hindsight 配 `HINDSIGHT_API_RERANKER_PROVIDER=tei`，本地 mmarco 作为备用）。未测，且依赖那台机器在线。

## 上线变更（2026-10-10 13:55 UTC）

1. 备份：`/opt/hindsight/compose.yaml.bak-20261010-135442`。
2. 把测试时下载的模型复制进线上缓存，离线模式保持开启：`hf-cache/hub/models--cross-encoder--mmarco-mMiniLMv2-L12-H384-v1`（470 MB，属主 1000:1000）。旧的 `models--cross-encoder--ms-marco-MiniLM-L-6-v2`（88 MB）保留，供回滚用。缓存合计约 690 MB。
3. `compose.yaml` 的 `environment` 增加：

   ```yaml
   HINDSIGHT_API_RERANKER_LOCAL_MODEL: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
   ```

4. `docker compose config --quiet`，`docker compose up -d`。约 21 秒后 `/health` 返回 200，日志显示 `initializing local provider with model cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` 和 XLM-RoBERTa 兼容补丁，RestartCount 0。
5. 验证：40 条查询的线上召回，重排中位数 3.7 秒、最长 4.7 秒，端到端中位数 3.8 秒、最长 4.8 秒；线上分数与测试一致（最大差 7e-6）；容器内存约 1.6 GiB / 3 GiB。线上第一条相关为 32/40，低于测试时的 38/40：测试期间 IaC 库经过后台整理（删 10 条、增 15 条观察），4 个话题的标注答案换成了新记录，排第一的多是这些未标注的新记录；真正答错的只有 hermes 库“ASR 跨境建连”的两条，与测试一致。

### 回滚

删除 `compose.yaml` 里的 `HINDSIGHT_API_RERANKER_LOCAL_MODEL` 一行（或换回备份文件），`docker compose up -d`。MiniLM-L6 仍在缓存里，离线模式下可以直接启动。

## 风险与后续

- **延迟**：重排比原来多约 1.2 秒。本地重排串行执行（`MAX_CONCURRENT=1`），几个客户端同时召回会排队；`mid`/`high` 预算候选更多（约 300 个时估计 7~8 秒）。Hermes 每条消息前的查询有 8 秒上限，用的是 `low`。
- **分数尺度变了**：依赖固定分数阈值的配置需要重新确认；目前 Hermes 没有设 `recall_min_scores`。
- **评估局限**：只有两个库、40 条查询，一人标注；线上耗时由 4 线程测试折算到 6 线程，切换后的线上测量与估算一致。
- **以后的选项**：库明显变大后，重新评估多语言嵌入模型（要计划好全库重嵌入）；需要更高质量时，评估在 GPU 上跑 bge-reranker-v2-m3。
