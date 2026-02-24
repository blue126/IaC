# Open WebUI 配置指南

本文档记录 Open WebUI 与本地 llama-server 配合使用时的关键配置经验，
包括模型设置优化、Web 搜索配置、以及常见性能问题排查。

> 环境：Open WebUI v0.8.2 (Docker: `ghcr.io/open-webui/open-webui:main`) + llama-server (ik_llama.cpp) + MiniMax M2.5
>
> **注意**：`:main` 标签会随上游更新漂移。本文基于 v0.8.2 验证，升级后行为可能变化。
> 如需锁定版本，可改用 `:v0.8.2` 标签。

---

## 1. 模型设置三层开关

Open WebUI 的模型设置中有三个看似重叠的区域，实际各有不同作用：

### 1.1 Capabilities（能力声明）

**位置**：Model Settings → Capabilities

控制模型对外**声称**具备哪些能力，影响 UI 展示和功能可用性。

| 选项 | 类型 | 说明 |
|------|------|------|
| Vision | UI | 允许在聊天中发送图片（模型需支持多模态） |
| File Upload | UI | 允许上传文件 |
| File Context | UI | 允许文件上下文 |
| **Web Search** | UI + 工具门控 | 显示 🌐 按钮，且作为工具注入的前提条件 |
| **Image Generation** | UI + 工具门控 | 显示图片生成选项，且作为工具注入的前提条件 |
| **Code Interpreter** | UI + 工具门控 | 显示代码解释器选项，且作为工具注入的前提条件 |
| Usage | UI | 显示 token 用量 |
| Citations | UI | 显示引用来源 |
| Status Updates | UI | 显示状态更新 |
| Builtin Tools | 总开关 | 是否允许挂载任何内置工具 |

### 1.2 Builtin Tools（内置工具）

**位置**：Model Settings → Builtin Tools

控制哪些**工具类别**可以被注入到 prompt 中。

| 工具 | Token 开销 | 说明 |
|------|-----------|------|
| Time & Calculation | 轻量 | 时间和计算工具 |
| Memory | 非零（见注） | 记忆管理工具（需用户级全局开关，见下方说明） |
| **Chat History** | **~256 tokens** | 聊天历史搜索 |
| **Notes** | **~481 tokens** | 笔记工具 |
| **Knowledge Base** | **~789 tokens** | 知识库查询（最重） |
| Channels | 轻量 | 频道工具 |
| **Web Search** | 中等 | 搜索工具定义注入 |
| **Image Generation** | 中等 | 图片生成工具定义注入 |
| **Code Interpreter** | **~500 tokens** | 工具描述 + 浏览器加载 pyodide |

> Token 开销数据来自实测（详见 Section 2.2），每个开启的工具都会增加 prefill 时间。
>
> **隐藏门控：Memory 的用户级全局开关**
> Memory 工具需要额外前提：**用户头像 → Settings → Personalisation → Memory 必须开启**。
> 如果该开关关闭，即使 Builtin Tools 中勾选了 Memory，工具 schema 也不会注入，
> 模型无法调用记忆功能。这与 Web Search 需要 Admin 全局开关类似。

### 1.3 Default Features（默认功能）

**位置**：Model Settings → Default Features

控制每次**新建聊天**时哪些功能自动开启（即 🌐 等按钮的默认状态）。用户可在聊天中手动切换。

> **⚠️ Native FC 模式下的重要性**：`features["web_search"]`（🌐 按钮）是 native FC 工具注入的
> 必要门控条件之一（Gate 4，详见 Section 1.6）。🌐 按钮 OFF 时 `search_web` 工具**不会被注入**。
>
> 存在 **TTFT vs 便利性的取舍**：
> - **开启**（`defaultFeatureIds: ["web_search"]`）：模型能自主搜索，但工具 schema 占用 prompt_tokens
> - **关闭**（默认）：减少 prompt_tokens 降低 TTFT，但需搜索时须手动点击 🌐
>
> 详见 Section 2.3 的实测数据和推荐。

### 1.4 层级关系

Builtin Tools 是 Capabilities 的**下级控制**：

```
Capabilities
├── Vision, File Upload, File Context, Usage, Citations, Status Updates  (纯 UI 开关)
├── Web Search          ← 能力声明 + 工具门控
├── Image Generation    ← 能力声明 + 工具门控
├── Code Interpreter    ← 能力声明 + 工具门控
└── Builtin Tools       ← 总开关，控制下面整个 Builtin Tools 区域是否生效
     ├── Time & Calculation, Memory, Chat History, Notes, Knowledge Base, Channels
     ├── Web Search          ← 细粒度工具开关
     ├── Image Generation    ← 细粒度工具开关
     └── Code Interpreter    ← 细粒度工具开关
```

