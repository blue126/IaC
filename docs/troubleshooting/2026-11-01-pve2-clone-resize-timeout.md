# 事故报告：pve2 克隆员工 VM 后扩容超时，开户核对失败

> **事故编号**：INC-2026-11-01-PVE2-RESIZE
> **发现日期**：2026-11-01
> **调查结束日期**：2026-11-02
> **状态**：已确定根因并修复，复现验证通过
> **时间基准**：Australia/Sydney，AEDT（UTC+11）

## 结论与影响

退役功能实测需要先开一名临时员工 cc44，开户时由 Terraform 在 pve2 上从模板 9001 克隆出 VM 511，随后把系统盘从 20G 扩到 50G。PVE 的扩容任务因超时失败；Terraform 重试时 PVE 报告成功，但 VM 配置仍记为 20G。开户流程在 Terraform 执行后的核对中发现计划值（50）与 state（20）不符，报 `HUB_TERRAFORM_TARGET_STATE_UNPROVEN` 并中止。

**根因**：扩容命令 `qemu-img resize` 结束前会执行 `fdatasync`，要把克隆刚写入、仍留在页缓存里的约 4.6 GB 数据全部写到 SSD；SATA SSD 约 470 MB/s，需要约 9.8 秒，而 PVE 给这一步固定只留 10 秒。pve2 内存很大（377 GiB），按比例计算的后台写回阈值约 37 GiB，克隆数据在 30 秒到期前不会提前写回，所以扩容紧跟克隆时必然逼近上限。

影响仅限这次临时开户：没有员工数据受影响，cc44 是测试账号，事后已按退役流程删除。10 月 30 日的 VM 509 扩容同样用了约 10 秒，只是刚好没有超时。

## 环境

| 项目 | 现场配置 |
|---|---|
| 主机 | pve2（独立节点），内存 377 GiB |
| 目标存储 | `pve2-ssd`：Intel DC SSDSC2BB800G4（SATA，SMART PASSED），ext4 目录存储，raw 格式 |
| 模板 | 9001 `employee-workspace-baseline-20261022`，盘在 `mainpool`（ZFS zvol），20 GiB |
| 克隆方式 | PVE 全量克隆：`qemu-img convert -n -T none -f raw -O raw`；源是 ZFS 所以源端绕过缓存，目标是目录存储所以写入走页缓存 |
| 扩容方式 | `PVE::Storage::Common::qemu_img_resize(..., timeout 10)`：`qemu-img resize --preallocation=off -f raw <file> <size>` |
| 写回参数（事故时） | `vm.dirty_background_ratio=10`、`vm.dirty_ratio=20`、`vm.dirty_expire_centisecs=3000`，`dirty_bytes` / `dirty_background_bytes` 未设 |

## 时间线

| 时间 | 事件 |
|---|---|
| 10-30 13:39:16–13:39:27 | 克隆 VM 509；13:39:35–13:39:45 扩容用时约 10 秒，未超时 |
| 11-01 23:07:40–23:07:46 | 克隆 VM 511（6 秒） |
| 23:07:47–23:07:57 | 扩容 511：`command '/usr/bin/qemu-img resize …' failed: got timeout` |
| 23:07:59 | Terraform 重试扩容，PVE 报 OK；VM 配置仍为 `size=20G`，实际文件已是 50 GiB |
| 之后 | 开户核对报 `HUB_TERRAFORM_TARGET_STATE_UNPROVEN` 中止 |
| 11-02 | 在 pve2 上原样复现，确定根因；修复后复现验证 |

磁盘文件实际为 50 GiB（`qemu-img info` 的 virtual size 为 53687091200），说明第一次扩容在超时后仍完成了；重试时 PVE 认为大小未变，没有更新配置。`qm disk rescan --vmid 511` 把配置更正为 50G。

## 排查过程

