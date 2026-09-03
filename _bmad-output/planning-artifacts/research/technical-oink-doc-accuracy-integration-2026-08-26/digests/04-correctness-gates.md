# 持续文档准确性与发布门禁

**范围。** 仅使用外部资料；`accessed 2026-08-26`。以下明确区分事实、推论与建议。

## 定义与可验证边界

**事实。** W3C DQV 不给“质量”一个脱离用途的总定义，而以维度、指标、测量、政策和注释表达 fitness-for-purpose；其准确性是“在特定使用情境中正确表示真值”，完整性是预期属性/实体均有值，并可用 `wasGeneratedBy`、`wasAttributedTo`、`generatedAtTime`、`wasDerivedFrom` 记录测量 provenance。[W3C, 2016-08-30, accessed 2026-08-26, https://www.w3.org/TR/2016/NOTE-vocab-dqv-20160830/]

**推论。** 对代码/IaC 文档，准确性应定义为“可验证声明与指定 oracle 一致”；覆盖率是应验证声明中已被 oracle 判定的比例；freshness 是声明所依赖对象自上次验证后未变化且未超 SLO；provenance 至少含源版本/摘要、生成器与版本、参数、时间、执行身份。SLSA 同样要求验证签名、产物摘要、builder、规范源、`buildType` 和外部参数，并明确 provenance 若不被检查就不起作用。[SLSA/Linux Foundation, v1.2, n.d., accessed 2026-08-26, https://slsa.dev/spec/v1.2/verifying-artifacts]

**建议。** 建立声明清单，至少记录稳定 ID、文档位置、规范源、依赖文件/接口、owner、风险级别、oracle 与 freshness SLO。依赖摘要变化或 SLO 到期即转 stale；仅修改文档时间戳不能重置 freshness。清单外内容计入覆盖率分母，防止以“没有测试”制造高准确率。

## Deterministic Checks

**建议。** 按声明类型绑定 oracle：内部链接/锚点解析；外链 HTTP 结果（超时、限流为 `unknown`，不伪装 broken/pass）；JSON/YAML/OpenAPI 按锁定 schema 验证；文档命令在固定镜像、无生产凭据的临时环境执行；生成器后执行 clean-diff；Terraform 例子跑 `fmt/validate`、必要时 `test command=plan` 与断言；API、输出、变量、默认值做文档到实现的 contract test；最后用 policy gate 检查 owner、时限和风险例外。JSON Schema 只断言结构约束，且 `format` 可能仅为 annotation；Terraform `validate` 只查语法和内部一致性，不验证远端服务。因此 schema/validate 通过不能宣称语义正确，必须补例子或契约 oracle。[JSON Schema/IETF Internet-Draft, 2022-06-16, accessed 2026-08-26, https://json-schema.org/draft/2020-12/json-schema-validation] [HashiCorp, n.d., accessed 2026-08-26, https://developer.hashicorp.com/terraform/cli/commands/validate] [HashiCorp, n.d., accessed 2026-08-26, https://developer.hashicorp.com/terraform/language/tests]

## PR 控制的可靠边界

**事实。** GitHub required check 可把 `success`、`skipped`、`neutral` 都视为可合并；条件跳过的 job 报 Success，而路径/分支过滤掉整个 required workflow 会永久 Pending。Loose 模式不测试最新 base，且默认管理员/具 bypass 权限角色不受 branch protection 约束；状态来源若设 `any source`，有写权限的人或集成都可设置。CODEOWNERS 仅在启用 required code-owner review 后才是门禁；多 owner 任一人批准即满足，非法行会被跳过，且 CODEOWNERS 自身若无 owner 可被改写。[GitHub, n.d., accessed 2026-08-26, https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches] [GitHub, n.d., accessed 2026-08-26, https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks] [GitHub, n.d., accessed 2026-08-26, https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners]

**建议。** 使用 ruleset/branch protection 强制 PR、strict 或 merge queue、唯一 check 名、固定预期 GitHub App、禁止 bypass、禁止 force-push、保护 `.github/` 与 CODEOWNERS，并启用 stale-dismissal 或 latest-push approval。required check 应始终运行，由内部步骤输出明确 pass/fail/unknown；不要让“未执行”成为绿色。OpenSSF 也把 up-to-date、latest-push approval、status checks、CODEOWNERS、dismiss stale reviews 和管理员约束分层，且承认自动探测会有误判，低分不是风险定论。[OpenSSF Scorecard, n.d., accessed 2026-08-26, https://github.com/ossf/scorecard/blob/main/docs/checks.md]

## 最小准确性 Scorecard

**建议。** 不合成一个易掩盖风险的总分，每次发布报告五项：`verified coverage=(P+F)/N`；`observed accuracy=P/(P+F)`；`unknown=U/N`；`stale=S/N`；`provenance complete=具备 source digest+tool version+parameters+time+identity 的检查/N`。其中 N 为声明清单，P/F/U/S 为互斥状态。另从人工复核样本计算 `FP=误拦/全部拦截样本`、`FN=漏放/全部放行审计样本`，同时公布样本量和 95% 区间；事故发现的漏放并入 FN，但不能替代随机抽审。

## 发布门禁

**建议。** 关键运行手册、安全/IaC 参数与破坏性命令要求 `F=U=S=0`、provenance 完整且 CODEOWNER 批准；普通说明允许 `unknown/stale` 进入限时例外，但必须记录 owner、理由、范围、证据、到期日，过期自动转 fail。链接瞬时失败先重试并降级 unknown，连续失败再阻断，以压低 FP；对绿色结果按风险分层随机抽审以估 FN。人工审批只处置机器无法判定的语义、例外和风险接受，不得覆盖可重复的确定性失败；审批后任何相关提交都应失效并重审。OpenSSF 指出机器检测难覆盖所有实现，会产生 false positive/negative，而人工 claim+justification 可对冲但增加成本；这支持“自动门禁+抽样校准+有时限人工例外”，而非二选一。[OpenSSF Scorecard, n.d., accessed 2026-08-26, https://github.com/ossf/scorecard/blob/main/docs/checks.md]
