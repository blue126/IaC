# VM502 桌面启停与故障恢复

本页适用于管理员已完成 [桌面就绪部署](../deployment/vm502-presentation-readiness.md) 的 VM502。Ubuntu 内直接运行 XFCE 和 KasmVNC；桌面、Firefox 均以 `employee` 运行，由独立 systemd unit 管理，`Restart=no`，不开机自动启动。它们使用同一个员工文件系统；个人 Firefox profile 不复制到本机或另建临时工作区。

## 日常操作

先通过自己现有的 OCI Hub 接入包连接 WireGuard，再通过 SSH/Mosh 进入本人 VM。以下命令在 VM 内以 `employee` 执行：

```bash
workspace-desktop start
workspace-desktop status
workspace-browser start
workspace-browser status
```

`workspace-desktop start` 等待 X 与 XFCE 真正就绪；`status` 是只读查询，区分停止、就绪和失败，不启动服务。`workspace-browser start` 使用已有桌面和唯一日常 Firefox profile，浏览器就绪后输出桌面入口。连接与信任见 [OCI Hub 桌面指南](employee-browser-lifecycle.md)。`workspace-browser open https://example.com/` 在受管 Firefox 打开普通网页；个人授权仍使用原有 `workspace-login`，不要把授权链接或验证码贴到本机终端、聊天或测试日志。

关闭本机桌面网页仅断开查看，桌面与应用进程继续运行。刷新后可以重连原会话。需要主动停止时：

```bash
workspace-browser stop
workspace-desktop stop
```

前者只停止受管 Firefox；后者先停止受管浏览器再停止桌面及桌面内应用。独立 SSH/Mosh 任务不属于桌面进程组。桌面内运行的 Claude Desktop 也会随桌面停止，不要在应用尚有工作时执行。不要直接运行第二个 Firefox 进程、删除 profile 锁、手动删除 X socket 或强杀未归属进程。

Mac／Firefox 的当前已验证组合：Kasm 设置开启 `IME Input Mode`，Mac 选择本机拼音输入法；固定服务端画面使用 `Local Scaling`，文本传递使用 Kasm Clipboard 面板。刷新后保留原会话已经由本人确认。中国侧网络体验另外记录，不以澳洲结果代替。

## 管理员维护

管理员使用 `prepare-employee-desktop.yml` 的三个显式阶段。`trust` 维护前端证书；`prepare` 暂存并检查候选，不替换活动桌面；`activate` 取得共享锁后，核对候选代次、平台、profile 写入者与监听冲突，再关闭此 VM 桌面路由并替换受管定义。它拒绝活动 desktop/browser，不能用于无提示踢掉员工会话。

启动入口和维护使用同一个锁 inode。维护标记存在时，普通启动必须拒绝；不通过删标记绕过。材料使用固定 `generations/<generation>/502/`，没有 `latest` 或跨 VM 引用。后端仅绑定 loopback TLS 8444，前端为该 VM overlay 的 HTTPS 8443。

若切换失败或管理员连接中断：

1. 保留 `/var/lib/employee-workspace/transition.json` 和受保护的候选材料，核对所属操作及桌面/浏览器实际状态。断开控制端不等于后台进程已经停止。
2. 若同一操作仍在运行，先等待并核对结果。新操作应通过共享锁串行化；不要手工删除锁或材料。
3. 原因修正后，使用同一已批准 inventory、材料代次和 `activate` 阶段继续。失败关闭只影响桌面 route；不恢复旧 VM500 网关或旧 noVNC 栈。
4. 成功后先执行 playbook 的 verify，再由员工按需启动桌面和浏览器，验证实际 HTTPS/WSS。

`activate` 成功后的元数据校验不等于桌面已启动。证书、后端凭据、SSH/WireGuard 私钥与 profile 都不进入公开仓库。密钥和设备身份仍走既有私有管理员入口，不通过本页重新生成。

## 验证范围

当前源码的 `test-desktop-oci.py` 汇集桌面、浏览器、真实 OpenSSL/TLS、真实 POSIX 锁及维护失败续跑回归。`tests/oci-hub/test-desktop-network.py` 的显式隔离执行入口负责合成 HTTPS/WSS 和 HAPI 桥；生产元数据必须保持，详见其 README。个人 OAuth、真实设备撤销、Code/Cowork 任务和中国侧体验均不能由这些合成结果推断。