Web Search / Image Generation / Code Interpreter 出现在两层：
- **Capabilities** 层：决定"模型有没有这个能力"（UI 是否显示对应按钮）
- **Builtin Tools** 层：决定"是否挂载这个工具的具体实现到 prompt"

### 1.5 Function Calling 模式（关键设置）

**位置**：Model Settings → Advanced Params → Function Calling

| 模式 | 说明 |
|------|------|
| **`native`**（推荐） | 通过 OpenAI 兼容的 function calling API 传递工具定义，模型自主决定调用 |
| 非 native（默认） | 工具以文本/XML 格式注入 prompt，模型可能无法识别或调用 |

**`function_calling = native` 的影响**：

1. **Builtin Tools 才能真正工作**：非 native 模式下，即使勾选了 Time、Memory 等工具，
   模型可能看不到或无法调用它们（工具定义格式不被识别）
2. **Web Search 走不同路径**：native 模式下 RAG 搜索被跳过，改由模型通过 function calling
   自主调用 `search_web` 工具（详见 1.6）
3. **模型需支持 function calling**：llama-server 的 OpenAI 兼容 API 支持 tool calling，
   但模型本身需要经过 function calling 训练才能可靠使用

### 1.6 Web Search 机制（重要）

Open WebUI v0.8.x 中 Web Search 有**两套机制**，`function_calling` 设置决定走哪条路径：

#### 机制 A：RAG Web Search（仅非 native FC 模式）

由**聊天窗口的 🌐 按钮**触发，Task Model 生成搜索词：

```
流程：用户开启 🌐 → Task Model 生成搜索词 → 搜索引擎查询 → 结果注入上下文 → 主模型回复
```

门控条件（全部满足才触发）：

```
function_calling ≠ native             ← ⚠️ native 模式下此路径被完全跳过
    AND
Capabilities: Web Search ✅           ← 模型能力声明（UI 显示 🌐 按钮）
    AND
Admin Settings: ENABLE_WEB_SEARCH ✅  ← 全局开关（需配置搜索引擎）
    AND
Per-chat: 🌐 button ✅               ← 会话级开关（Default Features 控制默认值）
```

对应 middleware 代码：

```python
if "web_search" in features and features["web_search"]:
    # native FC 时跳过 RAG 搜索，改由模型自主调用 search_web 工具
    if metadata.get("params", {}).get("function_calling") != "native":
        form_data = await chat_web_search_handler(...)
```

#### 机制 B：Native Function Calling Web Search（推荐，需 native FC）

模型通过 function calling 自主调用 `search_web` 工具：

```
流程：模型收到用户消息 + 工具列表 → 模型判断是否需要搜索 → 调用 search_web → 结果返回 → 模型回复
```

前提条件：`function_calling = native` 且 `Capabilities: Builtin Tools ✅`（总开关）。

在此基础上，**四个条件全部满足**才注入 `search_web` 工具：

```
Capabilities: Web Search ✅           ← 能力声明（Gate 1）
    AND
Builtin Tools: Web Search ✅          ← 工具挂载开关（Gate 2）
    AND
Admin Settings: ENABLE_WEB_SEARCH ✅  ← 全局开关（Gate 3）
    AND
Per-chat: 🌐 button ✅               ← 会话级开关（Gate 4，由 Default Features 控制默认值）
```

对应 `tools.py` 代码：

```python
if (
    is_builtin_tool_enabled("web_search")         # Gate 2: builtinTools.web_search
    and getattr(..., "ENABLE_WEB_SEARCH", False)   # Gate 3: 全局 admin 开关
    and get_model_capability("web_search")         # Gate 1: capabilities.web_search
    and features.get("web_search")                 # Gate 4: 🌐 按钮（前端 features）
):
    builtin_functions.extend([search_web, fetch_url])
```

> **⚠️ 关键**：🌐 按钮在 native FC 模式下**同样是必需的门控条件**。
> 设置 `defaultFeatureIds: ["web_search"]` 可让新建聊天时 🌐 按钮默认开启，
> 否则用户每次新建聊天都需要手动点击 🌐 才能触发搜索。

**优势**：模型根据用户问题智能判断是否需要搜索，配合 Default Features 自动开启后使用体验最佳。

#### 隐藏陷阱：User Settings `webSearch: "always"`

**位置**：用户头像 → Settings → Interface → Web Search

该设置存储在 `user.settings.ui.webSearch`，可选值：

| 值 | 行为 |
|----|------|
| `"always"` | **前端强制在每条消息的 features 中携带 `web_search: true`** |
| `null` / 未设置 | 正常行为，由 🌐 按钮 / Default Features 控制（推荐） |

