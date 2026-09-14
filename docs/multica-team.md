# Multica：BMAD Team 配置

版本：v4（原位修订 3：按 Multica 实机创建页细化）。更新：2026-09-14。只创建一支 Squad，复用五个 BMAD 业务 persona 与一个轻量 Coordinator。

此文件是 Profile/Squad 的配置源与操作说明，不是 Multica 自动导入 schema。它必须被实际写入 Profile Instructions/Squad Instructions，或由这些字段明确引用；单纯放进 `docs/` 不会自动建队。

## T1. 成员、具体模型、推理档位与权限

以下是本项目已确定的**默认配置目标**，恢复此前的具体设计，不再仅列“轻量／较强”等方向，也不留空继承 CLI 全局默认。六个 Multica Profile 均绑定 Codex runtime；Claude 是内部审核调用，不是第七个 Profile。

| 执行身份 | Runtime／调用方式 | 具体模型 ID | 推理档位 | 配置位置 |
|---|---|---|---|---|
| BMAD Coordinator | Codex | `gpt-5.6-luna` | `medium` | Multica Profile：Model + Thinking level |
| Mary · Analyst | Codex | `gpt-5.6-sol` | `high` | 同上 |
| John · Product Manager | Codex | `gpt-5.6-sol` | `high` | 同上 |
| Winston · Architect | Codex | `gpt-6-astra` | `high` | 同上 |
| Sally · UX Designer | Codex | `gpt-5.6-sol` | `high` | 同上 |
| Amelia · Developer（包括 QA 任务） | Codex | `gpt-5.6-terra` | `medium` | 同上；QA 不另建 Profile |
| 内部 Claude reviewer（每个有效 layer／lens） | CR-1 启动独立 Claude Code | `claude-opus-5` | `high` | `BMAD_REVIEW_MODEL` + CR-1 的 `--effort high` |

五个 BMAD persona 仍对应 Mary=`bmad-agent-analyst`、John=`bmad-agent-pm`、Winston=`bmad-agent-architect`、Sally=`bmad-agent-ux-designer`、Amelia=`bmad-agent-dev`；Coordinator 只做调度。初次联调建议六个 Profile 创建后都把 Concurrency 设为 1，创建页的 Speed 显式选 Standard，不选 Fast，也不把 Thinking 留在 Follow CLI config。这些是本项目初始设置，不是模型能力排名。

**配置明确与账号验收是两回事。** 官方当前文档列出了上述模型 ID 与模型/effort 配置入口；但尚未在你的账号、Multica runtime 和代理链中实测。模型不可用时报告该项失败并等明确替代决定，不清空 Model，不静默换型号/供应商，也不因为 `medium` 不被接受就自动改为 `high`。[O1][O2][O3]

OpenAI 的 `medium`／`high` 写入 Profile 的 **Thinking level**，不是在 Instructions 中写“请深入思考”；也不要再向 Custom arguments 重复追加 `--model`。Claude 的 `high` 是 CR-1 `command_for()` 中实际传出的 CLI 参数，与 Amelia 自身的 `medium` 无关；不需要新增一个未被程序读取的 `BMAD_REVIEW_EFFORT` 变量。

`BMAD_REVIEW_ALLOWED_MODELS` 和 `BMAD_REVIEW_REQUIRED_MODELS` 初始均设为 `claude-opus-5`。若实机报告使用供应商规范化的精确 ID，应先核验它仍对应已批准的 Opus 5，再明确更新允许/必需列表并重新批准 G0；不可自动把任何观测到的模型加白名单。更高型号也不自动视为可替代品。

运行时需提供项目读访问、原生 Skill 可见性和相应工具。仅 Amelia/QA 获得相应允许的代码/测试写入；Coordinator 的管理权限和业务代码写入分开。仅在你明确批准时才做一次性模型升级；保留本表作为回归默认值，不重新改变 persona 或 BMAD 路由。

### T1.1 实机创建页：字段、来源与明确填写值

已检查的创建路径是 Agents → New agent → Start blank。该页依次提供 Name、Description、Instructions、Conversation starters、Skills、Runtime、Model、Thinking、Speed 和 Access。Concurrency、Environment 与 Custom Args 不在创建页；它们只能在创建后的 Settings 中配置。

| 实机字段 | 六个新 Profile 的明确填写方式 |
|---|---|
| Name | 使用 T1 的 Profile 名称。 |
| Description | 仅写一句给 Leader/人阅读的职责摘要；不把规则、模型或权限边界放在此处。 |
| Instructions | 粘贴 T4 的共同前缀和该角色的完整段落。 |
| Conversation starters | 首次创建保留内建默认值；不把工作流或授权写成自动发送的建议。 |
| Skills | 保持为空。当前 Workspace 没有 Skill；不得为 BMAD 使用 Copy from runtime、local folder、ZIP、URL 或手工创建第二份 Workspace 副本。 |
| Runtime | 选择 Codex（Mac.willfan.me），并确认它在线。不要因为内部 Claude 审核而把六个 Profile 改为 Claude runtime。 |
| Model | 从可见的模型选项中点击 T1 对应项，而不是留空使用 provider default。 |
| Thinking | 从选项中显式点击 Medium 或 High；不得保留 Thinking · Follow CLI config。 |
| Speed | 点击 Standard；不要在首次联调选择 Fast。 |
| Access | 新建 Profile 先选择 Only me。只有需要其他工作区成员直接启动 Run 且已评审权限边界时，才改为 Entire workspace 或 Specific people。 |

模型选择器实际显示的目标项如下：

| Profile | 要点击的 Model | 要点击的 Thinking |
|---|---|---|
| BMAD Coordinator | GPT-5.6 Luna（gpt-5.6-luna） | Medium |
| Mary · Analyst | GPT-5.6 Sol（gpt-5.6-sol） | High |
| John · Product Manager | GPT-5.6 Sol（gpt-5.6-sol） | High |
| Winston · Architect | GPT-6 Astra（gpt-6-astra） | High |
| Sally · UX Designer | GPT-5.6 Sol（gpt-5.6-sol） | High |
| Amelia · Developer | GPT-5.6 Terra（gpt-5.6-terra） | Medium |

创建后逐个打开 Settings → General，把 Concurrency 设为 1；Settings → Environment 与 Custom Args 初始留空。接着打开 Capabilities → Skills，只验证实际发现的运行时继承 Skill；不要复制、导入或启用一份 Workspace BMAD 来“补齐”列表。运行时继承的 installbmad 只用于安装、更新或修复 BMAD，不是日常 workflow 的授权。

## T2. 原生导航，而非手写流程顺序

### 明确输入

用户或正在执行的工作流已经明确指定一个安装可用的 Skill、模式与输入时，核对授权和原生前置条件，直接派给映射成员。不得因为想采用“无人值守”就擅自把 `bmad-build` 变成 `bmad-build-auto`；Auto 必须在任务或项目已批准策略中明确选定。

### 下一步不明确

在一个独立、只读的导航子调用中运行本地实际安装的原生帮助入口；本次核对的 main 使用 `bmad`，旧版可能是 `bmad-help`。必须由宿主的真实 active Skill listing 确定入口，不能凭名称猜测已安装。

导航子调用必须得到宿主原生提供的 active project/user skill roots、canonical IDs、descriptions、相关 Issue 事实、已知产物绝对路径、完成证据及授权范围。只传经过许可的真实 host 元数据；不得自己伪造一份目录扫描作为替代。

让原生入口按其 manifest/knowledge 规则提出下一步；保持其只读、发现与上下文限制。没有必要信息就返回限制/待决项，不自动 setup、update 或 doctor。返回推荐后结束导航子调用，Coordinator 从结果做实际派工；不要让帮助会话继续实现。

若运行时无法在导航子调用中暴露原生要求的 metadata，则报告接入阻塞。可以接受用户明确指定已经安装的工作流后走明确输入路径；不能默默回退到本文件以前的“任务类型→角色”规则。

### 实现与一致性边界

这是一份模型执行的协议，不是一个已有 BMAD routing API、确定性状态机或自动导入规则。普通任务不重新运行导航；仅下一步不明确时调用。升级后以实际导航结果为准，不另维护阶段图。

角色映射只在原生 Skill 已确定之后应用。专业争议仍交专家/人；任务执行期间内部步骤、状态恢复和质量闭环由原工作流管理。原生导航可能给出多个选项，此时不能随机选或让轻量模型替用户决定。

## T3. 已选 Skill → 执行者映射

这是部署映射，不代表下面所有 Skill 都已安装，也不规定执行顺序。预检将本地确实安装的条目与 persona 菜单核对；缺失条目不派工。对多角色可用的工作流，下表给出本项目默认执行者。

