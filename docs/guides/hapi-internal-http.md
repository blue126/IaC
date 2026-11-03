# HAPI 受控内网 HTTP 简化

> **历史记录（2026-11-03）**：本文涉及的角色、playbook、脚本与测试已在 story 5.24 中删除，员工 VM 一侧改由 `hapi` role管理（默认随`prepare-employee-desktop.yml`的provision／update阶段部署），见[统一入口](hapi-unified-entry.md)。下文命令不可再执行，仅供追溯。

状态：2026-11-02已按用户授权部署[PR #210](https://github.com/blue126/IaC/pull/210)合并版本，VM500／VM502内部HTTP切换及playbook现场验收通过，旧PKI和证书巡检服务已退役。详见[发布记录](../planning/2026-11-02-hapi-internal-http-rollout.md)。本方案接受VM500到员工VM这一段明文传输，不新增VPN或SSH隧道。

## 保留的职责

- 公网仍由Cloudflare Access验证用户，HTTPS及Tunnel配置沿用既有入口。
- VM500继续运行唯一Hub、会话数据库、身份网关及登录引导；员工VM保留Runner、Claude与个人Firefox环境。
- HAPI原生API令牌／JWT和本项目固定凭据到namespace的补丁继续工作。浏览器通过已验证Access身份换取本人JWT；Runner的实际来源IP被代理固定映射到本人namespace／credential，再由Hub校验令牌与资源归属。
- 源地址使用Nginx的实际`$remote_addr`，不使用客户端自报的`X-Forwarded-For`；客户端提供的工作区身份头被代理覆盖。未知来源拒绝，错误工作区令牌由现有Hub租户校验拒绝。
- PVE／SDN继续负责VM外隔离和IP／MAC防伪。部署入口首先只读运行现有边界编译器的`verify --routing`，成功后才允许内部HTTP迁移。没有核验边界时迁移失败，不自动修改网络授权。

内部端口仍是既有私网9443，协议改为HTTP；Hub本体仍只监听VM500 loopback 3006。worker的loopback兼容代理保留，减少Runner连接方式变化。员工VM的默认路由、员工VM资源所有权和身份登记不由此迁移重新分配。

## 移除的运维体系

四个当前代理角色不再要求内部CA、CRL或叶证书变量。内部证书签发／分发agent及定时器、证书只读巡检程序和PKI写入endpoint退出当前源码；现网对应的旧程序只在HTTP验证通过后停用并移除。

CA签发密钥、历史证书与签发状态不在迁移中销毁，仍保留为显式回退材料。本方案没有新增备份系统；VM级备份由用户负责。TLS材料属于旧布局，不能因此重新启用已撤回的独立HAPI开户流程。

## 部署与回退入口

在已授权执行位置使用该任务工作树自己的`.venv`和项目collections；不使用已退役Sandbox，也不使用其他项目的全局Ansible。涉及员工VM的管理写入由现有执行器授权通道完成，不临时扩大Mac来源或借路绕过管理边界。

```bash
# 从ansible目录执行；此处只有语法检查，夹具明确不授权实际迁移。
../.venv/bin/ansible-playbook -i ../tests/hapi-http/inventory.yml playbooks/migrate-hapi-internal-http.yml --syntax-check
../.venv/bin/ansible-playbook -i ../tests/hapi-http/inventory.yml playbooks/rollback-hapi-internal-http.yml --syntax-check
```

此次迁移使用私有inventory和用户批准的发布清单，由既有执行器执行。后续变更仍使用独立批准的清单。`hapi_internal_http_authorized`默认false，必须显式确认受控内网明文模型。当前原地切换入口限定VM500与VM502，不表示已完成新员工provisioning。

迁移顺序：

1. 只读核验PVE现有边界；核对运行中的代理、现有worker登记和Cloudflare／工作区映射。
2. 在两台主机的root-only目录`/var/lib/hapi-internal-http/`保存一次性旧配置／单元checkpoint及原启用状态，不读取Hub数据库或复制个人Claude凭据。
3. 暂停签发timer并等待已开始的签发结束，避免迁移中并发修改材料。
4. 在原服务仍运行时生成并验证全部HTTP候选，保持worker和用户归属不变；校验失败不发布候选。
5. 发布候选并向现有代理master发送HUP，协调两端协议切换。控制面身份服务升级时重启该服务；Hub及Runner PID必须保持。
6. 验证worker到Hub的真实HTTP、VM500到登录API的真实HTTP、未知来源／伪造头拒绝、公开代理匿名拒绝及原Hub／Runner进程存活。
7. 所有主机验证成功后，才停用并删除旧`hapi-pki-*`／`hapi-health`单元和相关程序。任何验证失败都会终止后续退役；按已批准回退入口恢复，而不是带着失败继续。

`rollback-hapi-internal-http.yml`要求独立的`hapi_internal_http_rollback_authorized`。它核对root-only archive及固定成员白名单，恢复原HAPI配置和单元、校验Nginx并reload、恢复原身份进程和先前启用的证书服务，不覆盖Hub数据库、令牌登记或个人Claude文件。checkpoint只在首次迁移创建，重复运行不会用新HTTP配置覆盖原回退材料。

## 本机验证与现场验收边界

本机使用项目Python/Ansible与Homebrew Nginx，仅启动临时loopback进程。身份回归覆盖真实签名Access JWT、CSRF、停用与会话撤销，也确认Cloudflare公钥获取仍严格使用HTTPS验证。真实代理回归覆盖两用户路由、HTTP来源固定绑定、伪造namespace／credential／转发头覆盖、错误Host、非控制面来源、SSE／WebSocket撤销、票据交换及大响应。

本机没有Linux noVNC静态包及websockify，三项对应的真实GUI用例明确skip，不算通过。未更改的Hub租户补丁不因这些代理回归获得新的全通道验收结论。现网发布还须验证真实Runner重连、Socket.IO终端、登录引导／noVNC、浏览器自动登录和错误工作区访问拒绝；不得将本机模拟上游或跳过项目当作现场验收。
