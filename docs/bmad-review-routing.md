# BMAD 选择性跨模型评审：路由表

版本：v4 修订 7；2026-09-15。范围是**替换选定 reviewer 的执行模型**，保留 BMAD 的评审方法、入口、时机、输入边界、输出格式和原生后续动作。

本文件路由的是**模型**，不是人。"某个 reviewer 走 Claude 还是保留原生"取决于 BMAD 的工作流结构和 CR-1 的能力，与谁派的工、用什么平台追踪工作项无关。调用协议见同包 `docs/bmad-cross-model-review.md`（下称"核心文档"）。

本文件不引入准入门禁。按核心文档 X1，本包不提供防止蓄意规避的技术边界；下面的规则防的是事故——换错 reviewer、把原生评审当成 Claude 评审、把执行失败当成零发现、把需要联网的核验换成只读进程。

## R0. 本次选择

| 工作流与位置 | 执行方式 |
|---|---|
| `bmad-architecture` 的 rubric walker | 独立 Claude Code / claude-opus-5 / high |
| `bmad-architecture` 的架构一致性对抗 reviewer | 独立 Claude Code / claude-opus-5 / high；仍按原生 AD 一致性问题审查 |
| `bmad-architecture` 的技术现实/版本核验 reviewer | **保留原生**研究执行方式与联网能力 |
| `bmad-build` 的三层 `review_layers` 及 one-shot 的 `oneshot_review_layers` | **默认不启用**；仅在任务明确要求跨模型审核时逐次开启，见 R1.2 |
| `bmad-code-review` 的三层基础评审及 full 模式 acceptance-auditor | 各层独立 Claude Code；保留 `when` 条件与原生分诊 |
| `bmad-build-auto` 的四层、`bmad-review` 已选 lenses | 沿用已有 Claude 定制，不另加一套评审 |
| PRD / UX 的独立 gate、研究 verifier / red-team、TEA 独立评审 | 本轮不修改，保留原生模型、方法与工具 |
| 原生 `doc_standards` 或 Retrospective 转调用 `bmad-review` | 继续原本转调用，沿用已存在的 Claude lens 覆盖 |

**为什么技术核验不换。** 版本/技术现实核验需要联网检索，而 CR-1 的子进程是只读、无网络工具的。把它换成 Claude 只读进程会**静默废掉**这个 reviewer——它会"审"完并返回零发现，因为它根本查不了。这是整张表里最危险的一格：换错了不会报错。同理，PRD/UX gate 与 TEA 有各自的工具依赖，本轮一并保留原生。

只处理新名称。旧名称交原生转发器解析，不新增旧入口 TOML。额外 ad-hoc reviewer 不因为带有 review 字样就自动换模型；先说明其目标和所需工具，未明确选择时保留原生方式。

## R1. 调用约定

1. **只在上表已选择、且本次真正要执行的 reviewer 上应用 CR-1。** 规划、材料恢复、普通讨论、lint、来源提取、文档生成、Spec 两遍 Self-Validate、确定性评分和测试运行保留原生方式。原生可选评审仍可明确跳过，不强制增加镜头。

2. **`bmad-build` 默认走原生，不自动起 Claude。** 它是日常主力实施工作流；每次 build 起三个 Opus 5 / high 进程会让费用与实际收益严重不匹配。要跨模型审核时，在任务中明确写出"本次 build 启用 CR-1 审核层"，或改用本身就带审核的 `bmad-build-auto`。未明确要求时，`bmad-build.toml` 的层不执行，宿主在回报中注明"本次未执行跨模型审核"，不得含糊成"已审核"。

3. **每个选中的 reviewer 启动独立 Claude Code 进程**，使用核心文档 X4 的 CR-1、`claude-opus-5` 与 `high`。不能以同供应商的子 agent 加一个 Claude 名称替代真实 Claude 调用。原来直接派发 reviewer 的工作流仍直接派发，不统一重定向到 `bmad-review`。