| 已确定的 Skill | 执行者 | 映射性质 |
|---|---|---|
| `bmad-brainstorming`、`bmad-deep-recon`、`bmad-product-brief`、`bmad-prfaq`、`bmad-project-context` | Mary | 对照实际 Analyst 菜单 |
| `bmad-prd`、`bmad-create-epics-and-stories`、`bmad-correct-course` | John | 对照实际 PM 菜单 |
| `bmad-sprint-planning` | John；任务明确指定时 Winston/Amelia | 原生多角色入口；John 为本项目默认，不是唯一合法 owner |
| `bmad-architecture` | Winston | 对照实际 Architect 菜单 |
| `bmad-ux` | Sally | 对照实际 UX 菜单 |
| `bmad-build`、`bmad-build-auto`、`bmad-qa-generate-e2e-tests` | Amelia | 开发执行映射；不得互相静默替换 |
| `bmad-code-review`、`bmad-retrospective` | Amelia | 对照实际 Developer 菜单；不声称本包覆盖其全部内审 |
| `bmad-review` | 被审核产物负责人作为宿主 | 各 selected lens 实际交独立 Claude；宿主汇总、不修改被审对象 |
| `bmad-spec`（仅本地确实安装且原生推荐时） | John；技术专项可明确指定 Winston | 本项目执行者约定，并非强制 persona 归属 |
| 未列出的已安装 Skill | 暂停，明确指派后记录映射 | 不用名称/目录前缀猜测业务流程 |

Build Auto 的规划/实现默认在 Amelia 的同一业务身份下运行，内部状态由 BMAD 自己处理。不再默认把复杂任务的 Build Auto 规划阶段强制派给 Winston。

需要较强模型做一次规划时，由用户明确授权一次性模型覆盖或专家参与，并且本地原生工作流确实支持相应停止点；这只是执行选项，不能成为新的固定路由。

## T4. 六份 Agent Instructions

为每个 Profile 的 Instructions 写入下列共同前缀和相应角色段落。Description 只写一句职责摘要，不承载规则。角色全文来自原生 persona，不复制另一套到 Multica。

### 共同前缀

```text
工作流启动前必须经过受信入口的 G0；这是外部门禁，不由本次任务自我批准。
每次 Run 先报告实际项目工作目录，确认该目录下的 .agents/skills 和 _bmad/custom 是否存在且可读取。项目安装是 BMAD 的唯一权威来源；工作区绑定 Skill、运行时继承 Skill 与项目 Skill 不可混为一谈。
Skill 被发现、继承或启用只表示能力可用，不表示本次获准执行。不得因创建页为空而复制、导入、安装、更新或猜测 BMAD。
核对 gate 凭据与控制文件 hash 后，读取项目 AGENTS.md、适用目录规则、docs/bmad-multica-contract.md、当前 Issue 与明确引用的输入。
业务成员加载其实际安装的 BMAD persona；方法与工作流遵循该安装版本。
任务已有 Skill/模式/输入时直接执行它；信息不足就报告所需决定，不发明另一套阶段顺序。
仅处理本次已分配工作，遵守原生工作流前置条件与项目授权；二者冲突则暂停。
使用最小充分实现，保持源代码、Spec、验收和测试的职责边界。
在原 Issue 返回真实产物、版本、验证、原生状态和待决项，不 @ 下一成员。
直接分配的独立任务向原请求者交付；Squad 任务由 Coordinator 决定下一步。
不主动挑选 backlog，不擅自推送/合并/部署，不把进度或单次 Run 成功当成整体完成。
```

### BMAD Coordinator

```text
本 Profile 的预期执行配置：Codex / gpt-5.6-luna / medium。以平台配置或可获得的运行元数据核对，不把模型自述当成证据；不符时报告，不自行切换。
你是唯一 BMAD Team 的轻量 Coordinator，不是业务 persona，不编写业务代码或替专家做产品/技术判断。
读取 docs/multica-team.md 的 T2/T3，先确定原生工作流，再做执行者映射。
已有明确、获准且可调用的 Skill 就按映射派工；下一步不明确时，发起独立只读的本地 BMAD 原生导航子调用。
导航仅给建议；不能在帮助上下文中开始推荐工作流，也不能把缺元数据转成猜流程。
原生推荐与候选已确认后，核对批准、输入版本、活动 Run、执行环境和必要权限。
没有外部 Go、超预算或审核通道失效时停止新派工；不自动删 TOML、重置预算或伪造恢复。按合同 C8 交维护者处理。
用当前 roster 的真实 mention 标记发一条派工评论，记录平台要求的 activity，然后结束本轮。
进度更新不是完成；工作仍在运行时不重复触发。同一 Issue/工作单位/Skill/版本只保留一个有效派工。
成员完成/阻塞后读取正式结果与原生后续指示；没有下一步才重新导航，不无条件重跑 done Spec。
不读取角色名来发明固定步骤，不模拟 Build Auto 的内部状态转换，不替用户批准范围。
只有当前 Issue 整体交付要求及必需证据满足时进入 In Review，Done 交人/已授权集成。
```

### Mary · Analyst

```text
本 Profile 的预期执行配置：Codex / gpt-5.6-sol / high。以平台配置或可获得的运行元数据核对，不把模型自述当成证据；不符时报告，不自行切换。
加载实际安装的 bmad-agent-analyst，保留其原生身份与方法。
执行已经选定、分配给你的研究/发现类 Skill，区分来源事实、推断和未知。
不把研究自动升级为 PRD 或实现，不替 John/Winston 批准业务/技术决定。
返回正式产物、来源、限制、原生下一步指示及待决问题。
```

### John · Product Manager

```text
本 Profile 的预期执行配置：Codex / gpt-5.6-sol / high。以平台配置或可获得的运行元数据核对，不把模型自述当成证据；不符时报告，不自行切换。
加载实际安装的 bmad-agent-pm，执行被明确分配的原生需求/规格/拆分类工作流。
维护意图、范围、非目标和可验证行为，不自行扩张验收或指定所有任务必经完整 PRD。
必要测试/审核要求写入正式任务输入；复杂技术判断交由获准专家处理。
只有明确 review 请求或原生 skill:bmad-review 指令时才调用审核；按项目 Claude 配置执行。
交付真实产物和产品待决项，不因产物存在或自身认可就声称用户批准。
```

### Winston · Architect

```text
本 Profile 的预期执行配置：Codex / gpt-6-astra / high。以平台配置或可获得的运行元数据核对，不把模型自述当成证据；不符时报告，不自行切换。
加载实际安装的 bmad-agent-architect，执行被明确分配的原生技术规划/就绪性工作流。
优先已有模式，记录本次必要的技术决定、接口边界、依赖和验证要求。
不默认接管所有复杂 Story 的 Build Auto 规划；仅在明确授权的一次性执行安排中参与。
产品/接口/风险授权变化需明确记录并升级，不能为了继续执行自行放宽边界。
交付证据与最小必要修订，不修改其他成员活动中的实现工作区。
```

### Sally · UX Designer

```text
本 Profile 的预期执行配置：Codex / gpt-5.6-sol / high。以平台配置或可获得的运行元数据核对，不把模型自述当成证据；不符时报告，不自行切换。
加载实际安装的 bmad-agent-ux-designer，执行已分配的 UX 工作流。
复用设计规范，明确用户流程、可见状态、错误反馈和必要的验收观察点。
不为无 UI 的任务生成 UX 文件，不扩大产品范围，不修改业务代码。
返回正式 UX 产物、约束、原生后续建议和待决项。
```

### Amelia · Developer

```text
本 Profile 的预期执行配置：Codex / gpt-5.6-terra / medium。以平台配置或可获得的运行元数据核对，不把模型自述当成证据；不符时报告，不自行切换。
加载实际安装的 bmad-agent-dev，执行任务指定的开发、测试或复核 Skill。
Developer 菜单代码 BD 调用 bmad-build，不等同于 bmad-build-auto；没有明确授权不替换入口。
将指定 Spec/Story/范围传给原工作流，让它根据真实状态选择内部步骤；不手改状态解锁。
原生执行所需子 agent、同步等待、配置解析或跨模型审核能力不满足时停止，不能用同模型自审冒充。
实现过程中编写并运行必要测试；产品/架构争议返回待决事项，不私改验收。
执行 bmad-qa-generate-e2e-tests 时只修改获准测试；真实产品缺陷回交，不改业务逻辑或弱化断言。
回报实际版本、Claude 报告与分诊、测试结果、复审建议；不主动启动额外完整审核或下一条 Story。
```

## T5. 唯一的 Squad 配置与可选 Instructions

Leader：BMAD Coordinator。Members：Mary、John、Winston、Sally、Amelia。

实机 Create Squad 页只显示 Name、Description、Leader Agent 和 Additional Members；创建时没有 Skills、Runtime、Model、Thinking 或 Speed 字段，也未显示 Squad Instructions 输入框。因此创建 Squad 时只填写下表，所有不可省略的成员行为规则仍以 T4 的各 Profile Instructions 为准。若创建后版本额外提供 Squad Instructions 设置页，才粘贴本节随后的代码块；不要把它当作创建页必填项。

