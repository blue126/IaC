- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 将 Proxmox 节点和 VMID 直接传入动态 inventory，消除 Terraform 与 host_vars 的重复元数据。
  evidence: n8n 本次必须手工新增 `proxmox_node: pve0` 和 `proxmox_vmid: 106`；迁移或重建后容易失配并操作错误容器。
- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 建立所有新节点都会执行 common、Tailscale 和服务 role 的统一部署入口。
  evidence: `deploy-n8n.yml` 只执行 n8n role，新增 host_vars 本身不会触发 `install-tailscale.yml`；同类遗漏会影响其他新节点。
- source_spec: `_bmad-output/implementation-artifacts/spec-enable-tailscale-on-n8n.md`
  summary: 为包含 Proxmox snapshot 区段的 LXC 设计安全的 TUN 配置管理和重复执行验证。
  evidence: 当前简化的 `lineinfile` 适用于没有 snapshot 的 VMID 106，但不理解配置文件中的 snapshot 区段；缺少连续执行与重启后的自动验证。
- source_spec: `_bmad-output/implementation-artifacts/spec-oink-documentation-site.md`
  summary: 单独清理现有 Markdown 的断链、坏锚点和过期仓库文件引用。
  evidence: OINK 审查确认 `llm-server-deployment.md` 等既有文档含错误目标；本试点按人类确认保持 `docs/` byte-for-byte 不变，因此不在展示层变更中修复。
- source_spec: `_bmad-output/implementation-artifacts/spec-oink-doc-accuracy-integration-phase-1.md`
  summary: 保留 Ansible Vault 到私有 Notion Credentials DB 的单向密码同步，并以显式 credential allowlist、全量日志脱敏和 OINK/detector 隔离加固这个人类可读 GUI。
  evidence: 用户明确 Notion 是弥补 Ansible Vault 无 GUI 的授权 secret sink；该目标与只读仓库文件的 deterministic detector 可独立交付，且同 PR 会混合 secret 存储与文档验证两种 blast radius。
