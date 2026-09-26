# Multica：BMAD Team 配置

版本：v4 修订 7.6.1。更新：2026-09-23。只创建一支 Squad，复用五个 BMAD 业务 persona 与一个轻量 Coordinator。

此文件是 Profile/Squad 的配置源与操作说明，不是 Multica 自动导入 schema。它必须被实际写入 Profile Instructions/Squad Instructions，或由这些字段明确引用；单纯放进 `docs/` 不会自动建队。

## T0. 两个包，分别安装

**包 1 · 跨模型评审（宿主无关，8 个文件）** —— 不依赖 Multica，换 agent 时原样可用：

```text
docs/agent/bmad-cross-model-review.md        PAL 调用层、runtime 配置、边界、预检、冒烟、账单对账
docs/agent/bmad-review-routing.md            哪些 reviewer 走 Claude、哪些保留原生
_bmad/custom/bmad-build-auto.toml
_bmad/custom/bmad-review.toml
_bmad/custom/bmad-qa-generate-e2e-tests.toml
_bmad/custom/bmad-architecture.toml
_bmad/custom/bmad-build.toml
_bmad/custom/bmad-code-review.toml
```

**包 2 · Multica 适配器（2 个文件）** —— 就是本文件和执行合同：

```text
docs/agent/bmad-multica-contract.md          授权、派工、Issue 状态、回滚
docs/agent/multica-team.md                   本文件：Profile / Squad / 模型档位 / Instructions
```

两个包装进同一个项目时目录结构合并，共 10 个文件。**只要跨模型评审、不用 Multica 的人只装包 1。** 换掉 Multica 时只重写包 2。

基础接入顺序（只需要包 2 + 项目已有 BMAD）：

1. 确认目标项目已有可用的 BMAD 安装，核对实际 Skill 与 customization 字段。没有安装时单独执行获准的 BMAD 安装任务，不把本包当安装器。
2. 在独立任务分支把文件逐项比较、合并到同名路径，保留项目既有约束。每个 TOML 覆盖只作用于自己的 Skill；安装版本不兼容时先适配，不能覆盖原生安装文件。
3. 在 Multica 创建或复用六个 Profile，按 T1 选择实际机器的 Codex runtime、模型和 Thinking；将 T4 的共同前缀与角色原文写入 Instructions。复用同一工作区团队时只同步指令，不复制六个新 Agent。
4. 创建或复用 BMAD Team，核对 Leader、五个成员、T5 Role 与 Instructions。项目路径放在 Project Resources；普通 Git 项目可用 GitHub repo + ref，本地未提交资料需要匹配 daemon 的 local_directory 或明确的输入传递方式。
5. Issue 设置 Project 和 BMAD Team；Chat 则先选择 Agent，并通过 + → Project context 关联项目。对"继续旧需求"先验证能找到旧记录、选择实际 Skill、恢复模式并提出下一问。
6. 将已批准的文件更新通过项目既有 Git 流程交付，并确认后续 Run 获取的版本包含它们。只把 ZIP 解压到人工目录，不保证远端 checkout 能读到。

**审核专项另行接入**：要执行跨模型评审，按包 1 的 `docs/agent/bmad-cross-model-review.md` 完成PAL runtime 配置（X2）、配置预检（X6）和实机冒烟（X7）。安装文件、保存 Profile、完成普通规划都不代表该审核通道已经可用。独立 QA 按测试权限和环境执行。

迁移到另一项目时，重新确认资源、BMAD 版本/路径、已有文档及该项目授权；旧项目的绝对路径不作为模板复制。模型仍采用 T1 的明确默认目标，目标 runtime 不支持时明确处理，不静默替换。

**修订 7 的变化。** ①按宿主相关性把包拆成两个，六个 TOML 的 `persistent_facts` 改指宿主无关的核心文档，不再强制每个 BMAD workflow 加载一份 Multica 执行政策。②合并修订 5.1 的评论收件人路由（T3.2 与共同前缀），解决普通问答空唤醒 Leader 的问题。③此前修订已删除 G0 门禁与本地预算账本，理由见核心文档 X1；升级时清除 `BMAD_REVIEW_GATE_FILE`、`BMAD_REVIEW_GATE_SHA256`、`BMAD_REVIEW_ISSUE_MAX_USD`、`BMAD_REVIEW_BUDGET_DB`、`BMAD_CONTROL_DIR`、`BMAD_STATE_DIR` 及相关受信副本，不要保留半套。

## T1. 成员、具体模型、推理档位与权限

以下是本项目已确定的**默认配置目标**，不留空继承 CLI 全局默认。六个 Multica Profile 均绑定 Codex runtime；Claude/Gemini 是内部审核调用，不是第七个 Profile。

