# LLM Server 使用说明

> **适用版本**：mainline llama.cpp pin `10bf611e`，Open WebUI，SearXNG `latest`
> **最后核验**：2026-08-18（实机）
>
> 本文是**日常使用与运维参考**，重点回答"怎么用"。
> Open WebUI 配置原理详见 [open-webui-config.md](open-webui-config.md)；
> DeepSeek 的调优过程与瓶颈分析详见
> [deepseek-v4-optimization-handoff.md](../designs/deepseek-v4-optimization-handoff.md)。

---

## 1. 系统概览

### 1.1 服务架构

```
浏览器
  │  http://192.168.1.247:3000
  ▼
Open WebUI (Docker)
  │  http://host.docker.internal:8081/v1
  ▼
openai-compat-proxy (systemd, 端口 8081, CIDR 白名单)
  │  unit 名仍沿用历史名 deepseek-v4-ik-compat
  │  http://127.0.0.1:8082
  ▼
llama-server (mainline llama.cpp, Docker Compose + systemd)
  │  /data/models/*.gguf
  ▼
Dual RTX 3090 (48GB) + 384GB RAM
```

**关键**：`8081` 是稳定入口，**永远不变**。后端 `8082` 由当前运行的模型占用，
切换模型时 Open WebUI 和所有客户端**无需任何改动**。

**硬件**：Dell T7910，2× RTX 3090 (48GB VRAM)，双路 E5-2686 v4（36 核），384GB RAM，Ubuntu VM (ESXi)

### 1.2 可用模型

同一时间**只运行一个模型**（两者合计超过 48GB 显存，且共用后端端口 8082），
通过 Ansible playbook 切换。

| 模型 | 服务名 | 架构 | 量化 | ctx | decode 实测 | 定位 |
|------|--------|------|------|-----|------------|------|
| **Qwen3.6-27B** | `qwen36` | Dense 27B（原生多模态） | Q5_K_M | 131072 | **37.6 tok/s** | **日常主力**，开机自启 |
| **DeepSeek V4 Flash** | `deepseek-v4-mainline` | MoE 284B（约 13B 激活） | UD-Q3_K_M | 131072 | 9.5 tok/s | 高难任务，按需启动 |

> 两个 playbook 都不会改变开机归属：Qwen 始终 `enabled`，DeepSeek 始终 `disabled`。
> 切换只影响当前运行的服务，重启后回到 Qwen。

> **当前开机模型**：`qwen36`（`enabled`）。DeepSeek 为 `disabled`，需手工切换。

### 1.3 API 接入

| 项 | 值 |
|---|---|
| Base URL | `http://192.168.1.247:8081/v1` |
| 模型名 | `qwen36` 或 `deepseek-v4-flash`（取决于当前运行哪个） |
| API Key | 不需要 |
| 访问控制 | CIDR 白名单：`192.168.1.0/24`、`172.17.0.0/16`、`172.18.0.0/16`、`127.0.0.0/8` |
| 协议 | OpenAI 兼容（`/v1/chat/completions`、`/v1/models`） |

**先确认当前跑的是哪个模型**——`model` 名写错会得到 404：

```bash
curl -s http://192.168.1.247:8081/v1/models | python3 -m json.tool
```