4. **调用前检查配置与环境，而不是凭据。** 确认本工作流的覆盖确实解析生效（核心文档 X6 预检覆盖全部六个 Skill），`BMAD_REVIEW_MODEL`/`ALLOWED`/`REQUIRED`/`MAX_USD` 已设置，Claude CLI 已认证。缺少实际安装入口、方法文件或认证时，**只将该项 Claude 评审记为"未执行"**，保留已完成的草稿和其他 reviewer 的结果。不能把原生同模型评审标成 Claude。

5. **未执行项必须一路可见。** 记为未执行的评审要出现在本轮报告、交接说明和宿主的工作项记录中。**存在未执行的必需评审时，上游工作项不得进入验收状态**（在使用工作项追踪器的宿主上，即父工作项不得进入待验收；具体状态名由宿主适配文档定义）。部分失败不毁掉整轮工作，但也不能悄悄变成通过。回报区分"已审核""零发现""未执行"三种状态，不合并成一句"没问题"。

6. **保留每项原生 reviewer 的完整方法和输出约定。** rubric walker 使用实际 good-spine checklist；架构对抗 reviewer 使用原生"两个下层单元都遵守 AD 仍不兼容"的问题；技术核验仍使用原生联网子 Agent。不能用通用 adversarial lens 偷换架构专用方法。

7. **每个 Claude reviewer 按核心文档 X3 获得自己的冻结 staging**：待审材料、方法文件副本及该项确实需要的来源/上下文。方法文件必须复制进 staging 并以 staging 内绝对路径交给子进程——`{skill-root}` 路径在受限 CLI 下读不到，即使读得到也是未固定的实时文件。不得加入宿主聊天、无依赖 reviewer 的报告或无关秘密；没有证据不等于没有问题。技术研究与网络检索不能伪装为只读文件评审。

8. **保持原生同步点**：启动该批所有独立 reviewer 后再收集和分诊；可同时包含 Claude 质量 reviewer 与原生技术核验。`structure`→`prose` 等原生依赖保持顺序；不得给无依赖 reviewer 看其他人的 findings。

9. **宿主验证结果语法和完整性后写入原生 review 文件**；修改和报告生成仍由获准宿主执行。留下实际 argv、`modelUsage`、输入 hash、退出状态、CR-1 摘要行与证据路径。失败或不合规结果不得当成零发现。

## R2. 定制方式与实际保证

`bmad-build`/`bmad-code-review` 使用原生 keyed `review_layers`，`bmad-build` 的 one-shot 使用独立的 `oneshot_review_layers`。仅改变各层 `instruction`，保留 IDs、`when`、方法与分诊。**使用工作流的真实变量 `{diff_output}`，不要引入 `{diff_file}` 这类未声明字段**——杜撰的模板变量不会被展开，会把未展开的花括号原样送进提示词。

`bmad-architecture` 没有统一的 reviewer executor 字段。本覆盖使用其公开 activation hook 和 `persistent_facts` 指定上述两个 reviewer 的执行方式；`finalize_reviewers` 不改、不追加。**这是提示词层的适配，必须通过真实 Run 验证派发结果，不能宣称平台代码已强制切换。**

原生转调用 `bmad-review` 的地方继续转调用；Architecture/Build 自有评审保持自己的流程。普通研究 subagent、PRD/UX gate、TEA、自检和用户评审不受本轮扩展影响。

## R3. 已知的未确认项

这两条不能靠读文档确定，必须在目标机器上验证；在验证前不要按无人值守运行受影响的入口。

1. **`bmad-code-review` 的 `when` 字段语义。** 本包写入 `when = "Only when {review_mode} = \"full\"."`。`bmad-review` 的 lens `when` 显然是模型理解的自然语言（例："Documents whose shape is the author's to change."）。若 `bmad-code-review` 的 `when` 实际是机器求值的表达式，这句会失效或报错，acceptance-auditor 可能永远不跑或永远跑。核心文档 X6 预检会打印各层解析出的 `when` 原文；用一次 `review_mode=diff` 和一次 `full` 的真实 Run 确认它的行为。
2. **`bmad-architecture` 的 activation hook 是否真能改变 reviewer 派发。** 见 R2。用一次真实 Architecture Run 观察是否确实起了独立 Claude 进程，且技术核验仍走原生联网路径。