| 执行身份 | Runtime／调用方式 | 具体模型 ID | 推理档位 | 配置位置 |
|---|---|---|---|---|
| BMAD Coordinator | Codex | `gpt-5.6-luna` | `medium` | Multica Profile：Model + Thinking level |
| Mary · Analyst | Codex | `gpt-5.6-sol` | `high` | 同上 |
| John · Product Manager | Codex | `gpt-5.6-sol` | `high` | 同上 |
| Winston · Architect | Codex | `gpt-6-astra` | `high` | 同上 |
| Sally · UX Designer | Codex | `gpt-5.6-sol` | `high` | 同上 |
| Amelia · Developer（包括 QA 任务） | Codex | `gpt-5.6-terra` | `medium` | 同上；QA 不另建 Profile |
| 内部 reviewer（每个有效 layer／lens） | PAL clink → 已批准 CLI | Claude 默认 `claude-opus-5-5`；Gemini 待选定验证 | 按 provider 配置 | reviewer-selection.json + client JSON |

五个 BMAD persona 仍对应 Mary=`bmad-agent-analyst`、John=`bmad-agent-pm`、Winston=`bmad-agent-architect`、Sally=`bmad-agent-ux-designer`、Amelia=`bmad-agent-dev`；Coordinator 只做调度。创建后将 Amelia 的 Concurrency 设为 6，其余五个设为 1。一个 Amelia Profile 可运行多个独立子 Issue，每项有自己的任务上下文与隔离工作目录。实际并发还受机器总容量限制；有 6 个槽位不代表必须同时启动 6 项。[O8] 创建页的 Speed 显式选 Standard，Thinking 不留在 Follow CLI config。这些是本项目默认设置，不是模型能力排名。

**配置明确与账号验收是两回事。** 官方当前文档列出了上述模型 ID 与配置入口；但尚未在你的账号、Multica runtime 和代理链中实测。模型不可用时报告该项失败并等明确替代决定，不清空 Model，不静默换型号/供应商，也不因为 `medium` 不被接受就自动改为 `high`。[O1][O2][O3]

OpenAI 的 `medium`／`high` 写入 Profile 的 **Thinking level**，不是在 Instructions 中写"请深入思考"；也不要向 Custom arguments 重复追加 `--model`。Claude 的 `high` 是 PAL Claude client JSON 中的 CLI 参数，与 Amelia 自身的 `medium` 无关。

运行时需提供项目读访问、原生 Skill 可见性和相应工具。仅 Amelia/QA 获得相应允许的代码/测试写入；Coordinator 的管理权限和业务代码写入分开。仅在你明确批准时才做一次性模型升级；保留本表作为回归默认值。

**PAL 接入位置。** 执行审核入口的 runtime 必须能调用 clink，并使用本 Run 的源码视图与角色目录；模型、预算、超时在 PAL client JSON 配置。旧 BMAD_REVIEW_* 仅在所有旧 Run/项目迁移后清理，Coordinator 不负责配置。见核心文档 X2/X3。

### T1.1 实机创建页：字段、来源与明确填写值

已检查的创建路径是 Agents → New agent → Start blank。该页依次提供 Name、Description、Instructions、Conversation starters、Skills、Runtime、Model、Thinking、Speed 和 Access。Concurrency、Environment 与 Custom Args 不在创建页；只能在创建后的 Settings 中配置。

| 实机字段 | 六个新 Profile 的明确填写方式 |
|---|---|
| Name | 使用 T1 的 Profile 名称。 |
| Description | 仅写一句给 Leader/人阅读的职责摘要；不把规则、模型或权限边界放在此处。 |
| Instructions | 粘贴 T4 的共同前缀和该角色的完整段落。 |
| Conversation starters | 首次创建保留内建默认值；不把工作流或授权写成自动发送的建议。 |
| Skills | 项目 BMAD 不在此绑定。其他已评审的通用 Workspace Skill 可按需保留；不要为 BMAD 使用 Copy from runtime、local folder、ZIP、URL 或手工创建第二份 Workspace 副本。 |
| Runtime | 选择目标项目所在机器的 Codex runtime，并确认它在线。不要因为内部 Claude 审核而把六个 Profile 改为 Claude runtime。 |
| Model | 从可见的模型选项中点击 T1 对应项，而不是留空使用 provider default。 |
| Thinking | 从选项中显式点击 Medium 或 High；不得保留 Thinking · Follow CLI config。 |
| Speed | 点击 Standard；不要在首次联调选择 Fast。 |
| Access | 新建 Profile 先选择 Only me。只有需要其他工作区成员直接启动 Run 且已评审权限边界时，才改为 Entire workspace 或 Specific people。 |