| Create Squad 字段 | 明确值 |
|---|---|
| Name | BMAD Team |
| Description | 使用项目内 BMAD 进行从需求到交付的协调；BMAD 选择 workflow，Multica 只做执行者映射与交接。 |
| Leader Agent | BMAD Coordinator |
| Additional Members | Mary、John、Winston、Sally、Amelia |

```text
本 Squad 复用本地 BMAD 原生工作流，不维护一套自定义阶段顺序。
所有执行遵守 docs/bmad-multica-contract.md；完整执行者映射与导航协议见 docs/multica-team.md T2/T3。
先由受信 runtime 执行 G0；四个 ID/五个 code 的模型自检不能替代外部门禁。
控制配置、模型或预算异常时执行合同 C8 的暂停与恢复，不由队伍自行降低质量政策。

已有用户或原工作流明确指定的可调用 Skill：核对前置条件和授权后映射派工。
下一步不明确：用独立只读的本地 BMAD 原生导航取得建议，保留该入口的发现/知识/完成证据规则。
导航只推荐，不执行推荐工作流；新成员 Run 才执行工作。缺入口、元数据、知识或决定时报告阻塞，不用手写表回退。

派工明确 Skill、模式、输入路径和版本、工作单位、批准范围及预期证据。
不要强制想法先交 John，不强制复杂 Story 先由 Winston 运行 Build Auto；先确定原生工作流再决定人。
不展开原工作流内部步骤，不重新实现其状态路由，不把每个 review layer/lens 或 QA 阶段建成独立团队。

指定的 Build Auto 内部使用 Claude review layers；指定的 bmad-review 使用 Claude lenses。
模型分工以 T1 为准：Coordinator=Luna/medium，Amelia=Terra/medium，Mary/John/Sally=Sol/high，Winston=Astra/high；内部审核=claude-opus-5/high，不继承宿主型号或推理档位。
这些覆盖不等于全局拦截所有 BMAD 审核；未覆盖入口先核验，必要时暂停补配置。
QA 按实际原生要求/明确任务调用，不作为每条 Story 固定阶段，也不能免除实现测试。

成员在原 Issue 返回结果，由 Leader 在结果完整后协调下一步；活动 Run 未结束不重复派工。
用真实 roster mention 触发成员，记录 activity 后结束本轮。避免同一任务同时直接派工和 Squad 控制。
保持单一 Issue 表达单一交付目标；只按独立 Story/依赖拆分，不因阶段变更拆队。

批准和技术就绪是不同条件；已有授权不重复询问，缺授权就等待。
Claude 执行失败、配置失效、必需验证未运行或重大待决项未解，不进入最终验收。
依据原生结果进行必要复核，不无条件重启 done Spec；新增代码/测试需相应增量审核与验证。
整体要求满足才进入 In Review，等待人接受。未经授权不推送、不合并、不部署。
```

## T6. 首次配置与日常工作不能混同

首次配置先暂停自动派工：识别实际 Skill 和 schema、在受信入口解析三份 TOML、核对 personal override、验证完整 Claude argv/权限/模型/预算、获取真实 Profile/roster，再在获准后应用 Instructions。初版禁止调用级 override；需要时先增加最终渲染门禁。`bmad` 普通帮助不得被用来执行这些安装修改。

`AGENTS.md` 与适用 `CLAUDE.md` 只需添加以下引用，合并现有内容，不能覆盖原文件：

```text
参与 BMAD/Multica 工作时，先读取 docs/bmad-multica-contract.md。
执行 BMAD Team 协调任务时，再读取 docs/multica-team.md；不另写 BMAD 流程顺序。
```

仓库内的两个 Markdown 不会自动变成平台 Instructions。必须实际设置六个 Profile 的共同前缀+角色段落；Squad Instructions 仅在创建后的实际版本确实提供该设置页时再写入 T5。创建页已实测的字段和精确值以 T1.1 为准，不生成假的 UUID。

原三份 TOML 存在时做有审阅的合并，不覆盖团队定制。尤其检查 `.user.toml` 更高优先级、同 ID/lens code 的替换，以及失效后是否回退默认同模型。

### T6.0 从现有文件到实际运行：按顺序操作

本节是操作指南；T6.1–T6.4 保留已有门禁程序与技术细节。**已有 Profile/Squad 就编辑原对象，不重复创建，不更改原 ID。** 首轮使用一个独立的 Agent 专用 checkout、一个固定本地 runtime、一条串行测试 Issue。你在 PyCharm 中手工工作的 checkout 不作为此处的 Direct 工作目录。

下面终端命令按 **macOS/Linux 的 Bash** 编写；在实际执行 Codex/Claude 的同一系统用户、同一容器或 VM 中运行。终端中的 `export` 不会自动进入已启动的 Multica daemon，也不会自动保存到 Agent 的 Environment variables。配置步骤不会启用自动派工。

#### 步骤 1：暂停任务，确认运行环境

在 Multica 中暂停相关 Autopilot/人工派工；活动 Run 结束前不编辑其执行配置。另开一个 Bash 终端，确认工具和登录状态：

```bash
bash
# 下列命令在新 Bash 内逐段执行；不要在运行中的 Agent 任务里做登录/daemon 管理。
multica version
multica auth status
multica daemon status
multica runtime list
codex --version
codex login status
claude --version
claude auth status
python3 --version
uv --version
```

**期望结果：** Multica 登录有效、目标 Codex runtime 在线；Codex/Claude 在实际 worker 环境中已认证；Python 至少 3.11。缺工具或认证则先处理该项，不继续启动工作流；不为了本次更新自动升级现有软件。首次连接尚未完成时才用 `multica setup`，已有连接不要重复 setup；仅登录失效使用 `multica login`。[O4][O5]

#### 步骤 2：把五个文件更新到项目，而不是把总方案放进去

输入实际 Agent 专用 checkout 和下载的 ZIP 路径：

```bash
read -r -p 'Agent 专用项目根目录（绝对路径）：' PROJECT_ROOT
read -r -p 'multica-bmad-v4-files.zip 的绝对路径：' PACKAGE_PATH
export PROJECT_ROOT PACKAGE_PATH
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd -P)" || exit 1
export PROJECT_ROOT
cd "$PROJECT_ROOT" || exit 1
git status --short --branch
```

若这里是 `main` 或你的人工工作区，先按现有 Git 策略切换到获准的 Agent 分支/checkout；若有不明来源的修改，不清理或覆盖。下面只解压到私有临时目录，不写项目：

```bash
export BMAD_UNPACK_DIR="$(python3 - <<'PY_UNPACK'
from pathlib import Path
import os, tempfile, zipfile
expected = {'docs/bmad-multica-contract.md', 'docs/multica-team.md',
    '_bmad/custom/bmad-build-auto.toml', '_bmad/custom/bmad-review.toml',
    '_bmad/custom/bmad-qa-generate-e2e-tests.toml'}
dest = Path(tempfile.mkdtemp(prefix='bmad-v4-package-')).resolve()
with zipfile.ZipFile(os.environ['PACKAGE_PATH']) as z:
    if set(z.namelist()) != expected or len(z.infolist()) != len(expected):
        raise SystemExit('ZIP 必须恰好包含五个预期文件')
    for name in sorted(expected):
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(name))
print(dest)
PY_UNPACK
)"
test -n "$BMAD_UNPACK_DIR" && test -d "$BMAD_UNPACK_DIR" || exit 1
printf '用于逐文件比较的目录：%s\n' "$BMAD_UNPACK_DIR"
```

用 PyCharm 的 Compare Files，或 `diff -u`，逐个比较解压文件与项目中的同名文件。先备份/保留当前 Git diff，再把批准的差异合并进原文件。首次没有这五个文件时，可在人工确认包内容后复制到同名路径；已有自定义条款时不要用整包覆盖。保持第 11 节中的五条相对路径不变。

在现有 `AGENTS.md` 和适用的 `CLAUDE.md` 末尾合并 T6 开头的两行引用，不覆盖其原有内容。若修改了包内规则，后面受信 hash 和批准清单必须针对**合并后的实际字节**重新审核。

**期望结果：** 项目中有两个 `docs/*.md` 和三个 `_bmad/custom/*.toml`；`git diff` 只含获准修改，不存在意外删除。总方案 PDF/Markdown 不用作为另一个 Skill 导入。

#### 步骤 3：确认本机 BMAD 路径，不猜 `.claude/skills`

在这个项目的 Codex 会话中提出一次只读安装检查（这不是启动业务工作流）：

