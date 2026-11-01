# HAPI 内部证书自动续期与分发

状态：已按用户授权于2026-10-31部署并完成首轮现场验收，VM500控制面承载签发服务。该服务只维护现有VM500／VM502的四个TLS身份，不承担provisioning，不创建VM或修改Cloudflare。

## 有效期与执行周期

| 材料 | 新有效期 | 自动处理 |
|---|---|---|
| 服务端／客户端叶证书 | 365天 | 每小时检查，剩余60天内续签 |
| 两套内部CA证书 | 1825天 | 首次发布延长；不足叶证书完整周期加60天时提前续期 |
| CRL | 180天 | 每30天重新签署并分发，保留原撤销条目 |

CRL有效期不再限制叶证书只有90天；两者分别维护。首次发布只延长现有CA证书，保持CA公钥、subject和信任范围，不进行CA私钥换代。叶证书复用本机已有密钥；私钥更换及新增撤销是另行审阅的运维动作。CRL撤销集合发生变化时，本续期循环停止要求专门发布，不会自动补发已撤销身份或在回退时删除新增撤销。

## 现有身份与材料来源

| 主机 | 身份 | 当前服务路径 |
|---|---|---|
| VM500 | `hapi-control-plane`客户端 | `/etc/hapi-control-plane/` |
| VM500 | `hapi-hub.internal`服务端 | `/etc/hapi-shared-hub/` |
| VM502 | `vm502`客户端 | `/etc/hapi-hub-client/` |
| VM502 | `vm502.hapi.internal`服务端 | `/etc/hapi-ingress/` |

2026-10-31现场核对确认上述路径和身份；VM502使用`hapi-ingress-proxy`，不部署旧的每VM Hub／workspace角色。自动续期发布前的叶证书／CRL最早到期日为2027-01-28，该批材料已由首轮签发替换。首轮签发验收记录：四张叶证书到2027-10-31 12:43:15 UTC，两套CA到2031-10-30 12:43:15 UTC，CRL到2027-04-29 12:43:15 UTC。此处是验收快照；后续实际到期日以现网材料及控制器状态为准。

Hub CA签发密钥已有HapiWorkspace BWS记录；入口CA签发密钥目前保存在既有加密运行Vault。两者均已在管理员环境按公钥摘要匹配现网CA，未打印私钥。本轮保持既有来源，不迁移BWS项目或机器授权。部署通过加密runtime Vault向VM500的root-only凭据目录提供这两把签发密钥，再由systemd `LoadCredential`交给专用`hapi-pki`用户；VM500不取得BWS管理员token。叶私钥仍留原VM，不经网络分发。

## 自动化路径

1. `hapi-pki-controller.timer`在VM500每小时运行，专用服务只可写自己的状态目录。
2. 两台机器上的root证书agent仅监听Unix socket；VM502经已有9443 mTLS入口的`/_hapi_pki/op`访问，额外限制源为VM500，不新增监听端口。
3. agent核对固定身份和公钥，返回公有材料及本机CSR。远端不能指定文件路径、命令或新的签发身份。
4. 控制面按批准profile签发，在两端预校验；写前记录generation、原材料及待发布材料。
5. 原子替换公有证书／CA／CRL，保留权限与原私钥，分别验证并平滑reload对应Nginx实例，不重启Hub、Runner或个人Claude。
6. 在两个方向建立真实mTLS连接，校验证书指纹及`/health`、`/api/login/status`。短暂旧Nginx worker允许有限重试；全部通过才记录已验证。
7. 失败尽量回退本generation的公有材料；未知文件变化、新增撤销、无法确认的回退或配置漂移进入人工核对状态，不自动覆盖。

CA私钥和签发权限只在VM500的专用签发环境；worker agent在systemd中看不到该目录或签发服务凭据。签发器的文件和网络权限均按两台现有主机限定。配置及完整TLS签名／用途验证使用[cryptography X.509接口](https://cryptography.io/en/latest/x509/reference/)，凭据隔离依据[systemd credentials](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)。

## 部署与静态配置的边界

`deploy-hapi-pki.yml`先准备两端agent，再准备VM500签发服务。显式启用timer时，先执行并验证首轮续期，再开启定时器；verify标签只做只读检查。

初次在VM502添加endpoint时，必须绑定现有Nginx配置SHA256和服务名，只增加一个受限include及片段，语法或reload失败恢复原文件。以后配置漂移须重新准备部署计划。

完成签发后，agent写入自己的管理标记。普通`hapi-control-plane`、`hapi-shared-hub`、`hapi-hub-client`和`hapi-ingress`角色检测该标记后跳过TLS材料覆盖；历史运行Vault不能把旧证书写回。其他服务配置仍由原角色负责。

证书失效之后可能无法再通过旧mTLS连接自动修复，须由管理员走原管理通道恢复；本实现不提供忽略证书、忽略CRL或降级明文的旁路。现有只读`hapi-health`巡检继续保留，控制器另记录`health.json`及systemd失败状态；尚未新增外部消息告警。

## 已完成的发布与验证

隔离测试覆盖真实CSR／证书签名、双向TLS、有效期与撤销保留、幂等、回执丢失回退与续跑、profile／签发密钥／文件漂移拒绝；真实Nginx测试覆盖新增endpoint及路径拒绝。另用实际Ansible验证普通角色不能覆盖已管理TLS，并测试Nginx配置发布与恢复。

VM500／VM502 agent与VM500定时器均已启用，四张叶证书、两套CA证书和CRL已更新；双向真实mTLS及再次执行的无变更回读通过。源码与材料清单已授权，现场记录见[发布记录](../planning/2026-10-31-hapi-pki-rollout.md)。没有安装BWS SDK。

VM500由用户承担VM级备份；本任务不另建数据库备份服务。证书签发状态目录和签发凭据随该VM备份保留。旧的一次性现有VM挂接执行器及专属角色、测试和文档已按授权清理；共享组件保留，PKI服务不依赖被移除的执行器。

验证：20项相关隔离／集成回归通过，Ansible lint与语法检查通过。Sandbox缺少systemd-analyze的离线解析测试跳过，但目标主机的实际systemd单元校验已通过。部署中修正了systemd凭据0440兼容及加固环境中的Nginx重载；采用固定PID校验和直接向现有master发送reload，不使用PAM会话，不重启业务服务。

配置中的旧CA／CRL只用于初次引导和公钥绑定；后续以VM500受保护状态目录中的当前authority材料校验有效期，历史引导CRL到期不会停掉已续期服务。普通文件的私钥仍要求严格权限，0440兼容仅限systemd凭据目录中的预期属组。
