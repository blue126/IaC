---
title: '非交互审批路径可用：固定凭据目录并串行运行 wsctl'
type: 'bugfix'
ticket: '6'
created: '2026-11-02'
status: 'done'
baseline_revision: '7fa91d2'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: []
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** AD-1/R12 要求 Semaphore 以 `--plan-only` 看计划、再以 `--approve <SHA>` 执行。执行器上 `wsctl-secrets.py` 每次把 BWS 凭据物化到随机目录（`mkdtemp` → `/run/wsctl-XXXX`），并把 settings 中 6 个字段改写为该目录下的路径；开户的运行目录名、审批 SHA、以及运行状态里保存的子流程 settings 都含这些路径，所以两次 wsctl 调用之间 SHA 不同、运行目录找不到、状态里的凭据路径已被删除。实测：`provision --approve` 报 `WSCTL_APPROVAL_MISMATCH`，`apply` 报 `FileNotFoundError .../state.json`。另：`semaphore/wsctl.sh` 未处理 `retire`。

**Approach:** 物化目录改为固定路径 `<run_root>/wsctl`（执行器上为 `/run/wsctl`）。`wsctl` 在物化前取得全局锁 `<run_root>/wsctl.lock` 并持有到运行结束（排队等待，超时报错），因此同一时间只有一个 wsctl 使用该目录；运行结束仍删除目录。路径不再随调用变化，`--plan-only` 与 `--approve` 跨调用得到同一 SHA 与运行目录。`semaphore/wsctl.sh` 的两步审批分支加入 `retire`。

**Decision:** 2026-11-02 用户选方案 A（固定目录 + 串行；保留"运行结束即删除凭据"）。

## Boundaries & Constraints

**Always:**
- 只在 settings 含 `bws_materialize` 时生效（执行器）；无该块时（管理员 Mac）行为不变：不加锁、不物化。
- 锁：`flock` 在物化之前取得，覆盖整个 wsctl 运行（包括只读命令）；等待上限 1800 秒，超时以 `WSCTL_BUSY` 退出码非零（与现有 `WSCTL_*` 错误风格一致）。锁文件与固定目录都在同一 run_root（`XDG_RUNTIME_DIR` 或 `/run`，沿用 `--run-root` 的现有选择逻辑）。
- 固定目录：持锁时若已存在（上次运行崩溃残留），先安全删除（拒绝符号链接，只删除普通文件）再以 0700 重建；文件仍以 `O_EXCL` 0600 创建。
- 运行结束（含失败）删除目录，锁随进程释放。
- 现有 `exclusive_admin_lock` 等内部锁不变；不得引入 wsctl 递归调用自身导致的死锁（执行器路径上没有 wsctl/onboard.sh 子调用，实现时复核）。
- `semaphore/wsctl.sh` 两步审批分支包含 `retire`；`wsctl-confirm.py` 的 retire 流程已支持 `--approve`/`--plan-only`，保持不变。

**Never:**
- 不改变"运行结束删除凭据"。
- 不在 settings 或状态文件中写入凭据内容。
- 不改 AD-1 的审批语义（计划、输入或代码变化仍拒绝）。
- 不修改用户未提交的文件（README.md、admin-core.py、ansible/onboard.yml、onboard.sh、test-admin-core.py、requests-cli.py）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 两次计划 | `provision --plan-only` 连续两次 | 相同 `approval_sha256` 与 `run_dir` | — |
| 两步执行 | `--plan-only` 后 `--approve <SHA>` | 执行该计划 | SHA 不符 `WSCTL_APPROVAL_MISMATCH` |
| 并发 | 运行中再启动一个 wsctl | 后者等待，前者结束后继续 | 等待超时 `WSCTL_BUSY` |
| 崩溃残留 | 固定目录已存在 | 删除后重建，正常运行 | 目录为符号链接 → 拒绝 |
| Mac | 无 `bws_materialize` | 行为不变 | — |
| Semaphore retire | `retire` 无/有 `WSCTL_APPROVE` | 分别为 `--plan-only` / `--approve` | — |

</frozen-after-approval>

## Code Map

私有代码 `/Users/weierfu/Projects/IaC/remotecc/employee-admin/`。不 commit、不 push、不 ssh。