> **⚠️ 陷阱**：用户 Settings → Interface 中的 Web Search 开关可能会将设置写为
> `"always"`。影响：
> - **RAG 模式**：每条消息都强制触发搜索，无视 🌐 按钮状态
> - **Native FC 模式**：Gate 4 始终满足，`search_web` 工具始终被注入（模型仍自主判断是否搜索，
>   但工具 schema 始终占用 prompt_tokens）
>
> **排查方法**：
> ```bash
> docker exec open-webui python3 -c "
> import sqlite3, json
> conn = sqlite3.connect('/app/backend/data/webui.db')
> cur = conn.cursor()
> cur.execute('SELECT settings FROM user')
> for r in cur.fetchall():
>     s = json.loads(r[0]) if r[0] else {}
>     print(s.get('ui', {}).get('webSearch', 'not set'))
> "
> ```

#### 两种模式对比

| | RAG Web Search | Native FC Web Search |
|--|----------------|---------------------|
| 前提 | `function_calling ≠ native` | `function_calling = native` |
| 🌐 按钮作用 | 开启=每条消息都触发搜索 | 开启=授权模型调用搜索工具（按需判断） |
| Default Features: Web Search | **关闭**（避免每条消息都搜索） | 按需（开=模型自主搜索；关=省 tokens 但需手动 🌐） |
| 搜索词生成 | Task Model (gpt-4o-mini) | 主模型自主生成 |
| 搜索语言 | 由 Query Template 控制（可强制英文） | 由模型自主决定 |
| Builtin Tools: Web Search | 不需要 | **必须开启** |
| 可控性 | 用户手动控制 | 模型自主，依赖模型判断力 |

---

## 2. 性能优化：Builtin Tools 的 Prompt 膨胀

### 2.1 原理

在 `function_calling = native` 模式下，开启的 Builtin Tools 会将工具 schema 注入 prompt。
**即使本轮不实际调用任何工具**，schema 也会占用 `prompt_tokens`，从而增加 prefill 时间。

> 当前环境下 decode 速度基本稳定（约 8.4-8.7 tok/s），主要瓶颈是输入侧 prefill，
> 不是输出侧 generation。"发送后到进入 thinking 前的等待"主因是工具 schema 注入
> 导致的 prefill 增长。

### 2.2 各工具 Token 开销实测

测试方法（2026-02-17，Open WebUI v0.8.2 + MiniMax M2.5 UD-Q5_K_XL）：
固定提示词 `只回复"OK"，不要调用任何工具。`，每次新建会话，逐个关闭 Builtin Tools，
记录 `prompt_tokens`（`prompt_ms` 受前缀缓存影响，以 `prompt_tokens` 为准）。

| 配置状态 | prompt_tokens | 相对全开变化 |
|---|---:|---:|
| 全开（Deep 配置） | 2,130 | baseline |
| 关 Knowledge Base | 1,341 | **-789** |
| 再关 Notes | 860 | **-481** |
| 再关 Chat History | 604 | **-256** |
| 再关 Memory | 604 | ~0 ⚠️ |

> **⚠️ Memory ~0 的数据不准确**：测试时用户级 Memory 全局开关（头像 → Settings → Memory）
> 未开启，导致 Memory 工具 schema 实际未注入。开启后 Memory 有非零 token 开销。

**开销排序**：`Knowledge Base (789) > Notes (481) > Chat History (256) > Memory (待重测)`

> 早期发现的 Code Interpreter（~500 tokens）也是重量级工具，
> 另外会在浏览器端加载 pyodide（Python WASM 运行时），增加前端延迟。

### 2.3 优化建议

基于实测数据的核心原则：**仅开启必要的 Builtin Tools**，每多开一个都增加 prompt_tokens。

**Capabilities**（纯文本模型如 MiniMax M2.5）：
- ✅ File Upload, File Context, Web Search, Citations, Status Updates, Builtin Tools, Usage
- ❌ Vision（纯文本模型不支持）
- ❌ Code Interpreter, Image Generation（按需开启）

**Builtin Tools**：
- Knowledge Base、Notes、Chat History 是主要开销源，建议默认关闭，按需开启
- Time & Calculation 几乎无额外开销，可常开
- Memory 需用户级全局开关开启后才实际注入，有非零开销（需按需评估）

**Default Features**：Web Search 存在 **TTFT vs 便利性的取舍**：
开启时 `search_web` schema 注入 prompt（增加 tokens）但模型能自主搜索；
关闭则省 tokens 但需手动点击 🌐。根据使用频率选择。

完整推荐配置详见 **Section 9**。

---

## 3. Web 搜索功能配置

> **重要**：本节的前置条件和搜索流程取决于 `function_calling` 设置，详见 Section 1.5-1.6。

### 3.1 前置条件

#### Native FC 模式（`function_calling = native`，推荐）

需满足 Section 1.6 机制 B 的四道门控条件（Capabilities、Builtin Tools、Admin 全局开关、🌐 按钮）。

> 🌐 按钮在 native FC 下的含义是"授权模型使用搜索工具"，而非"每条消息都搜索"。
> 可通过 Default Features 设置为默认开启，或手动按需点击（详见 Section 2.3 TTFT 取舍）。

