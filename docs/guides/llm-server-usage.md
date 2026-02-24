# LLM Server 使用说明

> **适用版本**：ik_llama.cpp commit `f7923739`，Open WebUI v0.8.2，SearXNG `latest`
>
> 本文是**日常使用与运维参考**，重点回答"怎么用"。
> 配置原理和参数调优详见 [open-webui-config.md](open-webui-config.md)；
> 系统部署详见 [llm-server-deployment.md](../deployment/llm-server-deployment.md)。

---

## 1. 系统概览

### 1.1 服务架构

```
浏览器
  │  http://<server-ip>:3000
  ▼
Open WebUI (Docker)
  │  http://host.docker.internal:8080/v1 (OpenAI 兼容接口)
  ▼
llama-server (ik_llama.cpp, systemd 管理)
  │  /data/models/*.gguf
  ▼
GGUF 模型文件 (Dual RTX 3090 + CPU 混合推理)

Open WebUI ←→ SearXNG (Docker 内部, http://searxng:8080)
              ↕
         Google / Bing / DuckDuckGo / Wikipedia (聚合搜索)
```

**硬件**：Dell T7910，2× RTX 3090 (48GB VRAM)，384GB RAM，Ubuntu VM (ESXi)

### 1.2 可用模型

同一时间**只运行一个模型**，通过 `switch-model` 命令切换（约 30 秒冷启动）。

| 模型 | 服务名 | 架构 | 量化 | ctx | parallel | 速度 | 特性 |
|------|--------|------|------|-----|----------|------|------|
| **Qwen3-VL-32B** | llama-server@qwen3-vl-32b | Dense 32B | Q4_K_M | 65536 | 2 | ~31 tok/s | 视觉（图片）、推理 |
| **MiniMax M2.5** | llama-server@m25 | MoE 230B (10B active) | UD-Q5_K_XL | 65536 | 1 | ~8 tok/s | 深度推理 |
| **GLM-4.7-Flash** | llama-server@glm-4.7 | MoE | Q4_K_M | 32768 | 1 | 未实测 | 轻量快速 |

> **当前开机模型**：qwen3-vl-32b（服务器重启后自动启动）

---

## 2. 模型选择指南

### 2.1 模型对比

| | Qwen3-VL-32B | MiniMax M2.5 | GLM-4.7-Flash |
|---|---|---|---|
| **定位** | 日常主力（视觉+推理） | 深度推理 | 极速响应 |
| **生成速度** | ~31 tok/s | ~8 tok/s | 最快（未实测） |
| **思考模式** | ✅ reasoning_format=auto | ✅ reasoning_format=auto | 未确认 |
| **视觉（图片）** | ✅ mmproj 视觉编码 | ❌ | ❌ |
| **并发请求** | 2 个 slot | 1 个 slot | 1 个 slot |
| **中文质量** | 极强 | 极强 | 好 |
| **VRAM 占用** | ~36GB（全 GPU） | ~48GB VRAM + CPU RAM 混合 | ~18GB |

> M2.5 使用 CPU-GPU 混合推理：注意力层在 GPU，MoE expert 层部分在 GPU、部分在 CPU。
> 48GB VRAM 无法容纳全部 230B 参数，因此通过 tensor override 精确控制每层放置位置。

### 2.2 场景推荐

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| **图片分析、截图解读** | Qwen3-VL-32B | 唯一支持视觉的模型 |
| **日常问答、写作、代码** | Qwen3-VL-32B | 默认开机模型，速度快，综合能力强 |
| **复杂推理、长文深度分析** | M2.5 或 Qwen3-VL | M2.5 更深但更慢，按时间/质量需求选择 |
| **两人同时使用** | Qwen3-VL-32B | parallel=2，唯一支持双 slot 并发 |
| **快速检索、简单问答** | GLM-4.7-Flash | 轻量快速（如已切换到该模型） |

> M2.5 的 ~8 tok/s 不代表"不可用"——开启 thinking 后大量推理在 `<think>` 阶段完成，
> 最终答案质量可能更高。适合不赶时间的复杂任务。

---

## 3. 后端运维操作

### 3.1 查看当前状态

```bash
# 当前运行的模型实例
systemctl list-units 'llama-server@*' --state=active

# 服务状态详情（含最近日志）
systemctl status llama-server@qwen3-vl-32b

# API 健康检查
curl -sf http://localhost:8080/health && echo "OK"

# 当前加载的模型名称
curl -s http://localhost:8080/v1/models | python3 -m json.tool
```