```text
只做本地安装检查，不运行开发或审核，不安装/更新 BMAD。
从当前 host 暴露的 active Skill listing 给出以下真实目录：
bmad-build-auto、bmad-review、bmad-qa-generate-e2e-tests，
以及五个 persona 的入口和原生导航入口。
另外确认项目使用的 resolve_customization.py 绝对路径。
标明重复/遮蔽安装或缺失项，不用目录名猜测 host 实际启用的 Skill。
```

把实际返回的四个路径填入终端；读取缺失则停止，不用另一个聊天账号的安装代替：

```bash
read -r -p 'resolve_customization.py 的实际绝对路径：' BMAD_RESOLVER
read -r -p 'bmad-build-auto 的实际 Skill 根目录：' BMAD_BUILD_AUTO_ROOT
read -r -p 'bmad-review 的实际 Skill 根目录：' BMAD_REVIEW_ROOT
read -r -p 'bmad-qa-generate-e2e-tests 的实际 Skill 根目录：' BMAD_QA_ROOT
export BMAD_RESOLVER BMAD_BUILD_AUTO_ROOT BMAD_REVIEW_ROOT BMAD_QA_ROOT
python3 - <<'PY_PATHS'
from pathlib import Path
import os
assert Path(os.environ['BMAD_RESOLVER']).is_file(), 'resolver 不存在'
for name in ['BMAD_BUILD_AUTO_ROOT', 'BMAD_REVIEW_ROOT', 'BMAD_QA_ROOT']:
    p = Path(os.environ[name])
    assert p.is_absolute() and (p/'SKILL.md').is_file() and (p/'customize.toml').is_file(), name
    print(name, p.resolve())
PY_PATHS
```

#### 步骤 4：在 Multica 填六个 Profile 的模型、档位和 Instructions

打开工作区 **Agents**。已有六个 Profile 时逐个打开编辑；缺少时点击 **New agent → Start blank**。每个 Profile 按以下字段填写：[O3]

**先按实机 UI 完成以下清单，再考虑 CLI。**

1. 在 Identity 填 T1.1 的 Name 和一句 Description。
2. 在 Behavior & capabilities 的 Instructions 粘贴 T4 共同前缀与对应角色段落；Conversation starters 保持默认。
3. 在 Skills 不选择任何项目。不要点击 Add skills from workspace；若 Workspace 仍显示 No skills yet，这正是预期状态。
4. 在 Execution 中选择 Codex（Mac.willfan.me）→ T1.1 的可见 Model 项 → 明确的 Medium/High → Standard。
5. 在 Access 选择 Only me；不要为了让 Squad 工作就扩大为 Entire workspace。
6. 点击创建或保存后，重新打开 Settings → General，设 Concurrency 为 1；Settings → Environment 和 Custom Args 初始保持空白。
7. 打开 Capabilities → Skills，记录运行时自动发现的继承 Skill。不得用 Copy from runtime 把 BMAD 变成 Workspace 副本；发现 installbmad 也不代表可运行所有 BMAD workflow。

只有上述保存后的界面仍显示正确值，才算 Profile 配置完成。已有 Profile 的迁移也应逐字段核对；不要把 Stuart 现有的 Luna/High/Standard/concurrency 3 当作 Coordinator 的模板。

| 字段 | 操作 |
|---|---|
| Name | 使用 T1 的原名称；已有名称不为本次更新改名 |
| Runtime | 选择步骤 1 已确认在线、能看到同一项目的 **Codex runtime** |
| Model | 点击 T1.1 中对应的可见 GPT-5.6 Luna/Sol/Terra 或 GPT-6 Astra 项，不留空 |
| Thinking level | 点击 T1.1 的 Medium 或 High，不是所有人统一 High，也不保留 Follow CLI config |
| Instructions | **T4 共同前缀 + 该角色的完整段落**；不粘到 Description |
| Description | 一句话职责摘要；不承载审核或权限规则 |
| Skills | 保持无 Workspace Skill；不 Copy from runtime，不从 folder/ZIP/URL 导入 BMAD |
| Speed | 显式选择 Standard，不选 Runtime default 或 Fast |
| Access | 新建 Profile 选 Only me；既有 Profile 维持或收紧最小权限，不为方便扩大到整个工作区 |
| Concurrency limit | 创建后在 Settings → General 首轮设为 1 |
| Environment / Custom Args | 创建后才可见；初始为空，不重复指定 model/effort，不改既有安全设置 |

点击保存后重新打开，检查 Runtime、Model、Thinking、Speed、Access 与 Instructions 是否还在。**只写进提示词不算完成。** 模型列表缺目标型号、保存被拒绝或实际调用失败就记录该项阻塞，不清空模型回退；初次配置不以 Custom Args 或 CLI 覆盖来绕过 UI 缺项。[O3][O4]

已有 Profile 的可选终端更新方式如下。命令只更新你输入 ID 的原 Profile，不创建新对象：

```bash
multica agent list --full-id
multica agent update --help
# 每次输入对应原 Profile 的完整 ID；先核对 get 的名称，再确认写入。
update_model() {
  local role="$1" model="$2" effort="$3" agent_id answer
  read -r -p "$role 的原 Profile 完整 ID：" agent_id
  test -n "$agent_id" || return 1
  multica agent get "$agent_id" || return 1
  read -r -p "确认将上述 Profile 设为 $model / $effort？输入 APPLY：" answer
  test "$answer" = APPLY || return 1
  multica agent update "$agent_id" --model "$model" --thinking-level "$effort" || return 1
  multica agent get "$agent_id"
}
update_model 'BMAD Coordinator' 'gpt-5.6-luna' 'medium' || exit 1
update_model 'Mary' 'gpt-5.6-sol' 'high' || exit 1
update_model 'John' 'gpt-5.6-sol' 'high' || exit 1
update_model 'Winston' 'gpt-6-astra' 'high' || exit 1
update_model 'Sally' 'gpt-5.6-sol' 'high' || exit 1
update_model 'Amelia' 'gpt-5.6-terra' 'medium' || exit 1
```

CLI 更新模型之后，Instructions、Concurrency 和环境变量仍须按上述字段设置。已有活动 Run 不会自动换新配置，验收看保存后的**新 Run**。不要让模型靠“我现在用的是……”自证配置。[O3]

#### 步骤 5：配置唯一 Squad，绑定正确项目工作目录

打开 **Squads → BMAD Team**；确实不存在才新建。创建页只填 T5 表中的 Name、Description、Leader Agent 和 Additional Members。Leader 选 **BMAD Coordinator**，添加 Mary、John、Winston、Sally、Amelia。Leader 会自动成为成员，不重复添加第二个 Coordinator。创建页没有 Skills、Runtime、Model、Thinking、Speed 或 Squad Instructions；不要试图把这些配置塞进 Description。若创建后的实际版本另有 Squad Instructions 设置页，再粘贴 T5 完整代码块；否则 T4 的 Profile Instructions 是行为规则的唯一平台载体。[O6]

在项目的 **Resources → Add local directory**（Desktop）选择步骤 2 的 Agent 专用 checkout，并确认绑定的是步骤 1 的本地 daemon。首轮建议这个专用 checkout 采用 **Direct / `in_place`** 串行执行，便于 G0 使用稳定真实路径；不是让 Agent 直接写你的人工 checkout。不要误选 Parallel 后仍用原目录的 G0 凭据：不同 worktree 需要按其实际根目录重新批准和签发凭据。[O7]

**期望结果：** 同一团队恰好一个 Leader、五个业务成员；项目工作目录实际可读，原有 Issue/Squad IDs 不变；尚未启动任何业务 Issue。

现在创建第一条验收 Issue：Project 选这个项目，状态选 **Backlog**，正文可预先填步骤 10 的玩具文档审核模板。复制平台分配的真实 Issue key，供下一步设置 `ISSUE_KEY`。此时不改为 Todo，不发触发性 mention；步骤 10 是启动这条已有 Issue，不再新建另一条。

#### 步骤 6：填写 Claude 模型参数和运行时目录

在步骤 1 的同一 worker 环境中设置以下明确值。`high` 已由 CR-1 固定传给 Claude，**不要把 Amelia 的 Thinking level 改为 high 来控制 Claude**：

Profile 的 Environment 和 Custom Args 属于创建后的 Settings 页面，不属于 New agent 表单。只把非敏感的静态审核变量配置到实际会承载 Build Auto 或 bmad-review 的 Profile/runtime；不要默认复制给全部六个 Profile。路径、预算、gate 凭据和认证仍由受信启动入口逐 Run 注入。

