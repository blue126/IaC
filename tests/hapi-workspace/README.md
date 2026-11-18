# HAPI 工作区验证

本目录只用合成身份、临时文件和 loopback 服务，不读取实际 inventory、Vault、BWS、Cloudflare 或个人 Claude 认证。控制面应用代码及其测试（`test-auth.py`、`test-proxy.py`、`test-reconcile.py`）在私有仓库的 `hapi-control/tests/`。

## 回归测试

PR 校验在相关路径变化时运行；本地从仓库根用同一入口：

```bash
scripts/ci/validate-test-suites.sh hapi-workspace
```

- `test-login-agent.py`：登录代理只暴露固定的认证代理操作；手工码、取消、超时与浏览器保留用真实 tmux/PTY 和 `tests/employee-workspace/test-login.py` 的合成 CLI 夹具验证。缺少 tmux 时这些用例跳过，不能算通过。
- `test-hub-config.py`：共享 Hub 角色的 `hapi-hub-config.py`——worker 与凭据一一绑定、不能跨 namespace、重复 token/地址拒绝、登记文件权限，以及服务启动时的签名密钥强度与批准摘要。
- `test-hub-boundary.py`：`scripts/oci-hub/boundary.py` 的 `hapi_hub_grants`——只有已登记且启用的 worker 能访问精确的 Hub:9443，宽网段、公网、metadata 和 worker 网段目标拒绝，重复 grant 拒绝。

## 手工验证（需要额外输入，不在 PR 校验内）

- `probe-hub-binary.py <binary> <sha256>`：在能执行该构建产物的 Linux 上，用随机 loopback 端口、临时 home 和合成凭据启动编译好的 Hub，验证内嵌网页与认证边界，结束时停止本次进程。
- `test-shared-hub-auth.mjs <prepared-source>`：对经 `scripts/prepare-hapi-shared-hub.py` 固定摘要准备的补丁 Hub 源码，运行 HTTP、Socket.IO、RPC、SSE 的租户隔离回归（固定凭据、跨 namespace 资源、RPC 方法覆盖、凭据撤销、JWT 过期、损坏登记）。
- `workspace-browser.mjs DIST UPSTREAM_ROOT EVIDENCE_DIR`：用真实编译页面和 Chromium，经 loopback 模拟网关验证自动进入、账号切换和会话失效恢复；构建步骤见 [scripts/hapi-workspace-web](../../scripts/hapi-workspace-web/README.md)。

以上均不代表真实 Access 链路、真实 KasmVNC 画面、个人 Claude 授权或现网验收。

单 Hub 迁移期的一次性脚本与现场探针（`hapi-hub-data.py`、`prepare-hapi-hub-boundary.py`、`run-hub-validation.py`、`probe-hub-worker.py`、`probe-live-shared-hub.mjs`、`probe-shared-hub-auth.mjs`）已于 2026-11-18 退役，历史版本见 Git 记录；迁移过程见[迁移记录](../../docs/planning/2026-10-30-hapi-single-hub-migration.md)和[单 Hub 评估](../../docs/planning/2026-10-30-hapi-shared-hub-assessment.md)。