### 3.2 切换模型

```bash
# 查看可用模型列表 + 当前状态
switch-model

# 切换到指定模型
switch-model qwen3-vl-32b    # 视觉模型（默认）
switch-model m25              # MiniMax M2.5
switch-model glm-4.7          # GLM-4.7-Flash
```

切换流程：
1. 停止所有 `llama-server@*` 实例
2. 启动目标模型实例
3. 轮询 `/health` 接口直到就绪（超时 120 秒）
4. 输出 `✓ <model> ready`

> **切换期间服务不可用**。如有用户正在对话，请求会超时。
> 切换完成后 Open WebUI **无需重启**，刷新页面或点击模型下拉框即可看到新模型。

### 3.3 查看推理日志

```bash
# 实时日志流
journalctl -u llama-server@qwen3-vl-32b -f

# 最近 100 行
journalctl -u llama-server@qwen3-vl-32b -n 100

# 按时间过滤
journalctl -u llama-server@qwen3-vl-32b --since "10 minutes ago"

# 只看生成速度指标
journalctl -u llama-server@qwen3-vl-32b -f | grep -E 'tok/s|timing'
```

关注指标：
- `n_prompt_tokens_processed`：prefill token 数（越多 TTFT 越长）
- `eval duration` / `tok/s`：生成速度

### 3.4 服务管理

```bash
# 重启当前模型（修改配置后）
sudo systemctl restart llama-server@qwen3-vl-32b

# 手动停止（停机维护）
sudo systemctl stop 'llama-server@*'

# 查看 systemd 服务定义
systemctl cat llama-server@qwen3-vl-32b
```

> 直接 `systemctl stop/start` 不经过 switch-model 的健康检查。
> 维护场景使用；日常切换请用 `switch-model`。

### 3.5 模型配置文件

配置文件位于 `/opt/llm-server/models/`：

```
/opt/llm-server/models/
  ├── m25.env              # MiniMax M2.5 参数
  ├── m25.ot               # MiniMax M2.5 tensor override 规则
  ├── qwen3-vl-32b.env     # Qwen3-VL 参数
  └── glm-4.7.env          # GLM-4.7 参数
```

关键变量（`.env` 文件）：

| 变量 | qwen3-vl-32b | m25 | glm-4.7 |
|------|-------------|-----|---------|
| LLAMA_CTX_SIZE | 65536 | 65536 | 32768 |
| LLAMA_PARALLEL | 2 | 1 | 1 |
| LLAMA_TEMP | 0.6 | 0.8 | 1.0 |
| LLAMA_TOP_K | 20 | 40 | — |
| LLAMA_TOP_P | 0.95 | 0.95 | 0.95 |
| LLAMA_REASONING_FORMAT | auto | auto | — |
| LLAMA_CACHE_TYPE_K / V | q8_0 | q8_0 | q8_0 |
| LLAMA_MMPROJ | ✅ (视觉编码器) | — | — |

> **临时调参**：直接编辑 `.env` 文件，然后 `sudo systemctl restart llama-server@<name>`。
> **持久化**：修改 `ansible/inventory/host_vars/llm-server.yml` 并重跑 Ansible playbook，
> 否则下次 Ansible 运行会覆盖 `.env`。

---

## 4. Open WebUI 日常使用

### 4.1 访问与登录

- **地址**：`http://<server-ip>:3000`
- 首次访问需注册账号，第一个注册的账号自动成为管理员
- 如果不知道 server-ip：SSH 到服务器执行 `hostname -I | awk '{print $1}'`

### 4.2 选择模型

打开新对话 → 点击顶部模型下拉框选择：

- `qwen3-vl-32b` — 当前运行的 Qwen3-VL 模型
- `MiniMax-M2.5` — 切换到 M2.5 后才可见
- `glm-4.7-flash` — 切换到 GLM 后才可见
- `gpt-4o-mini` — OpenAI API（仅用于标题/标签生成，不建议直接对话）

> 模型列表由 Open WebUI 从 llama-server 的 `/v1/models` 动态拉取。
> 如果看不到某个模型，说明对应的 llama-server 实例未运行，需要 SSH 切换（见 Section 3.2）。

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