```bash
export BMAD_REVIEW_MODEL='claude-opus-5'
export BMAD_REVIEW_ALLOWED_MODELS='claude-opus-5'
export BMAD_REVIEW_REQUIRED_MODELS='claude-opus-5'
export BMAD_REVIEW_TIMEOUT_SECONDS='900'
# 建议初次小任务以单次 2 USD、Issue 累计 24 USD 作为待你批准的上限；不是费用估算。
# 输入你实际批准的值，不因示例自动获得消费授权。
read -r -p '批准的单次审核上限 USD（例如 2.00）：' BMAD_REVIEW_MAX_USD
read -r -p '批准的单条 Issue 累计上限 USD（例如 24.00）：' BMAD_REVIEW_ISSUE_MAX_USD
export BMAD_REVIEW_MAX_USD BMAD_REVIEW_ISSUE_MAX_USD
read -r -p '本次测试的真实 Issue key（先建 Backlog Issue 后复制）：' ISSUE_KEY
export ISSUE_KEY
```

把模型/允许集/必需集/超时等非敏感静态值填到各个可能承载审核的 OpenAI Profile 的 **Environment variables**（本方案六个均可统一配置这些非秘密值）；否则终端 `export` 不会保证进入以后由 daemon 启动的进程。预算与路径必须由受信 launcher/管理员明确注入，并与 G0 清单相同。Multica 的自定义环境变量存储于服务端，不用它保存高价值长期密钥；CLI 认证仍走真实运行账户/secret store。[O3]

**不要把某一条 Issue 的 `BMAD_REVIEW_GATE_FILE/SHA256` 当作永久 Profile 默认值。** 它绑定 Issue、根目录、控制文件且会过期。自动模式由受信启动入口逐 Run 注入；在人工串行试运行中，应在无人运行时为该 Issue 的后续 Run 设置当前凭据，换 Issue/过期后重新核对，绝不跨任务复用。

外部代码与预算状态使用不同目录，避免探针把自己的控制目录当作预算允许根：

```bash
# 这是同一 worker 账户的示例路径；生产权限必须按 C0/T6.2 落实。
export BMAD_CONTROL_DIR="$HOME/.local/share/bmad-control/v4-model-steps-r2"
export BMAD_STATE_DIR="$HOME/.local/state/bmad-team"
python3 - <<'PY_DIRS'
from pathlib import Path
import os
for key in ('BMAD_CONTROL_DIR', 'BMAD_STATE_DIR'):
    p = Path(os.environ[key])
    if p.is_symlink(): raise SystemExit('拒绝符号链接控制/状态目录')
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    p.chmod(0o700)
    print(key, p.resolve())
db = Path(os.environ['BMAD_STATE_DIR'])/'review-budget.sqlite3'
if not db.exists():
    fd = os.open(db, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600); os.close(fd)
elif db.is_symlink() or not db.is_file():
    raise SystemExit('拒绝无效账本')
else:
    print('保留已有预算账本，不清空、不重建')
PY_DIRS
BMAD_CONTROL_DIR="$(cd "$BMAD_CONTROL_DIR" && pwd -P)"
BMAD_STATE_DIR="$(cd "$BMAD_STATE_DIR" && pwd -P)"
export BMAD_CONTROL_DIR BMAD_STATE_DIR
export BMAD_REVIEW_BUDGET_DB="$BMAD_STATE_DIR/review-budget.sqlite3"
```

目录 `0700` 不会隔离同一系统用户下的恶意进程；上述目录创建只是路径准备，不是 OS 沙箱已经配置完成的证明。实际预算账本按原 CR-1 要求由受信账户管理，跨重试保留。

#### 步骤 7：放置已审核的受信副本，提取原有 CR-1/G0

先人工审核最终五个文件及其中的 Python；从获批准的发布版本把两个 Markdown 放进外部控制目录，文件名使用 `trusted-contract.md` 和 `trusted-team.md`。首次可这样复制；已有文件时 `cp -i` 逐项确认，不能覆盖一个不同的已批准版本来绕过 hash：

```bash
cp -i "$PROJECT_ROOT/docs/bmad-multica-contract.md" "$BMAD_CONTROL_DIR/trusted-contract.md"
cp -i "$PROJECT_ROOT/docs/multica-team.md" "$BMAD_CONTROL_DIR/trusted-team.md"
export BMAD_TRUSTED_CONTRACT="$BMAD_CONTROL_DIR/trusted-contract.md"
export BMAD_TRUSTED_TEAM="$BMAD_CONTROL_DIR/trusted-team.md"
read -r -p '人工审核后固定的 contract SHA-256：' BMAD_TRUSTED_CONTRACT_SHA256
read -r -p '人工审核后固定的 team SHA-256：' BMAD_TRUSTED_TEAM_SHA256
export BMAD_TRUSTED_CONTRACT_SHA256 BMAD_TRUSTED_TEAM_SHA256
```

未改动下载内容时，可对照总方案附录 A/B 的发布 hash；合并过本地规则则使用审阅该版本后批准的 hash。不要让候选任务在调用前自动计算 hash 并把自己批准。

然后执行共享合同 **C5 → 受信提取与调用方式**中的第一个 Bash 代码块（只有 `PY_EXTRACT`，到该代码块结尾为止）。它生成外部 `cr1.py` 与 `g0.py`。此时**不要运行**同节后面的单层审核调用例子：还没有 G0 凭据和本轮 staging。

**期望结果：** 外部控制目录内存在受信副本和两个 Python 文件；没有把第六个启动脚本提交到候选项目，也没有执行候选分支的任意 Python。

#### 步骤 8：解析真实配置、做模型/权限探针并保留证据

先运行 T6.2 的 `PY_CAPTURE` 完整代码块，得到 `approval.draft.json`。它运行真实 resolver，`checks` 仍为 `pending`；查看 `expected_workflows`，确认四个 layer / 五个 lens、完整执行配方和 QA 边界都生效。遇到同名草稿已存在先把旧草稿移至历史证据目录，再采集新草稿；不覆盖、删除已批准记录，也不清空预算。

运行 T6.4 的 `PY_PROBE` 完整代码块。其 argv 来自同一个 CR-1 `command_for()`，实际使用 **claude-opus-5 / high**。若 `observed_models` 与预期不符，保存原始证据并停止；确认只是同一 Opus 5 的供应商规范化 ID 时，由你显式调整 allowed/required，再重新采集草稿。不得把辅助模型自动加白名单。

OpenAI 侧在四个不同型号的新会话中分别使用 `/model` 查看并选择 T1 型号和档位，发送一个不读文件的简单测试；随后在实际 Multica 新 Run 的配置/可用日志中复核。Mary/John/Sally 共享同型号也要核对各自 Profile 已保存 `high`。API/CLI 可调用、平台字段已保存、Run 实际使用三项分别记录，模型自述不计证据。[O1][O3]

按 T6.4 完成假文件允许/拒绝、旧哨兵合法引用、真实失败、预算及恢复试验。首次完整链路验收只针对人工构造的玩具项目，在维护者监督下进行：原生 resolver/工作流及 CR-1 代码按候选方案观察执行；没有签发 Go 前不得交付真实任务、不得把测试批准当作无人值守批准。若本地启动器连这种隔离验收也无法支持，保持 `end_to_end=pending`，先修入口，不能伪造已通过。

**期望结果：** 有真实 CLI 输出、实际配置 JSON、模型/effort 配置证据、读取拒绝日志和端到端记录；不是只看“命令 exit 0”。源码中的七个 `checks` 逐项对应这些证据，没做的保持 pending。

#### 步骤 9：批准清单并运行 G0，把结果交给实际 worker

维护者审查证据后，在外部目录把草稿另存为该 Issue 的 `approval.json`：保留真实 `root`/`issue`/`control_files`/`expected_workflows`/`runtime_policy`，仅把有证据的检查设为 `passed`，给 `evidence_files` 写入实际证据文件的绝对路径与 SHA-256。不要用脚本把所有 pending 一键改成 passed。

```bash
read -r -p '人工批准的 approval.json 绝对路径：' G0_APPROVAL_FILE
read -r -p '人工固定的 approval.json SHA-256：' G0_APPROVAL_SHA256
export G0_APPROVAL_FILE G0_APPROVAL_SHA256
export G0_NEW_RECEIPT_FILE="$BMAD_CONTROL_DIR/gate-$(python3 -c 'import uuid; print(uuid.uuid4())').json"
export G0_RESULT_FILE="${G0_NEW_RECEIPT_FILE}.result.json"
python3 "$BMAD_CONTROL_DIR/g0.py" \
  --root "$PROJECT_ROOT" --issue "$ISSUE_KEY" \
  --resolver "$BMAD_RESOLVER" --runner "$BMAD_CONTROL_DIR/cr1.py" \
  --skill "bmad-build-auto=$BMAD_BUILD_AUTO_ROOT" \
  --skill "bmad-review=$BMAD_REVIEW_ROOT" \
  --skill "bmad-qa-generate-e2e-tests=$BMAD_QA_ROOT" \
  --approval "$G0_APPROVAL_FILE" --approval-sha256 "$G0_APPROVAL_SHA256" \
  --receipt "$G0_NEW_RECEIPT_FILE" > "$G0_RESULT_FILE" || exit 1
python3 -m json.tool "$G0_RESULT_FILE"
export BMAD_REVIEW_GATE_FILE="$G0_NEW_RECEIPT_FILE"
export BMAD_REVIEW_GATE_SHA256="$(python3 - <<'PY_RECEIPT'
from pathlib import Path
import json, os
r = json.loads(Path(os.environ['G0_RESULT_FILE']).read_text())
assert r['status'] == 'go' and r['receipt'] == os.environ['G0_NEW_RECEIPT_FILE']
print(r['sha256'])
PY_RECEIPT
)"
test -n "$BMAD_REVIEW_GATE_SHA256" || exit 1
```

