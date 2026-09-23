# BMAD 跨模型审核：PAL 调用层
版本：r8-pal-candidate；2026-09-23。发布候选，尚未通过 Multica 全链路验收。

## X1. 范围与保证
PAL clink 替代旧 CR-1 的 Python 提取、Claude 子进程管理和自定义回执协议。
BMAD 仍决定审核时机、方法、原生条件、同步点、分诊、修复及结束。
不新增审核轮次，不把一般讨论当作一次审核。选择规则见 docs/bmad-review-routing.md。

这是模型解释的调用政策，不是工作流引擎或防恶意沙箱。只读工具限制、独立会话和输入目录边界是不同保证。
不再声称保留旧模型白名单、输入哈希回执或累计预算协议。失败不能冒称零发现。

## X2. Runtime 接入
用户已批准固定采用 PAL PR #481 commit 9bb12126e3a0b8032446ad1dfd0e808f8dc1715a（未合并 PR，不是 upstream release）及 MCP SDK 1.30.0。
先按上游安装独立服务，再在实际宿主注册 MCP，仅启用所需 clink；不让 agent 临场修改 PAL 源码。
配置模板位于 bootstrap 的 runtime/pal-review/（claude、agy、codebuddy、dsh；旧 gemini 仅 API/企业候选）；它不是自动安装到项目的 payload。
Claude 模板：claude-opus-5-5，effort high，单次 max-budget-usd=2.00，timeout_seconds=900。
Gemini 模板：具体模型必须先获批准并填写，不继承 auto；不套用 Claude 的 effort 或美元预算参数。
这些值写入对应 PAL client JSON，不再从 BMAD_REVIEW_* 读取；2 USD 是每进程限制，不是四层合计限制。

CLI-only 启动的占位 provider 必须与目标 CLI 认证无关。#481 在已发现本机 CLI 时可直接以 CLI-only 模式启动；本次 agy/codebuddy/dsh 测试不需要占位 key。仅调用 clink，不调用 API 工具。
不要再给 Gemini 子进程传 GEMINI_API_KEY=FAKE_KEY，也不向 Anthropic 注入占位 key。
Claude 使用自己的订阅登录。旧 Gemini CLI 自 2026-06-18 不再支持个人免费/Pro/Ultra；仅在明确批准 API/企业认证时验证此候选。个人 Google 订阅须使用 Antigravity CLI (agy)，已批准的 #481 支持它，但文件审核权限尚未通过，保持备用禁用。
占位配置仅满足 PAL 启动检查，不提供真实模型能力。订阅下费用字段只是标价估算，不是额外扣费证据。

CLI_CLIENTS_CONFIG_PATH 指向本 Run 的已渲染客户端 JSON。
支持本地 stdio MCP 的宿主使用 bootstrap tools/launch_pal.py 绑定当前 Git checkout，参数为固定 --pal-root 和 --templates；解释器来自已安装 PAL 的专用 venv。它只生成 Run 配置并 exec PAL，不调度模型。
这不是 Multica 专用接口：Claude Code、Codex CLI、Cursor 等在各自 MCP 配置中注册相同 command/args，并把服务 cwd 设为当前 Git checkout；终端或 CI 可用标准 MCP client 调用。Multica 通过工作区 MCP 注册并分配给实际审核成员。各宿主都须能准备获准输入、等待工具返回和读取完整结果；不支持这些能力时明确报告不可用，不伪装原生接入或静默换通道。
在 Git checkout 启动时，通过 git rev-parse --git-path bmad-review-runtime.json 取得描述文件；在 Multica 非 Git Run 容器启动时，读取容器根的 .bmad-review-runtime.json（也就是仓库尚未 materialize 时的宿主工作目录）。不搜索其他 Run 或项目。
核对 workspace、PID、bundle、source、inputs、results、selection；checkout 为 null 时，按项目资源明确定位本 Run 内的实际仓库，再记录所审版本，不把容器当仓库。公共 source 初始为空，未经准备不得调用 reviewer。
描述文件仅在 worktree 本地 Git 元数据或非 Git Run 容器中，不提交；bundle 为私有临时目录，不放进业务 diff。同一 workspace 已有存活 PAL 时拒绝第二个实例，不能让并发 Run 共享 descriptor。
PAL 还读取 ~/.pal/cli_clients，同名用户配置可能覆盖该值，必须核对实际配置。
clink 请求没有 cwd 参数：服务 working_dir 必须绑定当前 Run 的授权源码视图；prompt 中写 cd 不会改它。
不同 worktree 必须使用各自服务配置/实例，不得在并发调用中修改共享 JSON 或复用另一个 Run 的 cwd。
不具备该接入条件时标为未执行；禁止临时启动 shell Claude、CR-1 或同模型替代并声称已跨模型审核。