#### 非 Native FC 模式（RAG 搜索）

| 条件 | 设置位置 | 作用 |
|------|---------|------|
| 模型开启 Web Search | Model Settings → Capabilities | UI 显示 🌐 按钮 |
| Admin 配置搜索引擎 | Admin Panel → Settings → Web Search | 全局开关 + 搜索引擎后端 |
| 聊天中手动开启 | 输入框旁 🌐 按钮 | 本次聊天触发搜索（按钮开启时**每条消息**都会搜索） |

> **注意**：🌐 按钮是手动开关。开启后该聊天中的每条消息都会触发搜索，
> 不需要搜索时请手动关闭。建议 Default Features 中不要默认开启 Web Search。

### 3.2 搜索引擎选项

| 引擎 | API Key | 说明 |
|------|---------|------|
| **SearXNG** | 不需要 | **推荐**。自建容器，聚合 Google/Bing 等多引擎，无限量，中文质量好 |
| **DuckDuckGo** | 不需要 | 零配置，有速率限制，中文查询质量差 |
| **Brave Search** | 需要（免费 2000次/月） | 质量好 |
| **Google PSE** | 需要（免费 100次/天） | 中文搜索质量好 |

> **SearXNG 已集成到 Docker Compose**：Ansible 部署时自动启动 SearXNG 容器，
> 与 Open WebUI 共享 Docker 网络，内部地址 `http://searxng:8080`。
> 只需在 Admin Panel 切换搜索引擎即可使用（见 3.3）。

### 3.3 Admin 面板配置

**位置**：Admin Panel → Settings → Web Search

推荐设置：

| 设置项 | 推荐值 | 说明 |
|--------|--------|------|
| Web Search | 开启 | 全局开关 |
| Web Search Engine | SearXNG | 自建元搜索引擎，聚合多引擎结果 |
| SearXNG Query URL | `http://searxng:8080` | Docker 内部网络地址 |
| Search Result Count | 5 | 结果数量（SearXNG 聚合多引擎，可适当增大） |
| Bypass Embedding and Retrieval | ✅ | **关键优化**：跳过向量化，直接传摘要给模型 |
| Bypass Web Loader | ✅ | **关键优化**：不抓取完整网页，只用搜索引擎摘要 |

> **从 DuckDuckGo 迁移**：如果之前使用 DDGS，只需将 Engine 改为 SearXNG 并填入 Query URL。
> SearXNG 默认启用 Google、Bing、DuckDuckGo、Wikipedia 等引擎，中文搜索质量显著优于单一 DDGS。

也可以通过数据库配置（适用于无法访问 Admin 面板的情况）：

> **⚠️ 修改数据库前建议备份**：`docker cp open-webui:/app/backend/data/webui.db ./webui.db.bak`
> 本文多处使用直接修改数据库的方式，出错时可通过备份恢复。

```bash
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute('SELECT data FROM config WHERE id=1')
cfg = json.loads(cur.fetchone()[0])

cfg.setdefault('rag', {}).setdefault('web', {}).setdefault('search', {})
cfg['rag']['web']['search']['enable'] = True
cfg['rag']['web']['search']['engine'] = 'duckduckgo'
cfg['rag']['web']['search']['bypass_embedding_and_retrieval'] = True
cfg['rag']['web']['search']['bypass_web_loader'] = True

cur.execute('UPDATE config SET data=? WHERE id=1', (json.dumps(cfg),))
conn.commit()
conn.close()
"
docker restart open-webui
```

### 3.4 搜索词生成模板（Query Prompt Template）

> **注意**：此模板仅用于 **RAG Web Search**（非 native FC 模式）。
> Native FC 模式下，模型自主决定是否搜索及搜索词，不使用此模板。

Open WebUI 使用 Task Model 根据聊天历史判断是否需要搜索并生成搜索词。
默认模板使用对话原始语言生成搜索词，且比较激进（倾向于搜索）。
推荐替换为以下自定义版本——强制英文搜索词 + 保守触发策略：

**位置**：Admin Panel → Settings → Web Search → Query Generation Prompt（或通过数据库修改）

当前推荐模板：

