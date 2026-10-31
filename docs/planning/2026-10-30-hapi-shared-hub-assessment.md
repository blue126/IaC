# VM500 单 Hub、多 Runner 可行性评估

状态：下文为原生认证风险评估；2026-10-31已完成固定凭据／namespace鉴权改造并将Hub与数据库迁到VM500。23项隔离回归、7项真实worker通道回归及20项迁移现场检查通过，用户已确认CF登录后HAPI可用。完整开户仍未就绪，详见[迁移记录](2026-10-30-hapi-single-hub-migration.md)。

## 结论

HAPI可以在VM500运行一个Hub，两台员工VM各运行Runner／Claude；但不能把当前设计直接替换为“共享基础token＋员工namespace”后就宣称隔离完成。当前锁定v0.33.2的namespace由客户端提交，Hub仅验证共同基础token。员工拥有本机sudo，可读取Runner凭据并更换namespace后缀；选择已知／可猜的另一员工namespace会取得相应身份。

本轮还只读核对了GitHub API返回的最新release v0.33.3：其namespace文档与HTTP／Runner认证源码仍采用相同方式；没有升级、下载新运行产物或对0.33.3做运行测试。证据来源为[namespace说明](https://github.com/tiann/hapi/blob/v0.33.3/docs/guide/namespace.md)、[HTTP认证](https://github.com/tiann/hapi/blob/v0.33.3/hub/src/web/routes/auth.ts)和[Runner Socket认证](https://github.com/tiann/hapi/blob/v0.33.3/hub/src/socket/server.ts)。

## 锁定源码实测

使用已验证的v0.33.2源码commit `730dfcb22e31ec5572446d066cbb5e92d6a6254d`，probe先核对4个源码文件SHA，再调用真实Hono认证handler、真实Socket.IO Runner认证、真实JWT签名／验证及内存Store。只在既有任务Sandbox的loopback随机端口运行，凭据、用户及数据均为合成；没有读取实际HAPI token、CF身份或员工数据，也没有触碰现网部署。

| 通道 | 合成输入 | 实际结果 |
|---|---|---|
| HTTP auth | 共同base加`:alice` | 200，签名JWT的ns为alice |
| HTTP auth | 同一个base改成`:bob` | 200，签名JWT的ns为bob |
| HTTP auth | 同一个base，不带后缀 | 200，ns为default |
| HTTP auth | 错误base加`:bob` | 401 |
| Runner Socket.IO | 共同base加`:alice` | 成功连接，服务端namespace为alice |
| Runner Socket.IO | 同一个base改成`:bob` | 成功连接，服务端namespace为bob |
| Runner Socket.IO | 错误base | 明确拒绝，Invalid token |

复现命令在已获准且已有依赖的Sandbox内执行：

```bash
/tmp/hapi-web-tools/bun-linux-aarch64/bun \
  tests/hapi-workspace/probe-shared-hub-auth.mjs VERIFIED_UPSTREAM_SOURCE
```

脚本仅接受锁定认证文件摘要，不能用改过的源码冒充上游原始行为。这里证明的是namespace认证可由基础token持有者选择，不是对真实Bob数据的攻击，也不是对HAPI整个产品的安全定性。namespace文档面向小团队共享；本项目要求持有sudo的员工也不能切换身份，威胁模型更严格。把namespace随机化并作为秘密保管，也不能替代按独立身份审计的服务器授权契约。

## 要保持单 Hub，需要补的能力

1. 每员工／Runner独立、可撤销的凭据，只有本人的秘密进入员工VM；共同管理级token只保留在控制面。
2. Hub服务器根据可信凭据固定namespace，不能根据客户端提交的后缀任意选择。HTTP与Runner Socket.IO使用同一认证规则；未知、错配、停用凭据拒绝。
3. 浏览器Access身份在VM500换取固定本人namespace的HAPI会话，不要求第二次HAPI登录，也不把管理级token给浏览器。
4. 审核并实测REST、SSE、终端、机器／会话注册、远程spawn、RPC及全局配置接口。只修登录入口不足以证明整个共享进程和数据库的租户隔离。
5. 撤销须覆盖既有浏览器流与Runner连接；保留原先个人Claude凭据和VM内执行边界。

可以通过受维护的Hub多租户认证补丁或完整的协议感知代理实现，但不是只改DNS或普通nginx转发。当前没有实施这些改造，不能据此批准单Hub生产部署。

源码检查还发现`web/routes/cli.ts`和`web/routes/bind.ts`也验证同一基础token；若做认证改造，至少要覆盖web auth、CLI HTTP、binding及Runner Socket.IO这些入口，不能只替换两个已实测的入口。

## 对当前计划的影响

- 用户已明确选择单Hub，原“每员工独立Hub”仅保留为历史对照。该决策授权后续设计／代码推进，不等同于已批准停机或搬迁当前Hub数据。
- 单Hub放500后，Runner到Hub的连接方向为员工VM→500；现有35项通信／11项生命周期测试主要覆盖500→VM:9443，不能冒充新方向已验收。要按明确端口重做最小放行和反向访问拒绝测试。
- 登录执行服务、个人Firefox和授权仍留在员工VM；这部分私有控制／画面通道是否继续使用TLS入口或改出站通道，须独立确定。移动Hub不等于可以直接删除该通道。
- 当前未安装新基线组件，未更改VM500应用、Cloudflare／BWS或两台测试VM的运行布局。现有两测试VM保留，未部署共享Hub。

若不改上游认证，集中在VM500运行每人独立Hub／数据库／令牌仍是另一条可验证路线；与一个共享Hub进程是不同选择，不能混称。
