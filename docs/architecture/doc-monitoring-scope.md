# 文档 AI 监管范围 — 说明与决策记录

**状态**: 现行
**最后更新**: 2026-09-26
**适用对象**: `.github/workflows/doc-candidate-discovery.yml`（OINK Document Candidate Discovery）与 `tools/doc-gardening/`

---

## 1. 本文档解决什么问题

仓库里有一个 CI：每次开 PR，它会自动挑出改动过的文档，交给 AI 判断"哪里的陈述可能已经和实际情况对不上了"，最后汇总成一份不阻塞 PR 的证据报告。

它**只看一部分文档**。本文档说明：

- 这个 CI 到底在做什么；
- 它为什么只看一部分、看的是哪一部分；
- 这个范围怎么划才算合理，以及当前的缺口。

`_bmad-output/specs/spec-oink-doc-accuracy-integration/automation-roadmap.md` 记录了该系统的规划边界（Phase 2A 第 1 条）。那份是当时的规划工件，其中的路径对已经随目录重构改写；**本文档是当前范围的权威说明**。

---

## 2. 这个 CI 做什么

分四步：

| 步骤 | 做什么 | 是否接触模型凭据 |
|---|---|---|
| `eligibility` | Draft / fork PR 直接跳过 | 否 |
| `prepare` | 算出改动文档 → 按范围筛选 → 稳定排序取前 5 份 → 生成清单 | 否 |
| `analyze` | 逐份文档把改动片段交给 AI，校验结构化输出 | 是 |
| `aggregate` | 用**受信基线代码**逐条回验所有产物，汇总成报告 | 否 |

三个关键设计：

- **只留证据，不改仓库**。它不生成编辑、不发评论、不阻塞 PR。
- **受信基线**。`analyze` 与 `aggregate` 检出的是**已合并的 merge base**，而不是 PR head 的代码。也就是说，审你的时候用的是"官方已发布的那套工具和规则"。
- **成本有上限**。单次 PR 最多分析 5 份文档，每份最多 3 轮对话、5 分钟超时，且**串行执行**（`max-parallel: 1`）。

---

## 3. 监管范围是什么

范围由 `tools/doc-gardening/contract.py` 的 `ALLOWED_DOCUMENT_PREFIXES` 定义：

```python
ALLOWED_DOCUMENT_PREFIXES = ("docs/guides/", "docs/architecture/")
```

**注意：这次范围其实是放宽了，不是收窄。**

| | 重构前 | 重构后 |
|---|---|---|
| 监管内 | `docs/deployment/` 7 份 + `docs/designs/` 9 份 = **16 份** | `docs/guides/` 13 份 + `docs/architecture/` 12 份 = **25 份** |

原因是原来的 `docs/guides/`（Terraform 综合指南、Ansible 最佳实践、sing-box 代理配置等）**本来就不在监管内**，这次并进来后一并纳管了。

### 3.1 有两条容易被忽略的规则

**规则一：只有「新增」和「修改」才送去问 AI，「重命名」和「删除」不算。**

```python
eligible = [item for item in changes if item["change_type"] in {"A", "M"} ...]
```

这有实际意义：纯搬家的文档本身没有产生新内容，让 AI 读一遍纯属浪费。以本仓库最近一次文档目录重构为例——76 个改动文件、30 份文档搬家，最终**只有 4 份进入 AI 分析**（1 份新增 + 3 份修改），5 份的预算都没用满。

**规则二：没被分析的要显式留痕，不许静默省略。**

超预算的记 `budget_exhausted`，重命名/删除/空新增记 `no_analysis`，都是零调用但**明确登记**。这样你看到的是"哪些没查"，而不是误以为"全查过了"。

---

## 4. 范围该怎么划

### 4.1 判断标准不是"是否在 docs 下"

这个 CI 不是在检查"文档写得好不好"，而是在找**"文档陈述的值与代码/配置对不上"**。它的准确性依赖一件事：**有没有可对照的事实源（oracle）**。

工具链本身就是这么设计的——`tools/check-doc-claims.py` 的每一条 claim 都必须配一个 oracle：

```
service.netbox.port
  文档侧: docs/guides/netbox-deployment.md  → Configuration Variables::netbox_port
  对照侧: ansible/roles/netbox/defaults/main.yml → netbox_port
```

没有 oracle 的文档，AI 只能给出 `unknown`。那是噪音，不是价值。

所以正确的判断标准是：**这份文档是否在陈述"当前可验证的事实"。**

### 4.2 三类划分

**① 应监管：陈述当前事实的文档**

