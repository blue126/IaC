# Brownfield 实施约束

## 现有资产

| 路径 | 当前职责 | 本功能影响 |
|---|---|---|
| `terraform/esxi/llm-server.tf` | 定义 `llm-server` VM、双 GPU 直通边界和 Ansible inventory | 只读参考，不修改 |
| `ansible/inventory/host_vars/llm-server.yml` | 固定 `192.168.1.247` 和现有运行时边界 | 只读参考；后续凭据只能通过 Vault 间接引用 |
| `ansible/playbooks/deploy-qwen3-tts.yml` | 构建并部署 `groxaxo` Qwen3-TTS、Compose、systemd 和 verify | 增加本地 shim、音色配置和双服务验证 |
| `docs/designs/qwen3-tts-openai-api-integration.md` | 记录本地 Qwen3-TTS PoC 设计 | 更新为包含本地 shim；移除“不提前增加协议转换层”的旧结论 |
| Cloudflare Worker `tts-shim` | 已验证 Speech Central 固定 alias 的映射模式 | 只参考映射和回退行为，不进入运行链路 |

## 目标部署边界

- Compose 包含 `shim` 和现有 `server` 两个服务，由同一个 `qwen3-tts.service` 管理。
- `shim` 发布 `192.168.1.247:8100`；`server` 仅通过 Compose service name 和容器端口 8880 被 shim 访问。
- shim 实现可以选择适合仓库的轻量框架，但必须是独立进程/容器，不得把映射逻辑写入 Cloudflare Worker，也不得修改第三方 pinned source。
- shim 的固定 upstream 由部署配置提供，客户端不能覆盖。
- `GET /health` 和 `GET /v1/models` 必须让现有客户端及 verify 继续工作；`POST /v1/audio/speech` 必须支持普通二进制音频和 chunked streaming 响应。
- systemd 的启动、停止和超时继续覆盖整个 Compose project；`restart: "no"` 和 `enabled: false` 保持不变。

## 请求与响应契约

- 对合法 JSON 请求只改写 `voice`，其余字段转发给 Qwen3-TTS backend。
- 对无效 JSON、空 `input` 或 backend 不可达返回明确的非 2xx 状态；不得伪造成功音频。
- backend 的非 2xx 状态和可安全返回的错误正文保持可诊断。
- 普通音频响应按原始 Content-Type 和字节返回。
- streaming 响应必须边接收边发送，保留 chunked 行为，不能先读完整音频再响应。
- 不复制 Cloudflare Worker 中的 `url_override`、`model_override` 或 `/admin/clone` 行为。

## Ansible 验证

安全本地验证：

```bash
cd ansible
ansible-playbook playbooks/deploy-qwen3-tts.yml --syntax-check
```

部署不是 PR 验证，只有用户明确授权后才能运行。部署前还必须执行仓库规定的 SSH agent 检查。部署后相关验证入口为：

```bash
ansible-playbook playbooks/deploy-qwen3-tts.yml --tags verify
```

verify 至少覆盖：

- shim 和 backend Compose 服务都在运行；
- systemd unit active，两个容器 restart count 都为 0；
- `/health` 和 `/v1/models` 可用；
- 男声 alias 和女声 alias 各生成一个有效 WAV；
- `stream=true` 返回 `audio/pcm` 和 chunked transfer；
- 全部 alias 解析到允许的 Qwen speaker；
- GPU 状态和既有 Qwen3.6/DeepSeek 边界保持有效。

## 回滚

停止 `qwen3-tts.service` 必须同时停止 shim 和 backend。Speech Central 随后切回已经可用的百炼提供商。保留模型缓存，除非用户明确授权删除。
