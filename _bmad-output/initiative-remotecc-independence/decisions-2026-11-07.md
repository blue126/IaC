# RemoteCC 独立：用户决定（2026-11-07）

来源：Multica WILL-107 线程，will 的回复“123都同意，不过3的那个目录放对了吗？”及其前后的 Coordinator 问题。

- D1 目标：RemoteCC 从 IaC 仓库独立出来，不再与 IaC 共生，走完整 BMAD 流程完成代码交付（WILL-107 描述）。
- D2 范围：以研究列出的依赖面作为候选。“带走”和“留在 IaC”的划分尚未决定，由 will 在 `scope-candidates.md` 逐项确认。
- D3 线上核查：授权对线上现状做只读核查，范围为执行器当前代码 SHA、实际配置、state、pending approvals。不授权任何线上写操作。
- D4 研究入库：同意公开研究记录入库，`restricted/` 不入库；提交需等目录确定，且提交本身另行授权。
- D5 目录：研究放在 initiative 目录下，不挂在 `_bmad-output` 根下。initiative 名称暂定 `initiative-remotecc-independence`，待 will 确认。
- D6 范围划分：will 在 WILL-109 回复“除了我问的这几个，其他可以按照你的建议来执行”。S0–S7、S9、S10、S12–S15 和 S8 的 `kasmvnc`、`semaphore` 按建议执行；initiative 名称和目录按 D5 确认。
- D7 CI：S11 的 GitHub 私有远端问题“暂时跳过”，等效校验的要求保留。
- D8 待确认：S8 的 `admin-ssh-keys`、`host-firewall`，will 询问用途后尚未决定。
- D9 管理员访问（取代 D8 对 `admin-ssh-keys` 的待定）：will 认为员工 VM 是整台租给员工的，上面不应有管理员 SSH 公钥；管理员需要访问时走 PVE CLI 或控制台。
- D10 `host-firewall`（取代 D8 对它的待定）：will 认为不值得单独做一个 role。防火墙规则保留，不再单独成 role。
- D11 提交：will 授权把 initiative 目录提交到本地分支；推送和 PR 不在授权内。
- D12 管理通道：will 认为开户和维护自动化不必经 SSH，倾向走 API。首选 PVE API 加 QEMU Guest Agent，可行性由架构验证。员工自己设备的 SSH 接入不受影响。
- D13 `host-firewall`：will 确认 D10 的理解，规则保留，role 不保留。
- D14 角色命名：will 不要 `remotecc-ops-runtime` 这个名字。迁移时改名为 `remotecc-ops`，与主机和 `deploy-remotecc-ops.yml` 一致；新名称由产品负责人提议，待 will 确认。
- D15 验收：will 于 2026-11-07 在 WILL-109 回复“验收”，需求与约束 v1 通过；D14 的 `remotecc-ops` 名称随之确认。这不授权推送、PR、部署或线上操作。
- D16 lifecycle 现状：will 于 2026-11-07 在 WILL-111 确认 HAPI 和 mosh 已完成，小程序暂停，并要求修正 lifecycle 看板，另开 WILL-112。will 未列出其他继续中的工作。
- D17 切分：will 于 2026-11-07 在 WILL-111 回复“按建议”，并同意过渡期暂停 RemoteCC 改动。5 个 epic 的草案通过：epic 1 和 2 分开，OCI Hub 单独成 epic，R11、R12 不进 epic，R14 排在最后，epic 1 最后一次同步到 epic 2 完成之间暂停 RemoteCC 改动。这不授权提交、推送、部署或线上操作。
- D18 Hub 终态：will 于 2026-11-07 在 WILL-111 同意按 S4、S9 执行：Hub 服务带走，密钥进 BWS，由架构修订 AD-25、AD-30、AD-31。
- D19 先后：will 于 2026-11-07 在 WILL-111 同意先做 lifecycle epic 8–12，再做本 initiative。D16 中“没有继续中的工作”由此被取代。这不授权提交、推送、部署或线上操作。
