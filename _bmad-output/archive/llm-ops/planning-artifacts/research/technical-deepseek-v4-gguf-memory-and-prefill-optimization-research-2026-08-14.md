---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'DeepSeek V4 GGUF memory and prefill optimization on dual RTX 3090'
research_goals: 'Identify safe, evidence-backed ways to use remaining GPU VRAM and host RAM to improve long-context and coding-agent prefill performance on the current dual-GPU CPU-MoE deployment.'
user_name: 'Will'
date: '2026-08-14'
web_research_enabled: true
source_verification: true
---

# From Spare Memory to Measurable Latency

## Comprehensive DeepSeek V4 GGUF Optimization Research for Dual RTX 3090

**Date:** 2026-08-14
**Author:** Will
**Research Type:** technical

---

## Research Overview

This report investigates evidence-backed ways to improve long-context and coding-agent
prefill performance for the current dual RTX 3090, GGUF, CPU-MoE deployment. It separates
steady-state free capacity from usable peak headroom and distinguishes host-RAM prompt cache,
CPU-resident expert weights, GPU tensor residency, KV cache and prefill workspace.

The analysis combines the pinned runtime source and binary interface, repository desired state,
read-only live measurements, versioned API fixtures and current primary documentation. The main
finding is that the remaining RAM and VRAM are useful, but for different problems: host RAM can
retain more coding-agent conversation states, while GPU VRAM can host selected MoE experts. The
fork-specific DeepSeek4 graph-split path is real but remains a topology- and correctness-gated
candidate rather than a default recommendation.

The full strategic conclusion appears in the Research Synthesis section. The immediate sequence
is `cache-ram` 16/32 GiB, one-layer-at-a-time GPU expert placement, and only then graph split after
CUDA P2P measurement. Context beyond 128K is a separate capacity profile, not a latency shortcut.

## Executive Summary

The deployed service is a reproducible, pinned `ik_llama.cpp` CPU/GPU hybrid: DeepSeek4 GGUF,
128K configured context, two RTX 3090 GPUs in layer split, all MoE experts on CPU, and a private
backend behind a LAN-controlled OpenAI compatibility boundary. The current service passes the
complete 19-case API contract and generates at approximately 8 tokens/s, but a realistic 8K cold
coding prompt still requires roughly 85 seconds before the first visible token. Correctness and
capacity are proven at 128K; interactive long-prompt latency remains the main limitation.

The 2026-08-15 snapshot showed 181,079 MiB host RAM available and 11,816/11,656 MiB free on the
two GPUs while idle. Those numbers are not one interchangeable pool. Live logs also showed the
default 8 GiB host prompt-state cache evicting individual 0.87-5.62 GiB entries, making a 16/32
GiB cache sweep the highest-confidence way to improve return-to-project latency. The next most
direct use of VRAM is to replace all-CPU-MoE with one GPU-resident expert layer at a time, using
the pinned fork's dry-run and exact correctness corpus.

DeepSeek's official model card describes million-token capability and recommends at least 384K
for Think Max, but model capability is not a local serving guarantee. This host has demonstrated
slower behavior at 256K and an OOM at 512K, so 128K remains the interactive baseline. Alternative
KTransformers/SGLang-KT support is strategically relevant but carries larger Ampere/AVX2 and
dependency uncertainty than the remaining ik experiments.

**Key Technical Findings:**

- Current upstream llama.cpp is not the deployed ABI; only pinned ik flags/source and live output
  are authoritative.
- `cache-ram` is already evicting real coding-sized states and is the first host-RAM experiment.
- GPU expert placement is more likely to improve cold PP/TG than using free VRAM for still larger
  context.
- The pinned source implements DeepSeek4 MLA graph split, but partial-offload correctness and P2P
  sensitivity require isolation.
- Native tool calling, stable tokenized prefixes and the compatibility proxy are separate latency
  factors and must be measured independently.

**Technical Recommendations:**

1. Implement constrained Ansible profiles and immutable per-run evidence before live tuning.
2. Test `cache-ram` 16 GiB, then 32 GiB only if host pressure and swap remain absent.
3. Test `--n-cpu-moe 42` first, then move at most one additional layer per successful run.
4. Measure CUDA P2P before comparing graph against the winning layer control.
5. Keep 256K/384K+, KV precision, concurrency and alternate runtime work in separate tracks.

## Table of Contents