## R4. 模型证据：主 reviewer 与辅助模型

2026-09-15 虚构输入实机探针的结果：

> 第一次调用返回 Opus 5 的评审，但 `modelUsage` 中**同时记录了 Haiku 的辅助用量**；固定 `--name` 后第二次调用的 `modelUsage` 只包含 `claude-opus-5`。

由此确立三条规则：

1. **`--name` 是缓解措施，不是保证。** 推测辅助模型原本用于自动生成会话名称，固定 `--name` 后不再触发；但这是推断，不是文档承诺的行为。CR-1 已固定传入 `--name`，仍须保留精确白名单检查。
2. **白名单检查区分两类。** `BMAD_REVIEW_REQUIRED_MODELS` 必须出现在 `modelUsage`（证明主审核真的发生）；`BMAD_REVIEW_ALLOWED_MODELS` 加可选的 `BMAD_REVIEW_AUX_MODELS` 之外的任何模型出现即失败。**辅助模型的出现不再导致整体失败**，但会记入 metadata 并在摘要行显示——早期版本严格的 `issubset` 会把这种合法运行误判为不合规。
3. **不自动加白名单。** 观察到新的辅助模型先弄清它做了什么，再决定是否写进 `BMAD_REVIEW_AUX_MODELS`。单次探针结果不保证以后绝无辅助模型。

## R5. 发布与验证

本包（跨模型评审核心）包含 **两个文档和六个 TOML，共八个文件**：

```text
docs/bmad-cross-model-review.md
docs/bmad-review-routing.md
_bmad/custom/bmad-build-auto.toml
_bmad/custom/bmad-review.toml
_bmad/custom/bmad-qa-generate-e2e-tests.toml
_bmad/custom/bmad-architecture.toml
_bmad/custom/bmad-build.toml
_bmad/custom/bmad-code-review.toml
```

需合并到目标项目并让后续 Run 取得相同版本才能生效；平台配置引用不能代替项目文件发布。这八个文件不依赖任何 agent 平台。

静态验收（核心文档 X6 预检）：原生 resolver 加载六项覆盖；默认 reviewers、条件与 one-shot 独立路径保留；预检接受原生 workflow 外层结构（`{"workflow": {...}}`）并报告完整解析结果，缺镜头、错条件、重复 key 均报错。

真实验收：先按核心文档 X7 用虚构材料验证 CLI 和模型返回，再分别运行 Architecture、Build normal/one-shot、Code Review diff/full。逐项要看到：

1. **Architecture** —— rubric walker 与一致性对抗 reviewer 确实起了独立 Claude 进程；技术/版本核验**仍走原生联网路径**（这条最隐蔽：换错了会返回空发现而不是报错）。
2. **Code Review** —— `diff` 与 `full` 各一次，acceptance-auditor 恰好只在 full 出现。
3. **Build** —— 默认 Run **没有**起 Claude 且回报写明"未执行跨模型审核"；再用一次明确要求的 Run 确认三层被启用。normal 与 one-shot 分别验。
4. **未执行项可见性** —— 故意让一项审核缺前提，确认它在报告和工作项记录中都标为"未执行"，且上游工作项停在验收之前。

CLI 冒烟不等于工作流端到端通过；未执行项明确保持待验收，按 R1.5 一路可见。

**费用范围。** 覆盖面从"仅 build-auto 四层 + review 五镜头"扩到六个工作流后，单日峰值会显著上升。`--max-budget-usd` 只管单次进程；本包不做本地累计记账。累计控制靠核心文档 X8 的事后对账，或你自行在供应商侧设置额度。`bmad-build` 默认关闭是控成本的主要杠杆。
