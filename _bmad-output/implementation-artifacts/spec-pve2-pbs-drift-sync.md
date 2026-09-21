---
title: 'pve2 / PBS 漂移同步'
type: 'chore'
created: '2026-09-21'
status: 'done'
baseline_commit: 'b664b49e7706564d3b84367f09fcbf5ee52c55fa'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** T7910 改为独立 pve2，PBS 迁移并重建存储；仓库与现场不一致。

**Approach:** 修正现有草稿，使用同 workspace 的独立 provider alias 纳管 PBS，通过只读 plan 对账。按用户追加要求纳入昨日新引入的PDM，复用origin/main中既有资源地址，保持其为保留服务。代码完成不代表 state 已同步。

## Boundaries & Constraints

**Always:** pve2 API token 经 Vault 桥接，inventory 使用 `proxmox_cluster` 组但非 corosync 成员；客机内 ZFS 为长期方案。按用户追加决定，备份作业、时间及保留策略不由 Ansible 管理，删除相关配置入口，现场配置只作记录。两块已直通 NVMe 留作后续 special vdev，本次不实施。ESXi 宿主已退役。pve1 LXC111 的 Time Machine 使用 nvme-lvm:vm-111-disk-0、900GB、ext4、/srv/timemachine，底层 nvme-vg/data。

**Ask First:** 凭据变更、安装依赖、import/state 写入、apply/部署、提交/推送/发布。

**Never:** 纳管实验 VM、改生产磁盘/认证/任务、复用其他任务 Sandbox、改写历史事故、编造决策理由。

## I/O & Edge-Case Matrix

| 输入 | 预期 | 边界 |
|---|---|---|
| pve2=.52，vmbr0，独立 | 独立 provider；NetBox 不挂原集群 | 不推断 quorum |
| PBS=.249，pve2/100，4核，配置16GiB | 精确资源绑定 | 不声称客机内存已生效 |
| tank池根=/mnt/datastore/tank，store=backup | compression/atime=on；recordsize=128K | 无子dataset、无special |
| 三个PCI，1HBA+2NVMe | 保留全部直通 | 不猜槽位对应设备 |
| pve0 100–109，pbs，00:00，保留3/7/4/3 | 仅记录现场；Ansible 不管理业务计划 | 不代表备份成功 |
| 缺token或HCP访问 | 报告阻塞 | 不误建VM、不伪造plan成功 |

</frozen-after-approval>

## Code Map

- `terraform/proxmox/{provider,variables,pve-cluster}.tf`：现有模式；`versions.tf`：bpg 0.70.0，workspace `iac-proxmox-lab`。
- `terraform/proxmox/windows-server.tf`：原生VM参考；`scripts/get-secrets.sh`：Vault桥接。
- `ansible/roles/pbs/`、`pbs-client/` 与两个PBS playbook：存储、认证、备份、验证。
- `terraform/netbox-integration/infrastructure.tf`、Homepage templates：归属与展示。
- `docs/specs/backup-architecture-consolidation-spec.md`、相关设计文档、README、`deferred-work.md`：当前事实与历史边界。

## Tasks & Acceptance

**Execution:**
- [x] Terraform上述文件、新建`pbs.tf`：核对schema后建模OVMF/q35、mainpool系统盘80GiB、local-lvm EFI/4m、virtio-scsi-single、QGA、serial、自启、MAC BC:24:11:00:01:13，PCI 01:00.0/0d:00.0/10:00.0；核对import身份格式。
- [x] `pve-cluster.tf`和密钥桥接：不默认pve2共享集群SSH密码；缺新token不破坏既有桥接或冒充可用凭据。
- [x] PBS roles/playbooks：对齐池根布局和属性；按追加要求删除备份业务playbook及pbs-client，去掉GC调度参数；仅保留服务/存储配置与检查。
- [x] NetBox、Homepage、README、设计文档及欠账：同步归属；D18只记已确认决定，理由未提供不代填；撤回“没有任何校验”“quorum至今未变”等断言。
- [x] `fileserver.tf`、LXC模块：根盘改local-lvm/8G，mp0引用已有nvme-lvm:vm-111-disk-0/900G；不处理unused0、不创建卷；用户给出的ext4/约840GB可用仅记录。
- [x] ESXi退役：移除inventory与默认state拉取，按用户单独授权停用仓库Jenkins/CI入口；历史根模块及远端workspace保留。
- [x] 专属direct Sandbox校验及完整plan已完成；后续根据用户逐项授权执行VM112退役、PBS导入、inventory新增、PBS归一化和故障恢复。state/plan文件受保护，未输出秘密；最终Proxmox plan无变更。

