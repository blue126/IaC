# HAPI控制面原型验证

HTTP简化候选的本机回归使用该工作树`.venv`与Nginx，无需Sandbox。`test-proxy.py`中的内部TLS案例已替换为实际来源绑定和伪造头拒绝；CA／CRL服务与旧`test-health.py`／PKI套件已从候选源码撤回。历史验收记录保留，当前限制见[内部HTTP说明](../../docs/guides/hapi-internal-http.md)。

单Hub方案的上游认证探针为`probe-shared-hub-auth.mjs`，只对锁定且摘要匹配的上游源码使用合成凭据，在任务Sandbox loopback运行。7个HTTP／Runner Socket.IO案例确认共享base允许客户端选择namespace；这是架构风险复现，不是租户隔离通过。结论与复现见[单Hub评估](../../docs/planning/2026-10-30-hapi-shared-hub-assessment.md)。

本目录仅使用合成身份、临时证书和loopback服务，不读取实际inventory、Vault、BWS、Cloudflare或个人Claude认证。测试不是部署脚本；`inventory.yml`是不可用于部署的文档地址夹具。

在已获准、工具齐备的任务Sandbox中，从仓库根执行：

```bash
python3 tests/hapi-workspace/test-auth.py
python3 tests/hapi-workspace/test-proxy.py
python3 tests/hapi-workspace/test-login-agent.py
export ANSIBLE_CONFIG="$PWD/tests/ci/fixtures/ansible.cfg"
export ANSIBLE_ROLES_PATH="$PWD/ansible/roles"
ansible-playbook -i tests/hapi-workspace/inventory.yml ansible/playbooks/deploy-hapi-control-plane.yml --syntax-check
ansible-playbook -i tests/hapi-workspace/inventory.yml ansible/playbooks/deploy-employee-hapi.yml --syntax-check
ansible-lint --profile production ansible/playbooks/deploy-hapi-control-plane.yml ansible/playbooks/deploy-employee-hapi.yml ansible/roles/hapi-control-plane ansible/roles/hapi
```

`test-auth.py`使用cryptography签发真实RSA测试JWT，经Unix HTTP接口验证issuer／AUD／时间／签名、邮箱与subject联合归属、停用、冲突分配、CSRF、错误Origin、伪造路由头和票据交换后再次停用检查。

`test-proxy.py`需要批准Sandbox中的Nginx、cryptography、PyYAML和真实ansible-core，真实启动两份工作VM代理及一份控制面代理，以本机端口替代私网。它验证SSE在上游结束前到达、WebSocket 101及数据帧、按身份代理、Access凭据不转发到VM、mTLS错误服务名／错误客户端／证书吊销，以及真实TLS票据交换。测试生成的CA和私钥仅存在临时测试目录，退出停止本次进程并清理夹具；不改变系统Nginx或网络规则。Nginx缺失时该测试报告skip，不能算代理验证通过。

这些证明代理与身份接口的原型契约，覆盖隔离环境中的既有连接撤销，但不代表真实HAPI Socket.IO、真实Access链路、个人Claude首次授权或现网隔离验收。测试WebSocket帧不能冒充完整Socket.IO会话。具体状态见[第一阶段计划](../../docs/planning/2026-10-30-hapi-control-plane-phase-one.md)。


## 自动登录前端

锁定源码、补丁、overlay和构建器在[scripts/hapi-workspace-web](../../scripts/hapi-workspace-web/README.md)。当前21项前端测试与完整类型检查、生产构建通过；`workspace-browser.mjs`使用真实编译页面与Chromium，通过loopback模拟网关验证自动进入、账号切换及会话失效恢复。它不调用真实Cloudflare或Claude账号，不代表现网验收。

当前身份套件17项，包括撤销持久化、Unix权限及共享Hub固定namespace票据交换；真实代理套件19项，包括既有SSE／WebSocket撤销、分配指纹不一致拒绝、登记损坏拒绝、2MiB响应完整转发、真实websockify到合成RFB端点、真实noVNC模块依赖与64路并发认证，以及共享Hub的证书／源地址联合绑定和namespace头覆盖。执行服务套件6项，使用已有隔离CLI夹具和实际tmux／PTY验证手工码、取消、超时与浏览器保留；并未使用真实Claude账号。

## 共享 Hub 与数据迁移

`test-shared-hub-auth.mjs <prepared-source>`在已批准Sandbox中运行实际补丁Hub的HTTP、Socket.IO、RPC及SSE，23项验证覆盖固定凭据、跨namespace资源、RPC方法覆盖、凭据撤销、JWT过期和损坏登记。准备源码必须经过`scripts/prepare-hapi-shared-hub.py`的固定源码摘要检查；测试使用独立临时数据和合成凭据。