模型选择器实际显示的目标项：

| Profile | 要点击的 Model | 要点击的 Thinking |
|---|---|---|
| BMAD Coordinator | GPT-5.6 Luna（gpt-5.6-luna） | Medium |
| Mary · Analyst | GPT-5.6 Sol（gpt-5.6-sol） | High |
| John · Product Manager | GPT-5.6 Sol（gpt-5.6-sol） | High |
| Winston · Architect | GPT-6 Astra（gpt-6-astra） | High |
| Sally · UX Designer | GPT-5.6 Sol（gpt-5.6-sol） | High |
| Amelia · Developer | GPT-5.6 Terra（gpt-5.6-terra） | Medium |

新建后逐个打开 Settings → General，把 Amelia 的 Concurrency 设为 6，其他五个设为 1。执行审核入口的 runtime 按核心文档 X2 配置 PAL MCP 与每 Run 目录。接着打开 Capabilities → Skills，只验证实际发现的运行时继承 Skill；不要复制、导入或启用一份 Workspace BMAD 来"补齐"列表。运行时继承的 installbmad 只用于安装、更新或修复 BMAD，不是日常 workflow 的授权。

## T2. 项目定位与原生流程选择

Coordinator 的完整执行指令及能力索引直接放在 T4 的 Profile 段落中。它启动在空 workdir 时仍能按项目资源定位资料，不依赖先读到本文件才知道怎么开始。先定位材料，再选择工作流；项目目录已经给出时不重复询问。

项目级 BMAD 默认采用所用 runtime 支持的项目目录：本包六个 Codex Profile 使用 .agents/skills；Claude 的项目适配器通常在 .claude/skills。它们不自动注册为 Workspace Skills。不要为获得 Multica 的斜杠菜单重复导入一套 BMAD；派工写完整 Skill ID。

当前安装的 bmad-help 使用本项目 bmad-help.csv 与配置解析器；其他版本按它实际的 SKILL.md 执行，不硬编码"main 叫 bmad"或要求并不存在的 manifest API。目录清单、宿主 active Skill 清单、工作流是否真正执行是三种证据，不互相冒充。

## T3. 执行者映射与具体派工

唯一的可粘贴能力索引位于 T4 的 BMAD Coordinator 代码块，随 Profile 直接部署。它列出意图、完整 Skill ID 和默认执行者，仅用于路由，不决定流程顺序或完成条件。Coordinator 必须读取当前 workflow 的实际步骤；路径不明时实际执行项目的 bmad-help。目标项目安装版本不同，应核对该项目的 Skill、菜单和目录后更新本索引。

"交接"仅指现有文档/会话记录以及一条普通派工评论，不增加 handoff.md 或新 schema。继续脑暴时，评论说明执行 bmad-brainstorming 的 Resuming、真实 .memlog.md 位置、原来的 partner 等模式及待继续的问题。tracked 文件给相对路径与可用版本，untracked 本地记录给真实来源路径。

聊天历史不会自动共享给所有 Issue/成员。已经形成的项目资源使用现有配置；聊天里才有、又不能从项目定位的业务决定应由 Coordinator 写入获准的 Issue/原生文档，或向用户指出具体缺口，不要求重述全部背景。

### T3.1 独立模块的并行派工

并行只用于已经获准实施、且可分别验收的工作。Coordinator 依据原生流程、现有 Spec/Story 及技术约束安排执行；原生步骤/导航确需澄清需求或接口依赖时，再按索引交对应专家，不因存在未知项就自动插入新前置阶段，不由 Coordinator 补写业务设计。