旧 BMAD_REVIEW_MODEL、ALLOWED_MODELS、REQUIRED_MODELS、AUX_MODELS、MAX_USD、TIMEOUT_SECONDS
在本版本没有作用。所有使用旧包的 Run 结束、所有相关项目和 Profile 切换完毕后才清理旧变量，
不要破坏仍在使用旧版本的项目。项目 bootstrap 不自行改全局 MCP、Profile 或账户。

## X3. 输入与角色
每个 Run 使用独立的固定输入版本：
- source/：保留完整源码、测试、调用方和目录结构；不采用人工挑选四个文件的视图。
- inputs/<role>/：只存该层获准的 diff、方法及其引用文件、意图或声明。
- results/：宿主保存结果；放在 source/ 和 inputs/ 之外，reviewer 不可读取。

source 不是盲目复制整个工作树：凭据、Git 元数据、用户会话、运行产物、spec、作者 claims、
其他 reviewer 报告必须不在该公共视图中。先核对完整源码/测试范围和排除内容；不能确定边界就停止。
这些排除不能删掉方法要求的源码/测试或生产调用方。若文档本身就是审核目标，单独放到该角色 inputs。
这是输入视图准备，不是新增批次状态机、脚本执行器或调度器。

PAL working_dir=source；各角色 role_args 只以 --add-dir 开放自身 inputs/<role>。
完整方法及其相对引用放入对应角色目录，保持结构。把原生任务的路径解析为这些真实可读路径，
不改变原生任务内容、顺序、输出格式，也不把临时目录名当成 BMAD 新模板变量。

角色：blind-hunter、edge-case-hunter、verification-gap、intent-alignment、acceptance-auditor、
adversarial、structure、prose、architecture-rubric、architecture-consistency。
每个角色只访问公共源码和自己的输入：
- blind-hunter/adversarial 不收到 spec、claims、构建者思考或其他 findings。
- verification-gap 读取完整代码/测试，不能收到 claims 或其他 findings。
- edge-case-hunter 的 claims 只放本层目录，仍在原生规定步骤才读取。
- intent-alignment 获得原始用户意图；acceptance-auditor 获得本次 spec。
- prose 仅在原生 after 依赖要求时，获得 structure 的结果副本；不能读整个 results。
- 架构 reviewer 只收到对应原生 gate 规定的材料。

模型可读范围必须用真实 CLI 验证，不能仅用“请勿读取”代替目录边界。
最小验收：完整源码/测试及本层输入可读；其他层 spec/claims/results 不可读；对一次性测试文件的写入被拒绝且文件未变。只在合成目录做负向测试，不拿业务文件试写。
只读必须依赖已验证的 CLI 工具/权限或既有隔离环境，不能仅靠提示词。无此能力的 provider 暂不执行仓库审核，不为它另建权限系统。
Blind Hunter 隔离的是额外提供的意图材料，不是清洗源码本身的命名、注释或正常调用关系。
独立角色没有自己的 cwd；若配置无法限制到上述范围，本次不能声称独立审核。
原始业务工作树保持不动，所有复制、目录授权和数据外发遵守用户原授权。

## X4. PAL 调用
执行本项目当前安装版本的原生 reviewer 子任务，以 clink 代替原来的 reviewer spawn：
cli_name=本 Run reviewer-selection.json 中批准且验证通过的 reviewer-selection.json client；role=对应 X3 角色；prompt=展开路径后的完整原生任务。
不要使用通用 codereviewer 方法，不传宿主完整聊天，不跨独立层使用 continuation_id。
不得把已下线的 diff_output 或新版 diff_file 硬编码在适配层；使用当前原生任务真实定义的变量。
原生独立组全部启动后等待全部终止再 triage；依赖组按原生 after 顺序。
pending 不是失败，不重复启动，不因工具暂时无输出主动 kill 正常任务，不结束回合遗留审核。
PAL 管理进程；宿主只调用工具、等待、接回结果。保留每层调用和响应，不新增 CR-1 回执。

## X5. 接收与失败
检查实际 return_code、is_error、permission_denials 和完整正文；外层 success/continuation_available 不代表审核成功。
语法及字段要求以原生方法为准。零发现必须是原生方法的有效结果，不是空 stdout、权限失败或摘要。
PAL 当前对超过 20,000 字符的 content 截断/摘要化；若有该标记，检查同一响应 Claude 的 metadata.raw.result 或 Gemini 的 metadata.raw.response。
Gemini 还要检查 raw.error、empty_response、rate_limit_status 以及 stats.models 中的错误，不把 parser 生成的失败说明当 findings。
只有原始正文完整、无截断且符合原生格式时才可交给 triage；原文缺失或宿主响应也被截断则该层未完成。
不要通过“再总结一次”替代丢失 findings。报告已完成层，按原生失败处理继续可做部分，不伪造全层通过。
必需审核未完成时不宣称完成或进入验收；不无限重试或自动重跑已成功层。
审核版本和最终交付版本须一致；新增改动按原生增量审核规则处理。