> **仅 Qwen3-VL-32B 支持**。M2.5 和 GLM 不支持视觉，上传图片不会被识别。

**操作步骤**：
1. 确认顶部显示 `qwen3-vl-32b` 模型
2. 点击输入框旁的纸夹/上传图标
3. 选择图片文件（JPG、PNG、WebP）
4. 输入问题，发送

**支持场景**：
- 截图解读（代码、错误信息、UI 界面）
- 图表/图形分析
- OCR（从图片提取文字）
- 多图对比（注意 ctx 消耗较大）

> 图片由 mmproj 视觉编码器转为 token，分辨率越高消耗 ctx 越多。
> 高分辨率图片（4K）可能增加数秒的 prefill 时间。

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

### 5.1 各模型速度参考

| 模型 | 生成速度 | 短 prompt TTFT | 长 prompt TTFT | 备注 |
|------|---------|---------------|---------------|------|
| Qwen3-VL-32B | ~31 tok/s | <1s | ~3s | Dense 全 GPU，KV cache q8_0 |
| MiniMax M2.5 | ~8 tok/s | ~3s | ~8s | CPU-GPU 混合，含 thinking |
| GLM-4.7-Flash | 未实测 | — | — | 预期最快（轻量 MoE） |

> TTFT = Time to First Token，发送消息后到第一个 token 出现的等待时间。
> Builtin Tools 开启越多，baseline prompt_tokens 越高，TTFT 越长
> （详见 [open-webui-config.md](open-webui-config.md) Section 2.2）。

### 5.2 Web 搜索额外延迟

模型决定搜索时额外增加 ~3-5 秒（SearXNG 查询 + 结果返回）。
不搜索时无额外延迟。

### 5.3 图片处理额外延迟

mmproj 编码阶段：视图片分辨率通常 1-5 秒。之后 TTFT 与纯文本无显著差异。

### 5.4 并发使用

| 模型 | 并发 slot | 行为 |
|------|----------|------|
| Qwen3-VL-32B | 2 | 两个请求可同时推理 |
| M2.5 / GLM | 1 | 第二个请求排队等待 |

> Task Model (gpt-4o-mini) 走外部 OpenAI API，不占用本地 slot。
> 标题/标签生成不影响用户请求。

---

## 6. 常见问题与排查

### 6.1 模型没有响应 / 连接错误

```bash
# 1. 确认 llama-server 是否在运行
systemctl list-units 'llama-server@*' --state=active
# 无输出 = 没有模型在运行

# 2. 检查健康状态
curl -sf http://localhost:8080/health && echo "healthy" || echo "not ready"

# 3. 未运行则启动
switch-model qwen3-vl-32b

# 4. 查看错误日志
journalctl -u llama-server@qwen3-vl-32b -n 50
```

### 6.2 响应速度很慢

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| 发送后长时间空白 | Thinking 阶段（`<think>` 内容不显示） | 正常现象，等待 "Thought for X seconds" |
| TTFT 很长 | 开启了过多 Builtin Tools | 关闭不必要的 Tools（Code Interpreter 等） |
| 长对话越来越慢 | KV cache 接近 ctx 上限 | 新建对话 |
| 明显低于预期速度 | GPU 异常 | 查 `journalctl` 日志 + `nvidia-smi` |

### 6.3 Web 搜索不工作

排查清单：

```
✅ 输入框旁 🌐 按钮是否开启？
✅ Admin → Settings → Web Search 全局开关是否开启？
✅ SearXNG 容器是否健康？
```

```bash
# 验证 SearXNG 状态
docker exec searxng wget -qO- "http://localhost:8080/healthz"
```

> Native FC 模式下模型自主决定是否搜索。如果问题"看起来不需要外部信息"，
> 模型可能不触发搜索。可在消息中明确要求。

### 6.4 图片上传后模型没看到

1. 确认当前模型是 `qwen3-vl-32b`（其他模型不支持视觉）
2. 确认 Admin → Models → qwen3-vl-32b → Capabilities → Vision 已勾选
3. 检查 mmproj 加载：
   ```bash
   journalctl -u llama-server@qwen3-vl-32b -n 100 | grep -i mmproj
   ```

### 6.5 对话标题未生成

- 标题由 gpt-4o-mini (Task Model) 生成，需要外网连接
- 检查：`docker logs open-webui --tail 50 2>&1 | grep -E '500|title|error'`
- 不影响对话功能，仅标题显示为默认值

