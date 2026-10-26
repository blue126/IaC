# Implementation phases and approval gates

## Authorization envelope

当前只授权 **Phase 0** 的本地仓库编辑与本地验证。生成本规格不授权执行 Phase 1–5。每个后续 gate 都需要基于上一阶段证据的明确用户批准；一次批准不自动传递到下一 gate。

| Gate | Requires explicit approval for |
|---|---|
| G1 | 启动现有 VM，并执行只读 guest/ESXi preflight |
| G2a | 修改 guest/storage 状态或增加/扩展 VMDK |
| G2b | 删除已解析的 MiniMax/Qwen/GLM 精确目标 |
| G2c | 下载模型、拉取镜像或执行其他大型网络传输 |
| G3 | 停止 legacy inference，并启动隔离 TP1 PoC |
| G5 | 接管生产连接、boot backend 或端口 |

## Phase 0 — Offline IaC preparation

**Entry:** 本规格已确认。

**Authorized work:**

- 新增聚焦的 DeepSeek role/playbook、Compose、systemd 编排和显式互斥定义。
- 让新 role 对现有 NVIDIA driver/Toolkit 做 fail-fast assertion，不在普通 PoC config 路径中安装、升级或重启。
- 定义模型/镜像 release manifest 变量与未解析值的 fail-fast validation。
- 定义可判定的 Open WebUI 首次初始化条件和一次性 connection seed；已有数据库路径只备份和验证，不覆盖连接。
- 准备 preflight、API contract、correctness corpus、benchmark 与冷恢复 fixture。
- 从未来生产 desired state 移除 MiniMax、Qwen 和 GLM，不删除任何远端文件。
- 为 deploy、config、preflight、artifact、verify、benchmark 等现实操作边界设计窄标签。
- 在本地运行 YAML/Ansible/Compose 可用的静态、语法和渲染验证。

**Forbidden:** VM/ESXi 访问、远端 facts、check mode 对目标主机、包安装、模型/镜像下载、服务启停、文件删除、生产配置更改。

**Exit evidence:**

- `ansible-playbook playbooks/deploy-deepseek-v4.yml --syntax-check` 通过。
- Compose 配置可以离线渲染/校验；如本地缺少 Compose 工具，明确记录未执行项，不伪造通过。
- 变更审查证明默认路径不会下载或启动任何 legacy 模型，旧 role/handler 不能重新激活它们。
- fixture 与 benchmark 具备稳定输入、结构化输出和阈值定义。
- 配置审查证明 Open WebUI seed 只作用于未初始化数据库，重复部署不会覆盖持久化 connection。
- 没有发生远端或外部状态变化。

## Phase 1 — Powered-on read-only discovery

**Entry:** G1 批准。

**Actions:**

- 启动现有 VM；不改 guest 包、服务、文件或 ESXi 配置。
- 采集 guest driver、CUDA compatibility、Docker、NVIDIA Container Toolkit 和 CUDA container smoke evidence。
- 采集两张 GPU 的 identity、PCI address、`nvidia-smi topo -m`、P2P/NVLink 与连接形态。
- 采集 AVX2/FMA、guest vCPU/vNUMA、内存、swap 和 ESXi `N%L/%RDY/%CSTP` 基线。
- 采集 guest filesystem free、model artifact size、VMDK allocation 与 datastore free。

**Exit:** 输出结构化 preflight 报告；容量足够时可以请求下一 gate，容量不足时停止并通知用户安排扩盘，不自动清理或扩容。

## Phase 2 — Storage and artifact preparation

**Entry:** G2a/G2b/G2c 按实际动作分别批准。

**Order:**

1. 备份 Open WebUI 非可重建状态并验证备份存在。
2. 记录 Open WebUI 状态恢复、IaC 重建和固定 artifact 重部署路径。
3. 确认本地 desired state 已不声明 MiniMax、Qwen 或 GLM。
4. 解析拟移除的 stale `.env/.ot` 与模型绝对目标、大小和归属；配置清理和权重删除分别执行各自获批范围。
5. 证明约 400 GB 实际可用模型存储余量，或完成获批的独立模型盘方案。
6. 先对模型下载运行 dry-run，解析总量和目标路径，再固定官方模型完整 revision 与 KTransformers image digest。
7. 下载到明确路径，验证完整 snapshot、必要 shard/index、revision 与 manifest。

**Stop:** 任一备份、恢复、空间或完整性证据失败时，不激活服务。

## Phase 3 — Isolated TP1 PoC

**Entry:** artifact 完整且 G3 批准。

**Actions:**

- 停止所有 `llama-server@*` 与其他 legacy inference owners。
- 启动 TP1、GPU 0、16K、并发 1、MTP off 的固定候选。
- 初始端点仅 loopback；先运行 native generation，再运行 OpenAI API，最后接入临时 Open WebUI connection。
- 使用最长 15–20 分钟的初始 readiness budget，并以真实 generation probe 判定 ready。

**Exit:** 容量、基础正确性与 API 冒烟通过；否则安全停止 DeepSeek，并保留失败证据。

## Phase 4 — Qualification and experiments

**Entry:** TP1 基础正确性通过。

**Actions:**

- 执行 `acceptance-contract.md` 全部合同、性能、安全和恢复测试。
- 保存每轮完整 release manifest 与 benchmark evidence。
- 只有 TP1 成为黄金基线后，才依 architecture scaling order 做单变量实验。
- 若 KTransformers 正确但性能不足，按相同 corpus 顺序评估独立的当前 `ik_llama.cpp` Q4 CPU-MoE 路线。

**Exit:** 产生 Go、No-Go 或继续单变量实验的证据化决定。不得用无界调参替代 Stop 条件。

## Phase 5 — Production cutover

**Entry:** 所有生产资格门通过且 G5 批准；Open WebUI 数据库已经接管 connection 权威并完成备份。

**Actions:**

- 将完整兼容发布集固定为生产版本。
- 使 DeepSeek 成为唯一 boot backend，并让 Open WebUI 使用批准的私有 endpoint。
- 演练停止 DeepSeek、保持 Open WebUI 数据完整，并从固定 manifest 重部署已通过候选或执行冷重建。

**Stop/recovery:** 若正确性、性能、资源、安全或恢复任一门回归，立即停止晋级并进入已验证的安全停止或冷恢复路径。

## Terminal decisions

- **Go:** 全部合同通过，可在批准后生产切换。
- **Conditional:** 正确性通过但性能不足，允许一次有界的 `ik_llama.cpp` 比较路线。
- **Stop:** 两条路线均无法在正确输出和稳定前提下达到 8 tok/s，或 parser 需要大规模自研、硬件拓扑不稳定、存储成本失衡；结论记录为“可加载但不适合作为当前服务”。
