# HAPI 单一入口迁移与验收

后续变更见[内部HTTP简化方案](hapi-internal-http.md)，目前是已批准的代码候选，尚未切换现网。

状态核对：2026-11-01。现有所有者试点的统一入口、单Hub和会话数据库已迁入VM500；VM502保留Runner、Claude、登录执行服务和Firefox。用户已确认网页登录与远程浏览器可用，个人Claude认证保留在本人VM。源码经[PR #201](https://github.com/blue126/IaC/pull/201)完整CI与独立审核后合入`main`。独立HAPI开户候选已撤回；现有试点验收不等于新员工完整开户验收。

唯一正式网址为 `https://hapi.willfan.me`，Claude登录引导位于 `/_workspace/login/`。Cloudflare Tunnel、身份网关、共享HAPI Hub和会话数据库均位于VM500。网关验证Access身份并换取绑定本人namespace的短期HAPI会话，不要求用户再次输入HAPI令牌。员工VM运行Runner、任务、文件和个人Claude环境，通过私有mTLS通道连接控制面。这里的Hub是HAPI应用服务，与OCI WireGuard Hub不同。

```mermaid
flowchart LR
    U[员工浏览器] --> C[Cloudflare Access 单次身份验证]
    C --> T[VM500 Tunnel与身份网关]
    T --> H[VM500 共享HAPI Hub与会话数据库]
    T --> P[VM500 同站Claude登录引导]
    P --> A[本人VM Claude登录执行服务与Firefox]
    R[本人VM Runner与Claude] -->|私有mTLS通道| H
```

## 入口切换历史（2026-10-30／31）

以下记录先于单Hub和PKI升级的入口切换步骤。Hub／数据随后完成集中迁移，签发权限的后续变化见[证书生命周期说明](hapi-pki-lifecycle.md)；不能将阶段内的旧布局当作当前部署。

- 将已有Access应用迁到正式域名，保留原所有者授权、应用AUD和168小时会话，不扩大可访问账户。
- 网关依已验证的邮箱与subject映射到当前登记工作区，在服务端换取短期HAPI票据；部署自动登录前端，不再要求浏览器填写长期HAPI令牌。
- 将原Tunnel连接器交接到VM500，远程配置只含正式主机名并指向本机身份网关。没有让两台宿主以不同localhost后端同时承载新配置。
- 停止并禁用VM502旧公网连接器，删除其本机Tunnel令牌副本，退役旧HAPI试点和独立登录域名的DNS。旧个人登录HTTP页面服务已停用，执行API改用同站Origin。
- VM500至VM502仅开放获批控制面源的私有TLS端口，验证服务器身份、客户端证书及CRL。原Hub和Tunnel令牌值保持原有BWS来源；签发CA私钥保留在管理员侧加密Vault，不部署到服务宿主。
- 更新Hub的公开URL与CORS Origin，并仅重载Hub。实际检查Runner进程未重启，任务目录、个人认证及Firefox配置没有迁移或重置。
- 既有WireGuard服务、员工VM通用出网和Cloudflare账户全局会话设置未随此次入口迁移修改。

本轮验收仅覆盖原获批所有者及其试点工作区。新增员工须在当前员工流程中明确本人VM、身份、凭据与路由，不共享试点，也不另建第二台工作VM或第二份Terraform state。员工管理以执行器上的`wsctl`为入口，见[当前操作约定](../deployment/oci-hub-native-provisioning.md)；旧独立HAPI执行器不再用于开户。新员工首次授权及两种接入的完整交付需另行验收。

## 真实问题与回归

原入口故障是VM502迁到受限出站网络后，TCP 7844未放行。HTTP/2模式的Tunnel仍需该端口；临时精确放行恢复服务后，将连接器迁至VM500，并撤销VM502的临时出站例外。没有为所有员工开放该端口。

首次迁移后的noVNC初始化失败来自认证Unix套接字等待队列：Python默认值为5，浏览器并发请求模块时发生排队溢出，表现为部分脚本随机500。顺序加载单个脚本无法发现此问题。

已将等待队列设为128，并补充真实noVNC模块依赖、JavaScript MIME／内容校验及64路同时请求回归。修复前并发测试复现500，修复后64路全部200。VM500现场检查监听队列为128；身份15项及代理18项回归均通过，用户再次刷新后确认远程浏览器画面出现。临时静态资源诊断日志配置随后关闭，未记录Cookie、JWT、授权码或请求体。

## 维护边界

使用`hapi-control-plane`管理VM500身份与路由，`hapi-shared-hub`管理共享Hub，`hapi-hub-client`管理worker到共享Hub的兼容通道，`hapi-ingress`管理私有登录适配和VM500连接器，`claude-login-agent`管理本人VM中的固定执行API。旧 `employee-hapi` 通过迁移标记拒绝重新部署旧公网试点，防止恢复旧域名或旧连接器。

PVE现有OCI边界需保留独立服务授权文件及相关编译器支持。现场编译器的既有Mosh等功能在修复时保留，不能直接用较旧分支覆盖现场版本。私有运行记录保存了部署基线、差异和回退配置；合并代码和后续部署应以当前边界所有者版本为基线集成作用域修复。

内部TLS已采用365天叶证书、1825天CA证书和180天CRL，由VM500每小时检查并自动续期／分发；详见[生命周期说明](hapi-pki-lifecycle.md)和[运维巡检](hapi-operations.md)。签发材料、回执和旧Vault位于Git忽略的私有运行目录；PKI接管后不能把历史Vault的旧TLS材料覆盖回现网。VM500的VM级备份由用户负责。服务配置变更和凭据操作仍需相应授权。
