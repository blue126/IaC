---
title: '一条命令登录（客户端）：本机 ssh 别名与 Include'
type: 'feature'
ticket: '15'
created: '2026-11-02'
status: done
baseline_revision: 'workspace-onboarding 080581b4d5745df5d1cd5c39b5a29bd67a65cc92; employee-admin af5d8bd'
route: 'full'
route_source: 'auto'
risk: 'medium'
review: 'quick'
review_source: 'pinned'
lenses_ran: [quick]
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 服务端（5.10）上线后，系统自带 `mosh-server` 和整段端口已可用，但员工本机的系统 `ssh`/`mosh` 读不到设备配置，也不认识 `<员工ID>-vm` 这个名字；网站显示的仍是 `oci-hub-<员工ID>`。

**Approach:** workspace-onboarding 发 1.1.0：设备 `ssh_config` 的 Host 行改为 `Host oci-hub-<设备> <员工ID>-vm`（`<员工ID>` 由清单 `vm_hostname` = `oci-hub-<员工ID>` 推出），重跑 setup 时若已安装的是旧版生成结果则原地升级，并在 `~/.ssh/config` 最前加一行 `Include "<设备 ssh_config 绝对路径>"`；之后员工直接 `ssh <员工ID>-vm`、`mosh <员工ID>-vm`。执行器状态推送的主机名改为 `<员工ID>-vm`，交付邮件中的登录说明同步。

**Decision (2026-11-02 用户):** 直接升级原 `ssh_config`，不另建文件；不重发设备包；网站只显示 `<员工ID>-vm`；系统 hostname 不改（5.14）；只在 1.1.0 发布前确认 5.10 已上线并完成迁移。

## Boundaries & Constraints

**Always:** 只有 `profile=oci-hub` 且 `vm_hostname` 匹配 `^oci-hub-[a-z][a-z0-9-]{0,19}$` 时才加别名；已安装 `ssh_config` 等于新版 → 不动，等于旧版 → setup 时原地升级（其他命令照常使用），二者都不是 → 仍报 `CONFIG_CONFLICT`；`~/.ssh` 不存在时以 700 创建，`~/.ssh/config` 不存在时以 600 创建，是符号链接或不可写 → 报错且不写；Include 行完全相同的已存在则不重复；Include 必须在任何 `Host`/`Match` 之前生效，用 `ssh -G <员工ID>-vm` 在测试中验证解析结果（HostName、User、IdentityFile 来自设备配置），且不影响用户原有其他 Host；`bootstrap.sh mosh`/`connect` 等子命令行为不变；Windows 只在文档中给出 WSL 步骤。

**Never:** 不改设备包格式、清单 schema 字段集合与执行器打包逻辑；不删除或改写 `~/.ssh/config` 中用户自己的内容；不碰 employee-admin 中用户未提交的文件；不 commit、不推送、不发版、不部署（另行授权）。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 新装 | 无 state，无 ~/.ssh/config | 写新版 ssh_config；新建 ~/.ssh（700）与 config（600），首行 Include | — |
| 旧版升级 | state 中为 1.0.0 生成的 ssh_config | setup 原地升级为新版；Include 加入 | — |
| 已是新版 | 再跑 setup | 无变化，Include 不重复 | — |
| 篡改 | 已安装 ssh_config 既非旧版也非新版 | `CONFIG_CONFLICT`，什么都不写 | — |
| 已有用户配置 | ~/.ssh/config 已有 Host 段 | Include 插到第一行，原内容不变；`ssh -G` 对其他 Host 结果不变 | 符号链接 → `SSH_CONFIG_UNSAFE` |
| 非 oci-hub | legacy profile 或 vm_hostname 不匹配 | 不加别名，不写 Include | — |
| 网站 | 执行器推送 | 主机名 `<员工ID>-vm`，登录命令 `mosh <员工ID>-vm` | — |

</frozen-after-approval>

## Code Map

- **workspace-onboarding**（worktree `/Users/weierfu/Projects/workspace-onboarding-alias`，分支 `claude/vm-alias`，基于 origin/main 080581b）：
  - `scripts/unix.sh:142-167` 读清单（`ssh_alias`、`vm_hostname`、profile 校验）；在此推出 `vm_alias`。
  - `scripts/unix.sh:279-303` `write_configs` 写 `$stage/ssh_config`：Host 行加 `$vm_alias`；另生成旧版内容 `$stage/ssh_config.v1`（仅用于比对，不安装）。
  - `scripts/unix.sh:309-314` `require_installed`：`ssh_config` 允许等于新版或旧版；新增标志供 setup 升级。
  - `scripts/unix.sh:385-400` setup：已安装时，若为旧版则用新版覆盖 `$state/ssh_config`（600）；之后执行 Include 写入函数。
  - 新函数 `install_ssh_include`：处理 `~/.ssh`、`~/.ssh/config`（拒绝符号链接），首行插入 `Include "$state/ssh_config"`（路径加引号），已存在相同行则跳过；用临时文件 + 原子替换，保留原权限。
  - `docs/mosh.md`、`docs/oci-hub.md`、`docs/manual-macos.md`、`docs/manual-linux.md`、`docs/manual-windows.md`（WSL 步骤）、`README.md`、`AGENTS.md`：登录方式改为 `ssh/mosh <员工ID>-vm`，保留 `bootstrap.sh mosh` 作为备选。
  - `VERSION` → 1.1.0；`tests/test_bootstrap.py`：覆盖矩阵每一行，包括用 `ssh -G -F ~/.ssh/config`（指向临时 HOME）验证解析结果。
