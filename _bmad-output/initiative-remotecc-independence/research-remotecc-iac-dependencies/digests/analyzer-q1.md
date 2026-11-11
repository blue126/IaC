# Q1

布局文档把 apply-site、employee-miniprogram、hapi-control、wsctl 列为同一个私有 RemoteCC 仓库的组件，employee-data 与 hapi-data 为不入 Git 的运行数据。 `docs/architecture/remotecc-layout.md:8-16 (RemoteCC) @ aad7d3d`

公开 IaC 的忽略规则排除整个 remotecc 目录。 `.gitignore:36 (remotecc) @ aad7d3d`

文档说明私有仓库远端为执行器上的 remotecc.git、无 GitHub 远端，提交和分支独立于 IaC；这不是本轮对远端服务状态的核验。 `docs/architecture/remotecc-layout.md:19-25 (main) @ aad7d3d`

上述为已检查范围；不是整个仓库的反向依赖穷举。全部按 load-bearing 进入验证。
