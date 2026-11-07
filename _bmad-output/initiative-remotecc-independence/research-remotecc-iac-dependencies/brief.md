# Research brief

1. where: RemoteCC 代码、文档、运行数据分别位于哪些仓库与目录，哪些受版本控制？
2. how: RemoteCC Terraform root、共享模块、backend/workspace 与 state 的引用关系是什么？
3. what touches: 哪些 Ansible playbook、role、inventory 和脚本被 RemoteCC 调用，如何共享 IaC 资源？
4. how: wsctl 与执行器如何解析代码根、父目录、工具链及配置，哪些入口依赖 IaC？
5. how: 现有测试和 CI 如何验证上述接口，覆盖及执行边界是什么？
6. why / where: 公开与私有仓库目前的边界如何形成，旧迁移记录在哪里、记载了哪些已决定与未批准事项？

IaC commit: aad7d3d9edc453c409a63d56f9bdd6e7b9c3f3c9 (aad7d3d).
Private repository commit: fe3f25e603506ff792deb2176c4f5f211bae5e54 (fe3f25e).
File budget: 15 per question. History budget: 10 commits. Validation: normal.
Exclude from evidence search: _bmad-output/, _bmad/, plans/specs/stories/tickets.
Q6 explicitly permits the named migration record only as evidence of recorded decisions, never evidence of implemented code.
Private source findings stay outside the public checkout.