**Acceptance Criteria:**
- Given 现场证据，when 比对代码与文档，then 节点、VM、路径、属性、备份参数一致，历史与当前可区分。
- Given 两端都有VMID100，when 检查绑定，then PBS只绑定pve2，不影响pve0 LXC100。
- Given 只读授权，when 对账，then 如实报告导入/新增/修改/替换/删除或阻塞，远端state不持久更新。

## Spec Change Log

- 2026-09-21：用户授权修复 GPT-6 报告问题，再重新校验。保留所有已定范围和禁止外部写入边界；报告的强制建池风险须修复为既有池纳管时查询失败即停止，不自动创建或导入。Verify 默认值应以命名空间回退，不覆盖 inventory。Homepage 需独立 pve2 凭据引用，缺凭据时明确未配置；不创建新 token。文档不夸大验证或 state 完成情况。

- 2026-09-21追加范围：用户撤销Ansible备份业务管理；确认ESXi退役、NVMe后续special vdev及LXC111新存储，并单独批准停用仓库ESXi CI入口。原来增加的业务策略断言与对应role一并删除，不通过其他路径恢复。旧验证结果保留为阶段记录，不冒充新增范围验证。

## Implementation Evidence

- `qm config 100`：CPU sockets=1，memory=16384；efi pre_enrolled_keys=false；serial0=socket，vga=serial0；smbios UUID=de3d8b94-f4fb-45aa-a123-fad255bed501；boot=scsi0；网卡firewall=true。不要自行填未确认的 balloon/CPU type。
- 已在本任务 Sandbox 读取 bpg 0.70.0 schema：`hostpci { device = "hostpci0"; id = "0000:01:00.0"; pcie = true }`，按0/1/2顺序对应01:00.0/0d:00.0/10:00.0；`serial_device { device = "socket" }`、`vga { type = "serial0" }`。此处分号仅表达字段分隔，HCL实际逐行书写。
- 同版本官方VM文档确认import ID为`pve2/100`；原始`hostpci.id`配置注明不兼容API token、要求root密码。不能因此声称只读import/plan必然失败或apply可用；保留token选择，后续写入能力标为未验证/受限，不擅改认证。用声明式import避免将既有PBS误建；不执行导入。
- 校验环境已获授权并创建：`iac-claude-run-iac-20260921020006-56022-direct-v130`，Terraform1.14.9、Ansible2.20.9、HCP认证和localhost smoke通过。实施subagent只修改仓库、不启动新Sandbox、不跑凭据/生产操作。校验由主会话串行运行；host提供Git文件清单，guest不具备宿主worktree的Git元数据。
- 本次仅完成明确范围内最低限度的NetBox描述；未读取live NetBox对象，不借机批量接管原有服务。报告coverage缺口时区分未建模与已核实的生产漂移。

## Verification