1. [Research scope and methodology](#technical-research-scope-confirmation)
2. [Technology stack analysis](#technology-stack-analysis)
3. [Integration patterns](#integration-patterns-analysis)
4. [Architecture and design](#architectural-patterns-and-design)
5. [Implementation and adoption](#implementation-approaches-and-technology-adoption)
6. [Technical recommendations](#technical-research-recommendations)
7. [Comprehensive synthesis](#research-synthesis)
8. [Performance and capacity](#6-performance-and-scalability-analysis)
9. [Security and governance](#7-security-and-governance)
10. [Roadmap and future outlook](#9-implementation-roadmap-and-risk-assessment)
11. [Methodology and source verification](#11-research-methodology-and-source-verification)
12. [Appendices and references](#12-technical-appendices-and-reference-materials)

---

## Technical Research Scope Confirmation

**Research Topic:** DeepSeek V4 GGUF memory and prefill optimization on dual RTX 3090

**Research Goals:** Identify safe, evidence-backed ways to use remaining GPU VRAM and
host RAM to improve long-context and coding-agent prefill performance on the current
dual-GPU CPU-MoE deployment.

**Technical Research Scope:**

- Architecture analysis — model/runtime placement, GPU/CPU/PCIe/NUMA data paths.
- Implementation approaches — reproducible single-variable experiment design.
- Technology stack — current llama.cpp/ik_llama, CUDA, NVIDIA Ampere considerations.
- Integration patterns — OpenAI-compatible API, Open WebUI and coding-agent workloads.
- Performance considerations — context/KV sizing, prompt cache, prefill/decode,
  concurrency, CPU-MoE and memory bandwidth.

**Research Methodology:**

- Current web data with rigorous source verification.
- Multi-source validation for critical runtime claims.
- Explicit separation of measured local evidence, vendor documentation and inference.
- Confidence levels for uncertain or deployment-specific findings.

**Scope Confirmed:** 2026-08-14

---

## Technology Stack Analysis

### Evidence and Version Boundary

The review found that the original analysis mixed three different contracts: current
`ik_llama.cpp`, current upstream `llama.cpp`, and repository defaults that are overridden by
inventory. They must remain separate.

| Evidence class | What is established | How it may be used |
| --- | --- | --- |
| Live, 2026-08-15 | `deepseek-v4-ik.service` and its compatibility service are active; backend is private on `127.0.0.1:8082`; the stable API is `8081`; runtime reports version `4834 (981e5ea0)` | Current-state facts |
| Pinned source | `ik_llama.cpp` commit `981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8`; model revision and SHA-256 are pinned in Ansible | Runtime ABI and source-level capability |
| Inventory desired state | 128K context, `threads=32`, `threads-batch=36`, `batch=4096`, `ubatch=2048`, NUMA `distribute`, pinned host memory enabled | Reproducible current configuration |
| Upstream reference | `ggml-org/llama.cpp` current documentation | Candidate ideas only; never proof that the pinned fork accepts a flag or shares its default |

Lifecycle actions remain disabled by default and require an explicit qualification tag. The role
and host inventory now agree that pinned host memory is enabled. All recommendations below first
require the pinned binary's `--help` or pinned source, then an API-level experiment.

### Current Runtime and Allocation Baseline

The serving path is a C/CUDA `ik_llama.cpp` binary in Docker, orchestrated by systemd and Ansible,
behind a small Python OpenAI-compatibility adapter. The live model endpoint reports:

- model architecture `deepseek4`, trained context 1,048,576, configured maximum 131,072;
- GGUF size about 145.6 GiB at roughly 4.4 bits per weight;
- two RTX 3090 GPUs, both active, with current idle headroom of 11,816 MiB and 11,656 MiB;
- 342,595 MiB host RAM total and 181,079 MiB available at the 2026-08-15 snapshot.

Startup evidence is more useful than total system memory alone. The runtime allocated 138.05 GiB
of pinned host memory, 5,504 MiB of GPU KV buffers, 4,640 MiB of GPU compute buffers and 672 MiB
of host compute buffers. System-wide `used` memory cannot be attributed entirely to CPU-MoE;
container cgroup/RSS/PSS and mapped pages are required for exact attribution.

### Pinned ik_llama Capabilities

The deployed binary directly confirms support for `--cache-ram`, `--attention-max-batch`,
`--parallel`, `--cpu-moe`, `--n-cpu-moe`, `--fit`, `--fit-margin`, `--gpu-fit-margin`,
`--worst-graph-tokens`, `--override-tensor`, and `--split-mode {none,graph,layer}`. It does **not**
advertise upstream-style `--cache-reuse`, `--cache-prompt`, or `--fit-target`; those are removed
from the current recommendation set.

The pinned source also contains a DeepSeek4-specific MLA graph-split path and explicitly labels
its per-device MLA shards for DeepSeek2/DeepSeek4. Therefore upstream's lack of DeepSeek2 tensor
split support only rules out **upstream tensor split**. It does not rule out the fork's distinct
`--split-mode graph` implementation.

Graph split is nevertheless an experimental candidate, not an established improvement. The
fork warns that graph split combined with partial GPU offload can produce incoherent output, and
suggests disabling CUDA graphs as a troubleshooting measure. On this quantized CPU-MoE deployment,
any graph test must start in an isolated instance and pass the full correctness/streaming/tool
contract before performance is considered.

Sources: [pinned ik parameters](https://github.com/ikawrakow/ik_llama.cpp/blob/981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8/docs/parameters.md),
[pinned DeepSeek4 MLA split declarations](https://github.com/ikawrakow/ik_llama.cpp/blob/981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8/src/llama-model.h),
[ik_llama graph/offload warning](https://github.com/ikawrakow/ik_llama.cpp),
[upstream multi-GPU limitations](https://github.com/ggml-org/llama.cpp/blob/master/docs/multi-gpu.md).

### Host RAM: Prompt-State Cache Before More Concurrency

The pinned fork's cache mechanism is a host-RAM prompt/KV-state cache. Its documented default is
8,192 MiB and it is explicitly intended for switching among coding-agent conversations. Live logs
show repeated cache-limit evictions, including entries of approximately 0.87, 1.75, 3.51 and
5.62 GiB. With about 176.8 GiB available at the snapshot, a controlled 8 -> 16 -> 32 GiB
`--cache-ram` sweep is the clearest way to turn spare host RAM into lower **warm** TTFT.

This will not accelerate a truly cold first prompt and will not increase decode tokens/s. It can
reduce re-prefill after changing projects or conversations only when the server can match the
tokenized prefix/state. Each step must record cache admission, eviction, warm TTFT, RSS/available
RAM and swap activity. `--parallel 2` is not the first response: it creates another decode
sequence and may divide or multiply context/KV costs, while the current workload is primarily one
interactive coding agent.

Source: [ik_llama host-RAM cache parameters](https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/parameters.md#cache-prompt-to-host-memory).

### GPU VRAM: Expert Placement Before Larger KV

The current command uses `--n-gpu-layers 100 --cpu-moe`: non-expert work is offloaded while all
MoE expert weights remain in host memory. The fork's own placement guidance says to keep regular,
shared-expert, gate and up/down tensors in fast memory first, then use spare VRAM for sparse
`exps`. This makes expert placement the most direct way to exchange the current 23+ GiB aggregate
VRAM headroom for PP/TG improvement.

The safe sequence is:

1. Capture current tensor allocation with the pinned binary's `--dry-run` and startup log.
2. Replace all-CPU-MoE with `--n-cpu-moe` one layer at a time, beginning with only the last MoE
   layer moved to GPU; stop before either GPU has less than a measured 2 GiB peak margin.
3. If whole layers leave unusable fragments, use narrowly scoped `--override-tensor` rules based
   on actual GGUF tensor names. Do not separate paired up/gate tensors across devices.
4. For each layout, run cold/warm 1K and 8K PP, TG, 128K-startup, peak VRAM and the full API
   correctness suite.

`--fit` is off by default in this fork, unlike current upstream llama.cpp. It can be evaluated
with fork-specific `--fit-margin` and `--gpu-fit-margin`, but explicit placement remains easier to
audit and reproduce.

Source: [ik_llama memory placement and fit guidance](https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/parameters.md).

### KV Cache, Context and Prefill Workspace

The current DeepSeek4 path uses MLA and startup reports only about 5.5 GiB of GPU KV allocation at
128K. The fork documentation says MLA is already a compressed cache representation and that
additional KV quantization often provides little value. KV quantization is therefore secondary:
use it only for a demonstrated context/concurrency requirement or to free VRAM for a higher-value
expert placement, followed by a quality regression suite.

The existing 512K startup OOM proves only that the tested configuration could not satisfy its
peak allocation. It does not identify whether KV, graph workspace, fragmentation or another
allocation was causal. `--worst-graph-tokens`, `--attention-max-batch` and `--max-extra-alloc`
exist in the pinned binary and can help isolate workspace pressure, but they are advanced
diagnostic variables. They should be introduced only in the isolated context-capacity track,
not mixed with expert or cache experiments.

The already measured `batch=4096` and `ubatch=2048` improvement is retained. Larger values are
not justified by free steady-state VRAM alone; PP throughput, peak allocation and correctness at
the target prompt depth decide.

Sources: [ik_llama cache and workspace parameters](https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/parameters.md),
[upstream batch terminology, reference only](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

### Hardware and Multi-GPU Boundary

Layer split remains the known-good baseline because it minimizes cross-GPU traffic. Graph split
is now a valid fork-specific A/B candidate, but its value depends on actual GPU-to-GPU topology.
The previously calculated 7.88 GB/s for PCIe Gen3 x8 is a protocol-level one-direction ceiling,
not measured P2P bandwidth and not an end-to-end guarantee. RTX 3090 supports NVLink as a product
capability, but presence of a bridge and a working passthrough P2P path have not been proven here.

Before graph-split performance testing, collect `nvidia-smi topo` and CUDA's
`p2pBandwidthLatencyTest`. Broadcom documents that ESXi 7.0 U2+ requires
`pciPassthru.allowP2P=true` and `pciPassthru.relaxACSforP2P=true` for passthrough peer DMA. That is
a separate maintenance-window decision; it must not be inferred from guest link width or changed
as part of an online runtime flag sweep.

Pinned host memory is already enabled. NVIDIA documents that page-locked host memory can improve
host-device bandwidth, while warning against excessive use. Local A/B evidence also found that
disabling it worsened 8K TTFT, so it remains part of the baseline rather than another open tuning
candidate.

Sources: [NVIDIA CUDA pinned-memory guidance](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#pinned-memory),
[Broadcom VMDirectPath requirements](https://knowledge.broadcom.com/external/article/312208/vsphere-vmdirectpath-io-and-dynamic-dire.html),
[NVIDIA CUDA samples](https://docs.nvidia.com/cuda/cuda-samples/index.html),
[RTX 3090 specification](https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3090/).

### Alternative Runtime Boundary

KTransformers/SGLang-KT remains a separate architecture evaluation. Its DeepSeek-V4 tutorial
documents heterogeneous expert scheduling and optional speculative/MTP features, but published
results on a different GPU generation do not predict this dual-3090 ESXi guest. It must not be
mixed into the current ik tuning matrix. Only revisit it after the pinned ik cache, expert and
graph experiments converge.

Sources: [KTransformers DeepSeek-V4-Flash guide](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/DeepSeek-V4-Flash.md),
[KTransformers RTX 3090 issue](https://github.com/kvcache-ai/ktransformers/issues/1999).

### Reviewed Technology Priorities

| Priority | Candidate | Capacity used | Expected effect | Confidence |
| --- | --- | --- | --- | --- |
| 1 | `cache-ram` 16/32 GiB | Host RAM | Warm project/chat TTFT | High; live eviction evidence |
| 2 | One-at-a-time GPU expert placement | GPU VRAM | Cold PP and possibly TG | Medium-high; exact gain requires A/B |
| 3 | Fork `graph` versus `layer` | GPU interconnect/VRAM | PP/TG distribution | Medium-low; source support proven, topology benefit not proven |
| 4 | NUMA/thread refinement after placement | CPU memory bandwidth | CPU-MoE PP/TG | Medium; current `distribute` already measured best among tested settings |
| 5 | KV quantization or >128K | GPU capacity | Context capacity, not speed | Medium for fit, lower for quality |
| 6 | SGLang-KT/MTP migration | Entire runtime | Potentially different ceiling | Low near term |

## Integration Patterns Analysis

### API and Compatibility Boundary

Clients use an OpenAI-style `/v1` API through the compatibility service on port 8081; the pinned
backend is private on `127.0.0.1:8082`. The adapter is an anti-corruption layer: it preserves the
client contract but is not an inference accelerator. Benchmark output must identify whether it
used direct backend or proxy, streaming or non-streaming, and distinguish time to HTTP headers,
first SSE event, first content delta and completion.

The current proxy has a streaming relay path and a normalization path; it should not be described
as buffering the full response without measurement. Direct 8082 versus proxy 8081 A/B is the
correct test. Final API acceptance remains on 8081 because that is what Open WebUI and LAN clients
consume.

### Current Cache Semantics and Coding Agents

The pinned ik binary uses host-RAM cache parameters `--cache-ram`,
`--cache-ram-similarity` and `--cache-ram-n-min`. It does not expose upstream
`--cache-reuse`. Its pinned source also disables generic context shifting for DeepSeek4 while
retaining architecture-specific partial reuse paths, so upstream cache recipes cannot be copied
across unchanged.

Reuse is determined by the server's rendered and tokenized prefix/state, not by a client JSON
hash alone. A stable system/tool prefix may be reusable even if transport JSON differs, while
identical-looking client JSON can tokenize differently after server-side template or date/tool
injection. The benchmark should therefore correlate returned prompt/cache counts and TTFT; request
hashes are only privacy-preserving correlation IDs.

For OpenCode, the user has confirmed this endpoint is a real workload, but the exact first-task
rendered prefix and multi-project reuse behavior are not yet captured. A valid workload test is:

1. cold project A;
2. immediate continuation in A;
3. cold project B;
4. return to A after B;
5. repeat under 8, 16 and 32 GiB `cache-ram`.

Record only token counts, cache-entry sizes, cache hits/evictions and timing unless prompt-content
retention is explicitly approved.

Source: [ik_llama host-RAM cache documentation](https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/parameters.md#cache-prompt-to-host-memory).

### Native Tools and Prompt Cost

Open WebUI documents Native mode as the supported agentic function-calling path and Legacy as the
old prompt-injection compatibility mode. Native tool definitions are structured request data, but
the target chat template ultimately decides how much becomes model input. Therefore the report
does not assume that every schema byte is a token or that Native has zero prompt cost.

Keep Native for correctness and measure three otherwise identical requests: no tools, one
essential tool, and the current enabled tool set. Compare returned prompt-token count and cold
TTFT. Attach only useful tools at model level, and remember Open WebUI separately checks each
user's read access to model-attached tools.

Open WebUI also warns that Workspace Tools execute arbitrary Python and that granting management
access is equivalent to server code execution. Tool availability and tool administration must
remain separate permissions.

Source: [Open WebUI Tools and Native mode](https://docs.openwebui.com/features/extensibility/plugin/tools/).

### Observability Contract

Upstream response fields such as `cache_n` or `cached_tokens` are not assumed. The harness should
feature-detect fields returned by the pinned server and always calculate protocol-level TTFT and
end-to-end time independently. Each run should emit a stable JSON evidence record containing:

- runtime commit, model hash/revision and rendered command;
- endpoint and streaming mode;
- prompt/output token counts and any returned cache counters;
- TTFT, PP, E2E and TG;
- per-GPU peak VRAM/utilization and host RSS/available/swap;
- cache admissions/evictions and service restart/error counts;
- fixture revision and correctness verdict.

Metrics or slot endpoints should be enabled only if the pinned binary supports them and they can
remain loopback/private. Existing structured benchmark output and logs are preferable to exposing
a new unauthenticated endpoint.

### Network and Security Boundary

Keep the backend bound to loopback. The stable API is intentionally LAN-reachable and protected by
CIDR policy; Docker warns that published ports are otherwise reachable beyond the host. If the API
boundary ever expands beyond the trusted LAN, add API authentication and rate/resource limits
before expanding the bind or CIDRs. This is especially important for a 145 GiB model where one
large request can consume minutes of CPU/GPU time; OWASP classifies unrestricted resource
consumption as an API risk.

Do not log raw coding prompts, tool secrets or full request bodies in normal benchmarks. Keep
debug/metrics endpoints private and inventory every published port.

Sources: [Docker port-publishing security](https://docs.docker.com/engine/network/port-publishing/),
[OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/).

### Reviewed Integration Experiments

1. Increase only `cache-ram` to 16 GiB, then 32 GiB if swap remains zero; run the A/B/A coding
   conversation sequence and inspect evictions.
2. Compare direct 8082 and proxy 8081 with the same SSE request; retain the proxy only if its
   contract behavior remains necessary and its first-content overhead is negligible.
3. Compare Native no-tool/one-tool/all-tool prompt tokens and TTFT.
4. Keep `parallel=1` until a real overlapping-user workload is demonstrated; if concurrency is
   later tested, explicitly account for per-sequence context and KV capacity.
5. Preserve the full synchronous/SSE/reasoning/tool/malformed contract suite for every runtime
   or tensor-placement change.

## Architectural Patterns and Design

### System Architecture Patterns

The appropriate pattern is a **single active inference owner with a narrow compatibility edge**,
not a distributed service mesh:

```text
Open WebUI / OpenCode / LAN clients
                 |
        CIDR-controlled :8081
                 v
      OpenAI compatibility adapter
                 |
        loopback-only :8082
                 v
       pinned ik_llama server
          /              \
  host RAM / NUMA    GPU0 + GPU1
 weights + KV cache  weights + KV + workspace
```

This isolates protocol compatibility from model execution. A parser or date/tool adaptation can
be removed without changing model placement, while a GPU experiment cannot accidentally broaden
the LAN API. There remains only one owner of the large model and GPU lifecycle; simultaneous
candidate and primary instances would overcommit host RAM and complicate evidence.

### Design Principles and Best Practices

Five principles govern changes:

1. **Pin before tuning.** Record image digest, ik commit, model revision/hash and the actual
   binary `--help`; documentation from another fork is not a contract.
2. **Separate capacity pools.** Weight residency, GPU KV, GPU workspace and host prompt cache are
   independent budgets. Free memory in one pool does not prove another allocation will fit.
3. **One variable, one hypothesis.** Cache size, expert placement, split mode, context and NUMA
   are separate experiments with a known-good control.
4. **Correctness precedes speed.** A graph/expert layout that is faster but corrupts reasoning,
   SSE or tools is rejected.
5. **IaC remains authoritative.** Successful experimental arguments must be rendered by Ansible;
   ad-hoc CLI commands are diagnostic only. Ansible check/diff can preview supported tasks, but
   check mode is a simulation and cannot replace live service validation.

Source: [Ansible check and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html).

### Scalability and Performance Patterns

This is a vertical-scaling system. The immediate objective is not more replicas but better use of
one host's memory hierarchy:

- **Host cache tier:** 8 -> 16 -> 32 GiB `cache-ram` for warm coding-agent prefixes.
- **GPU residency tier:** migrate one MoE layer/tensor group at a time while preserving at least
  2 GiB measured peak headroom on each GPU.
- **Compute tier:** retain the measured batch/ubatch baseline; change workspace controls only to
  explain a capacity failure.
- **Interconnect tier:** compare layer and graph only after P2P/topology evidence, and require a
  meaningful end-to-end improvement rather than merely higher GPU utilization.
- **Context tier:** 128K is the interactive baseline. 256K/512K are capacity profiles, not speed
  optimizations, and should not share a run with placement tuning.

Horizontal concurrency through `parallel > 1` is deferred. It can improve aggregate service
throughput only when simultaneous demand exists, while it increases or partitions context/KV and
can worsen the single coding agent's latency.

### Integration and Communication Patterns

Use a stable OpenAI-facing contract and a replaceable backend adapter. Every performance test has
two layers:

- a direct-backend diagnostic to attribute runtime cost;
- an end-to-end proxy test to prove the client-visible contract and TTFT.

SSE is the latency-bearing path, so first HTTP byte is insufficient; the architecture records
first content delta. Native tool calling remains structured at the integration boundary, with
tool-set size measured rather than assumed. Host-RAM cache behavior is tested with realistic
project switching rather than synthetic identical JSON alone.

### Security Architecture Patterns

The trust boundary is explicit:

- backend `8082`: loopback only;
- compatibility API `8081`: trusted LAN CIDRs only;
- Open WebUI: authenticated users and per-model/per-tool access;
- debug, metrics and evidence: local/admin only;
- Workspace Tool management: trusted administrators only.

No experiment may widen a bind address, remove CIDR controls or persist raw prompts merely for
better observability. Rate and context/output limits are architectural safety controls because a
single request can monopolize scarce GPU/CPU resources.

Sources: [Docker port-publishing security](https://docs.docker.com/engine/network/port-publishing/),
[Open WebUI tool security](https://docs.openwebui.com/features/extensibility/plugin/tools/),
[OWASP unrestricted resource consumption](https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/).

### Data Architecture Patterns

Treat three data classes differently:

1. **Immutable artifacts:** GGUF, runtime commit and container digest; verify hashes before use.
2. **Ephemeral runtime state:** GPU KV and host `cache-ram`; it may contain conversational state,
   remains volatile, has a fixed memory budget and must not be mistaken for durable chat history.
3. **Evidence records:** sanitized JSON with run ID, parameters, token counts, timings, resource
   peaks and verdicts; no raw prompts or secrets by default.

This permits reproducible comparisons without turning performance telemetry into a second copy of
private source code or conversation content.

### Deployment and Operations Architecture

Each candidate is a named configuration profile rendered by Ansible. The operational sequence is:

1. local syntax/render/policy validation;
2. read-only preflight and pinned-binary capability check;
3. isolated startup or explicit single-owner restart;
4. health and model metadata verification;
5. correctness contract;
6. cold/warm benchmark with resource telemetry;
7. promote the winning parameters to inventory or restore the known-good profile.

Systemd should orchestrate the service boundary while Docker owns the container process; avoid
two independent restart policies. Keep the last known-good rendered configuration and evidence,
but do not automatically roll back during an exploratory run merely because one metric regresses:
first collect failure evidence unless correctness, OOM, corruption or system stability requires
termination.

### Architecture Decision Matrix

| Decision | Status | Rationale / promotion gate |
| --- | --- | --- |
| Retain layer split as control | Accepted baseline | Current correct configuration; least inter-GPU traffic |
| Increase host `cache-ram` | Next experiment | Live 8 GiB evictions; pass if warm A/B/A TTFT improves with zero swap/regression |
| Move MoE experts to GPU incrementally | Next GPU experiment | Direct use of 23+ GiB headroom; pass correctness and improve PP/TG materially |
| Test ik graph split | Isolated candidate | Pinned DeepSeek4 path exists; requires P2P evidence and full correctness before speed comparison |
| Increase context beyond 128K | Separate capacity track | Model supports it, but it is not a prefill-speed optimization |
| Enable `parallel > 1` | Deferred | No proven simultaneous workload; risks single-agent context/KV |
| Migrate to SGLang-KT | Deferred | Larger architecture change with unresolved 3090/AVX2 evidence |

## Implementation Approaches and Technology Adoption

### Technology Adoption Strategies

Adopt tuning as a sequence of named, time-limited canaries rather than a broad runtime rewrite.
Google SRE defines a canary as a partial and time-limited change evaluated against a control, and
recommends reproducible artifacts, automated tests, small changes and only one overlapping canary
when signal contamination matters. On this single large-memory host, the equivalent is a
before/after candidate: preserve the known-good rendered profile, stop the single active model
owner, run exactly one candidate, collect evidence, then either promote its parameters or restore
the control.

The adoption order is deliberately evolutionary:

1. retain the pinned ik runtime, GGUF and API contract;
2. add a larger host cache without changing tensor placement;
3. move one MoE layer/tensor group without changing cache or split mode;
4. evaluate graph split without changing context or precision;
5. revisit context capacity or another runtime only after these tracks converge.

This keeps the cost of a failed experiment to one service restart and one evidence run, rather
than combining several un-attributable changes.

Source: [Google SRE canarying releases](https://sre.google/workbook/canarying-releases/).

### Development Workflows and Tooling

Extend the existing `deepseek-v4-ik` role rather than introducing another deployment path. The
minimum repository change set for future implementation is:

- defaults: add `deepseek_v4_ik_cache_ram_mib`, an explicit CPU-MoE placement mode/count,
  `deepseek_v4_ik_split_mode`, and a required experiment ID;
- validation: allow only reviewed values and reject cross-variable combinations, such as graph
  without exactly two GPUs or both `--cpu-moe` and `--n-cpu-moe`;
- Compose template: render the corresponding arguments, never accept a free-form argument list;
- candidate tasks: create an experiment-specific evidence directory and save the rendered command,
  runtime/model pins and preflight snapshot before startup;
- runners: add a coding-cache A/B/A sequence and capture returned server timing/cache fields only
  when present;
- localhost tests: render every approved profile plus invalid combinations and assert the exact
  argument list and network boundary.

Use IDs such as `cache16-r1`, `ncmoe42-r1` and `graph-layercontrol-r1`; never overwrite fixed
`benchmark.json` or `candidate-result.json`. Each experiment directory should contain a manifest,
contract output, benchmark output, resource samples and relevant sanitized logs.

The pinned build currently contains only the `llama-server` executable. Although the fork
documents `llama-sweep-bench`, it is not a current deployable dependency. Continue using the real
OpenAI API harness first. Building the same-pinned sweep target may later provide diagnostics, but
must not replace end-to-end evidence or silently introduce another binary revision.

Sources: [pinned ik parameters](https://github.com/ikawrakow/ik_llama.cpp/blob/981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8/docs/parameters.md),
[Ansible check and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html).

### Testing and Quality Assurance

Testing has four layers:

1. **Static:** Python compilation/self-tests, JSON parsing/schema checks, Ansible syntax, localhost
   rendering, Compose validation and policy assertions.
2. **Capability preflight:** exact runtime version/commit, model metadata/hash, supported flags,
   GPU visibility/topology, free disk/RAM/VRAM and baseline service state.
3. **Candidate correctness:** health, `/v1/models`, deterministic synchronous response, SSE
   termination, reasoning separation, single/parallel tools, continuation, malformed input and
   the fixed correctness corpus.
4. **Performance and stability:** at least three measured repetitions after a declared cold or
   warm setup; PP/TTFT/E2E/TG, cache behavior, peak resources, error/restart counts and a final
   soak for the selected winner.

The workload must match the hypothesis:

- Cache tests use project A cold, A continuation, project B cold and return-to-A, under 8/16/32
  GiB cache limits. They measure warm revisit TTFT and eviction, not decode improvement.
- Expert-placement tests use the same cold 1K/8K prompts and output length, then compare PP, TTFT
  and TG while recording GPU peak headroom.
- Graph tests use the same tensor placement and first establish CUDA P2P/topology evidence. They
  run the full correctness suite before performance because graph plus partial offload has a
  documented output-corruption risk.
- Context tests use long-context recall and peak allocation; they are not mixed with a speed
  promotion decision.

The existing absolute gates remain: full API contract, median decode at least 8 tok/s, no OOM,
no sustained swap and no unexpected service restart. A tuning candidate should also improve its
declared user-facing metric by approximately 10% to exceed normal variance. A cache candidate may
not materially regress cold TTFT; an expert/graph candidate must retain at least about 2 GiB of
measured peak headroom per GPU and preserve 128K startup/correctness.

Source: [ik_llama benchmark and placement guidance](https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/parameters.md),
[Google SRE reliability testing](https://sre.google/sre-book/testing-reliability/).

### Deployment and Operations Practices

The existing candidate task already has the right structural primitive: stop the active GGUF
owner, run the candidate inside an Ansible `block`, and restore the primary in `always` unless an
explicit keep-running flag is set. Preserve this behavior for normal qualification. For live
troubleshooting, keeping a candidate active must remain an explicit experiment control and the
evidence manifest must state that automatic restoration was disabled.

Operational sequencing for every run is:

1. render and validate locally;
2. take a read-only baseline snapshot;
3. record the intended single variable and control evidence ID;
4. stop the active owner and start the candidate;
5. wait for true ready state, not only an open port;
6. run correctness before performance;
7. collect cold/warm samples and a post-run resource snapshot;
8. preserve logs/evidence, then restore or explicitly keep the candidate;
9. verify the stable proxy and Open WebUI path after lifecycle completion.

Collect normal-run telemetry with API timings, `nvidia-smi`, container/cgroup memory, host
available/swap, process RSS/PSS and NUMA counters. Linux cgroup v2 exposes current and peak memory
accounting suitable for a container/service boundary. Use Nsight Systems only for a short,
isolated diagnostic when ordinary evidence cannot distinguish H2D copies, GPU kernels or idle
gaps; profiling adds overhead and is not part of promotion benchmarks.

If Prometheus metrics are later enabled, keep the endpoint loopback-only and labels low-cardinality;
experiment IDs belong in evidence files rather than unbounded metric labels.

Sources: [Linux cgroup v2 memory accounting](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html),
[NVIDIA Nsight Systems CUDA tracing](https://docs.nvidia.com/nsight-systems/UserGuide/index.html),
[Prometheus instrumentation practices](https://prometheus.io/docs/practices/instrumentation/).

### Team Organization and Skills

This homelab workflow needs one operator but four explicit competencies:

- Ansible/Jinja and variable-precedence knowledge to keep inventory authoritative;
- ik_llama/GGUF knowledge to interpret tensor names, dry-run allocation and MoE placement;
- inference benchmarking knowledge to distinguish cold PP, warm cache reuse, TTFT and TG;
- Linux/CUDA/NUMA diagnostics to interpret cgroup, pinned memory, P2P and topology evidence.

No additional team or orchestration platform is required. The important process control is to
record the hypothesis and control run before changing a value, and to have a second-pass review
of graph/tensor-override expressions because a syntactically valid regex can move the wrong
tensors.

### Cost Optimization and Resource Management

Use existing capacity before purchasing or migrating:

- host RAM funds prompt-state caching, not faster cold matrix multiplication;
- GPU VRAM funds active tensor residency, KV or workspace, with expert placement prioritized;
- PCIe/NUMA changes are justified only after a runtime candidate demonstrates sensitivity;
- longer context consumes capacity and may reduce responsiveness, so offer it as a separate
  profile only when a workload requires it;
- a second runtime duplicates operational and storage cost, so defer it until the pinned ik path
  reaches a measured ceiling.

The first two candidates require no new model download, image or hardware. Their dominant cost is
model restart and benchmark time. Graph/P2P and physical PCIe work carry a higher maintenance cost
and follow the low-risk memory experiments.

### Risk Assessment and Mitigation

| Risk | Trigger | Mitigation / stop condition |
| --- | --- | --- |
| Cache drives host pressure | swap, cgroup OOM/high events, loss of available restart headroom | Stop at prior cache size; never use unlimited `-1` |
| Expert placement causes startup OOM | dry-run or real peak exceeds a GPU | Move only one layer, retain measured margin, preserve control profile |
| Expert regex moves paired tensors incorrectly | allocation log differs from manifest or output corrupts | Prefer `--n-cpu-moe`; review exact GGUF tensor names before override rules |
| Graph split produces gibberish | any correctness/SSE/tool failure | Reject performance result; optionally diagnose CUDA graphs in isolation |
| Cache benchmark reports false hits | only JSON hash matches, no server/cache evidence | Use token counts, cache logs/fields and A/B/A TTFT |
| Profiling distorts latency | Nsight-enabled run differs from normal run | Diagnostic runs never enter promotion statistics |
| Evidence is overwritten | fixed output filenames | Required experiment ID and immutable per-run directory |
| Candidate remains active unintentionally | keep-running flag set | Manifest flag plus explicit post-run owner verification |
| LAN API resource exhaustion | oversized/concurrent requests | CIDR boundary, context/output caps; add auth/rate control before wider exposure |

## Technical Research Recommendations

### Measured convergence addendum — 2026-08-15

The controlled host-cache sweep did not produce a promotable replacement for the 8 GiB control.
At 16 GiB, return-to-A TTFT regressed from 19.93 s to 22.19 s. At 32 GiB it improved to
18.36 s (7.9%), below the declared approximately 10% line, while 8K TG decreased from 7.56 to
7.37 tok/s. The original 32 GiB manifest incorrectly named the rejected 16 GiB run as its
control, so it remains exploratory evidence even though the corrected automation now requires
both 16 and 32 GiB to compare against the same accepted 8 GiB control.

Moving one expert layer to the GPU with `--n-cpu-moe 42` retained correctness and headroom, but
improved 1K/8K TG by only 3.4%/2.4%. The approved stop-on-first-immaterial-step rule therefore
prevented a 41/40 sweep. This result means “not promoted under the current contract,” not “further
layers cannot accumulate a benefit.” A future expansion may test 41 and 40 as separate
single-variable candidates, with the observed GPU0-heavy allocation and 2 GiB/GPU peak margin
still enforced.

Graph split was not executed. The captured pair was PHB, both directional P2P capability checks
returned `NS`, no NVLink was present, and the CUDA bandwidth sample was unavailable. Lack of
NVLink alone is not a blocker; the missing peer-access/bandwidth proof is. The result is an
ineligible experiment, not evidence that graph would necessarily fail.

Final run `final-baseline-20260815-r6` verified the exact live image, argv, mounts, runtime/model
hashes, pre/post 19-case contracts, and a 126,992-token marker recall. The one-hour run completed
12/12 exact-OK completions and 361 complete resource samples with no swap, OOM or restart. It did
not pass the strict availability gate: one `/health` probe timed out for 30 s during the first
cold completion, and the maximum health gap was 60.0001 s.

Pinned-runtime logs make the cause concrete. When leaving the 127K conversation, the server
synchronously saved a 127,048-token host prompt-cache state of 34,116.6 MiB; the save took
72.15 s and queued health/control requests. The pinned implementation enforces its MiB limit by
evicting old states but deliberately retains at least one state, so an individual state can exceed
`--cache-ram 8192`. Raising the limit to 32 GiB cannot remove the copy: the observed state is still
larger and serialization is unchanged. The next corrective experiment must therefore review a
policy that skips oversized states or a pinned-runtime change that makes saving non-blocking.
Either route is outside the approved variable set and must be explicitly authorized; weakening
the soak timeout is not an acceptable substitute.

There is also a smaller pinned-runtime configuration candidate: `--ctx-checkpoints N`. The live
default was 32 and the 127K state contained 32 checkpoints of about 872.6 MiB each. Reducing the
count should reduce save size/time without changing the model or binary, but it increases the
number of tokens that must be recomputed when restoring a long conversation and may affect DSV4
private per-position state rollback. Treat checkpoint count as a new primary variable, first test
8 and then 4 only if needed, and require 128K recall, transition-time health, return-to-project
latency, full API correctness and resource evidence before any promotion.

### Implementation Roadmap

**Stage A — repository support, no service change**

- Add strict cache, MoE placement, split-mode and experiment-ID variables.
- Render approved profiles and invalid-case tests.
- Add per-run evidence manifests and the coding-cache runner.
- Extend benchmark output with medians for TTFT/PP/E2E/TG and optional server cache fields.

**Stage B — host-cache experiment**

- Re-establish an 8 GiB A/B/A control.
- Test 16 GiB; test 32 GiB only if swap/pressure remains absent.
- Promote the smallest cache size that retains project A and materially improves return-to-A
  TTFT. Do not expect cold first-task speedup.

**Stage C — GPU expert-residency experiment**

- Save pinned `--dry-run` and actual baseline allocation.
- Replace `--cpu-moe` with `--n-cpu-moe 42`, moving only the last MoE layer first.
- If correct and within margin, proceed one layer at a time; stop at the first OOM, correctness
  failure or sub-material gain.
- Use `--override-tensor` only when whole-layer granularity wastes otherwise usable VRAM.

**Stage D — multi-GPU graph experiment**

- Capture CUDA P2P bandwidth/latency and topology.
- Test graph against the winning layer-placement control, without changing cache/context.
- Require full correctness and at least roughly 10% user-facing improvement before promotion.

**Stage E — separate capacity and alternate-runtime track**

- Test 256K/512K workspace/KV questions only after speed tuning converges.
- Revisit SGLang-KT/MTP only if ik remains below the service objective after the preceding stages.

### Technology Stack Recommendations

- Keep `ik_llama.cpp@981e5ea0`, the current GGUF and compatibility proxy pinned during tuning.
- Use Ansible inventory/profile validation as the only promoted configuration source.
- Keep the existing Python standard-library API runners and versioned fixtures.
- Add cgroup/process/GPU sampling to evidence; do not require a new monitoring stack.
- Optionally build `llama-sweep-bench` from the identical pin after API-level bottlenecks are
  characterized, never from current upstream master.
- Keep backend loopback-only and the stable API CIDR-controlled.

### Skill Development Requirements

- Learn the pinned fork's `--dry-run`, `--n-cpu-moe`, `--override-tensor`, cache and graph logs.
- Practice interpreting PP versus TG and cold versus warm TTFT without mixing them.
- Learn GPU topology/P2P testing and basic NUMA/cgroup resource accounting.
- Maintain Ansible render tests for cross-variable invariants and failure-safe lifecycle blocks.

### Success Metrics and KPIs

| Objective | KPI | Required evidence |
| --- | --- | --- |
| Faster repeated coding work | Return-to-project warm TTFT and cache eviction rate | A/B/A sequence, 3+ samples, cache logs/fields |
| Faster cold prompt processing | 1K/8K PP and TTFT median | fixed cold corpus, same output/settings |
| Preserve interactive generation | median TG ≥ 8 tok/s; target ≥ 10 tok/s | repeated API samples |
| Use VRAM safely | peak free VRAM approximately ≥ 2 GiB per GPU | sampled peak, not idle snapshot |
| Preserve capacity | 128K model metadata, startup and recall pass | model API plus context fixture |
| Preserve correctness | complete sync/SSE/reasoning/tool/malformed contract | versioned contract JSON |
| Preserve host stability | no OOM, sustained swap or unexpected restart | cgroup/host/service evidence |
| Ensure attribution | exactly one primary variable differs from control | rendered-command diff and manifest |
| Justify promotion | approximately ≥ 10% declared user-facing benefit | control/candidate comparison and verdict |

## Research Synthesis

### 1. Technical Significance and Achieved Objectives

DeepSeek V4 Flash is explicitly designed for long-context inference, but running such a large MoE
model on consumer GPUs shifts the design problem from simple GPU fit to memory hierarchy and data
movement. The official model card describes million-token intelligence and recommends at least
384K context for Think Max. On this host, however, the model's experts largely execute from CPU
memory, so coding latency depends on CPU/NUMA bandwidth, pinned transfers, GPU-resident tensors,
cache reuse and cross-GPU behavior as much as the model's theoretical context window.

Source: [DeepSeek V4 Flash official model card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash).

The research achieved its original objectives:

- established a live, version-pinned allocation and performance baseline;
- separated host-cache, GPU-residency, workspace and context capacity decisions;
- corrected upstream-versus-fork flag and default-value errors;
- proved DeepSeek4 graph source support without claiming unmeasured speed;
- designed an incremental implementation and promotion framework;
- identified explicit evidence gaps before physical PCIe or runtime migration work.

### 2. Current Technical Landscape and Architecture

| Layer | Current verified state | Architectural implication |
| --- | --- | --- |
| Model | DeepSeek4 GGUF, about 145.6 GiB, trained context reported as 1,048,576 | Cannot reside wholly in 48 GiB VRAM |
| Runtime | `ik_llama.cpp` version 4834, commit `981e5ea0...` | Pinned fork interface is authoritative |
| CPU/GPU placement | `--cpu-moe`, `--n-gpu-layers 100` | Sparse experts dominate CPU/RAM path; non-expert work is GPU-offloaded |
| Multi-GPU | two RTX 3090, layer split | Compatible low-communication control; not tensor parallelism |
| Context | configured 131,072; 256K tested slower; 512K failed peak allocation | 128K is interactive baseline; larger windows are capacity experiments |
| API | compatibility service `8081` -> loopback backend `8082` | Client stability and runtime diagnostics stay separable |
| Lifecycle | systemd orchestration plus Docker Compose candidate | One active large-model owner prevents resource overcommit |

The compatibility adapter is an anti-corruption boundary, not a performance layer. The memory
architecture has four distinct pools: host model/expert pages, host prompt-state cache, GPU model
and KV residency, and GPU/host compute workspace. A safe design never infers that capacity in one
pool can satisfy a peak allocation in another.

Sources: [pinned ik parameters](https://github.com/ikawrakow/ik_llama.cpp/blob/981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8/docs/parameters.md),
[pinned DeepSeek4 split declarations](https://github.com/ikawrakow/ik_llama.cpp/blob/981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8/src/llama-model.h).

### 3. Implementation Approaches and Best Practices

The recommended implementation pattern is a sequential configuration canary. Each candidate is a
named Ansible profile with one changed primary variable, exact release pins, an immutable evidence
directory and an explicit control run. Static render/policy validation precedes any restart;
correctness precedes performance; resource and lifecycle evidence accompany the result.

The existing role already provides a suitable failure-safe block: it stops the active owner,
starts the candidate and restores the primary in `always` unless troubleshooting explicitly keeps
the candidate running. Implementation should parameterize that path rather than create a second
lifecycle owner.

Google SRE recommends small reproducible changes, automated tests and a control-versus-canary
evaluation, while cautioning that concurrent canaries contaminate signals. Ansible check mode is
useful for previewing supported tasks but remains a simulation; GPU allocation and runtime
correctness require live validation.

Sources: [Google SRE canarying](https://sre.google/workbook/canarying-releases/),
[Ansible check and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html).

### 4. Technology Stack Evolution and Current Trends

The near-term stack remains the pinned ik fork because it already provides DeepSeek MLA/FlashMLA,
hybrid MoE placement, host prompt caching, tensor overrides and a DeepSeek4 graph path. Current
upstream llama.cpp is valuable comparative documentation but is not a compatible flag/default
contract.

KTransformers/SGLang-KT represents the main alternative architecture. Its official V4 guide uses
heterogeneous expert scheduling and newer sparse-attention/MXFP4 components, but documents a
specific CUDA/FlashInfer/Transformers dependency set; open RTX 3090/AVX2 evidence remains mixed.
Migration would change the runtime, artifact layout, API/parser and operational surface at once,
so it follows rather than precedes the smaller ik experiments.

Sources: [ik_llama project](https://github.com/ikawrakow/ik_llama.cpp),
[KTransformers V4 guide](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/DeepSeek-V4-Flash.md),
[KTransformers RTX 3090 issue](https://github.com/kvcache-ai/ktransformers/issues/1999).

### 5. Integration and Interoperability Patterns

The stable integration contract is OpenAI-style chat completion with synchronous JSON and SSE,
including reasoning separation and native tools. Direct backend tests answer runtime questions;
proxy tests answer client-visible correctness and streaming questions. The proxy should be
removed only when the backend natively passes its compatibility regression, not merely because
the adapter appears architecturally small.

Open WebUI recommends Native function calling and treats Legacy as the prompt-injection fallback.
Native mode does not make tool definitions free: the effective server template and token count
must be measured. Model-attached tools also remain subject to each user's access. A lean coding
profile should therefore attach only the tools actually required, without disabling the native
tool mechanism itself.

Source: [Open WebUI tools and Native mode](https://docs.openwebui.com/features/extensibility/plugin/tools/).

For coding agents, reuse is a tokenized-prefix/state property rather than a JSON-byte property.
The pinned ik mechanism is host-RAM `cache-ram`, not upstream `cache-reuse`. The correct workload
is project A -> B -> A with cache admissions and evictions, not repeated synthetic JSON alone.

### 6. Performance and Scalability Analysis

#### Verified Performance Baseline

| Metric | Current evidence | Interpretation |
| --- | ---: | --- |
| API contract | 19/19 pass | Correctness baseline established |
| 1K cold TTFT | about 22 seconds in the controlled sequence | Noticeable but workable first prompt |
| 8K cold TTFT | about 85 seconds in the best controlled sequence | Primary coding-agent limitation |
| Single-request TG | approximately 8 tok/s | Meets minimum usability, little margin |
| Context | 128K active; 256K correct but slower; 512K OOM | Native model context is not local service capacity |
| Host available RAM | 181,079 MiB at 2026-08-15 snapshot | Supports bounded cache experiments |
| Idle GPU free VRAM | 11,816 / 11,656 MiB | Candidate expert capacity, not guaranteed peak headroom |
| Host prompt cache | 8 GiB, observed 0.87-5.62 GiB entry evictions | Direct evidence for 16/32 GiB sweep |

These values come from the guest evidence directory, learning note and 2026-08-15 read-only live
sampling. They are not claims about other hardware or runtime revisions. Idle VRAM is reported for
orientation; promotion uses sampled peak headroom.

#### Scaling Strategy

The service scales vertically along independent axes:

- host cache capacity improves warm revisits;
- GPU expert residency may improve cold PP and TG;
- graph split may redistribute computation but increases interconnect sensitivity;
- context capacity increases supported input but often increases latency and workspace demand;
- `parallel > 1` improves aggregate concurrency only when real simultaneous demand exists.

The existing current-fork `llama-sweep-bench` documentation can guide a future same-pin build, but
the deployed artifact currently includes only `llama-server`; API-level measurements remain the
promotion evidence. Nsight Systems is reserved for short diagnostics because tracing can add
overhead.

Sources: [ik_llama benchmark guidance](https://github.com/ikawrakow/ik_llama.cpp/blob/main/docs/parameters.md),
[NVIDIA Nsight Systems](https://docs.nvidia.com/nsight-systems/UserGuide/index.html).

### 7. Security and Governance

The backend remains loopback-only; the stable endpoint is restricted to trusted LAN CIDRs;
metrics/debug endpoints remain private. Docker documents that published ports are otherwise
externally reachable, and OWASP identifies unrestricted resource consumption as a material API
risk. A large-context request can monopolize CPU/GPU resources even without a software defect, so
context/output limits and concurrency controls are security controls as well as performance knobs.

Raw prompts, source code, authorization headers and tool secrets do not belong in benchmark
evidence. Store token counts, hashes, timings and verdicts. Open WebUI Workspace Tool management
must remain administrator-only because imported tools execute server-side Python.

Sources: [Docker port publishing](https://docs.docker.com/engine/network/port-publishing/),
[OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/),
[Open WebUI tool security](https://docs.openwebui.com/features/extensibility/plugin/tools/).

### 8. Strategic Technical Recommendations

The decision framework is value per unit of change:

1. **Use host RAM for proven cache pressure.** Test 16 GiB, then 32 GiB; select the smallest size
   that retains project A across a B conversation and materially reduces warm return TTFT.
2. **Use VRAM for active expert computation.** Start with `--n-cpu-moe 42`; advance one layer per
   correct, stable and materially faster run.
3. **Treat graph as a compute/interconnect experiment.** Measure P2P first, keep the winning tensor
   placement fixed, and require full output correctness before comparing speed.
4. **Keep capacity separate from speed.** Add 256K/384K only as an explicit long-context profile
   after peak allocation is understood.
5. **Defer runtime migration.** Revisit KTransformers only after the pinned ik ceiling is measured.

No hardware purchase is justified before these low-cost experiments. PCIe slot or ESXi P2P work
is justified only if graph/expert evidence shows a transfer bottleneck that topology can address.

### 9. Implementation Roadmap and Risk Assessment

| Stage | Change | Required gate | Principal risk |
| --- | --- | --- | --- |
| A | Profile variables, render tests, evidence IDs | local syntax/render/policy pass | configuration ambiguity |
| B | Cache 16/32 GiB | warm A/B/A TTFT gain, no swap/pressure | host restart headroom |
| C | `n-cpu-moe 42`, then one layer per run | full contract, ≥10% target benefit, ~2 GiB/GPU peak margin | OOM or wrong tensor placement |
| D | Layer versus graph | P2P evidence, full contract before benchmark | corruption or PCIe regression |
| E | 256K/384K capacity | recall, peak allocation, usable TTFT | workspace/KV OOM |
| F | Alternate runtime | isolated release manifest and same corpus | dependency/API/quality drift |

Stop promotion immediately on correctness corruption, OOM, sustained swap or unstable service
ownership. A mere metric regression during a non-production experiment should preserve diagnostic
evidence before restoring the control. The known-good rendered profile remains available at every
stage.

### 10. Future Technical Outlook and Innovation Opportunities

**Near term:** host-cache sizing and one-layer expert placement are likely to deliver the clearest
signal. Add a same-pin dry-run manifest and coding-project cache runner before testing.

**After near-term convergence:** evaluate graph split with measured P2P; investigate exact tensor
overrides only if whole-layer placement leaves unusable VRAM fragments; optionally build the
same-pinned sweep benchmark for diagnosis.

**Capacity outlook:** the model's million-token training and 384K Think Max recommendation justify
a future 256K/384K profile, but not at the expense of the 128K interactive profile. Workspace
controls and peak allocation must be diagnosed before another 512K attempt.

**Runtime outlook:** KTransformers/SGLang-KT may become more attractive as Ampere/AVX2 support and
dependency packaging mature. It remains a separate release candidate with its own model artifact,
API parser, operational owner and acceptance evidence.

### 11. Research Methodology and Source Verification

#### Source Classes

1. **Highest authority for current behavior:** pinned ik commit/source, pinned model metadata,
   rendered inventory and live binary output.
2. **Primary external sources:** DeepSeek model card, ik/KTransformers repositories, NVIDIA,
   Broadcom, Linux kernel, Docker, Ansible, Open WebUI, OWASP and Google SRE documentation.
3. **Supporting evidence:** upstream llama.cpp documentation, project issues/discussions and local
   historical notes. These identify candidates or risks but do not establish current behavior.

#### Web Research Queries

- DeepSeek V4 Flash official context, model card and deployment guidance;
- pinned/current ik_llama cache, MoE placement, graph split, dry-run and benchmark behavior;
- upstream llama.cpp multi-GPU, KV, batch and cache differences;
- KTransformers DeepSeek V4, Ampere and AVX2 deployment evidence;
- NVIDIA pinned-memory, CUDA P2P and profiling guidance;
- Broadcom VMDirectPath peer DMA requirements;
- Open WebUI Native tools and security boundaries;
- Docker port publishing, OWASP API resource risk, Linux cgroup memory accounting;
- Google SRE canarying and Ansible validation practices.

#### Confidence Assessment

| Finding | Confidence | Reason |
| --- | --- | --- |
| Current pins, flags, allocations and API state | High | repository plus live binary/log/API evidence |
| 16/32 GiB cache improves return-to-project TTFT | High that it did not meet promotion | fixed A/B/A measured 16 GiB slower and 32 GiB only 7.9% faster than 8 GiB |
| One-layer GPU expert placement improves PP/TG materially | High that the first step did not | `n-cpu-moe=42` gained only about 2.4-3.4% and failed the 8K TG gate |
| DeepSeek4 graph can start and outperform layer here | Low | source path exists, but measured PHB/P2P `NS` and absent CUDA sample made it ineligible |
| 384K is useful on this host | Low-medium | official mode recommendation; local 256K slowdown and 512K failure |
| KTransformers will outperform current ik | Low | different dependencies and unresolved host-specific evidence |

#### Limitations

- No CUDA `p2pBandwidthLatencyTest` result is yet available; `nvidia-smi` reports P2P `NS`.
- 16/32 GiB cache and one-layer GPU expert candidates were executed and rejected; graph was
  correctly skipped because its topology gate did not pass.
- Free-VRAM idle samples now have candidate peak traces for cache and `n-cpu-moe=42`; they remain
  configuration-specific and do not prove a different split mode safe.
- Historical performance runs do not all share one exact configuration and corpus.
- Model-native context and official hardware recipes do not guarantee GGUF quality or latency.
- OpenCode's rendered token prefix/cache reuse has not yet been captured end to end.

### 12. Technical Appendices and Reference Materials

#### Local Evidence and Code

- `/var/lib/deepseek-v4-ik/evidence/` on the guest: contract and benchmark artifacts.
- `ansible/inventory/host_vars/llm-server.yml`: current desired performance state.
- `ansible/roles/deepseek-v4-ik/`: pinned runtime, Compose, lifecycle and compatibility boundary.
- `ansible/roles/deepseek-v4/files/`: versioned contract, benchmark and context runners.
- `docs/learningnotes/2026-08-14-deepseek-v4-dual-gpu-deployment.md`: deployment and benchmark chronology.

#### Primary Technical References

- [DeepSeek V4 Flash model card](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash)
- [Pinned ik_llama parameter documentation](https://github.com/ikawrakow/ik_llama.cpp/blob/981e5ea0d7579b4803c86afbb09a7cd7d7bf3bb8/docs/parameters.md)
- [ik_llama project and graph/offload warnings](https://github.com/ikawrakow/ik_llama.cpp)
- [KTransformers DeepSeek V4 guide](https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/DeepSeek-V4-Flash.md)
- [NVIDIA CUDA best practices](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html)
- [Broadcom VMDirectPath requirements](https://knowledge.broadcom.com/external/article/312208/vsphere-vmdirectpath-io-and-dynamic-dire.html)
- [Open WebUI tool documentation](https://docs.openwebui.com/features/extensibility/plugin/tools/)
- [Google SRE canarying](https://sre.google/workbook/canarying-releases/)

## Technical Research Conclusion

The current DeepSeek V4 service is not under-provisioned in a single, simple sense. It has spare
host RAM, spare steady-state VRAM and a correct 128K API, yet cold coding prompts remain slow
because the workload crosses CPU expert compute, memory bandwidth, GPU attention/KV and client
prefix behavior. The correct response is targeted allocation, not indiscriminate context or
concurrency growth.

The research therefore recommends three evidence-gated experiments in order: enlarge host prompt
cache, migrate one MoE layer at a time into VRAM, and compare graph only after P2P measurement.
This sequence is inexpensive, attributable and reversible. It also establishes a genuine local
performance ceiling before hardware changes or a KTransformers migration are considered.

**Technical Research Completion Date:** 2026-08-15  
**Research Period:** 2026-08-14 through 2026-08-15  
**Source Verification:** pinned source, live evidence and current primary documentation  
**Overall Confidence:** high for the baseline and experiment ordering; conditional for unexecuted gains