- **employee-admin**（main af5d8bd）：
  - `hub-publish.py:28-30` `hostname()` 改为 `<员工ID>-vm`；`test-hub-publish.py` 相应断言。
  - `deliver-temp.py:141-146` 与 `templates/mosh-hub-trial.html`：交付邮件的登录说明改为 `mosh <员工ID>-vm`（`bootstrap.sh mosh` 作备选）；`test-temp-delivery.py:257-262`。

## Tasks & Acceptance

**Execution:**
- [ ] `scripts/unix.sh` -- 别名、旧版升级、Include
- [ ] `tests/test_bootstrap.py` -- 矩阵全行 + `ssh -G` 解析
- [ ] 文档与 `VERSION`
- [ ] employee-admin `hub-publish.py`、`deliver-temp.py`、模板与测试

**Acceptance Criteria:**
- Given 临时 HOME 中完成 setup，when `ssh -G <员工ID>-vm`，then HostName、User、IdentityFile、UserKnownHostsFile 均来自设备配置。
- Given 1.0.0 已安装的设备目录，when 运行 1.1.0 setup，then 不报 CONFIG_CONFLICT，配置升级且 Include 加入。
- Given 网站收到新推送，when 员工登录我的工作区，then 主机名与登录命令均为 `<员工ID>-vm`。

## Implementation Notes

## Plan Change Log

## Review Triage Log

### Pass 1 (quick) — high 0 / medium 3 / low 7 / false 0 / maybe-false 0

| # | Finding | Verdict | Route | Evidence / action |
|---|---------|---------|-------|-------------------|
| 1 | Include 预检在 setup 最前，符号链接/只读 ~/.ssh/config 会阻止整个 setup（含隧道），且掩盖 CONFIG_CONFLICT | medium | patch | 挪到 setup 最后（隧道与配置安装之后）；仍报 SSH_CONFIG_UNSAFE 且不写 |
| 2 | 升级分支 `mktemp` 未受保护，失败时无 JSON 报告 | low | patch | 纳入 `|| fail CONFIG_UPGRADE_FAILED` |
| 3 | `mv -f` 替换用户 config 会拆开硬链接、丢属主/ACL | low | patch | 链接数 > 1 时按 SSH_CONFIG_UNSAFE 拒绝；保留属主不可行则文档说明 |
| 4 | 去重按全文匹配，已在中后部的 Include 不会被移到最前 | low | patch | 首行不是该 Include 时移除其他位置的同一行并插到首行 |
| 5 | 旧版升级测试接受 DEPENDENCY_MISSING，未验证其他命令可用旧配置 | low | patch | 让客户端就绪或用 connect 等命令验证旧配置照常 |
| 6 | 别名测试只用 desktop 模式清单 | medium | patch | 补 access_mode=mosh 且 vm_hostname=oci-hub-<id> 的用例 |
| 7 | "不可写"边界未测试 | low | patch | 补 ~/.ssh 与 config 不可写用例 |
| 8 | AGENTS.md 一条命令登录缺少"主机名为 oci-hub-<id> 时"的条件 | low | patch | 补条件 |
| 9 | troubleshooting.md 缺 SSH_CONFIG_UNSAFE、SSH_CONFIG_WRITE_FAILED、CONFIG_UPGRADE_FAILED | low | patch | 补含义与下一步 |
| 10 | 交付邮件提示词同时给出原生 mosh 与 workspace-mosh/端口说明，员工可见文字用了 Agent 口吻 | medium | patch | 有别名时去掉 workspace-mosh/端口括注；员工可见文字改为第二人称 |

## Verification

**Commands:**
- workspace-onboarding：`python3 -m unittest tests/test_bootstrap.py tests/test_verify_session.py` -- 全部通过；`bash -n scripts/unix.sh`
- employee-admin：`python3 -m unittest test-hub-publish.py test-temp-delivery.py` -- 全部通过

**Manual checks (发布后，另行授权):**
- 管理员在 macOS 上对 control 设备重跑 1.1.0 setup，`mosh control-vm` 进入工作区。