- `git diff --check`、`bash -n scripts/get-secrets.sh`。
- Sandbox：变更目录`terraform fmt -check`、`terraform validate`、两个PBS playbook `--syntax-check`；不用生产秘密做离线测试。
- 按现场值核对YAML参数与VMID集合，验证认证偏离不会被描述为无变更重跑。
- 实环境plan与离线检查分别报告；核实凭据授权后执行。缺凭据则明确未完成，不创建凭据或安装依赖。
- 不运行apply、部署或有写入副作用的check-mode；用户指定的 GPT-6 Astra 独立只读审查已完成（修复前版本），未执行 CR-1，修复后未再次独立审查。

## Verification Results — 2026-09-21（用户追加退役/存储范围之前）

- 专属 Sandbox 工具/HCP 认证/localhost smoke：通过；不等于资源 plan 通过。
- 隔离无凭据副本：Proxmox 与 NetBox `terraform validate`、两个 PBS playbook syntax-check 均通过。`pbs.tf` 首次 fmt 失败，修正后定向复查通过；其余受检 HCL 格式通过。
- `ansible/tests/pbs-drift-check.py`：11/11 通过。涵盖池正常/重复执行、缺池和路径不符安全失败、inventory 优先级、datastore 路径、备份精确集合/缺109/禁用，以及 Homepage 两种独立凭据状态。失败用例期望 Ansible 返回2，不是真实生产失败。
- `iac-proxmox-lab` state 只读检查：serial58，无 PBS/pve2 匹配条目；未写state。
- 实环境 `plan -input=false -lock=false -detailed-exitcode -json`：退出1，两项 `No value for required variable`（`pm_api_token_id_pve2`、`pm_api_token_secret_pve2`）。没有资源变更结论，不将缺凭据当成无漂移。原始输出仅留在Sandbox权限受限临时目录。
- 完整对账仍受凭据阻塞，所以工作项保持 in-progress。PBS/PVE inventory的state写入、生产verify任务修正、Homepage token配置和NetBox live对象对账均未执行。

## 追加范围验证

- Terraform格式、Proxmox/NetBox validate、保留的deploy-pbs syntax-check均通过。
- LXC模块mock测试3/3通过：已有900G托管卷与local-lvm根盘、旧host-path模式、托管卷缺size拒绝。首次测试夹具init因复制根模块lockfile并设readonly而失败；仅在临时副本允许更新lockfile依赖集合后通过，仍用bpg0.70.0，未修改仓库lockfile。
- 仓库CI夹具通过，新增ESXi根目录/历史模块不选为执行目标、ESXi验证入口拒绝、Jenkins不再路由ESXi等回归检查。没有运行真实Jenkins任务或发布流水线。
- PBS本地fixture调整为9/9通过；删除旧业务作业断言，新增不含Ansible备份策略/GC调度入口的边界检查。
- LXC111字段来自用户pct config和PVE storage JSON。只读复查HCP serial58：module.fileserver.proxmox_virtual_environment_container.lxc仍记录根盘vmdata/8G与旧/tank/timemachine挂载，确认state尚未反映现场local-lvm根盘和nvme-lvm/900G数据卷。未写state、未运行实机apply；此前凭据缺失的plan失败不能视为LXC变更无漂移的证明。ESXi远端state及外部Jenkins job保留未修改。

## 补齐 Vault 后的实环境对账

- 用户已更新Vault；仅执行现有桥接中的Proxmox部分，验证两个pve2 token变量非空，并以no_log生成task-local secrets.auto.tfvars，未显示秘密或改动OCI配置。
- 再次完整plan退出1。PBS导入报non-existent；只读API核实节点确为pve2且online，但token查询VM100配置返回403：缺少`/vms/100`上的`VM.Audit`；有效权限查询为空。不能把该导入错误解释成VM已被删除。未更改ACL。
- VM112配置仍引用`scsi1=tank:vm-112-disk-1`，但pve1存储列表已无tank；`scsi0=local-lvm:vm-112-disk-1`也被provider报告找不到LV。其EFI盘现在是local-lvm，代码仍有旧存储描述。尚未修复或清理磁盘，需用户确认实际存储/是否保留VM112。
- 不完整plan包含MCP Gateway replacement（未执行，原因待进一步核实）以及PDM VM/image/inventory删除。后者与分支落后有关：当前origin/main已有`terraform/proxmox/pdm.tf`，任务HEAD基于b664b49，尚未纳入该文件。未擅自合并或应用这些变更。
- 该轮阻塞从“缺变量”变为“token读取权限、VM112存储引用及分支/state基线差异”。计划不可用于apply；远端state未写入。

