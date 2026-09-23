# BMAD 选择性跨模型审核路由
版本：r8-pal-candidate。只替换执行通道，不改 Coordinator 派工。调用协议见 docs/bmad-cross-model-review.md。

## R0. 选择表
| 原生入口 | 路由 |
|---|---|
| Architecture rubric walker / 架构一致性 adversarial | PAL 已批准 reviewer provider，分别使用 architecture-rubric / architecture-consistency |
| Architecture 技术现实和版本核验 | 保留原生联网研究 |
| Build review_layers / oneshot_review_layers | 默认原生；仅明确要求跨模型审核时走 PAL 对应角色 |
| Build Auto 原生启用层 | PAL 同名角色；不新增层 |
| Code Review 原生启用层 | PAL 同名角色；acceptance-auditor 仍仅满足原生条件才调用 |
| bmad-review 已选 lenses | PAL 同名角色；保留 applies_to、when、after |
| QA / PRD、UX 独立 gate / TEA / 研究 | 不改变原生工具与模型 |
| 原生转调用 bmad-review | 继续原转调用，不再增加一轮 |

## R1. 不变的规则
只在原生确实触发且 R0 选中的审核执行跨模型调用。普通对话、规划、自检、代码生成、测试不触发。
Build 未明确要求跨模型审核时仍执行其原生审核，不把“未执行跨模型审核”写成“没有任何审核”。
不改变原生方法及 finding 数量约定；本版本移除旧自建零发现/最小数量改写，完全交回安装版本。
新出现的必需 reviewer 先核对角色和工具能力，未配置不得静默降级为同模型。
独立层启动与等待、依赖镜头顺序、分诊及人类决策均按原生工作流。
只读 reviewer 不承担联网核验或执行测试；缺少必要能力标为未执行，不写成零发现。

## R2. 定制入口
六份 TOML 仅使用公开 activation hook / persistent_facts 接入 PAL 调用政策；
原生 review_layers、oneshot_review_layers、lenses、finalize_reviewers 从实际安装版本读取，不复制旧方法。
这些是提示词驱动的路由，不是机器强制派发。必须通过实际 Run 观察 clink 调用。
不要同时保留旧 CR-1 .user.toml：数组追加可能导致新旧协议同时执行。X6 检测残留。

## R3. 验收边界
输入隔离及每 Run cwd 按核心文档 X3；缺少技术边界不能仅凭文字承诺通过。
Code Review 的 no-spec/full、Build 的 opt-in/one-shot、Architecture 的选择性路由、Review 的 after
都要在实际宿主验证。手工从配置抽取四个 prompt 并行成功不证明 agent 自动执行了这些选择。
已完成与未执行分开报告，不丢弃失败；既不无限重试，也不额外添加审核轮数。

## R4. 证据
使用 PAL 的真实命令/模型/退出信息及完整原生 findings；费用有就记录，无就未知。
不再签发 CR-1 摘要，不要求旧 BMAD_REVIEW_* 白名单变量。工具成功不等于审核通过。

## R5. 发布
仍为两份审核文档及六份 TOML（8 个项目文件）；runtime 模板在 bootstrap runtime/pal-review，
属于服务配置，不由项目安装器自动写入全局目录。
跨模型包与团队包须同步迁移引用和 manifest；不修改派工行为。
## R6. 多 provider
选择与限额回退按核心文档 X10。当前配置候选为 Claude/agy/CodeBuddy/dsh（旧 Gemini 仅 API/企业），不自动启用未验证备用。
模型选择不会改变上述哪些 reviewer 要跨模型、何时执行或原生方法；也不改变 Coordinator 派工。
