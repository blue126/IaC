# HAPI控制面原型验证

本目录仅使用合成身份、临时证书和loopback服务，不读取实际inventory、Vault、BWS、Cloudflare或个人Claude认证。测试不是部署脚本；`inventory.yml`是不可用于部署的文档地址夹具。

在已获准、工具齐备的任务Sandbox中，从仓库根执行：

```bash
python3 tests/hapi-workspace/test-auth.py
python3 tests/hapi-workspace/test-proxy.py
python3 tests/hapi-workspace/test-login-agent.py
export ANSIBLE_CONFIG="$PWD/tests/ci/fixtures/ansible.cfg"
export ANSIBLE_ROLES_PATH="$PWD/ansible/roles"
ansible-playbook -i tests/hapi-workspace/inventory.yml ansible/playbooks/deploy-hapi-control-plane.yml --syntax-check
ansible-playbook -i tests/hapi-workspace/inventory.yml ansible/playbooks/deploy-hapi-workspace.yml --syntax-check
ansible-lint --profile production ansible/playbooks/deploy-hapi-control-plane.yml ansible/playbooks/deploy-hapi-workspace.yml ansible/roles/hapi-control-plane ansible/roles/hapi-workspace ansible/roles/claude-login-agent
```

`test-auth.py`使用cryptography签发真实RSA测试JWT，经Unix HTTP接口验证issuer／AUD／时间／签名、邮箱与subject联合归属、停用、冲突分配、CSRF、错误Origin、伪造路由头和票据交换后再次停用检查。

`test-proxy.py`需要批准Sandbox中的Nginx、cryptography、PyYAML和真实ansible-core，真实启动两份工作VM代理及一份控制面代理，以本机端口替代私网。它验证SSE在上游结束前到达、WebSocket 101及数据帧、按身份代理、Access凭据不转发到VM、mTLS错误服务名／错误客户端／证书吊销，以及真实TLS票据交换。测试生成的CA和私钥仅存在临时测试目录，退出停止本次进程并清理夹具；不改变系统Nginx或网络规则。Nginx缺失时该测试报告skip，不能算代理验证通过。

这些证明代理与身份接口的原型契约，覆盖隔离环境中的既有连接撤销，但不代表真实HAPI Socket.IO、真实Access链路、个人Claude首次授权或现网隔离验收。测试WebSocket帧不能冒充完整Socket.IO会话。具体状态见[第一阶段计划](../../docs/planning/2026-10-30-hapi-control-plane-phase-one.md)。


## 自动登录前端

锁定源码、补丁、overlay和构建器在[scripts/hapi-workspace-web](../../scripts/hapi-workspace-web/README.md)。当前21项前端测试与完整类型检查、生产构建通过；`workspace-browser.mjs`使用真实编译页面与Chromium，通过loopback模拟网关验证自动进入、账号切换及会话失效恢复。它不调用真实Cloudflare或Claude账号，不代表现网验收。

当前身份套件15项，包括撤销持久化和Unix权限；真实代理套件16项，包括既有SSE／WebSocket撤销、分配指纹不一致拒绝、登记损坏拒绝、2MiB响应完整转发，以及真实websockify到合成RFB端点。执行服务套件6项，使用已有隔离CLI夹具和实际tmux／PTY验证手工码、取消、超时与浏览器保留；并未使用真实Claude账号。

浏览器模拟回归还打开集中登录页面、提交模拟码并返回HAPI，验证身份变化后旧画面清理。浏览器RFB模块是测试替身，不能代替真实Firefox图形操作；协议套件的websockify是真实进程，RFB端点仍为合成服务。

角色验证不会自动开始个人授权；新VM须有经批准的Firefox／Claude基线和浏览器管理权限。noVNC资源仅在控制面，VM的websockify不再提供静态目录；不将个人OAuth或浏览器profile复制到模板。


## 提交前审核回归

代理夹具现在使用真实Ansible渲染完整Nginx模板，不再以手写filter替身模拟指纹编码。`test_failed_candidate_validation_preserves_the_live_registry_and_bob_stream`直接提取部署任务的template参数：错误subject分配须被候选校验拒绝，正式配置字节及权限不变，Bob原WebSocket仍能双向传输；合法候选另行验证可接受。

配置通过template的`validate`成功后才由Ansible原子替换。远程画面三个代理跳点的空闲读超时单独为1800秒，API／SSE／Socket.IO仍为60秒；票据／路由撤销由独立守卫执行，不依赖空闲超时。部署前仍需真实HAPI心跳与现网验收。