## VM112 退役执行记录

- 用户明确授权销毁pve1/windows-server/112，并确认允许provider固定使用的purge=1和destroy-unreferenced-disks=1。事前API核对VM已stopped、无lock、无HA/replication记录，当前备份任务不包含112；state serial58确认两条目标身份。
- 因失效磁盘导致refresh失败，使用已核对现场身份的-target、-destroy、-refresh=false生成saved plan；JSON断言仅proxmox_virtual_environment_vm.windows_server和ansible_host.windows_server两项delete，无其他资源或输出变更。执行前再次检查VM配置digest未变和saved-plan SHA256。
- apply退出1，部分完成：ansible_host.windows_server已删除；VM删除任务因storage tank不存在失败。复核VM112仍存在且stopped，配置digest和磁盘引用未变；state serial59保留VM资源、已无inventory资源。没有执行state rm、创建替代存储或进一步磁盘清理；该saved plan已失效，不得复用。
- 用户随后授权清理失效引用并要求尽快完成。使用宿主已信任的pve1 SSH公钥与转发agent，在PVE配置锁内验证name/digest/stopped、无快照、tank未注册、LVM无112卷后，备份112.conf并只删除scsi0/scsi1/efidisk0三条失效引用；未创建存储或删除实际磁盘。
- 重新使用正常refresh生成saved plan，严格断言仅VM112一项delete；apply退出0。HCP serial60已无两条Windows资源，PVE VM列表确认112消失；PDM117和Fileserver111仍running，备份作业的ID/成员/启用状态未变。windows-server.tf已删除以防重建。原PVE配置备份位于pve1的/tmp/vm112-before-retirement-GbVx_O.conf，权限0600。
- 销毁后完整只读plan成功完成（detailed-exitcode=2，无error），保存为Sandbox受限临时文件；尚未执行。剩余为PBS导入及更新、两个inventory新增、Homepage description、n8n memory及MCP Gateway的EFI pre_enrolled_keys导致的replacement。绝不把此完整计划当成已授权apply。

## 剩余漂移处理授权

- 用户同意n8n按现场4096MB更新代码、LXC忽略description以保留Homepage备注、PBS仅导入state、仅创建pbs/pve2两个inventory记录。随后明确同意精确忽略EFI创建期字段；模块仅增加efi_disk[0].pre_enrolled_keys，不忽略整个VM，也不重建EFI盘。剩余MCP磁盘discard差异按保留现场原则显式设置ignore，其他VM保持模块默认on，未对运行VM执行更新。
- PBS CLI import已成功：state serial60→61，资源proxmox_virtual_environment_vm.pbs绑定pve2/100。导入前后PVE配置digest一致，没有改VM配置。
- 仅含ansible_host.pbs及ansible_host.pve2两项create的saved plan已获授权执行，state serial62；零VM资源动作。动态inventory实测包含PBS/pve2/PDM，不含windows-server。
- PCI rombar按现场显式设置true，消除该差异但未写VM。最新完整plan退出2、无diagnostic，仅剩PBS一项原地update；无create/delete/replace。PBS导入后的boot/on_boot/SMBIOS读回缺口、agent类型及provider默认值仍待审阅，未获授权执行VM更新。n8n、Homepage、MCP、PDM、Fileserver已无资源动作建议。

## PBS 归一化执行与恢复记录

