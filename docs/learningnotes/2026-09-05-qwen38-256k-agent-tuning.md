# Qwen3.8-27B：256K context 与 coding agent 参数

日期：2026-09-05

## 已部署的配置

目标为 `llm-workstation`（`192.168.1.191`）上的 `qwen38.service`。
模型仍为 `Qwen3.8-27B-UD-Q5_K_M.gguf`，保留原有模型、摘要和运行时源码 pin。
API 为 `http://192.168.1.191:8081/v1`，模型别名为 `qwen38`。

| 项目 | 配置 |
| --- | --- |
| context | `262144`，原生 256K，输入与输出合计 |
| 主模型 K/V cache | `q8_0` / `q8_0` |
| MTP | `draft-mtp`，草拟上限 `2`，draft K/V 保持默认 `f16` |
| GPU | 全层 GPU offload，`split-mode=layer`，`tensor-split=3,5`，`fit=off` |
| prefill batch / ubatch | `1024` / `256` |
| Flash Attention | 开启 |
| temperature / top_p / top_k | `1.0` / `0.95` / `20` |
| min_p / presence_penalty | `0.0` / `0.0` |
| reasoning effort | 默认 `medium`，请求可覆盖为 `low` 或 `xhigh` |
| 思考历史 | 显式 `--reasoning-preserve`；客户端仍需回传 `reasoning_content` |
| 并发 | 保留自动选择的 4 个 slot，共享 KV 容量 |
| TTS | 保持运行；当前生产 TTS 使用物理 GPU 0 |

采样默认值参考 [Qwen 官方模型说明](https://huggingface.co/Qwen/Qwen3.8-27B#best-practices)。
客户端传入的采样参数优先于服务默认值。客户端若单独登记模型窗口大小，也应设置为 `262144`。
`medium` 是日常交互的默认选择，不代表已证明它在所有 coding 任务上优于 `xhigh`。

## 关键取舍

### 为什么主模型 KV 改为 Q8？

KV cache 是模型复用前文计算结果的缓存，精度与模型权重量化是两个独立设置。
128K 的主模型 f16 KV 约占 8 GiB，256K 的 Q8 KV 约占 8.5 GiB。
但实际显存还包含 MTP 缓存、计算缓冲、CUDA Graph 和运行时开销，不能仅按 KV 增量判断。
本次保留 Q5 模型权重，降低主模型缓存占用，以便与约 10 GiB 的 TTS 共存。

### 为什么改为固定分卡？

部署前线上使用 `--fit-target 12288,3072`，并让 LLM 先于 TTS 启动。
llama.cpp 的 fitter 按当时的空闲显存再减去 margin 计算预算。
TTS 已运行时重启 LLM，会再次扣除为 TTS 预留的 margin，导致分卡或 offload 结果改变。

本次使用固定 `3,5` 分配比例和全层 GPU offload，使启动顺序不再改变 LLM 分配策略。
该比例依赖 TTS 位于物理 GPU 0；迁移 TTS、调整其并发或加载其他 GPU 服务后需要重新验证。
`tensor-split` 是层分配权重，不保证最终显存严格符合比例。

### 为什么限制 batch？

256K 下默认计算缓冲会明显增加显存。试运行的 `1,2` 分配让 GPU1 余量不足；
改为 `3,5` 后，再将 batch/ubatch 限制为 `1024/256`，为两卡恢复运行余量。
较小 ubatch 可能影响 prefill 吞吐，本次优先验证长窗口与 TTS 共存。

## 验证

- 使用现有 Docker Sandbox 中的 Ansible，运行独立 task 目录下的 `deploy-qwen38.yml`；未安装依赖。
- Ansible syntax-check、离线 ansible-lint 通过；部署后 context 和采样默认值断言通过。
- 最后重复执行 playbook：`ok=28 changed=0 failed=0`，未触发服务重启。
- 仓库文档验证通过：22 项 doc-claims 测试、20 项 doc-gardening 测试、11 个离线案例与 6 条声明检查。
- 工具调用往返通过：调用 `read_file`，再根据工具返回值回答 `TIMEOUT_SECONDS=37`。
- 实际输入 **260,633 tokens**，输出 71 tokens，四个标记 **4/4** 精确匹配；
  `finish_reason=stop`，服务日志 `truncated=0`。
- 本次冷 prefill 为 **408.17 秒 / 638.54 tok/s**，输出为 **31.83 tok/s**。
  输出只有 71 tokens，不能作为持续代码生成吞吐基准。
- 三路 TTS 在长请求期间全部返回有效 WAV，分别耗时 **1.83、1.89、1.79 秒**；
  TTS 容器 ID 与部署前相同，未重启。
- 15 秒间隔采样中，GPU0/GPU1 最低空闲为 **1,781 / 2,133 MiB**；
  未发现本次变更后的 NVIDIA Xid 或内核 OOM 记录。

长请求使用固定随机种子生成的合成记录，在约 10%、35%、65%、90% 深度插入四条独立标记。
请求关闭 thinking，以 JSON 返回标记；它检验容量、基本检索和共存稳定性，不是复杂编程能力基准。

### 输出格式限制

长请求虽然指定 `response_format.type=json_object`，返回仍包含 Markdown JSON 代码围栏。
最初直接调用 `json.loads` 的验证脚本因此失败。去除明确的围栏后，四个值全部精确匹配。
这条结果只计入检索正确性，**不计为严格 JSON 响应契约通过**；工具调用参数 JSON 的往返测试单独通过。

## 回退与配置来源

原始线上 Compose 和 systemd unit 已保存在目标主机：

```text
/opt/qwen38/backup-20260905-256k/docker-compose.yml
/opt/qwen38/backup-20260905-256k/qwen38.service
```

恢复旧的自动 fit 配置时，需要重新考虑当时 TTS 的显存占用和原启动顺序。
本次也把线上已存在的 Compose healthcheck 和 systemd `--wait` 同步进 Qwen role，避免重部署覆盖它们。

相关文件：`ansible/roles/qwen38/defaults/main.yml`、`templates/docker-compose.yml.j2`、
`templates/qwen38.service.j2`、`tasks/main.yml`、`tasks/verify.yml`。