```bash
curl http://192.168.1.247:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen36",
    "messages": [{"role": "user", "content": "你好"}],
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

**白名单之外的客户端会被拒绝**（例如经 Tailscale 访问）。需要放通时修改
`ansible/inventory/host_vars/llm-server.yml` 的 `deepseek_v4_ik_api_allowed_cidrs`。

---

## 2. 模型选择指南

### 2.1 模型对比

| | Qwen3.6-27B | DeepSeek V4 Flash |
|---|---|---|
| **定位** | 日常主力 | 高难任务 |
| **decode 实测** | **37.6 tok/s** | 9.5 tok/s |
| **8K 提示首字延迟** | 数秒 | **约 38 秒** |
| **加载时间** | **20 秒** | 4–5 分钟 |
| **显存** | 28.5 GB（剩约 19 GB） | 约 40 GB（剩约 8 GB） |
| **SWE-bench Verified** | 77.2（厂商自报） | 79.0（厂商自报） |
| **思考模式** | 可关（见 2.3） | 默认开 |
| **工具调用** | ✅ playbook 每次部署都验证结构化 `tool_calls` | 未纳入当前 playbook 验证 |
| **视觉** | 模型原生支持，但当前**未加载 mmproj**，等同不可用 | ❌ |

### 2.2 场景推荐

| 场景 | 推荐 | 原因 |
|------|------|------|
| **日常问答、写作、代码** | Qwen3.6 | 实测 decode 约快 4 倍，适合高频交互 |
| **agent 多轮工具循环**（Hermes、OpenClaw） | Qwen3.6 | 多轮任务会累积 TTFT 和生成延迟 |
| **大范围重构、迁移、安全相关** | DeepSeek | 厂商基准略高，但本地任务正确率尚未对照验证；适合愿意用等待换取潜在质量收益的任务 |
| **根因高度模糊、错误代价高的任务** | DeepSeek | 作为高能力备用档；是否更正确需结合你的实际任务验证 |

> 判断依据：多轮循环会放大延迟——每轮的首字延迟和生成时间累加，DeepSeek 的 38 秒
> 8K TTFT 在十轮任务里代价显著。单次深度问题则相反，等待换取质量可能划算。
>
> 上面两个 SWE-bench 数字都是**厂商自报、不同 harness**，不足以证明两个本地 GGUF
> 在同一 agent 框架下的真实差距。请以你自己任务上的实测为准。

### 2.3 思考模式（Qwen3.6）

**默认开启**，回答会进 `reasoning_content`，`content` 为空。日常使用建议关闭：

```json
"chat_template_kwargs": {"enable_thinking": false}
```

关闭后 `<think>` 块为空，答案直接进 `content`。需要深度推理时去掉这一行即可。

### 2.4 接 agent 框架的注意事项

- **有副作用的工具设** `"parallel_tool_calls": false` —— Hermes 社区实测这一项把依赖调用错误从 10/10 降到 0/10
- **OpenClaw 开** `localModelLean` —— 减少工具 schema 和隐藏上下文开销
- **不要用 Q4 KV** —— llama.cpp 明确警告激进 KV 量化会伤害工具调用；本部署固定 `f16`

---

## 3. 后端运维操作

### 3.1 查看当前状态

```bash
# 哪个模型在跑
systemctl is-active qwen36 deepseek-v4-mainline

# 稳定入口与后端健康
curl -sf http://127.0.0.1:8081/health && echo "stable OK"
curl -sf http://127.0.0.1:8082/health && echo "backend OK"

# 当前模型名
curl -s http://127.0.0.1:8081/v1/models | python3 -m json.tool

# 显存
nvidia-smi --query-gpu=index,memory.used --format=csv
```

### 3.2 切换模型

**在开发机执行**，不是在服务器上：

```bash
cd /workspaces/IaC/ansible

# 切到 Qwen3.6（日常）
ansible-playbook playbooks/deploy-qwen36.yml

# 切到 DeepSeek（高难任务）
ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml
```

每条命令都是完整部署 + 验证：校验模型文件 → 停掉另一个运行时 → 等端口释放 →
启动目标 → 等 health → 跑固定 chat（Qwen 还会验证结构化工具调用）。

> **两个模型的校验强度不同**：Qwen 每次部署都计算并比对 SHA-256；DeepSeek 保存了
> SHA-256 pin，但日常部署**默认只检查文件大小**（哈希 138GB 要约 7 分钟）。模型
> 重新同步或来源变化后，显式跑一次完整校验（注意这是**完整部署**，会切换并重启服务，
> 不只是算哈希）：
>
> ```bash
> ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml \
>   -e deepseek_v4_mainline_verify_model_checksums=true
> ```
>
> **模型每次重新下载、同步或替换后都应执行一次**——大小检查发现不了同尺寸替换或静默损坏。

耗时：Qwen 约 1 分钟，DeepSeek 约 4–5 分钟（模型 130GB，加载慢）。

> **切换期间服务不可用**，正在进行的对话会超时。
> 切换后 Open WebUI **无需重启**，但模型下拉框里的名字会变，需要重新选一次。

**只做只读验证**（不切换、不重启）——**按当前运行的模型二选一**，两个 verify 都会
断言自己是唯一 active 的运行时，验证未运行的那个必然失败：

```bash
ansible-playbook playbooks/deploy-qwen36.yml --tags verify
ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml --tags verify
```

### 3.3 查看推理日志

**以下命令在 LLM 服务器上执行**（`ssh ubuntu@192.168.1.247`）。两个模型都跑在
Docker 里，推理日志用 `docker logs`，`journalctl` 只有启停记录。

```bash
# 当前容器名
docker ps --format '{{.Names}}' | grep -E 'qwen36|deepseek'

# 实时日志（按当前运行的模型二选一）
docker logs -f qwen36-server-1
docker logs -f deepseek-v4-mainline-server-1