1. **排除硬件与内核问题**：SMART PASSED；事故窗口内核日志无 I/O 错误、任务挂起或链路重置；内存充足。
2. **排除并发负载**：同一时段有 `root@pam` 在同一块 SSD 上反复克隆并运行 PNETLab 测试 VM（9250/9251），一度被怀疑为原因。但 509 那次没有这类负载，扩容同样用时约 10 秒；而且单纯抢带宽不足以让一次 `ftruncate` 慢到 10 秒，这个推断被放弃。
3. **复现并定位到系统调用**：用 PVE 克隆的同一条 `qemu-img convert` 命令把模板盘复制到 pve2-ssd 的测试目录，紧接着用 `strace -T` 跑扩容，并以"先 sync 再扩容"做对照：

| | 立即扩容 | 先 sync 再扩容 |
|---|---|---|
| 克隆复制耗时 | 6.0 秒 | 6.1 秒 |
| 克隆后脏页（Dirty） | 4592 MB | 4632 MB |
| 手动 sync | — | 9.9 秒 |
| `qemu-img resize` 总耗时 | **9.87 秒** | 0.06 秒 |
| 其中 `ftruncate` | 0.00002 秒 | 0.00002 秒 |
| 其中 `fdatasync` | **9.806 秒** | 0.0006 秒 |

扩容本身（`ftruncate`）几乎不耗时，耗时全在 `fdatasync` 冲刷克隆留下的脏页；先 sync 后扩容立即完成，确认根因。

## 修复

| 改动 | 位置 |
|---|---|
| `vm.dirty_background_bytes=536870912`（512 MiB）：后台写回在脏页达到 512 MiB 时就开始 | `ansible/roles/oci-hub-pve`，PR #212 |
| `vm.dirty_bytes=1073741824`（1 GiB）：脏页上限，克隆被限速到磁盘写入速度，扩容时最多剩约 1 GiB 待写 | 同上，PR #213 |

两项写入 `/etc/sysctl.d/90-oci-hub-guest-writeback.conf`，与该 role 已有的 `90-oci-hub-forwarding.conf` 同一管理方式；该 role 在每次开户时运行。只加后台阈值时，扩容从 10 秒降到 3 秒（克隆仍快于 SSD 写入）；加上限后完全消除。

修复后复现（同一脚本）：

| | 修复前 | 修复后 |
|---|---|---|
| 克隆复制耗时 | 6.0 秒 | 10.5 秒 |
| 克隆后脏页 | 4592 MB | 4 MB |
| `qemu-img resize` | 9.87 秒 | **0.054 秒** |
| `fdatasync` | 9.806 秒 | 0.0005 秒 |

代价是克隆本身变慢（约等于磁盘写入速度），克隆加扩容的总耗时基本不变。

## 同期发现的相关问题

这次开户是第一次完整从执行器（ws-executor）运行，同时暴露了几个与扩容无关的问题，均已单独修复：

- PVE 按字母序保存 VM 标签，员工 ID 排在 `oci-hub` 之前时计划值与 state 顺序不一致，同样触发 `HUB_TERRAFORM_TARGET_STATE_UNPROVEN`：标签改为 `sort()` 声明（PR #211）。
- 开户重新部署 pve2 的 boundary 脚本时覆盖了 HAPI 在本机打的补丁，导致所有 VM 开机检查失败：补丁并入仓库（PR #209）。
- 执行器缺少 `wireguard-tools`（PR #213），网关未授权执行器密钥，员工 VM 默认只授权管理员 Mac 的公钥；后两项已在执行器与网关上处理。

## 经验

- 克隆后立即扩容属于"写入后立刻 fsync"的模式；在大内存主机上按比例的写回阈值过大，应使用按字节的阈值。
- PVE 的扩容超时固定为 10 秒且不可配置，只能通过控制脏页量让它稳定落在上限之内。
- 一次超时还会留下"文件已扩容、配置未更新"的不一致，`qm disk rescan` 可以更正。