- `wsctl-secrets.py` `materialize()` -- `tempfile.mkdtemp` 改为固定 `<run_root>/wsctl`，残留处理。
- `wsctl` -- 物化前取锁（`flock -w 1800` 于 fd，或 python 包装），保持到退出；`cleanup` 照旧删除目录。只在 settings 含 `bws_materialize` 时加锁（可由 wsctl-secrets 输出一个标志，或 wsctl 先读 settings）。
- `semaphore/wsctl.sh` -- case 加 `retire`。
- 测试：`test-wsctl.py`（固定目录、残留、符号链接拒绝、锁排队/超时、Mac 无锁）、`test-runtime-bridge.py` 如涉及 wsctl-secrets 则同步。

## Tasks & Acceptance

**Execution:**
- [x] `wsctl-secrets.py`、`wsctl`、`semaphore/wsctl.sh` 与测试 -- 实现
- [x] 部署（hitl，主会话）-- push employee-admin；执行器跑相关测试
- [x] 实测（hitl）-- 执行器上 `provision --plan-only` 两次 SHA 与 run_dir 相同（只读计划，不执行）；两个并发 `wsctl status` 后者排队；`retire --plan-only` 经 `semaphore/wsctl.sh` 两步路径可调用（无候选时为空计划）

**Acceptance Criteria:**
- Given 执行器，when 连续两次 `wsctl provision --plan-only --email X`，then 两次 `approval_sha256` 与 `run_dir` 相同。
- Given 一个 wsctl 正在运行，when 再启动一个，then 后者等待前者结束后才运行。

## Implementation Notes

- 2026-11-02 实现（未 commit）：
  - `wsctl-secrets.py`：物化目录固定为 `<run_root>/wsctl`（run_root 选择逻辑不变；评审 Pass 1 后去掉 `tempfile.gettempdir()` 回落，见下）。`fresh_dir()` 在持锁时处理残留：路径非目录（含符号链接）→ `WSCTL_RUN_DIR_UNSAFE`；内部只允许普通文件与 socket（崩溃残留的 `agent.sock`），其他（符号链接、子目录）→ 拒绝且不删任何东西；然后 `mkdir 0700`。新增 `--lock-path`（无 `bws_materialize` 时输出空）与 `--lock-fd N`（对 wsctl 继承的 fd 做 `fcntl.flock`，轮询至 `WSCTL_LOCK_WAIT` 秒，默认 1800，超时 `WSCTL_BUSY` 退出 3）。用 Python `fcntl.flock` 而非 `flock` 命令，Mac/Linux 均可运行：flock 锁属于打开的文件描述，子进程退出后由 wsctl 的 fd 9 继续持有，wsctl 退出即释放。
  - `wsctl`：物化前 `exec 9>>"$lock_path"` 并取锁（仅 lock_path 非空即执行器）；`ssh-agent` 与最终分派命令都以 `9>&-` 启动，避免常驻子进程（ssh-agent、ssh ControlMaster）继承 fd 而把锁拖过本次运行。`cleanup` 不变，仍删除目录。
  - `semaphore/wsctl.sh`：两步审批 case 加 `retire`（手工验证：无 `WSCTL_APPROVE` → `retire --plan-only`，有 → `retire --approve <SHA>`）。
  - 与计划的偏差：残留目录内除普通文件外也删除 socket（否则崩溃留下的 `agent.sock` 会让之后所有运行被拒）；BUSY 退出码沿用 3（与其他 `WSCTL_*` 运行失败一致）。
  - 递归死锁复核：grep 执行器代码路径，`wsctl`、`wsctl-confirm.py`、`oci-hub-admin.py` 及其 hub-* 模块、ansible/ 下均无 `wsctl`/`onboard.sh` 子调用；唯一调用 `onboard.sh` 的是 `onboard-host.py`（Mac 端经 `sbx exec`，非执行器路径）。`onboard.sh --profile oci-hub` 用 `exec` 转交 wsctl，不嵌套。
  - 测试：`test-wsctl.py` 新增 `FixedRunDir`（固定路径且两次相同、残留替换、符号链接目录拒绝、残留内链接拒绝、锁超时 `WSCTL_BUSY`、第二次运行等待、运行结束释放锁、无 `bws_materialize` 时 run_root 下不产生锁或目录）；原 `Secrets` 用例改为设置 `XDG_RUNTIME_DIR` 指向临时目录——否则在执行器上跑测试会碰真实的 `/run/wsctl` 与锁。`test-runtime-bridge.py` 不涉及 wsctl-secrets，未改。