- `docs/guides/` —— 操作指南，含具体端口、路径、镜像版本
- `docs/architecture/` —— 架构设计与规范，含当前拓扑、决策
- `docs/reference/` —— 静态参考数据，**含大量可核对的具体值（当前缺口，见 §5）**
- `docs/README.md` —— 导航页，陈述当前目录结构（优先级低）

**② 不应监管：明确的历史记录**

- `docs/learningnotes/`（46 份）—— 按日期记录的学习笔记
- `docs/archive/`（4 份）—— 已退役文档
- `docs/troubleshooting/`（9 份）—— 事故复盘与排障记录

这三类**本来就该"过时"**——它们的价值恰恰在于忠实记录当时的情况。
`docs/architecture/docker-sandbox-migration.md` 的「5.2 保留历史原文」专门声明过：这些目录中的描述是当时事实，不做机械替换。

把它们纳入监管会**系统性产生误报**：AI 会报出一堆"疑似过期"，而每一份都是设计上正确的历史记录。
更严重的是，本系统的质量门槛要求正样本全中、**假阳性为零**（语料评估需 `6 TP / 0 FN / 0 FP` 才允许晋级）。一旦纳管历史目录，这个门槛就永远达不到。

**③ 监管不了：流程与规划类**

- `docs/agent/`（6 份）—— BMAD/Multica 工作流契约
- `docs/planning/`（5 份）—— 路线图、提案、已实现记录

这些没有"事实对错"可言：路线图写的是"打算做什么"，契约写的是"应当怎么做"，都不存在与代码配置对照的 oracle。

### 4.3 决策

**监管范围 = 「陈述当前可验证事实」的文档，而不是「`docs/` 下的所有文档」。**

对应的排除**不是遗漏，而是刻意**。将来若要把某个目录纳入范围，应先回答：**它有没有可对照的事实源（oracle）？**

---

## 5. 当前缺口

**`docs/reference/` 应纳入监管。**

其中唯一的文档 `netbox-custom-fields-reference.md` 满篇是可核验的具体值：

| 字段 | 值 |
|---|---|
| `infrastructure_platform` Default | `proxmox` |
| `infrastructure_platform` Choices | `proxmox`, `esxi`, `physical` |
| `infrastructure_platform` Weight | `100` |
| `automation_level` Type | Selection |

这类内容最容易漂移（NetBox 侧改了字段定义，文档不会自动跟着变），也最容易被机器核对。它当前在监管之外。

**待办**：另开一个独立的小 PR，把 `docs/reference/` 加入 `ALLOWED_DOCUMENT_PREFIXES`。

---

## 6. 操作约束：白名单不能和目录搬迁同期修改

改 `ALLOWED_DOCUMENT_PREFIXES` 时有一条硬约束，容易踩坑：

- `prepare` 在 **PR head** 上运行，用**新**白名单生成待分析清单；
- `aggregate` 在 **受信 merge base** 上运行，用**旧**白名单回验清单。

因此，**若同一个 PR 既改白名单、又搬迁文档**，清单里会出现 base 白名单不认的新路径，`aggregate` 会以 `document_path_out_of_scope` 失败。

这不是缺陷，而是"受信基线"机制在正常发挥作用：**监管范围只能由已合并进 main 的代码决定，不能由某个 PR 自行放宽。**

正确做法是拆成两步：

1. **先**合并一个只改白名单、不搬任何文档的 PR（因为不涉及范围内文档改动，清单为空，检查自然通过）；
2. **再**合并文档搬迁 PR（此时 base 白名单已更新，新路径被接受）。

同理，"提高 5 份上限""纳入新的目录"这类变更，按 `spec-oink-ai-candidate-discovery.md` 的 **Ask First** 约定，都属于需要人工批准的动作，不应顺手改。

---

## 7. 何时重新审视本决策

出现以下情况时应回到本文档：

- 新增文档目录，或某个目录的性质改变（例如历史目录被改造成现行规范）；
- 为某类文档引入新的 oracle 解析器，使原本"无法核对"的内容变得可核对；
- 质量门槛调整（例如不再要求零假阳性）；
- 5 份上限或串行策略调整，导致成本模型变化。

---

## 8. 参考

- `tools/doc-gardening/contract.py` —— 监管范围与各项上限的定义处
- `tools/doc-gardening/scan-changed-docs.py` —— 改动的分类、筛选与汇总逻辑
- `.github/workflows/doc-candidate-discovery.yml` —— 工作流编排与凭据边界
- `_bmad-output/implementation-artifacts/spec-oink-ai-candidate-discovery.md` —— 该系统的设计规格（Phase 2A）
- `_bmad-output/specs/spec-oink-doc-accuracy-integration/automation-roadmap.md` —— 规划边界（Phase 2A 第 1 条）