```bash
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute('SELECT data FROM config WHERE id=1')
cfg = json.loads(cur.fetchone()[0])

cfg.setdefault('task', {}).setdefault('query', {})
cfg['task']['query']['prompt_template'] = '''### Task:
Analyze the chat history to determine if the user is asking a question that **requires up-to-date or factual information from the web**. Generate search queries ONLY when genuinely needed. **Always generate search queries in English**, regardless of the conversation language.

### When to search (return queries):
- User asks about current events, news, or recent developments
- User asks factual questions (statistics, dates, technical specs, prices)
- User asks about specific products, services, or organizations
- User needs information that may have changed since the model training cutoff

### When NOT to search (return empty list):
- Casual conversation, greetings, or personal statements (e.g. \"my name is...\", \"remember this\")
- Creative writing requests (poems, stories, code generation)
- Requests about the AI itself or its capabilities, memory, or settings
- Math calculations or logical reasoning tasks
- Translation or language tasks
- Summarizing or rephrasing user-provided text
- Opinions, advice, or brainstorming that do not need external facts

### Guidelines:
- Respond **EXCLUSIVELY** with a JSON object. No extra text.
- **IMPORTANT: Always write queries in English**, translating intent from any language.
- When searching, return 1-3 concise, distinct queries: { \"queries\": [\"query1\", \"query2\"] }
- When no search is needed, return: { \"queries\": [] }
- **Default to NOT searching** unless the query clearly needs external information.
- Today\\'s date is: {{CURRENT_DATE}}.

### Output:
Strictly return JSON: { \"queries\": [\"...\"] } or { \"queries\": [] }

### Chat History:
<chat_history>
{{MESSAGES:END:6}}
</chat_history>
'''

cur.execute('UPDATE config SET data=? WHERE id=1', (json.dumps(cfg),))
conn.commit()
conn.close()
"
docker restart open-webui
```

与默认模板的关键区别：
- 明确列出了"不需要搜索"的场景（问候、创意写作、翻译等）
- 默认倾向**不搜索**，除非明确需要外部信息
- 强制输出英文搜索词，提高 DuckDuckGo 搜索质量

### 3.5 Web 搜索性能分析

> **注意**：以下耗时分析基于 **RAG Web Search** 路径（非 native FC 模式）。
> Native FC 模式下，搜索由主模型在回复过程中自主触发，流程不同。

RAG 模式下每条消息的处理流程和耗时（以本地 M2.5 @ 8 tok/s 为例）：

| 步骤 | 耗时 | 说明 |
|------|------|------|
| LLM 生成搜索词 | ~30s | 用主模型生成查询（可用 Task Model 优化到 <1s） |
| DuckDuckGo 搜索 | ~3s | 搜索引擎查询 |
| LLM 生成回复 | ~50-60s | 含 thinking 时间（`<think>` 标签内容不可见） |
| **合计** | **~85-95s** | 开启 Bypass 后；未开启 Bypass 需额外 ~30s |

> 在 "Searched X sites" 出现后到 "Thought for X seconds" 之间的空白，
> 是模型在生成 `<think>` 标签内的隐藏推理内容，UI 不显示直到 `</think>` 结束。

---

## 4. Task Model（外部辅助模型）

### 4.1 Task Model 的作用

Open WebUI 的部分辅助任务可以交给独立的"Task Model"处理，不占用主模型的推理资源。

**Task Model 负责的任务**：

| 任务 | 说明 | 是否需要 Task Model |
|------|------|-------------------|
| **标题生成** | 新聊天后自动生成对话标题 | 推荐（本地模型 ~30s 且可能 500 错误） |
| **标签生成** | 自动给对话打标签 | 推荐 |
| **搜索词生成** | RAG Web Search 路径下生成搜索关键词 | **仅非 native FC 模式需要** |
| Follow-up 建议 | 生成后续问题建议 | 推荐 |
| Emoji 生成 | 为对话生成 emoji 标识 | 轻量，影响不大 |
| Autocomplete | 输入框自动补全建议 | 轻量，影响不大 |

> **背景**：Task Model 最初引入是为了加速 RAG Web Search 的搜索词生成（从 ~30s 降到 <1s）。
> 切换到 `function_calling = native` 后，搜索词生成改由主模型自主完成，
> 但 Task Model 仍对标题/标签生成有价值——避免占用 llama-server 唯一的 slot（`--parallel 1`）
> 且避免复杂请求导致的 500 错误。

### 4.2 配置

**先看 Task Model 区域里有哪些设置（Admin → Settings → Interface → Tasks）**

- `Local Task Model`：当前聊天模型被识别为 `local` 时优先使用
- `External Task Model`：当前聊天模型被识别为 `external` 时优先使用
- `Title Generation`：自动生成会话标题
- `Follow Up Generation`：自动生成追问建议
- `Tags Generation`：自动生成标签
- `Retrieval Query Generation`：RAG 检索查询生成
- `Web Search Query Generation`：Web 搜索词生成（主要用于非 native FC 路径）
- 上述任务都有对应 Prompt，可按需自定义

**Web UI 方式（推荐）**

1. 打开 `Admin → Settings → Connections`，在 OpenAI API 区域点 `+` 新增连接  
   `URL=https://api.openai.com/v1`，`Provider Type=OpenAI`，`API Type=Chat Completions`，`Model IDs=gpt-4o-mini`（不要留空）
2. 打开 `Admin → Settings → Interface → Tasks`
3. 将 `External Task Model` 设为 `gpt-4o-mini`
4. 保留你需要的任务开关（标题/标签/追问等）
5. 保存后新建会话验证