- 2026-11-02 评审 Pass 1 修补：
  - 有 `bws_materialize` 时 run_root 必须存在、属于 `geteuid()`、无 group/other 写位，否则 `WSCTL_RUN_ROOT_UNSAFE`（退出 3，不加锁、不物化）；不再回落 `/tmp`。锁文件由 `--lock-path` 以 `O_CREAT|O_NOFOLLOW` 0600 创建并检查为本用户的普通文件，否则 `WSCTL_LOCK_UNSAFE`，之后 wsctl 才 `exec 9>>`。残留目录还要求 `st_uid == geteuid()`。
  - `main` 捕获 `OSError` → `WSCTL_RUN_DIR_UNSAFE`；`WSCTL_LOCK_WAIT` 非数字、负数或非有限值 → `WSCTL_LOCK_WAIT_INVALID`，均退出 3。
  - 延后：SIGKILL 后 ssh-agent 成为孤儿进程是既有问题（与本故事无关）；它不持锁（`9>&-`），下次运行会清理残留的 `agent.sock`，但 agent 进程本身仍在，需另行处理。
  - 部署前提：执行器运行 wsctl 的用户必须有可用 run_root——`XDG_RUNTIME_DIR`（属于本用户、0700）或以 root 运行使 `/run` 可写；否则所有执行器命令以 `WSCTL_RUN_ROOT_UNSAFE` 失败。
  - 测试补充：常驻子进程（`start_new_session`、`close_fds=False` 的 `sleep 30`）不持锁，第一次退出后 `WSCTL_LOCK_WAIT=0` 的第二次立即成功（已反向验证：去掉 `9>&-` 时该用例失败）；BUSY 断言退出码 3；`hold()` 句柄用 `addCleanup`；run_root 为 0777 或不存在、锁为符号链接、`WSCTL_LOCK_WAIT` 为 `soon`/`-1`/`nan` 的拒绝用例。属主不同的锁/目录需要 root 才能构造，未测。

- 2026-11-02 部署：employee-admin 1488702；执行器 test-wsctl / test-runtime-bridge / test-hub-create / test-hub-retire 全部 OK（含 ssh-agent 用例）。执行器与 Semaphore 均以 root 运行、XDG_RUNTIME_DIR 未设，run_root=/run（root 0755）。
- 2026-11-02 实测：经 semaphore/wsctl.sh 两次 `provision --plan-only`（cc45）得到相同 approval_sha256 9dfa3efe… 与 run_dir 73b492a7…；运行后 /run/wsctl 已删除。两个并发 `wsctl status`：A 31 s 完成，B 58 s 完成（排队）。`retire` 经 Semaphore 入口：无审批为空计划，错误 SHA 报 RETIRE_APPROVAL_MISMATCH。未以 --approve 实际执行开户（需建 VM，未授权）。
- 实测发现 4.4 缺口：退役员工的开户运行目录仍预留其 VMID/地址（新计划得到 512 而非 511）；ab0f0a1 让退役归档这些目录，复测新计划得到 511、10.234.0.11、10.235.0.13。测试计划目录已归档到 runs/archive-retire-test-20261102。

## Plan Change Log

## Review Triage Log

- Pass 1 (quick): high 0 / medium 1 / low 4
  - medium 已修：固定文件名在全局可写的回落目录（/tmp）不安全 → 要求 run_root 安全，否则 `WSCTL_RUN_ROOT_UNSAFE`；残留目录与锁文件校验属主、拒绝链接。
  - low 已修：`OSError` 与非法 `WSCTL_LOCK_WAIT` 不再抛 traceback → `WSCTL_RUN_DIR_UNSAFE` / `WSCTL_LOCK_WAIT_INVALID`，退出 3。
  - low 延后：SIGKILL 后 ssh-agent 成为孤儿进程（既有问题），已记入 Implementation Notes。
  - low 已修：补测试（常驻子进程不持锁、BUSY 退出码 3、`addCleanup`、run_root/锁/等待时长的拒绝用例）。
  - low 随 medium 一并修复。

## Verification

**Commands:**
- `cd remotecc/employee-admin && for t in test-wsctl.py test-runtime-bridge.py test-hub-create.py; do python3 $t || exit 1; done` -- expected: OK（ssh-agent/socket 用例需沙箱外）

**Result (2026-11-02, Mac 沙箱, Pass 1 修补后):** test-wsctl.py 42 项中 40 通过，2 失败为基线已知的沙箱限制（`Secrets.test_secrets_are_materialized_for_the_run_and_removed_after`、`Secrets.test_materialize_uses_its_own_token_when_set`：`unix_listener: cannot bind ... agent.sock: Operation not permitted`），新增用例全部通过；test-runtime-bridge.py 4/4 OK；test-hub-create.py 16/16 OK。`bash -n wsctl semaphore/wsctl.sh` 通过。执行器上需复跑以覆盖 ssh-agent 用例。
