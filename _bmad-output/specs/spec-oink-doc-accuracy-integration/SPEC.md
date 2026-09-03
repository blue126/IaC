---
id: SPEC-oink-doc-accuracy-integration
companions:
  - claim-registry.md
  - security-boundary.md
sources:
  - ../../planning-artifacts/research/technical-oink-doc-accuracy-integration-2026-08-26/research.md
---

> **Canonical contract.** 本 SPEC 与 `companions:` 中的文件共同构成构建、测试和验证必须遵守的完整契约。`sources:` 仅用于追溯，不是下游必读材料。

# OINK 文档准确性集成：Phase 1 确定性漂移检测

## Why

IaC 文档中的错误端口、版本或配置会误导维护者和 coding agent；同时，现有 Notion 同步脚本会从 Vault 或 Terraform secret 文件读取凭据、写入 Notion 并在 dry-run 输出掩码前缀。Phase 1 先收紧这条敏感信息边界，再以极小、封闭、可由已提交代码直接判定的 claim 集验证 OINK 文档准确性，而不把展示站点或检测器变成特权系统。

## Capabilities

- **CAP-1**
  - **intent:** 系统能够保留非敏感库存元数据的 Notion 同步，同时杜绝 Vault、Terraform secret 和凭据值进入 Notion payload、日志或文档自动化制品。
  - **success:** 使用唯一测试哨兵值的 mocked 同步证明出站属性及 stdout/stderr 均不含哨兵或其派生值，且允许的非敏感库存元数据仍可同步。

- **CAP-2**
  - **intent:** 系统能够对 [claim-registry.md](claim-registry.md) 中封闭的四条文档 claim，以确定性方式比较 Markdown locator 与已提交 Ansible defaults 中声明的 oracle。
  - **success:** 匹配、矛盾、缺失 source 及缺失或歧义 locator 的 fixture 都为每条 claim 产生规定状态与证据，不猜测或回退到运行时数据。

- **CAP-3**
  - **intent:** 系统能够生成不含敏感信息、可供人和 OINK 消费的漂移报告，说明每条 claim 的结果、文档位置、oracle、非敏感预期/观测值和 provenance。
  - **success:** 仅依赖 checkout 文件的运行能报告全部四条 claim；出现 contradiction 或 indeterminate evidence 时以非零结果结束，且报告不含任何凭据或 token 值。

## Constraints

- CAP-1 是阻塞前置条件：claim report、OINK-facing manifest、docs build、测试 fixture、日志和 Notion payload 都不得包含 Vault 值、Terraform secret 值、密码、API token、integration token 或其掩码/截断派生值。
- Claim registry 是封闭集，成员以 `tools/check-doc-claims.py` 的 `CLAIMS` 为权威，[claim-registry.md](claim-registry.md) 是其投影，必须随之重新导出；每条只映射一个稳定 Markdown locator 与一个已提交 Ansible defaults key，文档侧覆盖 `docs/deployment/` 与 `docs/designs/`。
- Oracle 只能通过确定性解析和标量比较获得；缺失、歧义或不可解析的证据一律为 indeterminate，不得推断为 verified 或 contradiction。
- OINK/Hugo、GitHub Pages 和 detector 均是无特权展示/验证面：只能消费非敏感报告或 manifest，不能接收生产凭据、调用 runtime 系统或触发 Notion/Vault/Terraform/HCP/NetBox/Proxmox/ESXi 访问。
- Provenance 必须绑定 checkout revision 或输入文件 digest；页面构建时间和报告生成时间不能作为事实正确性的证据。

## Non-goals

- Runtime collector、设备/API 采集、webhook 或 reconciliation。
- AI claim extraction、AI 自动编辑、任何自动文档修改、自动 PR 创建或自动 merge。
- 检查四条 registry claim 之外的端口、域名、资源规格、路径、版本、文档集合或开放世界 coverage。
- 将 Notion 数据、Terraform state、Vault、日志或生产状态作为 Phase 1 的 claim oracle。
- 向 OINK 页面或 `llms.txt` 发布凭据、token、密码或敏感派生信息。

## Success signal

在干净 checkout 上，先通过 Notion 同步的 sentinel 防泄漏测试；随后运行四条 registry claim 的 fixture suite 和 repository-only 检测。四条正常 fixture 均 verified，任何人为篡改都以可定位的 contradiction 或 indeterminate evidence 和非零结果失败，生成的报告仍只含允许的非敏感字段。

## Assumptions

- `scripts/sync-to-notion.py` 在去除凭据导出后仍是需要保留的库存集成；若应废弃该脚本，必须在实现前以新的决策取代 CAP-1。

## Open Questions

- 安全门禁通过后，非敏感 report 是否只作为 local/CI artifact，还是也应由 OINK 渲染？
