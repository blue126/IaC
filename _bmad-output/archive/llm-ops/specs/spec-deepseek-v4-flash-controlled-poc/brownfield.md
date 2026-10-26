# Brownfield context

## Current infrastructure

| Area | Current fact | Consequence |
|---|---|---|
| VM | `llm-server`：36 vCPU、348160 MB（340 GiB）内存、limit/reservation 同值 | DirectPath 所需全额预留已具备，但 VM 开机时基本独占 384 GB host |
| Storage | 600 GB thin system disk，datastore 为 `Intel800GSSD` | 标称容量不能证明 guest 与 datastore 有足够工作空间 |
| Firmware | EFI、64-bit MMIO、128 GB aperture、memory hot-add disabled | 双 GPU passthrough 基线可复用 |
| GPU ownership | Terraform 中 `pci_device_ids = []`；实际 DirectPath 由 ESXi UI 手工管理 | Phase 0 不接管 PCI device 声明，Phase 1 只采集事实 |
| Guest base | Ubuntu、Docker、CUDA Toolkit 12.8 声明、Open WebUI | 可复用，但 live driver/Toolkit 状态仍未知 |

主要声明位于：

- `terraform/esxi/llm-server.tf`
- `terraform/esxi/variables.tf`
- `ansible/inventory/host_vars/llm-server.yml`

## Current legacy service

现有 `llm-server` role 是 GGUF + `ik_llama.cpp` 专用栈：

- 引擎固定在 `f7923739`，这是 MiniMax M2.5 的已知可用版本，但早于 DeepSeek V4 支持。
- `tasks/main.yml` 要求非空 `llm_server_models` 和其中一个 `llm_server_boot_model`。
- `model.yml` 会下载所有包含 `download_repo` 的声明模型。
- `nvidia.yml` 可自动安装 driver、flush reboot handler 并安装 CUDA Toolkit；新 PoC 不能把这类变更隐藏在普通 config 部署中。
- `service.yml` 会停止非 boot instances，并启用和启动 boot model。
- handler 在配置变化后会停止所有声明实例，再启动 `llm_server_boot_model`。
- `switch-model.sh` 只认识 `llama-server@*`，等待时间固定为 120 秒。
- Open WebUI Compose 把单一 URL 固定为 host port 8080，并使用无认证占位 key。
- Open WebUI 已启用持久化配置语义，数据库中的连接可覆盖后续环境变量；新实现必须把环境变量 seed 与已初始化数据库区分开。
- Verify play 的基本 chat 检查不能证明 reasoning、tools、SSE 或结构正确性。
- 旧 role 不会清理已从 inventory 移除的 `.env`、`.ot` 或模型文件，单纯删声明会留下可切换的 stale 配置。

因此，KTransformers safetensors runtime 不能被塞入现有 per-GGUF 字典，也不能通过升级当前 checkout 实现。

## Current model desired state

`ansible/inventory/host_vars/llm-server.yml` 当前声明：

| Key | Role in current state | Target state |
|---|---|---|
| `m25` | MiniMax，自动下载 | 从未来生产声明移除；本轮不删除 guest 文件 |
| `qwen3-vl-32b` | 当前 boot model，自动下载 | 从未来生产声明和 boot 选择移除；本轮不删除 guest 文件 |
| `glm-4.7` | legacy model，自动下载 | 从未来生产声明移除；本轮不删除 guest 文件 |

Phase 0 必须确保本地目标状态不再触发 MiniMax、Qwen 或 GLM 下载或启动，并为后续精确移除其 stale `.env/.ot` 配置提供显式、受控任务。由于旧 role 要求非空 model 字典和 boot model，全部 legacy 声明移除后，它不能继续作为生产部署入口；DeepSeek 专用路径必须独立拥有服务生命周期。模型权重删除仍必须独立审批。

## Phase 0 change surface

下游实现至少需要评估以下逻辑单元；可在保持合同的前提下调整最终文件拆分：

| Change | Purpose |
|---|---|
| 新增 `ansible/roles/deepseek-v4/` | 隔离 KTransformers runtime、配置、manifest、fixture 与 lifecycle |
| 新增 `ansible/playbooks/deploy-deepseek-v4.yml` | 提供 Deploy + Verify 双 play 和窄标签入口 |
| 更新 `ansible/inventory/host_vars/llm-server.yml` | 移除 MiniMax、Qwen 和 GLM 的未来生产 desired state |
| 退役 legacy lifecycle 入口 | 防止旧 handler、boot unit 或 switch script 重新启动任一 legacy 模型 |
| 调整 Open WebUI bootstrap | 未初始化数据库时 seed DeepSeek connection；已有数据库时仅备份和验证 |
| 复用或扩展 `llm-benchmark` | 输出 DeepSeek 固定 corpus 与结构化指标，不复制无关基准逻辑 |
| 增补 templates/files | Compose、systemd、manifest、contract fixtures、benchmark harness |

Phase 0 不应修改 ESXi passthrough、VM 资源或 live guest。若实现发现现有通用 role 必须重构，应只提取 DeepSeek 与旧栈真正共享且可独立验证的基础能力，不进行全局清理。

## Repository conventions

下游必须同时读取 `../../../docs/designs/ansible-role-architecture.md`，并遵守仓库 `AGENTS.md`：

- role/playbook/文件名使用 kebab-case，变量使用 service-prefixed snake_case；
- 任务名用英文动词开头；
- Playbook 包含 Deploy 与 `tags: [verify]` 的 Verify play；
- 凭据使用 Vault indirection；
- 只参数化现实中会变化的值；
- 配置变更先本地验证，再用相关窄标签部署和验证；
- 未经用户明确授权不得 commit。

## Historical documentation warning

`docs/deployment/llm-server-deployment.md` 记录的是 MiniMax 路线及其历史实测。它可用于理解旧栈，但其中旧资源值、模板形态和操作命令不是 DeepSeek 的当前部署合同；新实现不得把历史参考值当成已验证的 DeepSeek 事实。
