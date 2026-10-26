# 非 CT111 精确清理清单

生成时间：2026-10-26T18:28:35.060089+11:00。状态：用户已批准全部精确目标；35块卷、2个演练注册、3份临时介质和2份snippet均已清理并核验。

本清单共16块已迁移业务机器旧源盘、19块合成演练卷、2个演练注册、3份演练临时介质和2份演练snippet。执行前逐项复核身份/配置引用/进程与挂载，先归档演练配置，再按精确对象操作；不使用前缀批量删除。

## 1. 已迁移业务机器旧源盘（16块）

| 节点 | 精确对象 | 逻辑容量 GiB | 身份 UUID / GUID |
|---|---|---:|---|
| pve0 | `mainpool/vmdata/vm-108-cloudinit` | 0.003906 | `8026169544984292597` |
| pve0 | `mainpool/vmdata/vm-108-disk-0` | 0.000977 | `9400692129289488314` |
| pve0 | `mainpool/vmdata/vm-108-disk-1` | 100.000000 | `11909461912969516391` |
| pve1 | `/dev/nvme-vg/vm-112-cloudinit` | 0.003906 | `nwVyKK-FORv-7DCM-jd8I-XUYA-REPF-TITMKm` |
| pve1 | `/dev/nvme-vg/vm-112-disk-0` | 0.003906 | `Xbo896-25So-3etB-6lal-stx1-QzWW-eBNkg0` |
| pve1 | `/dev/nvme-vg/vm-112-disk-1` | 20.000000 | `bHpfmN-rcHD-Mf2n-u4aU-Z5LJ-aRGP-O4zr96` |
| pve1 | `/dev/nvme-vg/vm-113-cloudinit` | 0.003906 | `KKtLAZ-8e04-bmwH-W7NE-J3XT-fOIt-TEahfl` |
| pve1 | `/dev/nvme-vg/vm-113-disk-0` | 0.003906 | `1WnBvw-KW5I-pqCt-7o32-tQ8N-NlDC-8ePSuT` |
| pve1 | `/dev/nvme-vg/vm-113-disk-1` | 20.000000 | `xR0HHc-S450-Ornf-7Lbd-vgg5-tpwM-IROwLj` |
| pve1 | `/dev/nvme-vg/vm-115-cloudinit` | 0.003906 | `pn8peb-Bhfr-A08m-7XE2-JdW0-qW2Q-IyiFd0` |
| pve1 | `/dev/nvme-vg/vm-115-disk-0` | 40.000000 | `eyErWu-RC9y-3b59-7KAq-qcfU-Dbm8-rxG2XI` |
| pve1 | `/dev/pve/vm-114-disk-0` | 0.003906 | `L3LjZJ-0hEC-UPcj-buWf-CfQm-jo7g-M1QJ4X` |
| pve1 | `/dev/pve/vm-114-disk-1` | 64.000000 | `cF58ik-6ENt-CG6P-cAyQ-mXmI-hKCF-ZuHaOs` |
| pve1 | `/dev/pve/vm-117-cloudinit` | 0.003906 | `szq0BX-jW0Z-593x-fBaK-mkb1-CeSe-s9g0DK` |
| pve1 | `/dev/pve/vm-117-disk-0` | 40.000000 | `tFA7og-t65Y-hvGh-RiD3-qQdN-IejU-XVeOII` |
| pve1 | `/dev/pve/vm-118-disk-0` | 24.000000 | `yIxQZP-RJQp-5vH5-h50N-erSp-V2Vz-gAD9KI` |

112/113/114/115/117/118已通过原单机业务与30分钟观察，其T0/T1在本轮PBS GET再次确认protected=true、verification.state=ok；VM108免备份，目标pve2保持stopped/onboot0且迁移完整校验已通过。删除的是迁前副本，不改变当前目标。源LVM薄盘逻辑容量不是实际释放量，实际释放以执行后pool读回为准。

## 2. 合成演练卷与注册（19块卷、2个注册）

