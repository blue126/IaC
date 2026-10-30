# VM500 旧 gateway 网卡清理

2026-10-30，用户明确授权清理 net1–net8 及对应 Terraform、Netplan、路由和旧规则。VM500 保留为 HAPI 控制面，net0/vmbr0、原 MAC、192.168.1.140/24、默认网关192.168.1.1、原盘、CPU、内存与管理 SSH 保留。

## 完成结果

- Terraform 的 employee_access.legacy_gateway_retired=true；仅当全部旧工作区已迁移或退役才允许移除旧 NIC。动态旧网卡分支关闭，不会被后续正常 apply 加回。
- PVE 当前及运行配置只剩 net0，没有待生效网卡删除。
- Guest Netplan 中 emp0–emp7 与其10.231.*直连地址/路由已移除，上联声明逐字段保留。未修改 HAPI 应用配置。
- VM500 的旧 forward chain、employee_nat 表、旧 WG/网卡相关规则移除；保留自身 input/output 防护。employee-firewall.service 为兼容名称，现只加载主机策略，不再调用旧 gateway controller 或开启路由。VM500 IPv4 forwarding=0。
- PVE 旧表中的 tap500i1–8 引用移除；VM503 的既有退役 guard 保留。OCI Hub/PVE 新边界与八条工作区 Spoke 的近期握手检查通过。
- 六个旧入口仍被 mask，旧退役 playbook 遇到清理标记会跳过旧配置部署，不会重新生成 gateway 策略。

## 执行与验证

使用已批准的 iac-codex-mosh-hub-pilot-direct-v130，定向 Terraform 仅原位更新 VM500 和 inventory 两项资源，net0及其他 VM 配置不变。没有备份、快照、软件安装或新网络放行。私有执行记录保存在 employee-data/oci-hub-pilot-20261030/runtime/vm500-legacy-nic-cleanup。

已核实原因：bpg/proxmox 0.70.0 的 vm.go 在 network_device 变化时直接设置 rebootRequired=true，并调用 RebootVM。Schema 中名为 reboot 的参数实际是 RebootAfterCreation，只控制创建后是否重启，不能禁止更新时的自动重启。PVE 任务记录明确为 VM500 的 qmreboot，API身份 root@pam!terraform，悉尼时间2026-10-30 22:40:56发起、TASK OK；后续qmstart完成。此前代理误解该参数并承诺热移除，是判断错误。QGA boot_id变化证实系统重启；随后已恢复，后续配置未再次重启，管理 SSH 严格校验通过。参考 [0.70.0 官方源码](https://github.com/bpg/terraform-provider-proxmox/blob/v0.70.0/proxmoxtf/resource/vm/vm.go)，网络更新逻辑5243–5259行，创建后重启参数294–299行。

本次一次性清理 playbook、辅助脚本及专属测试已移至管理员私有执行记录，不进入主线。实施时五项合成回归、语法、lint 与实际状态检查通过。不要对已清理的 VM500 再运行旧 employee-firewall.py verify --routing。VM500 主机防护的长期配置由独立 HAPI 工作负责，本轮只保留 Hub 及旧 gateway 退出的声明和记录，不包含 HAPI 配置实现。
