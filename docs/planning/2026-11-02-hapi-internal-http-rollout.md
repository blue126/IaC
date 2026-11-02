# HAPI 内网 HTTP 切换与 PKI 退役记录

日期：2026-11-02（Australia/Sydney）。用户在确认PR已合并后，明确授权现网部署、旧服务退役和文档收尾。

## 发布版本与范围

[PR #210](https://github.com/blue126/IaC/pull/210)的Claude审核、review-policy-gate及其余CI全部通过，合并版本为`b217bc904fde1f7785b10be580b795df58199316`。发布包只包含本次迁移、回退playbook及五个相关角色；与已审核PR的对应源码一致。发布包SHA256为`ff28cac7077470cb3195a6b60049964eda0449061ec2a3220a6affb2ce344a39`。

由既有执行器通过现有BWS临时SSH凭据执行`migrate-hapi-internal-http.yml`，结束后销毁该次临时凭据。没有创建Sandbox、安装额外依赖、创建员工VM或修改Cloudflare／BWS授权。

- VM500：控制面及共享Hub内部代理改为HTTP；身份服务更新为内部HTTP连接方式。
- VM502：Runner loopback兼容代理、私有登录入口改为HTTP。
- pve2：仅执行既有边界编译器`verify --routing`，没有应用规则。
- 继续使用原私网9443端口；公网Access、HTTPS和Tunnel入口不变。
- 保留实际来源IP到固定工作区的映射、Hub令牌／JWT校验、PVE／SDN隔离及防伪。

## 执行与现场验收

Ansible结束状态：

| 目标 | ok | changed | unreachable | failed |
|---|---:|---:|---:|---:|
| pve2边界 | 3 | 0 | 0 | 0 |
| VM500 | 45 | 17 | 0 | 0 |
| VM502 | 32 | 11 | 0 | 0 |

迁移先保存root-only checkpoint，暂停旧签发timer并等待已有签发结束，再核对现有worker登记和Cloudflare身份／路由映射。候选配置均经Nginx与身份配置检查后发布。Hub及Runner的PID在playbook前后相同；身份服务按设计更新，代理执行平滑重载。数据库、个人Claude配置和令牌登记未由迁移改写。

内置现场检查通过：

- 两端loopback健康接口及VM502到VM500真实HTTP健康请求。
- VM500经真实私网HTTP访问VM502登录状态API。
- 非登记来源即使伪造工作区和转发头也被Hub代理拒绝。
- 公网代理的本机入口在没有Access身份时返回403。

另从VM502使用既有原生令牌执行7项实际业务探测，令牌和会话内容不输出：取得固定`default`／`vm502` JWT、读取会话API、拒绝伪造namespace后缀及无效JWT、打开真实SSE、建立Runner与终端的Socket.IO长轮询及WebSocket连接。探测只建立并关闭连接，没有创建任务或执行终端命令，也没有改动生产身份登记。这不是两个新员工的完整交付验收。

VM500固定内部路由到登录API检查通过，Tunnel服务保持运行。迁移后的首次只读检查中，登录执行服务报告`idle`、`authenticated: false`、`viewer_ready: false`；当时尚未主动启动个人授权流程。公开网址可到达Cloudflare登录页，后续浏览器验收与测试流程清理见下文。

## 已退役与保留材料

两台主机上以下单元均为`not-found`／`inactive`：

- `hapi-pki-controller.timer`及`.service`
- `hapi-pki-agent.service`
- `hapi-health.timer`及`.service`

旧证书agent endpoint配置及签发、配置辅助、证书巡检程序已由迁移playbook移除。当前代理不再加载内部TLS证书，证书有效期与CRL刷新不再属于日常维护要求。

两台主机均保留`/var/lib/hapi-internal-http/rollback.tar.gz`、`original-units.json`和`active.json`，目录0700、文件0600。原CA签发材料、叶证书和历史状态暂留，仅用于显式回退，不再有后台服务使用。没有删除BWS管理token、原生HAPI令牌或用户真实数据。VM500的VM级备份继续由用户负责。

回退使用`rollback-hapi-internal-http.yml`和单独批准的`hapi_internal_http_rollback_authorized`；本次检查了回退材料存在及权限，没有为演练再次切回现网TLS。

## 浏览器最终确认

用户完成Cloudflare登录后，浏览器自动进入HAPI会话列表，没有第二次HAPI令牌登录；同站Claude登录引导及状态API加载正常。真实终端鉴权已按上文验证，没有执行交互命令。

启动登录引导后，远程画面WebSocket返回502。只读核对确认VM502浏览器已切至KasmVNC，实际监听loopback8444；旧websockify6081不再监听。HAPI代理仍指向6081，切换前checkpoint中的代理也是该目标。现有桌面任务已安装支持KasmVNC的`employee-login-guide.py`，而当前HAPI固定执行agent尚未接入该桥。发现时GUI验收未通过，暂未改动另一任务的桌面实现。随后用户明确授权恢复noVNC，该故障已按下文解决。本轮验收启动的个人授权流程随后通过页面取消，没有提交OAuth授权或删除Firefox配置。

个人Claude登录是员工本人授权，与本次公网Access登录不同，本轮没有代为提交个人OAuth授权。

## 记录位置

私有证据保存在管理员运行目录的`operations/20261101-internal-http/`；执行器保留按合并commit固定的发布目录与部署日志。公开文档仅记录非秘密摘要，不提交运行inventory、令牌、私钥、会话内容或数据库。

## 现有试点恢复 noVNC

用户将新provisioning的默认模式和双向切换另列为feature，明确要求本次仅把现有VM502恢复到noVNC；发现桌面仍有Firefox及Claude Desktop运行后，用户确认可以关闭图形会话。

本次恢复从已合并源码取回旧浏览器控制器、Xvfb／x11vnc／websockify启动脚本和浏览器unit，移除该unit对Kasm桌面的drop-in依赖，将浏览器配置设为`legacy-novnc`。停止当前Kasm图形会话，原WireGuard桌面HTTPS入口改接loopback6081，保留原入口证书与地址。旧独立`employee-login-guide`停止，HAPI继续使用既有`claude-login-agent`。没有安装包、卸载Kasm、重建VM或修改provisioning。

配置恢复前逐文件核对SHA256，Python及Nginx候选校验通过；在既有桌面维护锁下保存root-only配置checkpoint后执行。个人home、Firefox profile与Claude授权未复制、删除或重置。HAPI Runner、私有入口代理、登录agent PID在前后保持不变。内部HTTP和PKI退役保持有效。

恢复后6项检查通过：模式与服务状态、5901／6081回环监听、真实noVNC静态页面、原overlay HTTPS证书验证与代理、Firefox就绪标记。VM500到VM502真实WebSocket升级和RFB握手通过；Chrome中的HAPI同站登录引导实际显示远程Firefox及官方Claude登录页面，原502已消除。验收后取消测试授权流程，日常Firefox保持运行，没有提交个人OAuth。

原overlay入口的服务端TLS与页面检查通过；当前管理员Chrome未连通该overlay地址，不能据此声称员工设备的WireGuard端到端验收完成。公网HAPI画面已经真实浏览器验收。

恢复前配置留在VM502的`/var/lib/hapi-novnc-restore/20261102/`，只作本次操作回退证据，不作为新开户或通用切换入口。KasmVNC软件及个人配置保留，未来默认noVNC／按需KasmVNC／支持切回的管理员功能尚未实现，另作feature。
