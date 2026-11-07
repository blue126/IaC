# History Q6

c269b5b "feat(terraform): split the RemoteCC VMs into terraform/remotecc (story 5.19)"：实际 diff 新增 cloud binding；关联 PR #249 指向 #248，后者说明 root 拆分是为了 wsctl 与 Jenkins 分离，不把 PR 声称的离线 state 核验当作本轮实测。
1d0cda8 "feat(remotecc-ops): deploy RemoteCC from one repository and add Hugo"：实际 defaults/layout diff 将私有组件合成 remotecc checkout，PR #257 说明保留既有路径。其 push/check-out 窗口限制属 PR 记录，未现场核实。
29cfbc1：实际 diff 创建暂停 story，6d892db 后续把 plan 引用移至 remotecc/docs。没有发现批准实施的证据。
PR 查询：gh pr list --repo blue126/IaC --search <full SHA> --state merged --limit 5；本轮只读取得 #248/#249/#257。
历史查询触及 8 个不同 commit，未超过 10；未读取额外下一阶段计划。已有 layout 覆盖边界，无满足全部条件的新 ADR 提案。