# 只看速度指标
docker logs -f qwen36-server-1 | grep -E 'tok/s|print_timing'

# systemd 层面（只有启停，没有推理日志）
journalctl -u qwen36 -n 50
journalctl -u deepseek-v4-mainline -n 50
```

> 若当前用户不在 `docker` 组，所有 `docker` 命令前加 `sudo`。

关注指标：
- `prompt eval time` —— prefill，决定首字延迟
- `eval time` / `tok/s` —— 生成速度
- `draft acceptance` / `mean len` —— 仅 DeepSeek，投机解码效率

### 3.4 服务管理

**在 LLM 服务器上执行。**

```bash
# 重启当前模型（按实际运行的那个）
sudo systemctl restart qwen36
sudo systemctl restart deepseek-v4-mainline

# 停机维护（两个都停）
sudo systemctl stop qwen36 deepseek-v4-mainline

# 查看服务定义
systemctl cat qwen36
```

> 两个 unit 互相声明了 `Conflicts=`，启动一个会自动停掉另一个——它们抢同一个后端
> 端口 8082，且合计超过 48GB 显存。
>
> 直接 `systemctl start` 不经过 Ansible 的文件校验和验证步骤，**也不会调整开机归属**。
> 日常切换请用 playbook；`systemctl` 仅用于维护。

### 3.5 配置与参数

参数由 Ansible role 管理，**不要直接改服务器上的文件**（下次部署会覆盖）：

| 模型 | role 默认值 |
|------|------------|
| Qwen3.6 | `ansible/roles/qwen36/defaults/main.yml` |
| DeepSeek | `ansible/roles/deepseek-v4-mainline/defaults/main.yml` |

改完重跑对应 playbook 即可生效。

两个模型都保存了 SHA-256 pin。**Qwen 每次部署强制比对**；DeepSeek 日常部署只检查
文件大小，显式开启完整校验时才比对 SHA-256（见 3.2）。

---

## 4. Open WebUI 日常使用

### 4.1 访问与登录

- **地址**：`http://<server-ip>:3000`
- 首次访问需注册账号，第一个注册的账号自动成为管理员
- 如果不知道 server-ip：SSH 到服务器执行 `hostname -I | awk '{print $1}'`

### 4.2 选择模型

打开新对话 → 点击顶部模型下拉框：

- `qwen36` —— 当前运行的 Qwen3.6（日常默认）
- `deepseek-v4-flash` —— 仅在切换到 DeepSeek 后才出现
- `gpt-4o-mini` —— OpenAI API，仅用于标题/标签生成，不建议直接对话

> 模型列表由 Open WebUI 从稳定入口 `8081` 的 `/v1/models` 动态拉取。**同一时间只会有
> 一个本地模型**——看不到另一个是正常的，说明它没在跑。
>
> 切换模型后如果下拉框没更新，刷新页面即可。若某个自定义模型条目指向了已不存在的
> base model，会报 `404: Model not found`，需要在 Workspace → Models 里改 base model
> 或删掉该条目。

### 4.3 Web 搜索

当前配置：**Native Function Calling 模式 + SearXNG 元搜索引擎**

**使用方法**：
1. 点击输入框旁的 🌐 按钮开启搜索权限
2. 正常提问，模型会自主判断是否需要搜索
3. 搜索时消息下方显示 "Searching..." → "Searched X sites"

> 🌐 按钮的含义是"授权模型使用搜索工具"，不是"强制每条消息都搜索"。
> 模型根据问题内容自主决定是否触发搜索。如果需要强制搜索，可以在消息中明确要求
> （如"请搜索最新信息"）。
>
> 配置原理详见 [open-webui-config.md](open-webui-config.md) Section 1.6 和 3。

### 4.4 上传图片（视觉功能）

> **当前不可用。** Qwen3.6-27B 本身是原生多模态模型，但本部署**没有加载 mmproj
> 视觉投影器**，因此上传图片不会被识别。

要启用需要额外下载对应的 mmproj GGUF 并在 role 里加 `--mmproj` 参数。纯文本场景下
不加载它没有任何开销，所以默认关闭。

### 4.5 Memory（记忆功能）

跨对话持久化用户偏好和重要信息。

**前提条件**：头像 → Settings → Personalisation → Memory 开关**必须开启**，否则工具不注入。

- 模型通过 function calling 自主决定何时存储/检索记忆
- 查看/管理记忆：头像 → Settings → Personalisation → Memory → Manage Memories
- 清除特定记忆：直接告诉模型"请忘掉关于 XXX 的信息"，或在设置中手动删除

### 4.6 对话管理

