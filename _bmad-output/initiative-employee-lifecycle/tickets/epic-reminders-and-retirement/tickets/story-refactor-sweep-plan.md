---
title: 'Refactor sweep（epic 4）'
type: 'refactor'
ticket: '5'
created: '2026-11-02'
status: 'done'
baseline_revision: 'ab0f0a1'
route: 'quick'
route_source: 'auto'
risk: 'low'
review: 'self'
review_source: 'pinned'
lenses_ran: []
review_loop_iteration: 0
context: []
---

## Intent

清理本 epic 各 story 推迟的整理项，仅限清理，不新增行为。

## Items

| 来源 | 整理项 | 处理 |
|---|---|---|
| 4.4 Pass 3 low | 开户结果的回归测试为源码文本检查 | `hub-terminal.bundle_acceptance()` 抽出两处相同字段，测试改为直接调用该函数的行为测试 |
| 4.6 Pass 1 low | `FixedRunDir` 借用 `Secrets.fixture` | 改为模块级 `materialize_fixture()`，两个测试类共用 |
| 4.6 Pass 1 low | SIGKILL 后 ssh-agent 成为孤儿进程 | 属行为改动，不在清理范围，保留在 4.6 Implementation Notes |
| 4.4 Pass 3 low | 解密路径同时加载两份密码 | 评审结论为不改 |

## Implementation Notes

- employee-admin 71b8aed，已推到执行器。
- 执行器上全部测试文件：除下列 5 个外均 OK。这 5 个在 epic 4 起点 a1baac3 上结果相同，非本 epic 引入：
  - `test-legacy-entry-retirement.py`（1 failure）、`test-remotecc-layout.py`（1 error）：既有问题。
  - `test-admin-core.py`：执行器无 `ansible.parsing`（旧 Mac 路径，且为用户未提交文件）。
  - `test-device-bundle.py`、`test-preflight.py`：读取真实 `settings.json`；测试副本删除了 settings 才失败，带 settings 运行均 OK。

## Verification

- 执行器：`for t in test-*.py; do python3 $t; done`，结果如上。