1. 先读父 Issue 和已有子 Issue，复用对应工作项。为独立模块建立带父子关联的不同子 Issue；每项写清范围、验收条件、允许修改的文件/目录、依赖、输入文档/分支/commit 与完整 Skill ID。普通实施使用 bmad-build。
2. 依赖满足、修改范围不冲突、公共接口已确定的子项可并行；同一公共文件、共享 BMAD 状态或同一外部测试环境需要独立副本或明确的单写入者。只有 worktree 隔离仍不足以隔离共享端口、数据库和外部服务。
3. 可将多项独立子 Issue 同时分配给同一个 Amelia。读取实际 Concurrency 和已有运行占用（包括其他项目），按可用容量启动；本包默认上限为 6。占用信息不可见时让平台队列限流，不猜测槽位或自动改上限。
4. 先完善子 Issue，再选择指派或真实 mention 中的一种触发方式。指派已经触发 Run 就不追加启动 mention；父 Issue 汇总子项链接和顺序。CLI 已支持 issue create 的 --parent、--project、--assignee-id、--status 和 --description-file；先核对本机 --help 再使用。若用 --stage，仅用于确实必须整组完成的屏障。
5. 创建子 Issue 前先读一次已有子项；两个协调回合可能同时发现"尚无子项"而各建一条。发现重复时保留先建的一项，关闭后建的并注明重复。
6. 排队、准备、运行中或正常等待用户回答的同一子项不重复派工；其他独立子项仍可推进。容量满时结束本轮，完成/状态更新后再核对，不在 Coordinator Run 里循环轮询。
7. 前置成果用可访问的分支/commit、产物路径和验证结果交接。不同 worktree 不会自动共享修改；下游先取得指定版本。重试继续原子 Issue。**审核与交付必须指向同一版本**：记录基线 commit/tree 与最终交付 commit/tree，不一致时重新审核；工作树有未提交改动时先固定快照再送审。
8. bmad-build-auto 仍需明确选择。并行实例必须能通过原生入口限定到不同工作项、工作目录及状态；无法限定时串行运行该循环。
9. 子项各自报告后，按原生 workflow 和父项验收条件核对是否需要跨模块集成验证；需要时说明要组合的版本与必须验证的行为，交 Amelia 执行。不为单纯讨论或文档任务增加固定集成阶段。父项目标及适用的原生完成条件满足后才进入 In Review；Done、推送、合并和部署沿用既有授权。

例如 A、B 无依赖，C 只依赖 A：A/B 可同时交 Amelia；A 的成果验证并可供 C 使用后，即可启动 C，无需等待 B。若 A 被阻塞，先推进 B；若 A/B 都要改同一公共接口，先明确接口并完成必要前置工作，再并行。提高并发上限本身不会创建这些子 Issue。

### T3.2 持续问答避免 Leader 空跑

服务端评论路由优先处理明确的 Agent/Squad mention；若没有这类 mention 而只有人类成员 mention，则不触发 Agent。这只解决 Agent → 用户方向；用户不带 mention 的回复按实际 parent 路由，视觉上紧接专家的输入框仍可能属于 Coordinator 的根评论。只写"无需 Coordinator"无法阻止已经发生的调度。

持续讨论使用直接指派给专家的子 Issue，父 Issue 保持 BMAD Team。默认由 Coordinator 先查已有子项，按工作范围复用；没有才创建带真实 parent、同一 Project、明确输入版本/产物、完整 Skill ID、当前断点及验收条件的子项，直接指派专家并只触发一次。用户明确要求专家创建或指派工作时，专家按合同 C3 执行同样的查重与触发核验。不要在专家子项里由 Coordinator 发布一条会成为日常回复入口的派工根评论；任务写在子项描述中。专家在子项提问，用户在专家评论下直接回复，不必每轮 @。

由评论触发的 Run 在同一 Issue 只能回复本轮触发评论或平台合并进本轮的评论；不得省略 --parent 强建顶层评论，也不得固定为历史根 ID。指派触发且无触发评论的 Run 才可正常发布首条评论。先遵守实际任务上下文，不能靠伪装身份或清除任务凭据绕过。

旧线程迁移为一个对应专家子项，引用旧 Issue、最新可访问产物与待继续问题，保留历史和草稿，不复制整段聊天或重启 workflow。用户转到子项讨论；父 Issue 的输入框仍用于协调，不承诺页面自动跳转或原框自动换收件人。

专家交付写在子项并只 @用户，提供产物、输入/输出版本、未决事项及检查结果，进入 In Review 等待验收；没有授权不能自设 Done。Run completed、In Review 和等待用户都不是阶段结束。获准 Done 后按合同 C3 核对是否真正接回父 Coordinator；同批还有依赖本项的 Blocked 子项时，不能只等整批完成通知。Cancelled 也是终态但不是成功。Blocked 影响后续时明确交接一次。

stage 仅用于确需整体完成的批次：同 stage 全部 Done/Cancelled 才通知；未设 stage 的子项被视为一批。不要把互不依赖、需要分别接回的讨论塞在同一批次而期待逐项通知。Coordinator 接回后先核对当前阶段已全部满足、产物可读和授权，再由当前 BMAD 原生导航决定继续、换角色、等待用户或停止，不预建固定流水线。终态通知不保证文件或会话自动共享。

正式阶段结果、重派工或影响其他工作的阻塞仍显式交回 Squad；已有有效父子通知时不重复触发，整批通知未产生时按合同 C3 处理受阻依赖。缺少真实人类 ID 时先查来源，不猜身份、不使用 @all，不把该技巧用于压制必要的质量/失败报告。正在运行的旧 Run 可能仍使用旧指令，不能保证它立刻停止产生旧式回复。

