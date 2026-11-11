# 线上只读核查清单

结果：公开部分见 `live-fact-checks-results-public.md`（WILL-110，SHA-256 `1f55b5fa3e2314a3417b7ba46092b0859bf074e8af4e93994578f9d357bfc84e`），受限部分只在 WILL-110 附件。L1、L6、L7 已核实，L2 静态核实，L3、L4、L5 只部分核实。

授权来源：decisions D3。这些事实是 R11 的前置条件，研究未覆盖（研究报告 Open questions）。结果含私有实现或运行信息时只放 Issue 附件，不写入公开仓库；不记录员工信息、凭据值或配置值。

| 编号 | 要确认的事实 | 影响 |
| --- | --- | --- |
| L1 | 执行器 `/srv/remotecc`、`/srv/iac` 当前 commit，及其与研究基线 `fe3f25e`、`aad7d3d` 的差异 | 研究结论是否仍适用 |
| L2 | 执行器实际生效的代码根、工具链和数据目录绑定，只记配置项名称和路径 | R4、S10 |
| L3 | `iac-remotecc` 的资源地址清单、lineage、serial、execution mode，以及与当前代码的差异是否为零 | R2 的切换基线 |
| L4 | pending approvals 和未完成请求的数量与类型 | R5 的切换窗口 |
| L5 | 运行时实际用到的 IaC Vault 变量名 | S9 |
| L6 | Semaphore 模板清单及各模板指向的入口 | R4 |
| L7 | 执行器上的 Git 远端和部署钩子 | S0、S11 |

约束：

- 任一入口在确认真正只读之前不得调用。
- 不做 plan、apply、dry run、部署或任何写操作；需要 `terraform plan` 才能得到的差异结论，先交 will 决定。
- 用于 state 的只读命令不得把 state 内容写入公开路径。