| 操作 | 方法 |
|------|------|
| 新建对话 | 左侧 "New Chat" 或 `Ctrl+Shift+O` |
| 搜索历史对话 | 左侧搜索框 |
| 固定对话 | 右键对话 → Pin |
| 导出对话 | 对话右上角菜单 → Export |

> 对话标题由 gpt-4o-mini（外部 Task Model）自动生成，不占用本地 llama-server 资源。

---

## 5. 性能预期与等待时间

速度与能力对比见 [2.1](#21-模型对比)，此处只解释成因和使用影响。

> decode 数字为固定 corpus、cold prefill、三样本中位。标"约/数秒"的首字延迟是运维
> 观察值，不是同等方法的正式基准。

### 5.1 DeepSeek 为什么慢

它的 112 GiB 专家权重放不进 48GB 显存，只能常驻主存，每生成一个 token 要从内存读约
2.6 GiB。已实测确认瓶颈是 43 层串行链的每层固定开销（每层 2.6 ms 中仅 0.8 ms 是内存
读取），**不是带宽、不是线程数、不是 PCIe 宽度**——机器内存带宽 80 GB/s 只用掉 27%，
PCIe 只用掉 1.4%。

详见 [deepseek-v4-optimization-handoff.md](../designs/deepseek-v4-optimization-handoff.md)，
里面记录了已实测排除的十余个方向，避免重复投入。

### 5.2 Web 搜索额外延迟

搜索 + 抓取网页通常增加 3–10 秒，取决于返回站点数量。

### 5.3 并发使用

后端自动初始化 4 个 slot。**并发会摊薄单请求速度**。DeepSeek 的内存带宽有大量闲置
（只用了 27%），说明并发总吞吐**有提升潜力**，但 2/4 路并发尚未正式测量——
**不要用单流数字乘以 slot 数来做容量承诺**。

---

## 6. 常见问题与排查

### 6.1 模型没有响应 / 连接错误

**在 LLM 服务器上**：

```bash
# 1. 哪个模型在跑？两个都 inactive 就是没起来
systemctl is-active qwen36 deepseek-v4-mainline

# 2. 后端和稳定入口
curl -sf http://127.0.0.1:8082/health && echo "backend OK"
curl -sf http://127.0.0.1:8081/health && echo "stable OK"

# 3. 容器层面的错误 —— 先确认容器名，再按当前模型二选一
docker ps --format '{{.Names}}' | grep -E 'qwen36|deepseek'
docker logs --tail 30 qwen36-server-1
docker logs --tail 30 deepseek-v4-mainline-server-1
```

**在开发机的 `/workspaces/IaC/ansible` 目录**（重新部署会做完整校验）：

```bash
ansible-playbook playbooks/deploy-qwen36.yml
```

**8082 通但 8081 不通**：兼容代理没起来 →
`sudo systemctl start deepseek-v4-ik-compat`（unit 名沿用历史名）。

**从外部机器连不上**：检查来源 IP 是否在白名单内（见 1.3）。Tailscale 等非
`192.168.1.0/24` 的来源会被拒绝。

### 6.2 回复内容是空的

Qwen3.6 **默认开启思考模式**，答案进 `reasoning_content` 而不是 `content`。
请求里加：

```json
"chat_template_kwargs": {"enable_thinking": false}
```

Open WebUI 里看不到这个现象（它会显示 reasoning），但用 API 直连时很常见。

**先看 `reasoning_content`**：它非空而 `content` 为空，属于思考模式的正常表现；
**两者都为空才是异常**，继续检查 `finish_reason` 和容器日志。

### 6.3 `404: Model not found`

**最常见的原因是请求里的 `model` 与当前后端不一致**——同一时间只有一个模型在跑。

**第一步**，确认当前实际提供的模型名：

```bash
curl -s http://127.0.0.1:8081/v1/models | python3 -m json.tool
```

请求里的 `model` 必须等于返回的 `data[].id`（`qwen36` 或 `deepseek-v4-flash`）。

**第二步**，如果直接调 API 正常、只有 Open WebUI 报 404，那是 Open WebUI 的自定义
模型条目指向了已不存在的 base model。到 Workspace → Models 找到该条目，把 base
model 改成当前存在的，或直接删掉这个自定义条目。

### 6.4 响应速度突然变慢

```bash
# 确认跑的是哪个模型——切到 DeepSeek 会慢 4 倍
curl -s http://127.0.0.1:8081/v1/models | python3 -m json.tool

# 有没有别的进程抢 GPU
nvidia-smi

# 是不是并发请求摊薄了（容器名按当前模型替换）
docker logs --tail 20 qwen36-server-1 | grep slot
```

### 6.5 工具调用不工作 / 返回裸 JSON

模型把工具调用当普通文本输出，而不是结构化的 `tool_calls`。按层排查：

**1. 用 playbook 的 canonical 验证**（开发机 `/workspaces/IaC/ansible`）：

```bash
ansible-playbook playbooks/deploy-qwen36.yml --tags verify
```

它会直接断言 `tool_calls` 能被解析出来。这一步过了说明服务端没问题。

**2. 分别打后端和稳定入口**（服务器上），同一个带 `tools` 的请求：

| 现象 | 结论 |
|---|---|
| 8082 结构化、8081 异常 | 兼容代理的问题 |
| 两边都是裸 JSON/XML | 模型模板或 llama.cpp parser 没生效，检查 `--jinja` |
| 两边都正常、只有 Open WebUI 异常 | Open WebUI 的 Function Calling 需设为 `native` |

**3. 检查请求本身**：`tools` 数组是否符合 OpenAI 规范。

> **不要在客户端自己解析裸 JSON 绕过去**——那说明模板或解析器没生效，应该修服务端。

### 6.6 Web 搜索不工作

```bash
docker ps --filter name=searxng
docker logs --tail 20 searxng
```

确认 Open WebUI 里 🌐 按钮已开启（它是"授权模型使用搜索"，不是"强制搜索"）。

---

## 7. 快速参考卡

### 7.1 常用命令

**在 LLM 服务器上**（`ssh ubuntu@192.168.1.247`）：

```bash
systemctl is-active qwen36 deepseek-v4-mainline
curl -sf http://127.0.0.1:8081/health && echo OK
curl -s http://127.0.0.1:8081/v1/models | python3 -m json.tool
nvidia-smi --query-gpu=index,memory.used --format=csv

docker logs -f qwen36-server-1
docker logs -f deepseek-v4-mainline-server-1
docker restart open-webui
```

**在开发机的 `/workspaces/IaC/ansible` 目录**：

```bash
ansible-playbook playbooks/deploy-qwen36.yml                  # 切到日常
ansible-playbook playbooks/deploy-deepseek-v4-mainline.yml    # 切到高难任务
ansible-playbook playbooks/deploy-qwen36.yml --tags verify    # 只验证，不重启
```

### 7.2 模型速查

| | Qwen3.6 | DeepSeek V4 Flash |
|---|---|---|
| 模型名 | `qwen36` | `deepseek-v4-flash` |
| 服务 | `qwen36` | `deepseek-v4-mainline` |
| 速度 | 37.6 tok/s | 9.5 tok/s |
| 开机自启 | ✅ | ❌ |
| 思考模式 | 可关 | 默认开 |

### 7.3 访问地址

| 服务 | 地址 |
|------|------|
| Open WebUI | `http://192.168.1.247:3000` |
| **API（稳定入口）** | **`http://192.168.1.247:8081/v1`** |
| 健康检查 | `http://192.168.1.247:8081/health` |
| 后端（仅本机） | `http://127.0.0.1:8082` |
| SearXNG | Docker 内部，不暴露 |

---

## 8. 延伸阅读

| 文档 | 内容 |
|------|------|
| [deepseek-v4-optimization-handoff.md](../designs/deepseek-v4-optimization-handoff.md) | DeepSeek 调优全过程、瓶颈归因、已排除的十余个方向 |
| [open-webui-config.md](open-webui-config.md) | Open WebUI 设置原理、Native FC、搜索配置（⚠️ 其中模型名、8080 端口和 llama-server 命令属于已退役体系，**不可照抄**） |
| [llm-server-deployment.md](../deployment/llm-server-deployment.md) | Terraform + Ansible 基础设施部署（⚠️ 模型与 llama-server 部分仍是已退役的 ik + MiniMax 方案） |

> 历史文档（描述已退役的 ik_llama.cpp / `switch-model` 体系，仅作背景参考）：
> [multi-model-deployment-plan.md](../deployment/multi-model-deployment-plan.md)、
> [qwen3-vl-32b-tuning-log.md](qwen3-vl-32b-tuning-log.md)、
> [minimax-llama.md](../designs/minimax-llama.md)

---

> **参数覆盖优先级**：请求里的采样参数会覆盖 llama-server 默认值。当前部署没有在
> role 里固定 Temperature/top_k/top_p，用的是 llama-server 自身默认值。若要全局
> 统一，需要先把这些参数显式写进对应 role 的 `defaults/main.yml`。
