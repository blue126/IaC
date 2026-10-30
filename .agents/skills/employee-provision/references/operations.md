# 运行与恢复

规范源码为主 checkout 的 remotecc/employee-admin，真实配置/凭据/申请/包/回执留在相邻 employee-data，均不进入 IaC。

活动工作区使用 `onboard.sh --profile oci-hub` 的 provision、plan、apply、registry、online、export、deliver 等已有入口；具体参数见 [原生开户](../../../../docs/deployment/oci-hub-native-provisioning.md)。代码/配置改变后重新生成计划，已完成状态复用，结果不明的上传或通知停止核对。

旧 employee-access role 和部署入口已移除；旧写操作无条件拒绝，不能用缺少配置/标记绕过。未带 profile 的 login/auth-status 保留用于共享微软 Mail.Send 授权，registry 读取旧分配历史；recover 只用于宿主已有同步日志恢复。历史设备关联保存在私有 state/legacy-device-registry.json，不含私钥。

遇到数据同步失败先通过既有 recover 核对日志，不覆盖未回收状态，不从 Sandbox 回写旧源码。活动 Hub 的接入状态以 Portal 为准，用量/采样是账本数据；不要恢复 reasons 镜像。

PVE 上仍需的退役 VM 端口 guard 有独立 retired-workspace-boundary role，兼容安装路径保留；VM500 自身防护属于其他工作，本轮不部署或修改 HAPI。