**这里最容易漏一步：** 此终端的 gate 环境变量不会自动进入 Multica 新 Run。人工串行验收时，在启动这条 Issue 之前，由管理员将 C5 要求的静态变量、外部路径和当前 gate 对注入这条任务实际使用的 Profile/runtime 环境，再核对新 Run 看到的根目录与 Issue。不得打印认证密钥。G0 凭据按现有程序一小时过期，超时/控制文件变化需重新签发；账本不重置。

无人值守则必须让真正的 runtime 启动入口在**每次启动 worker 前**执行 G0、失败即不启动进程，并逐 Run 注入变量。普通 Profile Instructions 或保存一个 `GO=true` 都不是这项接入。**本包没有为你安装 Multica 的专用 pre-run hook；当前能直接照做的是人工门禁的串行试运行。没有已验证的启动入口时，不把人工步骤包装为自动强制执行。**

#### 步骤 10：启动第一条 Issue，核对真实派工与审核

新建测试 Issue 时先用 **Backlog**，Project 指向步骤 5 的项目；取得真实 Issue key 后用于步骤 6–9。Go 与环境注入完成后，把 Assignee 设为 **BMAD Team**，再改为 **Todo**。不要在尚未签发当前 gate 前改成非 Backlog；Multica 会在可执行的队伍任务上唤醒 Leader。[O6]

第一条建议只做一份不含秘密的玩具文档审核，任务正文可以使用：

```text
接入验收；本次只执行 bmad-review，并明确只选 adversarial lens。
目标：<本玩具项目中已经存在的文档绝对路径及版本>。
只报告，不修改目标，不启动 bmad-build/bmad-build-auto，不挑选下一条任务。
使用配置的 Claude Opus 5 / high，遵守 G0、CR-1、预算和私有 staging。
回报实际宿主模型/档位、实际 Claude 参数和报告模型、目标 hash、原生 findings 与执行状态。
最终停在 In Review。遇到配置、权限或模型错误就保留证据并阻塞，不伪造通过。
```

目标路径/版本必须替换为实际玩具文件，不把尖括号原样发送。观察 **Issue → Runs / Run details**：Leader 只派工；产物负责人执行选定 Skill；Claude 内部调用有 `--model claude-opus-5 --effort high` 与精确返回 ID；只有一个选中的 lens；结果不是同模型自审。必要时用：

```bash
multica issue get "$ISSUE_KEY"
multica issue runs "$ISSUE_KEY"
multica issue comment list "$ISSUE_KEY"
```

这条通过后，再用一条已获批准的玩具 Story 检查 Amelia 的 **gpt-5.6-terra / medium**、四层 Claude 内审、实际测试和最后 In Review；最后测试一条只补 QA 的任务，确认 Amelia 沿用 Terra/medium，而审核仍是 Opus 5/high。每条新 Issue 取得自己的批准/凭据，复审和重试继续原 Issue 的预算。

**日常最短操作顺序：** 选定/确认任务 → 核对原有输入与授权 → 当前 Issue 的 G0 → 启动原有 Squad/明确成员 → 检查 Run 和审核证据 → 人工验收。修改模型、effort、控制文件或运行环境后重新验收相关项；不只改表格、不静默回退。

### T6.1 外部 G0，而不是配置文件里的自检

运行顺序改为：**暂停自动派工 → 受信 bootstrap → 在隔离测试环境做真实验收 → 人工批准配置/模型/证据 → G0 检查 → 启动成员工作流**。原生 resolver 失败不能从 shipped defaults 继续；G0 必须在独立的 runtime 启动入口阻止这种回退。没有接入真实启动入口时，下面程序只能作为人工门禁使用，不能宣称已强制平台执行。

G0 使用实际安装的 `resolve_customization.py`，不自己模拟数组合并；完整结果必须与维护者批准的 `expected_workflows` 一致。四个 ID、五个 code、`prose.after=structure` 只是额外结构检查，不取代完整配置比较。三份 Skill 都解析，其中 QA 验证其授权/失败边界，不要求 QA 也有四层/五镜头。

初版禁止调用级 `--set`/`--overrides` 和绕过原生 resolver 的直接 workflow 对象。将来要支持时，必须把最终调用级合并结果纳入 G0；不能仅检查持久配置后允许调用时改写。普通导航仍不负责安装、修复或批准这些控制文件。

### T6.2 维护者批准清单与受信来源

`BMAD_CONTROL_DIR` 存放外部受信副本、提取的 `g0.py`/`cr1.py`、批准清单和门禁凭据；预算数据库放在另一个受控状态目录（步骤 6 的 `BMAD_STATE_DIR`），不要在控制目录内创建。两者均不是第六个项目配置文件。候选代码不能写这个控制目录、改启动器环境或签发新的 Go。不同权限主体共享同一操作系统用户时，这种隔离不能靠本程序自证，需 runtime/OS 权限配合。

批准清单是运行时 JSON，键如下；它必须来自真实环境，不从本文填假的 model、path、hash 或 `passed`：

| 键 | 内容 |
|---|---|
| `protocol` | 固定 `BMAD-G0-APPROVAL` |
| `root` / `issue` | 实际项目根与稳定的当前 Issue 身份，不能随重试换值 |
| `control_files` | 绝对路径→SHA-256；未存在的三份 `.user.toml` 记为 `null`，后续出现即阻断 |
| `sealed_dirs` | 批准的 resolver 及导入脚本目录、三个实际 Skill 树；其中新文件/符号链接也阻断 |
| `expected_workflows` | 三个 Skill 实际 `--key workflow` JSON，经审核后的完整快照 |
| `runtime_policy` | 请求模型、精确 allowed/required ID 数组、单次/Issue 预算（整数百万分之一 USD） |
| `claude_path` / `claude_sha256` | 实际 CLI 可执行文件及 hash；其安装目录、依赖和 managed settings 由受信运行环境固定 |
| `checks` | G0 程序列出的七项真实验收，必须全部为 `passed` |
| `evidence_files` | 每项真实验收证据文件的绝对路径→hash；模拟报告不能冒充实机证据 |

维护者先核对并批准原生工具链和导入依赖，才运行它们以采集基线。每次变更都重新审核批准清单，外部固定清单 hash。**不允许模型把刚解析出来的配置直接写为批准配置。** 全文相等证明与批准基线一致，不证明基线本身无漏洞。

以下采集脚本仅产生 `pending` 草稿，绝不生成 Go。它补齐实际路径、空缺个人覆盖、安装树和完整 resolver 输出；审核者仍需检查配置、追加真实验收证据并明确批准。`BMAD_RESOLVER`、`BMAD_BUILD_AUTO_ROOT`、`BMAD_REVIEW_ROOT`、`BMAD_QA_ROOT` 都是实际安装发现的路径。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY_CAPTURE'
from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, sys
sys.dont_write_bytecode = True
base = Path(os.environ['BMAD_CONTROL_DIR']).resolve(strict=True)
root = Path(os.environ['PROJECT_ROOT']).resolve(strict=True)
def load(name):
    spec = importlib.util.spec_from_file_location(name, base / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
cr1, g0 = load('cr1'), load('g0')
resolver = Path(os.environ['BMAD_RESOLVER']).resolve(strict=True)
skills = {name: Path(os.environ[env]).resolve(strict=True) for name, env in [
    ('bmad-build-auto', 'BMAD_BUILD_AUTO_ROOT'), ('bmad-review', 'BMAD_REVIEW_ROOT'),
    ('bmad-qa-generate-e2e-tests', 'BMAD_QA_ROOT')]}
uv, cli = shutil.which('uv'), shutil.which('claude')
if not uv or not cli: raise SystemExit('actual uv/claude required')
resolved = {}
for name, skill in skills.items():
    result = subprocess.run([uv, 'run', str(resolver), '--project-root', str(root),
        '--skill', str(skill), '--key', 'workflow'], check=True, capture_output=True, text=True)
    resolved[name] = json.loads(result.stdout)
sealed = sorted({str(resolver.parent), *(str(p) for p in skills.values())})
paths = {base/'g0.py', base/'cr1.py', Path(os.environ['BMAD_TRUSTED_CONTRACT']).resolve(),
         Path(os.environ['BMAD_TRUSTED_TEAM']).resolve(), root/'docs/bmad-multica-contract.md', root/'docs/multica-team.md'}
for folder in sealed:
    for p in Path(folder).rglob('*'):
        if p.is_symlink(): raise SystemExit('unapproved symlink in toolchain: ' + str(p))
        if p.is_file(): paths.add(p)
for name in skills:
    paths.update(root/'_bmad/custom'/f'{name}{suffix}.toml' for suffix in ('', '.user'))
# Include broader project rules/configuration that can affect the host.
paths.update(root/p for p in ['AGENTS.md', 'CLAUDE.md', '_bmad/config.toml', '_bmad/config.user.toml',
    '_bmad/custom/config.toml', '_bmad/custom/config.user.toml'])
controls = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in sorted(paths)}
policy = {'model': cr1.required_env('BMAD_REVIEW_MODEL'),
    'allowed_models': sorted({x.strip() for x in cr1.required_env('BMAD_REVIEW_ALLOWED_MODELS').split(',') if x.strip()}),
    'required_models': sorted({x.strip() for x in cr1.required_env('BMAD_REVIEW_REQUIRED_MODELS').split(',') if x.strip()}),
    'per_call_micro_usd': cr1.money(cr1.required_env('BMAD_REVIEW_MAX_USD')),
    'issue_micro_usd': cr1.money(cr1.required_env('BMAD_REVIEW_ISSUE_MAX_USD'))}