### 6.6 切换模型后看不到新模型

1. 确认 switch-model 输出 `✓ <model> ready`
2. 验证就绪：`curl -sf http://localhost:8080/health && echo "ready"`
3. 刷新 Open WebUI 页面或重新点击模型下拉框
4. 如仍不可见：`curl -s http://localhost:8080/v1/models | python3 -m json.tool`

---

## 7. 快速参考卡

### 7.1 服务端常用命令

```bash
# === 状态查看 ===
systemctl list-units 'llama-server@*' --state=active   # 当前运行哪个模型
curl -sf http://localhost:8080/health && echo "OK"      # API 健康检查
curl -s http://localhost:8080/v1/models | python3 -m json.tool  # 模型名称

# === 切换模型 ===
switch-model                  # 列出可用模型 + 当前状态
switch-model qwen3-vl-32b    # 视觉模型（默认开机）
switch-model m25              # MiniMax M2.5
switch-model glm-4.7          # GLM-4.7-Flash

# === 日志 ===
journalctl -u llama-server@qwen3-vl-32b -f     # 实时日志
journalctl -u llama-server@qwen3-vl-32b -n 50  # 最近 50 行

# === Docker ===
docker ps                          # 容器状态
docker logs open-webui --tail 50   # Open WebUI 日志
docker restart open-webui          # 重启 Open WebUI
```

### 7.2 模型特性速查

| 功能 | Qwen3-VL-32B | M2.5 | GLM-4.7 |
|------|:-----------:|:---:|:-------:|
| 图片/视觉 | ✅ | ❌ | ❌ |
| 深度推理 | ✅ (auto) | ✅ (auto) | — |
| 中文 | ✅✅ | ✅✅ | ✅ |
| 速度 | ~31 tok/s | ~8 tok/s | 最快 |
| 并发 | 2 slot | 1 slot | 1 slot |
| 默认开机 | ✅ | ❌ | ❌ |

### 7.3 Open WebUI 快捷操作

| 操作 | 方法 |
|------|------|
| 新建对话 | `Ctrl+Shift+O` |
| 切换模型 | 顶部下拉框 |
| 开启搜索 | 输入框旁 🌐 按钮 |
| 上传图片 | 输入框旁纸夹图标（需 qwen3-vl-32b） |
| 管理记忆 | 头像 → Settings → Personalisation → Memory |

### 7.4 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| Open WebUI | `http://<server-ip>:3000` | 主前端 |
| llama-server API | `http://<server-ip>:8080/v1` | OpenAI 兼容接口 |
| 健康检查 | `http://<server-ip>:8080/health` | 就绪状态 |
| SearXNG | Docker 内部 `http://searxng:8080` | 不暴露到宿主机 |

---

## 8. 延伸阅读

| 文档 | 内容 | 适合场景 |
|------|------|---------|
| [open-webui-config.md](open-webui-config.md) | Open WebUI 全部设置原理、陷阱、推荐配置 | 理解 Native FC、Builtin Tools 开销、搜索配置 |
| [multi-model-deployment-plan.md](../deployment/multi-model-deployment-plan.md) | systemd 模板单元架构设计 | 理解 switch-model / launch-llama 内部机制 |
| [qwen3-vl-32b-tuning-log.md](qwen3-vl-32b-tuning-log.md) | Qwen3-VL 7 轮调优 + 64K 上下文测试 | 视觉模型 benchmark、参数选型依据 |
| [minimax-m25-tuning-log.md](minimax-m25-tuning-log.md) | M2.5 17 轮调优记录 | CPU-MoE 配置依据、各参数实测影响 |
| [llm-server-deployment.md](../deployment/llm-server-deployment.md) | Terraform + Ansible 完整部署方案 | 重新部署或理解基础设施配置 |
| [minimax-llama.md](../designs/minimax-llama.md) | M2.5 原始部署设计 | 引擎选型背景、CPU-MoE 架构原理 |

---

> **参数覆盖优先级**：Open WebUI 模型设置 > llama-server `.env` 默认值。
> 如果在 Open WebUI 中设置了 Temperature/top_k/top_p 等参数，会覆盖服务端配置。
> 建议在 Open WebUI 侧保持 Default，统一由 `.env`（Ansible 管理）控制。
