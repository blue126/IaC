# RemoteCC 线上只读核查结果（公开部分）

- 工作项：WILL-110，依据 `live-fact-checks.md`（SHA-256 `729516b7746db60545c1304e927611f84671548ebce86eeedc06c971edebcd9b`）
- 核查时间：2026-11-07 02:43–02:53 UTC
- 对比基线：公开 IaC `aad7d3d9edc453c409a63d56f9bdd6e7b9c3f3c9`，私有 remotecc `fe3f25e603506ff792deb2176c4f5f211bae5e54`
- 本文件不含私有实现、配置值、凭据或员工信息；细节在受限文件 `live-fact-checks-results-restricted.md`。

## 结论

L1、L2、L6、L7 已核实。L3 的现状部分因无 HCP 访问未核实，L3 的差异结论需 will 决定。L4、L5 部分核实。

| 编号 | 事实 | 状态 |
| --- | --- | --- |
| L1 | 执行器代码 commit 与基线差异 | 已核实 |
| L2 | 代码根、工具链、数据目录绑定 | 已核实（静态配置；运行期派生配置未观察） |
| L3 | `iac-remotecc` 后端绑定 | 已核实 |
| L3 | 资源地址清单、当前 lineage、serial、execution mode | 因无访问未核实 |
| L3 | 与当前代码的差异是否为零 | 需 will 决定（需要 `terraform plan`，未执行） |
| L4 | 执行器本地的待处理项 | 已核实：未发现待处理项 |
| L4 | 网站侧实时待处理申请 | 因无访问未核实 |
| L4 | 历史运行记录是否算未完成 | 需 will 决定 |
| L5 | 代码静态引用的 IaC Vault 变量名 | 已核实 |
| L5 | 运行时实际解密使用的变量名 | 因无访问未核实 |
| L6 | Semaphore 模板清单及入口 | 已核实 |
| L7 | 执行器 Git 远端和部署钩子 | 已核实 |

## L1 要点

- 私有 remotecc：执行器与基线 `fe3f25e` 相同，研究对私有代码的结论不受版本差异影响。
- 公开 IaC：执行器在 `1f741691a4b0c6c29ed2fbb999ac1b1eb4d867ef`，落后基线 17 个 commit，没有基线之外的提交。基线 commit 不在执行器上。
- 两棵工作树的已跟踪文件逐一比对 blob 哈希，均与各自的 commit 一致。
- 这 17 个 commit 没有改动 `terraform/remotecc` 和 `terraform/modules`。

## 未决项

1. L3：取得 state 概况需要 HCP 访问，由 will 选择提供方式。
2. L3：是否执行 `terraform plan` 由 will 决定。
3. L4：网站侧待处理申请数量需要确认。
4. L4：历史运行记录是否算作未完成，由 will 判断。

本次未执行 plan、apply、dry run、部署、重启、审批或重试，也未调用 `wsctl`、`terraform`、`ansible`。