**数据库方式（兜底）**

如果 UI 版本差异导致无法设置，可直接写入配置：

```bash
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute('SELECT data FROM config WHERE id=1')
cfg = json.loads(cur.fetchone()[0])

cfg.setdefault('task', {}).setdefault('model', {})
cfg['task']['model']['external'] = 'gpt-4o-mini'

cur.execute('UPDATE config SET data=? WHERE id=1', (json.dumps(cfg),))
conn.commit()
conn.close()
"
docker restart open-webui
```

**费用**：gpt-4o-mini 约 $0.00005/次，日常使用每月不到 $0.50。

### 4.3 删除 Task Model

如果不再需要外部 Task Model（所有辅助任务回到本地模型）：

Web UI 方式（推荐）：

1. 打开 `Admin → Settings → Interface → Tasks`
2. 将 `External Task Model` 改为 `None`（或清空）
3. 保存后新建会话验证

数据库方式（兜底）：

```bash
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute('SELECT data FROM config WHERE id=1')
cfg = json.loads(cur.fetchone()[0])

# 移除 external task model
cfg.get('task', {}).get('model', {}).pop('external', None)

cur.execute('UPDATE config SET data=? WHERE id=1', (json.dumps(cfg),))
conn.commit()
conn.close()
"
docker restart open-webui
```

然后在 `Admin → Settings → Connections` 中删除 OpenAI API 连接（如果不再需要）。

> **注意**：删除 Task Model 后，标题/标签生成会回到本地 M2.5，
> 在 `--parallel 1` 下会占用唯一的 slot，用户请求需等待。

### 4.4 为什么不用本地模型做 Task Model

考虑过将 Task Model 从 gpt-4o-mini 换回本地 MiniMax M2.5，但在当前环境下不推荐：

1. **Slot 争用**：llama-server 运行在 `--parallel 1`（单 slot），后台任务（标题、标签、
   follow-up 建议等）会与用户对话争抢唯一的 slot，造成明显延迟
2. **速度差距**：本地模型生成标题需 ~30s，gpt-4o-mini 不到 1s
3. **500 错误风险**：本地模型处理含工具参数的标题生成请求时可能返回 500（详见 Section 8）
4. **费用极低**：gpt-4o-mini 约 $0.50/月，远低于体验损失

**但在以下条件满足时，本地 Task Model 也是可行的**：

- `--parallel` 足够大，能覆盖前台请求 + 后台任务并发
- 本地模型速度足够快（标题/标签等任务通常 1-3 秒内完成）
- 压测下无明显排队，且稳定性（5xx/超时）可接受

满足以上条件时，可以把 Task Model 切到本地模型，以减少外部 API 依赖。

**维护要点**：

- 确保 OpenAI Connection 的 **Model IDs** 包含 `gpt-4o-mini`，否则会出现 `404: Model not found`
- 所有 M2.5 模型配置（Fast / Deep 等）统一设置 `function_calling = native`，
  避免不同 profile 走不同的搜索路径（RAG vs Native FC），导致行为不一致

### 4.5 选路逻辑：什么时候用 Local Task Model，什么时候用 External Task Model

Open WebUI 的 `local/external` 是**连接器语义**，不是物理位置语义（不是"模型在不在本机"）。

- `Ollama API` 连接默认 `connection_type = local`
- `OpenAI API` 连接默认 `connection_type = external`
- 即使 llama-server 在本机，只要通过 OpenAI-compatible 接入，默认也按 `external` 处理

Task 路由规则（源码：`open_webui/utils/task.py`）：

1. 先以当前会话模型作为默认 task model
2. 若默认模型 `connection_type == local`，优先尝试 `Task Model (Local)`
3. 否则优先尝试 `Task Model (External)`
4. 若配置的 task model 不存在于当前模型列表，回退到当前会话模型

### 4.6 双 OpenAI Connection（本地 llama-server + OpenAI）时会选哪个？

假设你有两个 OpenAI 连接：

- `http://host.docker.internal:8080/v1`（本地 llama-server）
- `https://api.openai.com/v1`（OpenAI）

因为两者都在 OpenAI connector 下，默认都属于 `external` 分支，Task 会看 `Task Model (External)` 这个字段：

- `Task Model (External) = gpt-4o-mini`：任务走 OpenAI
- `Task Model (External) = MiniMax-M2.5`：任务走本地 llama-server
- 留空：回退到当前会话模型

> 建议给连接配置 `Prefix ID`（如 `local.`、`cloud.`）防止模型名冲突时误选。

### 4.7 `404: Model not found` 快速排障

按顺序检查，通常 2-3 分钟可定位：

