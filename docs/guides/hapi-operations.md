# HAPI 证书与网络规则巡检

`deploy-hapi-health.yml`部署独立的只读巡检。目标必须显式属于`hapi_health`组并指定检查范围，定时器默认不启用；获批发布时才设置`hapi_health_enable_timer: true`。2026-10-31曾按单独授权发布并验收；随后QA VM9101／9102完成回收，pve2巡检已撤下。目前仅VM500／VM502的证书巡检继续运行，见[发布记录](../planning/2026-10-31-hapi-health-rollout.md)及[QA回收记录](../planning/2026-10-31-hapi-qa-retirement.md)。

## 检查范围

| 目标 | 检查 | 周期 |
|---|---|---|
| VM500 | 网关客户端与Hub服务端证书、两个CRL | 每小时 |
| VM502 | Hub客户端与登录服务端证书、两个CRL | 每小时 |
| pve2 | 随两台QA VM回收，相关规则巡检已移除 | 已停用 |

PKI检查通过本机OpenSSL读取公有证书／CRL的有效期，提前14天报告临期，过期、尚未生效、缺失或解析失败也失败。它不读取叶私钥、CA签发私钥、BWS token或个人Claude资料。2026-10-31首次只读现场检查确认8项公有材料可读，当时最早到期为2027-01-28；随后已完成下文证书生命周期升级，验收当时pve2清单只有9101／9102；两者随后已由原Terraform state销毁，活动清单及专用ACL均已撤下。

规则检查只调用既有`hapi-network.py verify`，不执行apply或重启VM。失败输出最小JSON并使systemd服务失败，详情留在journal；没有配置邮件、外部通知或自动停机／恢复。它检测运行中漂移，但30秒间隔存在检测窗口，不能声称宿主清空规则后仍始终失败即关闭。

后续开户默认不启用运行期网络巡检，保留边界应用核验及启动门禁。将来是否启用生产监控及通知，由实际员工VM的运维要求另行决定；角色支持仍保留，不因升级自动增加定时器。

## 配置示例

以下只是公有材料路径示例，不是可直接部署的现网inventory：

```yaml
hapi_health_enable_timer: true
hapi_health_check_network: false
hapi_health_min_valid_days: 14
hapi_health_tls_files:
  - label: hub-server
    kind: certificate
    path: /etc/hapi-shared-hub/certificate.pem
  - label: hub-crl
    kind: crl
    path: /etc/hapi-shared-hub/crl.pem
```

角色先校验配置结构，再原子写入正式配置；不接收任意检查命令。定时服务将文件系统设为只读。网络检查仅放行既有`/var/lib/hapi-network/lock`的锁写入，用于与网络发布串行，其他回执和规则不由监控写入。

## 发布与回退

在获批Sandbox中使用私有、仅含目标与公有路径的inventory运行`deploy-hapi-health.yml`。发布仅增加检查脚本、配置、一个service与timer；不重启Hub、Runner、Tunnel或网络执行服务。验收检查实际配置、检查返回值、timer下一次运行时间及原服务状态。

回退将`hapi_health_enable_timer`设为false并执行相同角色以停用定时器；原服务和网络策略无需回滚。未授权前不删除现网文件。

`hapi-health`只读巡检不执行签发；续期和分发已由VM500上的`hapi-pki-controller`负责，见下文及[证书生命周期说明](hapi-pki-lifecycle.md)。签发私钥仅供VM500专用签发服务使用，不分发给员工VM。BWS管理员token的到期提醒和续发仍属于管理员授权生命周期，本次证书自动化不负责该项。

隔离测试6项覆盖真实OpenSSL有效期、临期／过期／未来材料、损坏文件、规则漂移／超时和安全诊断；相关production lint及语法检查通过。首次发布现场确认三台timer启用且检查成功、systemd单位校验及文件系统权限约束可用，已观察到pve2自动重复运行；两台VM的每小时周期由实际加载的timer属性验证，未等待完整一小时或执行生产重启。重复部署三台均changed=0，原业务服务及网络规则摘要保持一致。

## 证书生命周期改进

2026-10-31已按授权在VM500部署自动签发与分发，并在VM502部署受限agent。当前叶证书365天、CA1825天、CRL180天；每小时检查，叶证书提前60天续签、CRL每30天刷新。2026-10-31首轮自动签发验收时，叶证书到2027-10-31、CA到2031-10-30、CRL到2027-04-29；自动刷新后的实际到期日以现网公有证书／CRL及控制器状态为准。原只读巡检继续保留，生命周期服务负责续期与分发。详情见[生命周期说明](hapi-pki-lifecycle.md)与[发布记录](../planning/2026-10-31-hapi-pki-rollout.md)。VM500的VM级备份由用户负责，不新增数据库备份任务。
