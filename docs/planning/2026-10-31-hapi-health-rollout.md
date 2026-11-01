# HAPI 只读巡检现网发布记录

2026-10-31，用户明确批准向VM500、VM502和pve2部署并验收独立只读巡检。批准的私有清单SHA256为`8f72697c2624eeb57af2e4cd27dc2d690aeba1913f1bd9902ba57f7f9d43519e`；部署前再次核对清单、inventory目标与8个实际部署源码文件摘要，三台目标均无同名文件冲突。

## 作用范围与结果

| 主机 | 检查范围 | 周期 | 现场结果 |
|---|---|---|---|
| VM500 | 网关客户端／Hub服务端证书及两个CRL | 1小时 | 4项通过，timer active/enabled |
| VM502 | Hub客户端／登录服务端证书及两个CRL | 1小时 | 4项通过，timer active/enabled |
| pve2 | HAPI清单的内核规则与回执 | 30秒 | 1项通过，timer active/enabled，自动重复运行已观察 |

部署只新增`hapi-health.py`、配置目录／JSON及独立service/timer。没有重启Hub、Runner、Tunnel或网络执行服务，没有修改网络规则、Cloudflare、BWS、个人登录或员工VM分配。

通过正式绑定的`iac-codex-hapi-provision-direct-v130`及专用Ansible配置执行。新Sandbox起初按默认策略拒绝管理连接，核对拒绝日志后只为该Sandbox加入三台目标的精确TCP22规则；没有修改全局策略。复用已验证主机公钥与现有SSH agent，不复制私钥。

三台部署均failed=0、unreachable=0；每台changed=6。使用同一inventory和源码重复部署，三台均changed=0。`hapi-network.service`原本是未驻留的已安装一次性加载任务，部署前后保持inactive；真实内核规则核验通过，没有为巡检启动它。

## 验收证据

- 真实安装脚本摘要、目标配置、root归属及0755／0644权限一致。
- 三台`systemd-analyze verify`通过，受限service实际运行成功，退出码0；pve2只允许写既有网络锁文件的限制可用。
- 从systemd实际加载属性确认1小时／30秒周期，timer均已启用；pve2观察到后续自动触发，非只检查服务文件存在。
- 以stdin提供临期阈值或缺失公有材料的独立配置，三台实际checker均返回失败；没有改动正式配置、证书或内核规则，也没有模拟生产规则被清空。
- 前后11项既有服务的状态／PID／重启计数一致，三台stateless规则集摘要一致。

私有回执在主检出的`remotecc/hapi-data/operations/20261031-health/`，包括`deploy.log`、`idempotency.log`、`live-before.json`、`live-after.json`、`live-acceptance.json`和`live-timer-observation.json`。初次验收脚本未处理systemctl重复输出的`TimersMonotonic`属性，修正收集器后确认实际配置正确；部署代码与批准摘要始终未变。

首次只读巡检验收未等待完整一小时重复运行，也未执行生产重启；该阶段没有新增外部通知、自动规则恢复或自动证书续期，失败留在systemd和journal，当时30秒规则检测仍存在窗口。该阶段最早证书／CRL到期日为2027-01-28；后续已完成[自动续期与分发](2026-10-31-hapi-pki-rollout.md)，该旧日期不再描述续期后的材料。

该部署阶段的授权仅含部署及验收，当时尚未提交源码。公开角色、测试和文档随后已经[PR #201](https://github.com/blue126/IaC/pull/201)完成CI与独立审核并合入`main`；私有源码和运行材料不进入公开Git。

后续状态：用户确认QA VM已无保留需要，2026-10-31按原Terraform state回收9101／9102并撤下pve2巡检；VM500／VM502的证书巡检继续运行。本文上述三主机数据为首次发布时的历史验收，当前状态见[QA回收记录](2026-10-31-hapi-qa-retirement.md)。
