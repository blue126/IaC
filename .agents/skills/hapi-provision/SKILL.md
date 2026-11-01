---
name: hapi-provision
description: "已撤回的独立 HAPI 开户方案说明；用于识别历史入口并停止执行。不用于实际开户、创建VM或发布接入。"
---

# HAPI 独立开户方案已撤回

用户于2026-10-31要求回退本轮HAPI开户流程，provisioning由用户重新设计。HAPI与WireGuard是同一员工工作区VM的两种接入方式；不得据旧方案为同一员工创建第二台VM，或把同一VM交给第二份Terraform state管理。

本skill仅保留撤回说明，不提供实际开户步骤。不要运行独立`hapi-admin`的申请、资源计划／执行或应用发布命令，也不要将它自动接入`onboard.sh`；统一流程尚待新设计。

本轮未部署的应用开户候选代码已反向撤回。早期基础设施原型、历史提交及运行材料保留，不作为当前可用开户入口。现网HAPI服务维护、VM500统一入口与单Hub、VM502 Runner和个人Claude登录引导不在本次回退范围；不得据此停止服务、删除VM、清理BWS或运行数据。

参考[撤回记录](../../../docs/planning/2026-10-31-hapi-onboarding-withdrawal.md)及[历史设计说明](../../../docs/architecture/hapi-workspace-provisioning.md)。既有WireGuard工作区操作仍按`employee-provision`的实际已批准入口执行；本次不修改其运行流程或交付授权。