- 用户授权执行最后一项PBS更新。新saved plan断言仅PBS update，磁盘/EFI/PCI/CPU/内存/网卡无变化，reboot=false；执行前配置digest未变。
- 该检查不足以排除bpg0.70.0的自动重启。其vmUpdate会因agent、boot_order、keyboard等差异设置rebootRequired，不受reboot=false总控。本次provider写入配置后发起qmreboot，并因无法完成关机而等待。之前把此过程描述为仅Guest Agent等待不准确。
- Terraform被优雅中止，随后取消本次qmreboot任务。VM进程仍running且uptime未重置，但PBS SSH/HTTPS拒绝连接，不能认定服务健康。没有继续重试apply。
- 用户单独授权恢复重启：正常shutdown在20秒后超时，随后stop与start均OK。核对磁盘/EFI/PCI/网卡/CPU/内存配置未变；HTTPS恢复401（未登录），SSH确认proxmox-backup和proxy均active，tank healthy、backup datastore仍挂/mnt/datastore/tank，客机内存约15926MiB。未声称备份内容完成完整恢复验证。
- 这是一次发生了服务中断并完成恢复的操作，不是无中断更新；日志及计划保留在Sandbox受限临时目录。
- 恢复后首次plan遇到Proxmox HTTP596超时；降低请求并发后，完整plan退出0、diagnostics为空、changes为空。最终只读state核对serial66：无windows-server，LXC111根盘为local-lvm、mp0为nvme-lvm:vm-111-disk-0/900G，已反映现场配置。

## PDM 追加同步

- 用户确认PDM是昨日新引入、需要保留并纳入本次更新的服务。只读API确认pve1/117、192.168.1.117/24、2核/4GiB、local-lvm系统盘40G；HTTPS8443返回200，不代表其所有远端连接已验证。
- 复用origin/main中的pdm.tf、既有PDM安装playbook及cloud-image模块checksum算法支持，四个文件逐字一致。资源地址沿用module.proxmox_datacenter_manager及ansible_host.proxmox_datacenter_manager，不新增第二套资源，不执行安装playbook。未合并主分支的其他无关更改。
- Homepage及服务文档增加PDM；格式、Proxmox validate、PDM playbook syntax-check通过，Homepage相关fixture连同PBS回归9/9通过。
- 该阶段完整plan退出1，但PDM VM/image/inventory的删除建议已消失，也不再出现PBS导入权限错误。当时剩VM112磁盘错误及其他更新；后续处理见前述退役、纳管及恢复记录。

## 最终结果

Proxmox完整plan退出0，无错误、无资源变更；state serial66已记录LXC111新存储且无Windows112。PBS已恢复健康。NetBox live写入、外部Jenkins job/HCP ESXi workspace清理不在本次执行授权内，仍保留明确边界。最终版本未重新执行GPT-6独立review或CR-1，不把前期review当成最终版本审核通过。代码未自动提交或推送。

## Suggested Review Order

**纳管与运维边界**
- PBS纳管、防销毁及旧provider重启警告。
  [pbs.tf:1](../../terraform/proxmox/pbs.tf#L1)
- Fileserver引用现有卷，不分配新盘。
  [fileserver.tf:1](../../terraform/proxmox/fileserver.tf#L1)
- EFI字段精确忽略，不重建MCP。
  [main.tf:122](../../terraform/modules/proxmox-vm/main.tf#L122)
- 缺池即失败，不自动建池或改挂载点。
  [zfs-pool.yml:1](../../ansible/roles/pbs/tasks/zfs-pool.yml#L1)
- ESXi仓库路由退役。
  [Jenkinsfile-webhook-router:1](../../Jenkinsfile-webhook-router#L1)

**验证**
- PBS边界及Homepage回归。
  [pbs-drift-check.py:1](../../ansible/tests/pbs-drift-check.py#L1)
- 托管卷与bind mount的mock测试。
  [mount-points.tftest.hcl:1](../../terraform/modules/proxmox-lxc/tests/mount-points.tftest.hcl#L1)