| 节点 | 精确对象 | 身份 |
|---|---|---|
| pve0 | `mainpool/vmdata/subvol-9111-disk-0` | `12218899642402265891` |
| pve0 | `mainpool/vmdata/subvol-9111-disk-1` | `9834482295722651040` |
| pve0 | `mainpool/vmdata/vm-9108-cloudinit` | `2749496205641027500` |
| pve0 | `mainpool/vmdata/vm-9108-disk-0` | `5386654479033035102` |
| pve0 | `mainpool/vmdata/vm-9108-disk-1` | `6840647657254687214` |
| pve0 | `mainpool/vmdata/vm-9108-disk-2` | `1418209250719007666` |
| pve0 | `mainpool/vmdata/vm-9108-disk-3` | `15782782777127178984` |
| pve0 | `rpool/data/subvol-9111-disk-0` | `1751065225298621594` |
| pve0 | `rpool/data/subvol-9111-disk-1` | `3145849926776343322` |
| pve1 | `/dev/nvme-vg/vm-9111-disk-0` | `qAK82Y-GKz1-Aj9Q-ecHC-WI9X-2dCx-9h8W4C` |
| pve1 | `/dev/pve/vm-9111-disk-0` | `ukwFaG-eDwW-g0VT-AeT2-I81C-9iIA-YPQkwX` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-cloudinit.raw` | `inode=38535173` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-disk-5.raw` | `inode=38535177` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-disk-3.raw` | `inode=38535175` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-disk-4.raw` | `inode=38535176` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-disk-1.raw` | `inode=38535172` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-disk-0.raw` | `inode=38535171` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-disk-2.raw` | `inode=38535174` |
| pve2 | `/mnt/pve/pve2-ssd/images/9108/vm-9108-disk-6.raw` | `inode=38535178` |

- pve0：`/etc/pve/nodes/pve0/lxc/9111.conf`（归档后仅移除该演练注册）。

- pve2：`/etc/pve/nodes/pve2/qemu-server/9108.conf`（归档后仅移除该演练注册）。

CT9111/pve0与VM9108/pve2本轮native status均须复核stopped/onboot0，private原始演练档案、PBS点及protected本地VMA保留。pve2 disk4/5/6是现场实际额外演练卷，已按文件inode列入，不凭旧文档5卷数量删除整个images目录。

## 3. 冗余临时介质与snippet

- pve2：`/root/migration-proxmox-20261025/rehearsal-implementation-01/vm-pve2-restored.raw`（1073741824 bytes）。
- pve2：`/root/migration-proxmox-20261025/rehearsal-implementation-01/os-fixture-01/vzdump-qemu-9108-2026_10_25-23_21_44.vma.zst`（236313600 bytes）。
- pve2：`/root/migration-proxmox-20261025/rehearsal-implementation-01/os-fixture-01/direct-transfer-01/vzdump-qemu-9108-2026_10_25-23_21_44.vma.zst`（795324408 bytes）。
- pve0：`/var/lib/vz/snippets/migration-rehearsal-9108-os-01.yaml`。
- pve2：`/mnt/pve/pve2-ssd/snippets/migration-rehearsal-9108-os-01.yaml`。

完整中转VMA与pve0 protected原VMA实际SHA256均为3f84be78a04c92bbc6b50ae447e300bc515c40509788b042d320327f365c96a5；原protected文件不删。236313600B文件是失败中转残片，1GiB raw为合成演练取证副本；先保留其身份/既有校验记录，才移除介质。

## 明确保留

- All CT111 disks/configuration/restore/monitors/evidence
- All target production disks including VM108 unused seed
- All PBS and protected local backups
- All formal logs/configuration archives/manifests/proofs
- Shared active HCP local candidate and Terraform state snapshots
- All worktrees/branches and user changes

旧命名整理属于独立可逆代码修改，由原实施agent执行，不等同于上述盘释放。HCP发布仍等CT111收尾，所有清理结果将追加父计划并更新全局实际容量；不提前注销回退容量认领。


## 实际执行结果（2026-10-26 18:40 AEDT）

- pve1业务旧13 LV、pve0 VM108旧3 ZVOL全部native pvesm free exit0，逐对象读回不存在；每次操作前实际UUID/GUID、长度、无配置引用、无打开FD/holders及无依赖卷通过。
- 合成演练19卷全部确认不存在：pve0 9、pve1 2、pve2 8；两演练guest均先在原生config lock下核停止/onboot0/原SHA并私有归档，再仅退配置，未调用批量qm/pct destroy。
- pve0 local-zfs:subvol-9111-disk-0的原生删除超出父helper120秒等待；原failure如实保留，没有重发同一目标。原zfs destroy子进程1670008/pstart139177796继续运行，结束后实际确认PID/父均消失且精确dataset不存在；原native退出码因父超时未能取得，不假称exit0。随后独占synthetic-resume-01仅删除尚未尝试的disk-1，不设强制命令超时，真实exit0并确认两dataset不存在。没有取消/杀死任何CT111任务。
- 三份pve2临时介质及两份snippet均逐项SHA/size/inode/无打开FD核对后unlink并读回不存在。snippet原内容私有归档；完整中转VMA与pve0 retained protected原文件SHA一致。没有删除任何PBS或protected本地备份；pve2生产108的unused原seed仍保留。
- 各节点完整逐项proof保存在/root/migration-proxmox-20261025/non-ct111-cleanup-20261026-01/{production,synthetic,synthetic-resume-01,temporary-files}，按节点实际存在子目录。源码helpers/所有失败证据、正式manifests/配置归档及state候选均保留。
- 父18:39:16原子更新全局七台来宾source_cleanup=COMPLETE/old_source_volumes_remaining0及对应old_source_disks_retained=false；所有原回退容量claim金额保持，forward43820974080B不变，不把释放空间重复扣future。mainpool/vmdata freshavailable622748598272B；pve1 local-lvm147652712019B、nvme-lvm72380936356B。CT111 guest对象及pve0/rpool容量对象逐对象完全不变。audit为同私有root的parent-ledger-cleanup-publication.json。
- pve1 CT111原root8GiB/data900GiB LV实际UUID/长度与原记录相同；pve0原restore client1481125仍活。所有CT111卷、恢复、监控、数据清单和后续步骤保留，源盘清理不替代全局24–48h观察或整体迁移完成。
