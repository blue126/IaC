# deferred-work 与 GitHub Issues 同步

`scripts/sync-deferred-work.py` 把 BMAD 的延期工作清单注册成 GitHub issue，并跟踪它们的生命周期。

## 为什么需要它

BMAD 的 `bmad-build` 与 `bmad-code-review` 会把"本次不做、但确实该做"的工作追加到
`_bmad-output/implementation-artifacts/deferred-work.md`。这个文件有一个刻意的约束：

> Append one new entry ... **Do not modify existing entries or look for duplicates.**

也就是说它**只能追加、不能被修改**。这带来两个后果：

1. **没有 retirement 机制** —— 条目一旦写入就永远留着，即使工作已完成或已取消。
2. **不进日常视野** —— 它是一份需要主动打开的文件，很容易被遗忘。

本仓库的 `sprint-status.yaml` 是 BMAD 官方的追踪载体（`tracking_system: file-system`），但它只在 `bmad-sprint-planning` 流程中变化，同样不覆盖这类"流程外的延期项"。

因此这里的分工是：

| 载体 | 角色 |
|---|---|
| `deferred-work.md` | **收件箱**。BMAD 追加，人阅读。只增不改。 |
| GitHub Issues | **状态载体**。谁在做、做没做完，看这里。 |
| `.github/deferred-sync-map.json` | **账本**。记录条目 ID 与 issue 编号的对应关系。 |

## 用法

```bash
# 报告现状：新增、重措辞、以及需要退役的条目（不写 GitHub）
python3 scripts/sync-deferred-work.py --dry-run

# 执行同步：为新条目开 issue，并更新账本
python3 scripts/sync-deferred-work.py
```

脚本**从不修改 `deferred-work.md`**。需要退役时，它打印出可直接追加的记录。

## 条目身份

BMAD 的条目格式没有 id：

```markdown
- source_spec: `{spec_file}`
  summary: <one sentence>
  evidence: <why this is real>
```

所以脚本从内容派生 id：`sha256(<第一个字段的值> + "\x00" + summary)[:12]`。
**id 只用字段的「值」，不用「键名」**，因此同一个来源无论写成哪个键名都映射到同一个
issue，不会重复开。

第一个字段的名字目前是 `source_spec`（当前 `.agents/skills/bmad-build/` 的四个
producer 全部如此）。解析器也容忍 `source_plan` 作为别名——曾有一版 BMAD 修订把它改名，
但那一版**并未落地**（合并进 main 的 BMAD 同步仍用 `source_spec`）。保留别名纯属防御：
万一将来真的改名，新追加的条目不会被静默忽略。

**未知 id 一律按新工作处理，永不抑制创建。** 这个选择是刻意的：按来源
推断"这是改写而非新条目"会静默丢失工作，而丢失是不可见的。`spec-doc-gardening-phase-2.md`
一个 spec 就产生了 11 条，任何按 spec 归并的启发式都会把第 12 条误判为重复。

当一个**新条目**与账本中某条**共享来源**时，脚本会打印告警提示可能存在重复，
但仍然创建 issue。判断权留给人：确认重复后，关闭其中一个并追加对应的 `retired:` 记录。

解析器同时接受 BMAD 实际会写出的几种形态：

- 第一个字段带或不带反引号（拆分目标路径会写 `source_spec: none`）。
- `summary` / `evidence` / `note` 顺序任意，`evidence` 可缺省。
- 折行的 `evidence` / `note` 值会并回原字段（保留文本）；`summary` 的折行会被
  **忽略并告警**——`summary` 参与 id 派生，静默改写它会改变 id 并在下次运行时重复开 issue。
  BMAD 只写单行值，所以折行只可能来自手工编辑。
- `bmad-code-review` 的 `## Deferred from: ...` 标题加项目符号（含 `[ ]` / `[x]` 复选框）。
- 畸形或重复的条目只**告警**，不会中止整次同步——一行坏数据不应该阻塞其他所有条目。

## 退役（retirement）

因为在 `deferred-work.md` 中**修改既有条目是被禁止的**，退役通过**追加**一条记录表达：

```markdown
- retired: <entry_id>
  reason: completed | not_planned | superseded
  issue: <issue number>
```

两条路径都会用到它：

1. **GitHub 先关，清单后记**。脚本检测到账本中的 issue 已关闭、但清单里还没有对应
   `retired:` 记录时，会打印出可直接追加的文本。
2. **清单先记，GitHub 后关**。若 `retired:` 记录已存在而映射的 issue 仍然开着，
   脚本会按 `reason` 关闭该 issue（`completed` → completed，`not_planned` 与
   `superseded` → not planned）。两边因此收敛到同一状态。

非法 `reason`、缺失或非数字的 `issue`、以及指向不存在条目的 `retired:` 都会报告为
警告，不会被静默接受。id 大小写不敏感，反引号可有可无。

**非法 `reason` 不会关闭 issue。** 这类记录会被列为 `invalid retirements` 并保持
issue 开着——`completed`（我们做了）与 `not planned`（我们不打算做）在 issue 历史里
含义不同，一个拼错的 reason 不应该替作者决定这件事。

记录里的 `issue:` 号会与映射中的号码**交叉核对**，不一致时报告（以映射为准，因为那是
实际创建时记录的）。

## 跨仓库路由

qwen3-tts 已从本仓库剥离到 `blue126/llm-ops`，但它的延期条目仍记录在本仓库的清单里。
账本中的 `routes` 按 source 子串匹配目标仓库：

```json
"routes": [
  { "match": "qwen3-tts", "repository": "blue126/llm-ops" }
]
```

未命中任何路由的条目走顶层 `repository`。若将来还有其他组件剥离，在这里加一条即可。

## 幂等性与安全

- 脚本按 `entry_id` 查账本，已登记的条目不会再开 issue。重复运行安全。
- `--dry-run` 会**读取** GitHub 上的 issue 状态（只读调用），因此能报告需要退役的条目，
  但不做任何写入。推荐先用它。
- 映射文件以原子方式写入（临时文件 + fsync + rename），崩溃不会留下截断的映射。
- 运行期间持有锁文件（`<mapping>.lock`）。并发运行会被拒绝；**持有者已死或 pid 不可读的
  陈旧锁会被自动回收**，因此被 SIGKILL 打断不会永久卡住脚本。
- 若 issue 已创建但返回的 URL 无法解析，脚本用正文中的 `<!-- deferred-work:<id> -->`
  标记反查该 issue，避免留下孤儿。
- 映射记录损坏（例如手工改坏了 `issue`）会给出 `blocked:` 信息而不是抛出 traceback。

## 已知情况

- **source spec 失效**。目录重构已使 2 条来源路径失效（`docs/specs/…`、
  `docs/designs/qwen3-tts-…`）。条目仍按 id 同步，脚本会把这类路径列为
  `stale source specs` 供人核对——它只是溯源信息，不代表条目失效。
- **映射是唯一能把 id 与 issue 对上的地方**，所以每条记录同时保存了创建时的
  `title` 与 `label`。

## 尚未完成的部分

- **自动触发**。目前需要手动运行。加 GitHub Action 自动触发需要 `issues: write`
  权限，而本仓库现有的 AI 类 workflow 全部是只读设计（`contents: read` +
  `pull-requests: read`），因此授权自动开 issue 是一个独立的外部写边界决定，
  尚未实施。
- **改写条目不会自动更新既有 issue**。`summary` 被改写会产生新 id 而新建 issue，
  脚本只告警提示同 spec 已有映射。BMAD 本身禁止改写既有条目，因此这是异常路径。