1. 验证后端真实模型 ID（以 `/v1/models` 返回为准）
2. 检查 OpenAI Connection 的 `Model IDs` 是否包含该模型
3. 检查 `Task Model (External)` 是否设置成了一个不存在的模型 ID
4. 若刚改过连接或模型，刷新模型列表并新建会话重试

后端校验命令：

```bash
curl -sS --max-time 10 http://127.0.0.1:8080/v1/models | python3 -m json.tool
```

查看 Open WebUI 当前 task model 配置：

```bash
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cfg = json.loads(cur.execute('SELECT data FROM config WHERE id=1').fetchone()[0])
print(json.dumps(cfg.get('task', {}).get('model', {}), ensure_ascii=False, indent=2))
conn.close()
"
```

---

## 5. llama-server 模型别名

### 5.1 问题

llama-server 的 `/v1/models` 接口默认返回模型文件的完整路径作为 ID，
导致 Open WebUI 模型列表中出现类似
`/data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-...` 的难看条目。

### 5.2 解决方案

给 llama-server 添加 `--alias` 参数：

```bash
llama-server --model /path/to/model.gguf --alias MiniMax-M2.5 ...
```

Ansible 配置（`defaults/main.yml`）：

```yaml
llm_server_model_alias: "MiniMax-M2.5"
```

服务模板（`llama-server.service.j2`）中自动添加：

```jinja2
{% if llm_server_model_alias | default('') | length > 0 %}
    --alias {{ llm_server_model_alias }} \
{% endif %}
```

设置后，Open WebUI 侧也要把模型引用切到新别名。

Web UI 方式（推荐）：

1. 打开 `Admin → Settings → Connections`，在 llama-server 连接上点刷新模型列表
2. 打开 `Admin → Models`，分别编辑你的自定义模型（如 `M2.5 Fast` / `M2.5 Deep`）
3. 将 `Base Model ID`（或 Base Model）从旧路径改为 `MiniMax-M2.5`
4. 保存后新建会话验证

若 UI 无法保存或历史数据较多，再用数据库方式批量更新：

```bash
docker exec open-webui python3 -c "
import sqlite3
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
old_id = '/data/models/UD-Q5_K_XL/MiniMax-M2.5-UD-Q5_K_XL-00001-of-00005.gguf'
new_id = 'MiniMax-M2.5'
cur.execute('UPDATE model SET base_model_id=? WHERE base_model_id=?', (new_id, old_id))
print(f'Updated {cur.rowcount} models')
conn.commit()
conn.close()
"
docker restart open-webui
```

---

## 6. System Prompt 最佳实践

### 6.1 当前日期感知

LLM 的训练数据有截止日期（如 MiniMax M2.5 截止到 2024 年 4 月），模型默认不知道"今天"是哪一天。

有两种方式让模型获取当前日期：

#### 方式 A：Builtin Tools Time & Calculation（推荐，需 native FC）

开启 `function_calling = native` + `Builtin Tools: Time & Calculation ✅` 后，
模型可以通过 function calling 自主调用时间工具获取当前日期。

**前提**：`function_calling = native` 必须开启，否则模型无法识别和调用工具（见 Section 1.5）。

#### 方式 B：System Prompt `{{CURRENT_DATE}}`（备选）

在 System Prompt 中使用模板变量，Open WebUI 会自动替换为当天日期：

```
今天是 {{CURRENT_DATE}}。默认简短直答，除非我要求再展开。
```

适用场景：
- 非 native FC 模式下，Time 工具无法被调用时的唯一途径
- 想省去一次 tool call 往返延迟时

---

## 7. Connections 清理

### 关闭未使用的 Ollama 连接

如果没有运行 Ollama，建议在 Connections 页面关闭 Ollama API，
避免持续的连接错误日志：

```
Connection error: Cannot connect to host host.docker.internal:11434
```

---

## 8. 标题生成 500 错误

### 现象

在聊天完成后，llama-server 日志出现：

```
status=500 method="POST" path="/v1/chat/completions"
```

### 原因

Open WebUI 在用户收到回复后会自动发送一个**标题生成请求**。
当 `--parallel 1`（单 slot）时，标题生成和用户请求串行处理。
标题生成请求可能因格式问题（如包含工具参数）导致 500 错误。

### 影响

标题生成在主回复**之后**发生，不影响用户看到回复的速度，
但会导致聊天标题无法自动生成（显示为默认标题）。

### 缓解

- 关闭不必要的 Capabilities（尤其是 Code Interpreter）可减少标题生成请求的复杂度
- 配置外部 Task Model（如 gpt-4o-mini）后，标题生成走外部 API，不经过 llama-server

---

## 9. 推荐配置清单

### MiniMax M2.5 模型设置（Native FC 模式，TTFT 优化后）