`test-hub-data.py`的14项验证使用真实SQLite WAL，验证一致性备份、在线最终导入拒绝、Hub身份文件保留、篡改／软链接拒绝、重复导入不覆盖新写入、worker凭据映射和控制面签名格式／权限。导入保留原签名文件供校验，激活角色随后换为BWS控制面专用密钥；服务启动还校验批准的签名摘要及最终迁移标记，缺绑定或旧密钥无法启动。中断写入通过私有临时文件和独占发布安全重试；不把员工已知密钥继续用于共享Hub。最终快照要求来源Hub服务已停止，导入要求目标Hub已停止；脚本不自行停止服务，也不复制工程目录或个人Claude凭据。

`probe-hub-binary.py <binary> <sha256>`只在可执行该构建产物的Linux目标运行，以随机loopback端口、临时home和合成凭据启动子进程，验证编译产物与内嵌网页及认证边界，退出时停止本次进程。真实VM500已通过该烟测；这不代表现网Hub或数据库已迁移，现网状态见[迁移记录](../../docs/planning/2026-10-30-hapi-single-hub-migration.md)。

`test-hub-boundary.py`的4项验证检查对现场PVE helper的限定扩展保留既有功能、仅允许登记worker到精确Hub:9443、停用／广域／metadata目标被拒以及变更基线拒绝。`probe-hub-worker.py`使用实际worker叶身份验证mTLS、服务端固定namespace及管理端口阻断。

`probe-live-shared-hub.mjs <private-application-plan>`在任务Sandbox经两个真实worker路径对编译的隔离Hub执行7项回归：实际资源隔离、Runner WS／HTTP polling、终端、跨租户RPC覆盖及既有Runner／终端／SSE撤销，保留另一worker。临时测试不使用生产数据，结束恢复原登记并关闭本次连接；最终迁移另有20项真实历史数据、网关／Runner及签名隔离检查，不能将隔离测试报告当作已切换的证据。

浏览器模拟回归还打开集中登录页面、提交模拟码并返回HAPI，验证身份变化后旧画面清理。浏览器RFB模块是测试替身，不能代替真实Firefox图形操作；协议套件的websockify是真实进程，RFB端点仍为合成服务。

角色验证不会自动开始个人授权；新VM须有经批准的Firefox／Claude基线和浏览器管理权限。noVNC资源仅在控制面，VM的websockify不再提供静态目录；不将个人OAuth或浏览器profile复制到模板。

## 网络阶段

`test-network-plan.py`的18项回归验证冲突、固定网卡／可信peer、实际hook绑定、模拟PVE的所有权／幂等、pending／丢失响应、最小化快照、失败不发布和过期基线拒绝。三个network／allocation／access-bridge JSON夹具均为合成数据，不能部署。

按用户要求，本轮改为pve2两台新VM的真实测试，`test-pve-network.py`通过35项通信检查，`test-pve-lifecycle.py`通过11项停用／漂移／恢复／幂等检查。入口需要已授权的任务Sandbox、独立私有runtime及`--run-real-pve`，限定到本次测试VM的身份与分配，不能指向现有员工VM。结果见[两VM记录](../../docs/planning/2026-10-30-hapi-two-vm-pve2.md)。当前验收为vmbr0端口ACL，不是VLAN／VNet或真实HAPI应用验收。

历史`test-network-kernel.py`仍用于隔离namespace工具验证；当前Sandbox缺VLAN／bridge conntrack，只有9项基线／负向检查通过。它不作为本轮真实PVE验收前置，也不能代替真实结果，详情见[网络自动化说明](../../docs/guides/hapi-network-automation.md)。


## 提交前审核回归

代理夹具现在使用真实Ansible渲染完整Nginx模板，不再以手写filter替身模拟指纹编码。`test_failed_candidate_validation_preserves_the_live_registry_and_bob_stream`直接提取部署任务的template参数：错误subject分配须被候选校验拒绝，正式配置字节及权限不变，Bob原WebSocket仍能双向传输；合法候选另行验证可接受。

配置通过template的`validate`成功后才由Ansible原子替换。远程画面三个代理跳点的空闲读超时单独为1800秒，API／SSE／Socket.IO仍为60秒；票据／路由撤销由独立守卫执行，不依赖空闲超时。部署前仍需真实HAPI心跳与现网验收。
