# Release manifest contract

每个 PoC 候选和生产晋级版本必须生成一个不可含糊的 manifest。以下字段是合同，不代表尚未验证的 live 值已经确定。

## Identity

| Field | Required value |
|---|---|
| Release ID | 唯一、可排序的候选标识 |
| Created at | UTC timestamp |
| Purpose | `tp1-baseline`、`tp2-experiment`、`ik-llama-comparison` 或 `production` |
| Source revision | 生成本候选的 IaC git commit；未 commit 时记录 workspace diff identity |
| Fixture revision | corpus/API/benchmark fixture 的精确版本 |

## Model artifact

| Field | Baseline / rule |
|---|---|
| Repository | `deepseek-ai/DeepSeek-V4-Flash-0731` |
| Revision | 完整 commit hash；部署时重新解析并明确批准，不跟随 `main` |
| Format | 官方 safetensors；比较路线另记 matched GGUF 来源与转换 lineage |
| Local path | 解析后的绝对路径 |
| File manifest | 文件名、大小、必要 hash、model index 与 shard completeness |
| Mount mode | runtime 中只读 |

研究时观察到的 revision `7872f01b1d1fe23eabc4c98b48bffcef5a386062` 只能作为来源时间点证据，不能自动成为部署 pin；部署候选必须重新解析并有意识地固定。

## Runtime artifact

| Field | Required value |
|---|---|
| Primary engine | KTransformers/SGLang-KT |
| Image | registry/repository + immutable digest，不能只有 `DSV4-specific` tag |
| Effective entrypoint | 容器实际 command/args |
| Runtime commits/packages | KTransformers/SGLang-KT 及关键 coupled dependency 的可审计 identity |
| Parser | reasoning parser、tool-call parser 与相关参数 |
| Privileges | GPU device、IPC、capabilities、user 与 writable paths |
| API exposure | network、bind address、published port 与 auth mode |
| Open WebUI authority | database initialization evidence、是否执行 one-time seed、connection verification result；不得记录为持续 Ansible ownership |
| Secret material | Vault variable reference 与 root-owned `0600` runtime file path；不记录 secret value |
| Logging | driver、rotation/retention 与证据归档位置 |

比较路线还必须记录独立 `ik_llama.cpp` commit、build flags、binary path 与 GGUF lineage；不得引用旧 `f7923739` binary 作为 V4 runtime。

## Hardware and platform

| Field | Required value |
|---|---|
| VM | vCPU、memory、reservation、virtual hardware version |
| CPU | model、flags、guest socket/core/vNUMA topology |
| GPU | 每卡 model、UUID、PCI address、ordinal、driver、VRAM |
| GPU topology | `nvidia-smi topo -m`、P2P/NVLink test、连接形态 |
| CUDA | guest Toolkit、container CUDA 与 compatibility result |
| Driver decision | actual version、与 CUDA 12.8 的兼容证据；若低于首选 570.26+，记录接受依据或独立升级批准 |
| Storage | filesystem、free、artifact size、VMDK allocation、datastore headroom |
| NUMA evidence | guest placement 与 ESXi `N%L/%RDY/%CSTP` |

## Serving configuration

Baseline manifest values:

| Field | Value |
|---|---|
| Tensor parallelism | `1` |
| GPU ordinal | 明确指定单张 3090，初始为 GPU 0，最终以采集 identity 为准 |
| Context | `16384` |
| Max running requests | `1` |
| Speculative decode / MTP | disabled |
| Cache precision | 保守非量化基线；精确值按 runtime 支持固定 |
| Expert placement | 官方 SM86 heterogeneous fallback；任何 GPU expert 调整另建候选 |
| Reasoning parser | `deepseek-v4` 或经证据确认的等价配置 |
| Tool parser | `deepseekv4` 或经证据确认的等价配置 |
| Readiness budget | 初始 15–20 分钟，后续依据实测固定 |

其他必须记录的参数包括 sampling defaults、thread/NUMA policy、environment、volume、health check、restart policy 和 Open WebUI model identity/filter/prefix。

## Evidence references

Manifest 必须链接或嵌入以下机器可读结果的位置：

- preflight report；
- model/image integrity report；
- correctness corpus result；
- OpenAI/reasoning/tool/SSE contract result；
- performance benchmark result；
- cold boot/restart/first-request/soak result；
- exposure/security check；
- Open WebUI backup evidence、安全停止与固定候选冷恢复演练；
- 最终 promotion verdict 及批准记录。

缺少任一适用字段时，manifest 必须显式标为 unresolved，并阻止对应阶段晋级；不得用默认值或浮动 tag 悄悄补齐。