```
Advanced Params:
  function_calling = native            ← 关键：启用原生 function calling
  stream_response = true               ← 流式输出
  top_p = 0.9

System Prompt:
  简单问题简短回答，不要过度思考和输出。

Capabilities:
  ✅ Builtin Tools                     ← 总开关，必须开启
  ✅ Web Search                        ← 能力声明 + 工具注入门控
  ✅ File Upload, File Context, Citations, Status Updates
  ✅ Usage                             ← 便于持续观测 token 用量
  ❌ Vision                            ← 纯文本模型不支持
  ❌ Code Interpreter, Image Generation ← 按需开启

Default Features:
  ❌ Web Search                        ← 默认关闭以减少 prompt_tokens；需要搜索时手动 🌐

Builtin Tools（仅保留必要工具，详见 Section 2.2 实测开销）:
  ✅ Time & Calculation                ← 轻量，时间/计算
  ✅ Web Search                        ← native FC 下搜索依赖此工具
  ✅ Memory                            ← 需用户级全局开关（头像→Settings→Personalisation→Memory）
  ❌ Knowledge Base                    ← 按需开启（-789 tokens）
  ❌ Notes                             ← 按需开启（-481 tokens）
  ❌ Chat History                      ← 按需开启（-256 tokens）
  ❌ Channels, Code Interpreter, Image Generation
```

> **注意**：
> - TTFT 优化的核心是减少 Builtin Tools 注入的 prompt_tokens（详见 Section 2.2）
> - Default Features: Web Search 关闭意味着新建聊天时模型默认没有搜索权限，
>   需要搜索时手动点击 🌐 按钮（🌐 是 native FC 工具注入的 Gate 4，详见 Section 1.6）
> - 如果搜索使用频繁，可改为默认开启 `defaultFeatureIds: ["web_search"]`，以便利性换取少量 TTFT

### Admin 全局设置

```
Web Search:
  引擎 = SearXNG (自建元搜索引擎)
  SearXNG Query URL = http://searxng:8080
  Bypass Embedding and Retrieval = 开启
  Bypass Web Loader = 开启
  Search Result Count = 5
  Query Generation = 自定义模板（英文搜索词）

Task Model (External) = gpt-4o-mini
Task Model (Local) = Current Model

Connections:
  OpenAI API #1: http://host.docker.internal:8080/v1 (本地 llama-server)
  OpenAI API #2: https://api.openai.com/v1 (Task Model, Model IDs = gpt-4o-mini)
  Ollama API: 关闭（未使用）
```

> 说明：本地 llama-server 虽然部署在本机，但在 OpenAI connector 下默认属于 `external`。
> 因此实际任务路由看 `Task Model (External)`，不是 `Task Model (Local)`。

### 用户设置（头像 → Settings）

```
Interface:
  Web Search: 非 "always"（避免强制每条消息触发搜索，详见 Section 1.6 陷阱说明）

Personalisation->Memory:
  Memory: 开启（Builtin Tools Memory 的前提条件，不开则工具不注入）
```

### llama-server 参数

```
--alias MiniMax-M2.5      # 干净的模型名称
--parallel 1              # 单 slot（受 VRAM 限制）
--reasoning-format auto   # deep profile 自动决定是否思考
```

> 注意：`--parallel 1` 意味着标题生成和聊天请求串行执行，
> 用户发消息时如果正在生成标题，需要等待。
> 配置外部 Task Model 后，标题生成走 OpenAI API，不占用本地 slot。

---

## 10. 调试技巧

### 查看实际 prompt token 数

```bash
# 监控 llama-server 日志，观察 n_prompt_tokens_processed
journalctl -u llama-server -f | grep prompt_eval
```

无 Builtin Tools 时简单问题约 30-50 tokens；当前推荐配置（native FC + 最小工具集）下
baseline 约 **600 tokens**（详见 Section 2.2）。如果远超此值，说明开启了过多工具。

### 查看 Open WebUI 请求日志

```bash
docker logs open-webui -f 2>&1 | grep -E 'POST|500|error'
```

### 查看搜索词生成结果

在 llama-server 日志中搜索 `queries` 相关的请求，
观察生成的搜索词是否为英文、是否合理。

### 直接查看/修改数据库配置

```bash
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
cur = conn.cursor()
cur.execute('SELECT data FROM config WHERE id=1')
print(json.dumps(json.loads(cur.fetchone()[0]), indent=2, ensure_ascii=False))
conn.close()
"
```

### Task Model 相关问题快速检查

```bash
# 1) 本地 llama-server 是否正常返回模型列表
curl -sS --max-time 10 http://127.0.0.1:8080/v1/models | python3 -m json.tool

# 2) Open WebUI 中 task model 当前配置
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/webui.db')
cfg = json.loads(conn.cursor().execute('SELECT data FROM config WHERE id=1').fetchone()[0])
print('task.model.default =', cfg.get('task', {}).get('model', {}).get('default'))
print('task.model.external =', cfg.get('task', {}).get('model', {}).get('external'))
conn.close()
"
```