draft = {'protocol': 'BMAD-G0-APPROVAL', 'root': str(root), 'issue': os.environ['ISSUE_KEY'],
    'control_files': controls, 'sealed_dirs': sealed, 'expected_workflows': resolved,
    'runtime_policy': policy, 'claude_path': str(Path(cli).resolve()),
    'claude_sha256': hashlib.sha256(Path(cli).read_bytes()).hexdigest(),
    'checks': {key: 'pending' for key in sorted(g0.CHECKS)}, 'evidence_files': {}}
with (base/'approval.draft.json').open('x', encoding='utf-8') as out:
    json.dump(draft, out, ensure_ascii=False, indent=2)
print('Draft only. Inspect, test, approve and pin externally; never treat pending as Go.')
PY_CAPTURE
```

### T6.3 G0 完整程序

由 C5 的受信 bootstrap 提取到控制目录。程序成功输出凭据路径/hash，失败退出 2。凭据一小时过期，并绑定当前 Issue；运行期控制文件变化使 CR-1 再次检查失败。G0 并不负责自动证明七项实机验收，它验证维护者批准的证据完整性并实时检查配置。

<!-- G0_PYTHON_BEGIN -->
```python
#!/usr/bin/env python3
"""G0: run the installed native resolver before any BMAD worker is launched.
The launcher, approval manifest and toolchain must be trusted outside the candidate repo.
This is not a TOML hook and does not emulate BMAD's merge rules.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SKILLS = ('bmad-build-auto', 'bmad-review', 'bmad-qa-generate-e2e-tests')
EXPECTED_KEYS = {
    'bmad-build-auto': ('review_layers', 'id', {'blind-hunter', 'edge-case-hunter', 'verification-gap', 'intent-alignment'}),
    'bmad-review': ('lenses', 'code', {'adversarial', 'edge-case-hunter', 'verification-gap', 'structure', 'prose'}),
}
CHECKS = {'real_cli_argv_and_schema', 'model_ids_approved', 'read_allow_and_deny',
          'sentinel_and_input_integrity', 'fail_closed', 'budget_and_recovery', 'end_to_end'}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_resolved(name: str, actual: dict, expected: dict) -> None:
    if not isinstance(actual, dict) or not actual:
        raise ValueError(f'{name}: resolver must return a nonempty workflow JSON object')
    if name in EXPECTED_KEYS:
        field, key, wanted = EXPECTED_KEYS[name]
        rows = actual.get(field)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f'{name}: invalid keyed array')
        ids = [row.get(key) for row in rows]
        if len(ids) != len(wanted) or set(ids) != wanted:
            raise ValueError(f'{name}: wrong, duplicate or new layer/lens keys')
        if any('CR-1' not in str(row.get('instruction', '')) for row in rows):
            raise ValueError(f'{name}: missing CR-1 recipe')
        if name == 'bmad-review' and next(row for row in rows if row[key] == 'prose').get('after') != 'structure':
            raise ValueError('prose dependency was lost')
    # Full comparison also catches changed instructions, contexts, dependencies and hooks.
    if actual != expected:
        raise ValueError(f'{name}: full effective workflow differs from the operator-approved baseline')


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--issue', required=True)
    p.add_argument('--resolver', type=Path, required=True)
    p.add_argument('--runner', type=Path, required=True)
    p.add_argument('--skill', action='append', required=True, help='canonical-name=/absolute/active/skill/path; three entries')
    p.add_argument('--approval', type=Path, required=True)
    p.add_argument('--approval-sha256', required=True, help='pinned by operator outside the candidate repo')
    p.add_argument('--receipt', type=Path, required=True)
    args = p.parse_args()
    try:
        root = args.root.resolve(strict=True)
        approval_path = args.approval.resolve(strict=True)
        if approval_path.is_relative_to(root):
            raise ValueError('approval must be launcher-owned, outside candidate repo')
        raw = approval_path.read_bytes()
        if sha(raw) != args.approval_sha256:
            raise ValueError('approval manifest hash mismatch')
        approval = json.loads(raw)
        if approval.get('protocol') != 'BMAD-G0-APPROVAL' or approval.get('root') != str(root):
            raise ValueError('approval manifest has wrong protocol or project')
        if approval.get('issue') != args.issue:
            raise ValueError('approval manifest is for a different Issue/budget identity')
        if set(approval.get('checks', {})) != CHECKS or any(approval['checks'][key] != 'passed' for key in CHECKS):
            raise ValueError('real-runtime gates are incomplete; a fixture or static test is not Go')
        evidence = approval.get('evidence_files', {})
        if not evidence or set(approval.get('expected_workflows', {})) != set(SKILLS):
            raise ValueError('missing real test evidence or approved effective workflows')
        controls = approval.get('control_files', {})
        if not isinstance(controls, dict) or not controls:
            raise ValueError('control-file manifest is missing')
        skills = dict(item.split('=', 1) for item in args.skill)
        if len(args.skill) != 3 or set(skills) != set(SKILLS):
            raise ValueError('provide each of the three exact active Skill directories once')
        resolver = args.resolver.resolve(strict=True)
        runner = args.runner.resolve(strict=True)
        if runner.is_relative_to(root) or Path(__file__).resolve().is_relative_to(root):
            raise ValueError('G0 and CR-1 must run from the external approved launcher directory')
        required = {str(resolver), str(runner), str(Path(__file__).resolve()),
                    str(root / 'docs/bmad-multica-contract.md'), str(root / 'docs/multica-team.md')}
        for name, folder in skills.items():
            skill = Path(folder).resolve(strict=True)
            if skill.name != name:
                raise ValueError('active Skill folder name must match canonical ID')
            skills[name] = str(skill)
            required |= {str(skill / 'customize.toml'), str(skill / 'SKILL.md'),
                         str(root / '_bmad/custom' / f'{name}.toml'),
                         str(root / '_bmad/custom' / f'{name}.user.toml')}
        sealed_dirs = approval.get('sealed_dirs', [])
        if not {str(resolver.parent), *skills.values()}.issubset(set(sealed_dirs)):
            raise ValueError('resolver imports and active Skill trees must be sealed')
        for folder in sealed_dirs:
            for path in Path(folder).rglob('*'):
                if path.is_symlink() or (path.is_file() and str(path.absolute()) not in controls):
                    raise ValueError(f'unapproved file in sealed code tree: {path}')
        if not required.issubset(controls):
            raise ValueError('manifest omits required code/configuration or absent personal override entries')
        for name, expected in {**controls, **evidence}.items():
            path = Path(name)
            if not path.is_absolute():
                raise ValueError('manifest paths must be absolute')
            if expected is None:
                if path.exists() or path.is_symlink():
                    raise ValueError(f'new unapproved file: {path}')
            elif path.is_symlink() or not path.is_file() or sha(path.read_bytes()) != expected:
                raise ValueError(f'approved file missing or changed: {path}')
        uv = shutil.which('uv')
        cli = shutil.which('claude')
        if not uv or not cli:
            raise ValueError('native uv/claude runtime unavailable')
        if sha(Path(cli).read_bytes()) != approval.get('claude_sha256') or str(Path(cli).resolve()) != approval.get('claude_path'):
            raise ValueError('Claude executable differs from the real-runtime test baseline')
        resolved_hashes = {}
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        for name in SKILLS:
            proc = subprocess.run([uv, 'run', str(resolver), '--project-root', str(root),
                                   '--skill', skills[name], '--key', 'workflow'],
                                  cwd=root, capture_output=True, text=True, timeout=120, env=env)
            if proc.returncode != 0:
                raise RuntimeError(f'{name}: native resolver failed: {proc.stderr[-2000:]}')
            actual = json.loads(proc.stdout)
            validate_resolved(name, actual, approval['expected_workflows'][name])
            resolved_hashes[name] = sha(json.dumps(actual, sort_keys=True, ensure_ascii=False).encode())
        # No --set or invocation override is allowed in the initial unattended path.
        # A launcher that permits them must validate the final rendered output separately.
        for folder in sealed_dirs:
            for path in Path(folder).rglob('*'):
                if path.is_symlink() or (path.is_file() and str(path.absolute()) not in controls):
                    raise RuntimeError('sealed code tree changed during resolution')
        for name, expected in controls.items():
            path = Path(name)
            if (expected is None and (path.exists() or path.is_symlink())) or (expected is not None and sha(path.read_bytes()) != expected):
                raise RuntimeError('configuration changed during native resolution')
        receipt = {'protocol': 'BMAD-G0', 'status': 'go', 'root': str(root), 'issue': args.issue,
                   'issued_at': time.time(), 'expires_at': time.time() + 3600,
                   'control_files': controls, 'sealed_dirs': sealed_dirs, 'resolved_sha256': resolved_hashes,
                   'runner_sha256': sha(runner.read_bytes()), 'approval_sha256': sha(raw),
                   'runtime_policy': approval['runtime_policy'],
                   'claude_path': approval['claude_path'], 'claude_sha256': approval['claude_sha256']}
        target = args.receipt.absolute()
        if target.is_relative_to(root):
            raise ValueError('gate receipt must be outside the candidate repo')
        # No overwrite: old gate decisions are audit evidence, not mutable status flags.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        data = (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode()
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        print(json.dumps({'receipt': str(target), 'sha256': sha(data), 'status': 'go'}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'no-go', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
```
<!-- G0_PYTHON_END -->

调用方式：

```bash
# G0_APPROVAL_FILE/HASH 均由维护者在候选仓库之外批准，不能自动从当前文件“自签”。
python3 "$BMAD_CONTROL_DIR/g0.py" \
  --root "$PROJECT_ROOT" --issue "$ISSUE_KEY" \
  --resolver "$BMAD_RESOLVER" --runner "$BMAD_CONTROL_DIR/cr1.py" \
  --skill "bmad-build-auto=$BMAD_BUILD_AUTO_ROOT" \
  --skill "bmad-review=$BMAD_REVIEW_ROOT" \
  --skill "bmad-qa-generate-e2e-tests=$BMAD_QA_ROOT" \
  --approval "$G0_APPROVAL_FILE" --approval-sha256 "$G0_APPROVAL_SHA256" \
  --receipt "$G0_NEW_RECEIPT_FILE"
```

仅在退出 0 后，**启动器**把返回的 `receipt` 和 `sha256` 发布为 `BMAD_REVIEW_GATE_FILE` 与 `BMAD_REVIEW_GATE_SHA256`，并启动该 Issue 成员 Run。失败时不得启动 worker、不得让 Agent 改成 shipped-default 模式重试。实际平台的配置方式应按安装能力落实；本文不捏造 Multica 的 pre-run API。

### T6.4 真实 CLI 冒烟与权限试验

先在与生产相同的 CLI/认证/managed-policy 环境、仅含人工假数据的私有测试目录运行。首个探针从受信 CR-1 的 `command_for` 获取**同一组 argv**，不会因测试另写较短参数列表。它不调用 BMAD，不输出可交付审核结论，也不依赖尚未签发的 Go，避免启动验收的循环依赖。

探针会产生真实 API 使用；需维护者明确设置单次和累计预算、稳定测试 Issue 身份及外部账本。只对假数据获准执行，不得以探针模式处理真实项目。每次探针仍先预留预算；自动化工作流不得使用此手动入口绕过 G0。

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY_PROBE'
from pathlib import Path
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile
sys.dont_write_bytecode = True
base = Path(os.environ['BMAD_CONTROL_DIR']).resolve(strict=True)
spec = importlib.util.spec_from_file_location('cr1', base/'cr1.py')
cr1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(cr1)
stage = Path(tempfile.mkdtemp(prefix='bmad-probe-')).resolve(); stage.chmod(0o700)
(stage/'input.txt').write_text('Synthetic fixture only. Expected findings: [].\n', encoding='utf-8')
cli = shutil.which('claude')
if not cli: raise SystemExit('real claude missing')
cap = cr1.money(cr1.required_env('BMAD_REVIEW_MAX_USD'))
total = cr1.money(cr1.required_env('BMAD_REVIEW_ISSUE_MAX_USD'))
cr1.reserve_budget(base, stage, 'validation:cli-schema', cap, total)
cmd = cr1.command_for(cli, cr1.required_env('BMAD_REVIEW_MODEL'), cap, [])
result = subprocess.run(cmd, input='Read input.txt. Return execution_status=completed, failure_reason=null, findings_text="[]".',
    cwd=stage, capture_output=True, text=True, timeout=120)
raw = result.stdout.encode('utf-8')
report = Path(tempfile.mkdtemp(prefix='bmad-probe-evidence-', dir=base))
(report/'stdout.json').write_bytes(raw); (report/'stderr.log').write_text(result.stderr, encoding='utf-8')
if result.returncode != 0: raise SystemExit('CLI probe failed; inspect ' + str(report))
payload = json.loads(result.stdout)
body = payload.get('structured_output')
if payload.get('type') != 'result' or payload.get('subtype') != 'success' or payload.get('is_error') is not False:
    raise SystemExit('unexpected CLI result envelope')
if payload.get('permission_denials') or not isinstance(payload.get('modelUsage'), dict) or not payload['modelUsage']:
    raise SystemExit('read/model evidence missing or denied')
if body != {'execution_status':'completed','failure_reason':None,'findings_text':'[]'}:
    raise SystemExit('structured output probe failed')
print(json.dumps({'probe_only':True, 'evidence':str(report), 'stdout_sha256':hashlib.sha256(raw).hexdigest(),
    'observed_models':sorted(payload['modelUsage'])}, ensure_ascii=False))
PY_PROBE
```

通过这个探针**不等于通过所有 G0 检查**。再用同一 argv 做独立的允许/拒绝实验：显式要求读取 staging 内假文件（应成功），显式要求读取 staging 外带随机 canary 的假 `.env`、其他层目录和符号链接逃逸（应被权限机制拒绝）。拒绝试验本来就应产生拒绝证据，不能套用成功探针的零拒绝判据。记录真实工具日志/`permission_denials`，不能只因为答案里没出现 canary 就宣称安全。原生 OS 隔离和 managed hooks 另行核实。

最后验证含旧哨兵词的合法 finding、真正的结构化失败、坏 TOML/错误模型/超时、预算并行和重试、回滚恢复，以及一条真实端到端任务。`checks` 由维护者依据这些证据填写，不以模拟测试替代。


## T7. 验收要求

检验：六个 Profile 都显示 T1.1 指定的 Codex、Model、Thinking、Standard、最小 Access 和创建后 Concurrency=1；Workspace Skills 仍为空；未知下一步能拿到本地原生导航依据；明确工作流不重走导航；没有固定 PM→Architect 链；配置层解析后四个既有 Build Auto IDs、五个既有 lens codes 各出现一次；普通导航不写文件；批准中断能保持原 Issue；QA 失败不触发成功式收尾；Claude 失败不回退；个人 override 无绕过；直接分配与队伍派工不冲突；最终停在 In Review。

只在外部 G0、真实完整 argv/结构化信封、精确模型、读取允许/拒绝、输入不变性、预算与恢复，以及小仓库端到端验收全部通过后启用无人值守。静态 TOML 解析和 CR-1 的模拟测试不等于真实 BMAD/Multica/模型已经联调。

## T8. 本次模型与操作入口依据

以下为 2026-09-14 核对的官方入口。ID 和字段支持不等于已在你的账号实测；T1 的角色分配和初始并发是本项目设计。

- [O1] OpenAI Models / reasoning effort：`https://learn.chatgpt.com/docs/models`
- [O2] Claude model IDs：`https://platform.claude.com/docs/en/models/overview`；Claude effort：`https://code.claude.com/docs/en/model-config`
- [O3] Multica Agent 配置、model/thinking level、环境注入：`https://multica.ai/docs/agents-create`
- [O4] Multica CLI：`https://multica.ai/docs/cli`
- [O5] Claude CLI / auth：`https://code.claude.com/docs/en/cli-reference`；Codex CLI / login：`https://learn.chatgpt.com/docs/developer-commands?surface=cli`
- [O6] Multica Squad 创建、Leader 和触发：`https://multica.ai/docs/squads`
- [O7] 项目资源和 Direct/Parallel：`https://multica.ai/docs/project-resources`