## X6. 配置预检
使用 Python 3.11+：
python3 tools/run_preflight.py --project-root /actual/run/checkout
工具默认查该项目 _bmad/scripts/resolve_customization.py 和 .agents/skills；
可用 --resolver 和 --skills-root 显式指定真实安装位置，不能用旧备份伪装项目版本。
它调用真实 resolver，核对六项覆盖已加载、原生审核数组未被改写、旧协议没有混入。
项目自定义 reviewer 数组会提示冲突，需要逐项审阅，不自动覆盖。
[ok] 只证明持久配置符合预期，不证明 MCP 已注册、运行时输入隔离成立或模型遵守路由。
调用级覆盖仍须在激活时检查。未做预检写未执行。

## X7. 接入验收（不是每个 Issue 的额外审核）
首次接入、模型/CLI/PAL/安全参数/路由改变时验证相关部分；仅额度恢复不重跑 smoke。
1. 实际宿主发现 clink，请求模型配置明确、认证符合预期，cwd 属于本 Run；有返回模型字段就核对，没有则标未报告，不单独判失败。
2. 普通源码可读；blind 访问 spec/claims、任何层访问另一层结果必须被拒绝。
3. 小型固定 diff 走原生方法，四层独立会话无重复、收齐结果后分诊。
4. 核对长输出原文恢复与失败可见性。
5. 两个 Run/worktree 并行，无 cwd 或输入混用。
6. 真实工作流验证：Build 默认原生/显式 opt-in；Code Review no-spec/full；
   Architecture 两层 Claude、技术核验原生；Review 的条件/after 原样保留。
临时测试客户端不是 Codex 原生 MCP 自主调用或 Multica 验收。未完成项目保持未验证，不能自动发布切换。

## X8. 回报
记录：输入版本、层/角色、CLI、请求模型、返回模型（缺失写“未报告”）、退出状态、完整 findings 路径、可用的用量和未完成项。
Claude 记录 modelUsage；Gemini 记录 stats.models 中全部模型，不用自报“我是 Claude”充当证据。未知费用写未知。
请求模型来自已批准的明确配置，不等于已证实的实际返回模型。仅缺少返回模型或费用字段不阻塞审核，不新增模型白名单、证明协议或费用账本。
若返回字段明确与批准模型不一致，保留 findings 和证据，报告差异并交用户决定；不静默换模型或冒称满足指定模型要求。
不再要求 CR-1 摘要行，不用标价估算断言实际账户扣款。

## X9. 升级与恢复
顺序：停新派工并等待活动审核结束 → 项目文件逐个 diff/受管 hash 检查 → 提交并使 Run ref 可见 →
配置每个 Run 的 PAL 服务 → 更新实际执行审核的 Profile 引用 → X6/X7 → 再启用。
共享 Profile 升级前确认它服务的所有项目均已迁移。旧业务 worktree 不自动热改。
失败只阻塞受影响审核，不阻塞普通资料阅读与规划；保留已有产物。
回滚需恢复同一套文件与 runtime 配置，不保留新旧规则混用。

## X10. Provider 选择与额度回退
Run 启动时由宿主读取已批准的 reviewer-selection.json（模板位于 runtime/pal-review），配置位置必须由 runtime/任务明确提供；缺失就暂停选定审核。
这是人和宿主解释的选择合同，不是 PAL 自带自动 fallback。未填写/未启用/未验证的 provider 不可使用。
CLI 和具体模型分别选择，角色对应原生 reviewer；请求模型必须与已批准的 client JSON 或显式 profile 模型配置一致，不继承未知默认值。返回模型缺失只标未报告。
默认保留 Claude 主选；旧 Gemini 仅明确批准的 API/企业路径可候选，并须通过认证、只读、输入边界和原生方法测试。个人订阅的 agy 已配置为候选，但正式审核验证未完成。
自动回退默认关闭。仅明确批准的备用顺序、模型、数据外发与费用范围均满足时，才可对已确认结束的 quota/rate-limit 失败层切换一次。
成功层不重跑；pending 不回退；网络/权限/方法缺失/无效格式不是额度失败，不靠换模型绕过。
先保留失败记录与输入版本，再在备用 provider 中开新会话执行同一个完整原生子任务，不续用旧 session 或拼接半份结果。
备用失败即暂停，不轮转重试。报告逐层原 provider/失败原因/替代 provider/实际模型，不能把 Gemini 写成 Claude。
CodeBuddy（本机 codebuddy，不等同已验证 WorkBuddy 桌面账号）与 DeepSeek Harness dsh 使用 #481 的通用配置接口，不伪装成 Claude。两者仅完成内联通道测试，文件权限未验证，默认禁用；dsh 还须固定获准的 profile 模型。返回模型证据缺失本身不是禁用理由。