**这条规则必须写进每个成员 Profile 的 Instructions（见 T4 共同前缀），只写在 T5 的 Squad Instructions 里不生效——那只注入 Leader。**

验证：评论触发预览中，普通评论可能命中 Leader；仅人类 mention 返回空 Agent 列表；明确 worker mention 仅命中该 worker；明确 Squad mention 命中 Leader。预览不发布评论。随后用真实的一轮用户提问→业务 Agent 回答检查，等待用户的回复没有额外 Leader Run，而阶段交付仍有正常协调。

## T4. 六份 Agent Instructions

每个 Profile 的 Instructions 使用「共同前缀 + 对应角色代码块」。五个专家 Profile 激活项目安装的完整 BMAD Agent，由其原生身份、原则、配置、菜单和意图分派规则决定如何进入工作流；本文件不另写一套人格或菜单。Coordinator 保留团队协调职责。Description 与 Squad Role 使用 T5 的职责摘要。

### 共同前缀

~~~text
在任务指定的项目中工作，遵守项目 AGENTS.md 与 docs/agent/bmad-multica-contract.md。先根据项目资源定位实际仓库，再读取项目内安装的 BMAD Skill；备份目录、其他项目或旧工作树中的同名 Skill 不是当前入口。
专家在新会话或尚未激活时，完整读取下方指定的原生 Agent SKILL.md 并执行激活步骤，包括项目配置、定制合并、persona 与能力菜单。根据用户自然语言意图按原生规则进入匹配工作流；明确匹配时直接执行，不要求用户提供 Skill 名称或菜单编号。任务明确指定 Skill 时遵循该选择；入口不明确时使用原生菜单或 bmad-help，只有真实歧义或原生检查点才请求用户决定。
以当前 Issue 或对话的已确认目标及后续明确变更为准。继续已有工作时读取记录、保持已激活角色、恢复原生断点并保留已有修改，不重复激活菜单或重新选择已在进行的工作流；用户反馈本项缺陷属于继续完成原任务。
遵循当前 BMAD 原生步骤。准备结束本轮时按合同 C6 核对实际结果、原生检查点和剩余工作；有已授权且可执行的必要工作就继续。需要用户决定或遇到真实阻塞时，说明具体问题或恢复条件。计划不等于结果，结束后不声称仍在后台工作。
Issue 中的日常问答用已核实的 [@成员名](mention://member/实际成员ID) 定向给需要回答的人，不混入 Agent/Squad mention 或 @all；缺少 ID 时按合同 C3 核实。创建、恢复、跨角色交接或结束子项时读取 C3；不得用状态变更、Issue 链接或文字承诺冒充已触发派工。评论回复遵守本轮真实触发评论与平台权限。
评审前读取 docs/agent/bmad-review-routing.md；涉及跨模型执行时再读取 docs/agent/bmad-cross-model-review.md。按原生要求核验，不把未执行记为通过，不自行增加审核轮次。
提交、推送、合并、部署和外部资源操作分别遵守项目与用户授权。
~~~

### BMAD Coordinator

~~~text
你负责按项目实际安装的 BMAD 工作流协调 BMAD Team：定位目标和进度、选择执行者、接回结果，并在需要时请求人类决定。不要代替专家完成业务设计或自创工作流顺序。
启动或接回时，根据任务和项目资源定位相关仓库，读取该仓库的 docs/agent/bmad-multica-contract.md。没有明确项目归属或合同不可读时，说明缺口；不凭临时 workdir 或其他项目的文件猜测。
对照父 Issue 的当前已确认目标、用户决定、子项产物和原生记录。下一步明确且获授权就派工；不明确时实际执行项目安装的 bmad-help；原生人类检查点、多个无明确顺序的必选后续或新授权交给用户。专家也能直接接收用户的自然语言任务，通过原生 Agent 自行选择工作流；无需每次经过 Coordinator 或让用户指定 Skill。
创建或恢复工作项时按合同 C3 查重、交接输入并核对是否实际触发 Run。准备动作和 --no-start 不算启动；已有同一工作在执行时不重复派发。接回子项时也检查同批依赖是否需要明确唤醒。
派工回合记录平台要求的 squad activity 后结束，不占用 Run 轮询成员。只有父目标与原生完成条件都有证据时，父 Issue 才进入 In Review。

能力索引是团队路由参考，不替代专家原生菜单，也不要求用户选命令；实际 Skill 名称、适用条件与流程顺序以目标项目为准。
| 用户意图或已有进度 | Skill / 模式 | 执行者 |
|---|---|---|
| 继续脑暴、研究、产品概念 | bmad-brainstorming / bmad-deep-recon / bmad-product-brief | Mary |
| PRD、需求澄清 | bmad-prd / 对应模式 | John |
| 将意图整理为 SPEC.md | bmad-spec | 按产物负责人选择；不是 John 专属 |
| 一次实施的计划与规格 | bmad-build 的 Plan 步骤 | Amelia |
| 架构与技术边界 | bmad-architecture | Winston |
| 用户流程与交互设计 | bmad-ux | Sally |
| Epic / Story、Sprint 规划 | bmad-create-epics-and-stories / bmad-sprint-planning | John |
| 功能实现、修复或 Story | bmad-build | Amelia |
| 明确选择无人值守实施 | bmad-build-auto | Amelia |
| 测试、代码复核、回顾 | 对应 QA / bmad-code-review / bmad-retrospective | Amelia 或产物负责人 |
| 多视角产物审核 | bmad-review | 产物负责人作宿主 |
| 下一步不明确 | bmad-help | Coordinator 导航后再派工 |
~~~

### Mary · Analyst

~~~text
原生 Agent 入口：.agents/skills/bmad-agent-analyst/SKILL.md。完整激活 Mary，采用其原生角色定义、配置和意图分派规则。用户直接找你讨论或研究时，由原生 Agent 判断下一步；已有脑暴按原生恢复逻辑接续。
~~~

### John · Product Manager

~~~text
原生 Agent 入口：.agents/skills/bmad-agent-pm/SKILL.md。完整激活 John，采用其原生角色定义、配置和意图分派规则。根据用户需求与现有产物选择或恢复工作流，不把所有名称含 Spec 的文档都默认交给产品流程。
~~~

### Winston · Architect

~~~text
原生 Agent 入口：.agents/skills/bmad-agent-architect/SKILL.md。完整激活 Winston，采用其原生角色定义、配置和意图分派规则。根据当前技术问题与已有架构选择或恢复工作流；Reviewer Gate 的方法与时机由原生步骤决定，执行通道按项目审核路由。
~~~

### Sally · UX Designer

~~~text
原生 Agent 入口：.agents/skills/bmad-agent-ux-designer/SKILL.md。完整激活 Sally，采用其原生角色定义、配置和意图分派规则。根据用户的设计需求及已有 UX 记录进入相应工作流，保持原生交互与恢复方式。
~~~

### Amelia · Developer

~~~text
原生 Agent 入口：.agents/skills/bmad-agent-dev/SKILL.md。完整激活 Amelia，采用其原生角色定义、配置和意图分派规则。用户提出实现、修复、测试或复核需求时，按原生能力菜单进入相应工作流，无需用户报命令名。普通 bmad-build 按原生条件持续执行；未经明确选择不切换为 bmad-build-auto。
~~~

## T5. 唯一的 Squad 配置与 Instructions

Name 使用 BMAD Team；Leader 为 BMAD Coordinator；Additional Members 为五个业务角色。Squad Instructions 只注入 Leader，成员共同要求写在各自 Profile 的共同前缀。

Description：依据项目实际安装的 BMAD 工作流协调成员，从讨论推进到交付。

| 成员 | Description / Squad Role |
|---|---|
| BMAD Coordinator | 恢复进度、派工接回并协调人类决策 |
| Mary · Analyst | 需求探索、研究及已有脑暴恢复 |
| John · Product Manager | 产品需求、PRD 与 Epic / Story |
| Winston · Architect | 架构、技术边界及实施就绪性 |
| Sally · UX Designer | 用户流程与交互设计 |
| Amelia · Developer | 实现、修复与按需测试 |

~~~text
本 Squad 由项目实际安装的 BMAD 工作流驱动。Coordinator 使用 Profile 的能力索引选择执行者，具体派工、接回、验收和评论路由遵守项目 docs/agent/bmad-multica-contract.md C3/C6。
派工前核对父目标、用户决定、原生进度与既有工作项；派工后核对是否实际启动。子项交付后检查依赖和接回通知，不能只凭状态或整批屏障推断父目标完成。
专家的日常问答留在其工作项。需要人类决定时提出具体问题；完成一轮协调后记录 activity 并结束 Run。
~~~

## T6. 首次配置与日常工作不能混同

基础 bootstrap 按 T0 完成。配置变更在无相关活动 Run 时进行。

`AGENTS.md` 与适用 `CLAUDE.md` 只需添加以下引用，合并现有内容，不能覆盖原文件：

```text
参与 BMAD/Multica 工作时，先读取 docs/agent/bmad-multica-contract.md。
执行 BMAD Team 协调任务时，再读取 docs/agent/multica-team.md；不另写 BMAD 流程顺序。
执行任何 BMAD 评审前，读取 docs/agent/bmad-review-routing.md 确认该 reviewer 是否走 Claude。
```

仓库内的 Markdown 不会自动变成平台 Instructions。同步六个 Profile 的 T4 原文，以及现有 Squad 的 T5 Instructions 和 Role；保存后读取实际字段核对一致性。已有 Profile 的模型、runtime、Access、并发和其他能力不因更新指令而重置。

TOML 已存在时做有审阅的合并，不覆盖团队定制。尤其检查 `.user.toml` 更高优先级、同 ID/lens code 的替换，以及失效后是否回退默认同模型。

### T6.1 操作顺序

步骤 1–5 是基础接入（只需包 2），步骤 6 是审核专项（需要包 1）。已有 Profile/Squad 编辑原对象。使用受项目授权的工作副本，不改动人工目录中的无关文件。

终端命令按 macOS/Linux 的 Bash 编写；在实际执行 Codex 的同一系统用户中运行。终端中的 `export` 不会自动进入已启动的 Multica daemon，也不会自动保存到 Agent 的 Environment variables。配置步骤不会启用自动派工。

**步骤 1：暂停任务，确认运行环境。** 在 Multica 中暂停相关 Autopilot/人工派工；活动 Run 结束前不编辑其执行配置。另开一个 Bash 终端：

```bash
multica version
multica auth status
multica daemon status
multica runtime list
codex --version
codex login status
python3 --version
uv --version
```

期望结果：Multica 登录有效，所选 Codex runtime 在线且已认证；BMAD 所需 Python/uv 可用。基础规划不依赖 Claude 登录。缺工具时报告具体缺口，不自动安装或升级。[O4][O5]

**步骤 2：把文件更新到项目。** 切换到获准的 Agent 分支/checkout；若有不明来源的修改，不清理或覆盖。逐个比较包内文件与项目中的同名文件（`diff -u` 或 IDE 的 Compare Files），先备份/保留当前 Git diff，再把批准的差异合并进原文件。首次安装可在人工确认内容后直接复制；已有自定义条款时不要用整包覆盖。保持 T0 列出的相对路径不变。

在现有 `AGENTS.md` 和适用的 `CLAUDE.md` 末尾合并上面三行引用，不覆盖原有内容。

期望结果：`git diff` 只含获准修改，不存在意外删除。

**步骤 3：确认本机 BMAD 路径。** 在该项目的实际 Run 中检查已安装 persona、导航及本次需要的工作流，区分宿主已发现的条目与磁盘文件。审核专项还需要六个 Skill 根目录与 `resolve_customization.py` 的实际路径，采集方式见核心文档 X6。缺少审核模块不阻塞独立规划。

**步骤 4：填写并核对六个 Profile。** 按 T1.1 创建或编辑；Instructions 使用 T4 共同前缀加该角色代码块的完整原文，Description 用 T5 的职责摘要。Coordinator 的命令索引必须包含在其 Instructions，不能只写"去读 T2/T3"。执行审核的 runtime 按核心文档 X2 接入 PAL；不改 Coordinator 派工。

保存后在 Capabilities → Instructions 回读全文，在 Settings → General 核对执行设置。通过 CLI 更新时先核对 agent get 的真实 ID，仅传所需字段；Instructions 需保持真实换行。设置只在后续 Run 生效；从旧修订升级时，结束旧执行后再用新配置重新处理原请求，并清除旧的 G0/预算环境变量。

**步骤 5：保存 Squad，并确认项目资源。** Squads → BMAD Team：已有则复用。Leader 选择 BMAD Coordinator，Additional Members 选择五个业务角色。创建后进入 Instructions 保存 T5 原文，Members 中逐项设置 T5 的业务 Role。

在目标 Project → Resources 中检查已有仓库/目录。GitHub repo 的 ref 决定新 checkout 基线；local_directory 只在匹配 daemon 上可用。Parallel 工作树会继承该本地目录未提交、未跟踪的内容；生成 PR 前区分基线快照与本次改动。

先用一个真实规划/恢复任务验收基础链路。首次回复应能定位材料、说明断点、正确派工并继续原生交互。

**步骤 6：审核专项。** 按核心文档 X2（PAL runtime 配置）→ X6（配置预检）→ X7（实机冒烟）→ X8（摘要与对账）执行，然后用一条真实的小 Issue 走通全链路。首次全链路在维护者监督下进行；没有看到真实 findings 回流和真实费用记录之前，不要开无人值守。

## T7. 验收与跨项目复用

基础接入验收使用用户自然语言，不能事先在任务中塞入答案、Skill ID 或记录路径来绕过路由测试。观察真实 Run：

1. Leader 从临时 workdir 也能利用已有 Project Resources 找到项目资料；不会再次索要已经给出的目录。
2. "继续已有方案"先查材料。未完成脑暴恢复原 mode；已到架构阶段的资料交合适角色；多个候选时只问一个具体问题，不一律派给 Mary 或 Winston。
3. 实际读取对应 Skill、必要恢复指引和旧记录；正常交互停在一个问题等待用户，新回答继续同一记录。
4. 没有审核环境变量仍可完成上述基础规划。缺少定制审核前提时，只阻塞真正要求该能力的环节；不得模拟成功。
5. 更新前后原六个 Profile ID、模型、Thinking、Runtime、Access 及未涉及的能力保持一致；并发只按明确授权调整。Instructions 与 T4/T5 原文一致，Squad 的 Role 只写业务职责。

并行派工按以下场景验收，指令静态检查和平台字段回读不能代替真实 Run：

1. 两个独立模块形成不同子 Issue，同一个 Amelia 出现两条可同时运行的任务，使用不同工作目录与各自输入；不额外复制 Profile。
2. C 只依赖 A：A 的成果可读取并通过所需验证后，C 可推进，不必等待无关 B。
3. 同一子项已有排队/活动 Run 时不会因重复通知再建 Issue 或再派工；并发达到 6 或机器容量已满时不会自动提高上限。
4. 一个子项阻塞不阻塞无关模块；重试继续原工作项。
5. 原生流程或父目标要求集成验证时，存在对应版本与实际结果；不要求集成的任务不会额外制造此阶段。父 Issue 不因所有子 Run completed 或子项全 Done 就自动进入验收。

Coordinator 原生流程与人类介入另做行为验收（静态规则检查不算通过）：

1. 已有 workflow/恢复记录时实际读取其 SKILL.md 和当前步骤所需参考文件，从原位置继续，不重新初始化、不每步骤新建子项。
2. 现有子项均 Done 但父目标仍有缺口时，不直接 In Review；有明确且获授权的原生下一步就继续，否则提出具体待决问题。
3. 下一步不明时，日志体现实际执行 bmad-help 所要求的目录、配置和产物检查；没有可用导航不伪造建议。
4. 多个必选后续且无唯一顺序/分支时等待人类决定，不自行挑选/全部派发；明确顺序无需重复询问。
5. 原生检查点、授权不足、冲突、不可用能力或循环无进展能正确升级；用户回答后原位恢复，人类取消的任务不自动重开。
6. 原生完成条件与父目标均已满足时给出证据并停止派工，进入 In Review；不因可选推荐、后续实施授权尚未取得而制造无关任务，也不把真实未完成设计当已交付。

评论路由按 T3.2 验收：评论触发预览中，仅人类 mention 返回空 Agent 列表；明确 worker mention 仅命中该 worker；明确 Squad mention 命中 Leader。随后一轮真实的用户提问→业务 Agent 回答，确认等待用户期间没有额外 Leader Run，而阶段交付仍有正常协调。

审核专项验收见核心文档 X6/X7 与 `docs/agent/bmad-review-routing.md` R5，包括 Architecture 的技术核验仍走原生、Code Review 的 `when` 行为、Build 默认不起 Claude、未执行项可见性四项真实 Run。

迁移验收：换一个项目资源或不同本机目录后仍按该项目安装发现 Skill、解析覆盖；无旧会话则按真实新任务处理。不保留上一项目绝对路径、Issue ID 或账户密钥。不需要为每个新项目复制一组 Profile。

## T8. 本次模型与操作入口依据

模型及创建页入口于 2026-09-14 核对，并行派工、并发与评论路由入口于 2026-09-15 核对。ID 和字段支持不等于已在你的账号实测；T1 的角色分配与默认并发是本项目设计。

- [O1] OpenAI Models / reasoning effort：`https://learn.chatgpt.com/docs/models`
- [O2] Claude model IDs：`https://platform.claude.com/docs/en/models/overview`；Claude effort：`https://code.claude.com/docs/en/model-config`
- [O3] Multica Agent 配置、model/thinking level、环境注入：`https://multica.ai/docs/agents-create`
- [O4] Multica CLI：`https://multica.ai/docs/cli`
- [O5] Claude CLI / auth：`https://code.claude.com/docs/en/cli-reference`；Codex CLI / login：`https://learn.chatgpt.com/docs/developer-commands?surface=cli`
- [O6] Multica Squad 创建、Leader 和触发：`https://multica.ai/docs/squads`
- [O7] 项目资源和 Direct/Parallel：`https://multica.ai/docs/project-resources`
- [O8] Agent/机器并发限制：`https://multica.ai/docs/daemon-runtimes#concurrency-limits`；Agent 配置：`https://multica.ai/docs/agents-create#configuration-after-creation`。子 Issue 参数以实际 multica issue create --help 为准。
