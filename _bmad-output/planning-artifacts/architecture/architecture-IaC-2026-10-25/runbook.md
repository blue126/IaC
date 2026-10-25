# 迁移操作手册（方案定稿，尚未执行）

读者：操作者本人/持root权限的运维。按单来宾串行执行；本轮所有生产命令均未执行。命令标明主机，不在Mac运行qm/pct/pvesm；Terraform/Ansible只在仓库Sandbox运行。章节中的备份、停机、配额、注册交接、恢复、state及清理命令均须相应执行授权。

**红线：PBS/pve2不可达、同ID交接演练未通过、完整性证据不完整，或内存/容量现场准入不满足时不执行。** 本手册不能当作一键脚本；runtime输入必须来自本次变更的私有清单。禁止force/skiplock、destroy guest及按VMID扫描删盘。

## 0. 运行输入与检查点

每guest在源主机批准的私有目录（建议/root/migration-proxmox-20261025/<kind>-<ID>/）保存：source_node、target_node、kind、VMID、原netX/onboot/启动配置、真实卷列表、bind/device数据、private_config_sha256、T0/T1备份volume ID与verify任务结果、源/目标清单摘要、当前阶段、原生UPID/退出码。T0_VOL只在新备份完成并选定volume后设置，不能把旧恢复点或空值带入。配置可能含Cloud-Init凭据，仅本机root可读，不上传仓库或评审包。

下列变量由操作者从清单填写；未设置应停止，不以示例ID猜测：

```bash
# Bash on the named PVE host; assign these from the approved private manifest.
: "${VMID:?Set the exact guest ID}"
: "${PRIVATE_DIR:?Set the approved private evidence directory}"
```

阶段只推进：PRECHECK→QUIESCED→T0_VERIFIED→SOURCE_RETIRED→TARGET_RESTORED→OFFLINE_VERIFIED→TARGET_FIRST_BOOTED→VERIFIED→TARGET_WRITABLE→ACCEPTED。中断后先检查实际配置、进程、卷和任务，再从对应阶段继续；不盲目重跑分配/恢复/退注册操作。

## 1. 全局只读准入

在pve0/pve1执行并私有保存输出；pve2恢复可达后同样检查。pve2不要求有集群quorum，但须证明其独立身份。

```bash
hostname
pveversion -v
free -m
pvesm status
qm list
pct list
pvecm status
zpool status -v
zfs list -p -o name,used,available,referenced
lvs --units b -o lv_name,vg_name,lv_size,data_percent,metadata_percent
```

逐节点核对桥、VLAN、防火墙/ACL、DNS、路由、NTP、存储content类型和节点限制。pve0的vmbr1为OVS、pve1的vmbr1为Linux bridge；同名不证明策略/MTU相同。pve2核对VMID108无冲突、CPU支持、32GiB临时启动余量、vmbr0与pve2-ssd空间；未满足则整项停止，不自动换盘或换ID。

PBS：核对存储可访问、目标namespace/owner、可用字节及T0/T1保留空间、verify与file-restore能力；新恢复点由源节点完成后，目标也必须能读取。不得在此时运行prune/GC腾空间。

逐guest检查qm/pct config、pending、快照、HA/复制/备份作业；暂停涉及该guest的自动化，其他guest的自动化保持不变。私有保存guest firewall/ACL（含/vms/ID权限）、全部network/boot/EFI/TPM/Cloud-Init、本地ISO校验和、源volume属性。源配置中的未知unused记录另存，不删、不纳入有效卷清单；真实volid逐一pvesm path/size核对。

额外检查pve0 SATA盘smartctl只读报告、ZFS错误及系统盘增长；历史错误不能仅因当前ONLINE而忽略。所需工具不存在就记录缺口，不安装依赖。

## 2. 先演练注册交接和恢复（前置，不操作本次原guest）

获准后，在预留的测试VMID、隔离网络、合成文件/ACL/xattr/硬链接/稀疏文件上，演练附录A的退注册→同ID恢复→撤目标注册→原配置回退。使用与生产同版本PVE及相同存储类型；测试资源创建和回收另行授权。检查daemon/cluster VMID缓存、guest firewall/ACL、原盘仍在且哈希未变、原生锁与任务互斥。

随后用正式备份作一次适当范围的试恢复：小VM可全恢复到已预留临时ID；CT111在PBS中验证完整块/归档，并提取代表性数据和元数据验证读取。**不能在878GiB rpool同时放两份681GiB完整fileserver**；全量目标恢复只做一次，最终开放写入前完成全量比对。把“未完成全量试恢复”这一边界写入变更单；不得声称已完成灾难恢复演练。

## 3. 每guest停写与T0备份

进入PRECHECK，停机后为QUIESCED，本节全部门槛通过后为T0_VERIFIED。对每个guest完整执行本节→§4（VM108）/§5（普通VM与CT118）/§6（CT111）→validation验收→附录C解除栅栏并开放写入，再处理下一guest；不是先把所有来宾做完备份再统一恢复。

按顺序VM108→116（优先验证后关机）→112→113→117→114→115→118→111。每guest通过才推进；不一次停全部业务。

- VM108：记录当前containerlab拓扑/持久卷/启动方法；确认四个运行容器无待保留交互任务，先保存实验状态再停机。不得自动docker prune/down -v。
- VM112/113/117：使用其既有服务停止方法，记录数据库/定时任务；不凭名称假定测试数据可丢。
- VM114：暂停有物理副作用的自动化，再正常关闭HAOS。
- VM115：停止新请求、等待识别任务落盘，再按既有方法停应用；不导出容器环境变量。
- CT118：已核实Compose唯一服务为hindsight、文件为/opt/hindsight/compose.yaml。在源pve1经执行授权用pct exec 118 -- docker compose -f /opt/hindsight/compose.yaml stop停止服务、核实落盘，再正常停CT。该源侧操作只在本节做一次，不在恢复目标后重做源停写。
- CT111：在两Mac执行tmutil stopbackup，确认完成；停止源SMB/所有其他写入者。此时只确认写入停止；容器关机并完成T0验证后，在仍注册的宿主离线视图生成完整清单。lost+found权限错误转宿主核验，不能忽略。

在源节点，先记录原onboot，再关闭自启并优雅关机；关机超时停止本批，不自动硬停。

```bash
# Source PVE: choose exactly one guest type.
qm set "$VMID" --onboot 0
qm shutdown "$VMID" --timeout 180
qm status "$VMID"
```

LXC替代命令（不与上段VM命令一起执行）：

```bash
pct set "$VMID" --onboot 0
pct shutdown "$VMID" --timeout 180
pct status "$VMID"
```

确认stopped且无锁/进行中任务后，仅执行该类型的备份。CT111必须在备份配置中确认mp0 backup=1。源先主动关机并全程保持停止；对原本运行的guest直接使用vzdump stop模式，PVE可能在备份期间恢复guest，不能把stop模式当作全程停写保证。

```bash
# Source PVE; this writes a new recovery point and needs execution approval.
vzdump "$VMID" --storage pbs --mode stop --remove 0 --protected 1
pvesm list pbs --content backup --vmid "$VMID"
# Select the exact new volume ID only after task success, then:

: "${T0_VOL:?Set the exact NEW successful and verified recovery point}"
pvesm extractconfig "$T0_VOL"
```

核对备份任务完整成功、时间、范围、T0_VOL、protected标志、恢复配置和PBS verify结果；现场vzdump须先确认支持protected参数，保护未成功不得退注册。存在跳过盘/权限/读取错误则失败。归档任务完成不等于verify或试恢复已通过。附录D用于创建时保护后的状态复核，以及T1/历史恢复点保护；不是跳过protected门槛的替代流程。停止后的源数据保持不变。T0验证后，在仍注册的源宿主离线挂载视图采集附录B完整清单，确认数据没有再写入、正常卸载后再退注册；目标也用同类宿主离线视图和相同映射文件比对。不在容器内做一份、宿主做另一份。退注册后禁止rw挂载旧卷，确有必要的离线取证须单独批准ro,noload路径。

## 4. VM108：pve0→pve2（独立节点）

进入T0_VERIFIED，退源注册后SOURCE_RETIRED，完整恢复后TARGET_RESTORED。首次启动前按附录G验证内存停止线，并按validation的累计回退账本认领空间；未通过不启动。

源盘保留，但目标第一次启动前也须在pve0按已演练附录A退下源注册并私有归档；留置ID108：禁止对ID108源孤立卷执行rescan，也禁止把ID108再分配给新guest。目标首次启动记录权威转移，此后不能因pve2目标当前关机就直接启动旧源。目标pve2再次确认ID108不存在、目标存储已核定，PBS可读。所有目标启动统一执行附录C网络栅栏；VM108先只修改net0的bridge到已核实的vmbr0，保存目标预期网络配置，再执行fence，不改MAC等其他字段。

```bash
# pve2 only; TARGET_STORAGE is the preflight-approved storage, not a guessed default.
: "${TARGET_STORAGE:?Set the verified pve2 target storage}"
qmrestore "$T0_VOL" 108 --storage "$TARGET_STORAGE" --unique 0
qm set 108 --onboot 0
qm status 108
qm config 108
```

qmrestore默认不启动；禁止live-restore。完整保留磁盘/EFI/Cloud-Init/网络选项；从原net0全文仅更改已验证的bridge到vmbr0，不能丢失MAC/firewall/VLAN/MTU等字段。在源仍停机且目标存储恢复完整后，目标先隔离启动检查console/文件系统/containerlab，再以生产IP联网验证；随后优雅关机，onboot保持0。更新IaC中名称、独立provider、节点、存储、桥与started=false/on_boot=false；未清理源盘，不计算释放容量。


### VM108隔离验证与结束状态

1. 源四个containerlab容器并非闲置
2. 停止前由操作者记录拓扑和配置的持久化位置。目标先按pve2预期桥保存网络，再fence、启动，仅用PVE控制台验证OS与实验文件
3. 需SSH验证时，先正常关机、确认源仍关机、unfence后启动目标，只在短暂验证期间联网
4. 验证完再正常关机，并保持onboot=0。不得把运行中的实验容器当自动允许丢弃的状态。

## 5. pve1→pve0：逐guest同ID冷恢复

进入T0_VERIFIED，退源注册后SOURCE_RETIRED，完整恢复后TARGET_RESTORED。首次启动前先按附录G核实内存和按validation累计账本认领回退空间。

**使用前提：附录A已在合成guest演练通过并明确批准；该过程只退注册，不销毁磁盘。** 对每guest：源stopped、onboot=0、T0已验证、无snapshot/pending/任务锁冲突、目标无该ID、精确卷与配置已归档。冻结两节点关于此ID的全部写入自动化。

源pve1在原生配置锁保护下调用附录A的retire；先核对私有归档文件的哈希；归档配置与T0备份内配置的差异应只包含已记录的onboot和栅栏变化。查看集群资源列表并确认ID全局空闲；不以单节点qm list为空替代全局检查。若后续失败，按validation-and-rollback.md返回源。

```bash
# pve0 only, after the old registration is proven absent cluster-wide.
# QEMU VM112/113/117/114/115/116, one at a time:
qmrestore "$T0_VOL" "$VMID" --storage vmdata --unique 0
qm set "$VMID" --onboot 0
qm status "$VMID"
qm config "$VMID"
```

所有VM在首次启动前执行附录C的fence（工具先保存目标预期网络配置全文，再设link_down=1），并确认每个netX均为link_down=1；所有VM恢复后检查每个实际卷，不遗漏TPM/EFI和Cloud-Init；restore后的磁盘名可能改变，更新私有manifest和IaC绑定。Windows ISO先按源校验和比对并准备于pve0，不自动重装或替换TPM。目标尚未首次启动时按离线完整性规则验证；第一次启动后默认进入T1数据语义，即使尚无生产客户端。

CT118明确恢复rootfs，原还有其他mp时全部显式补齐；保留非特权映射、features和所有持久数据。

```bash
# pve0 only; this command applies only after confirming 118 has exactly its rootfs.
pct restore 118 "$T0_VOL" --rootfs vmdata:24 --unprivileged 1 --onboot 0 --start 0
pct config 118
```

逐guest在隔离网络中启动，按验收文件验证；确认source仍没有注册/运行、目标firewall/ACL和管理绑定正确后才开放入口。验收通过后，把原常开guest恢复为onboot=1；VM116验证后关机，并保持onboot=0。原盘不删，源归档不删。


### CT118目标服务验证

源停写已在§3完成；这里只操作pve0恢复后的目标。

1. 先完成离线清单比对、累计回退认领及附录G内存准入；用附录C断开全部netX，再启动CT，立即记为TARGET_FIRST_BOOTED/T1。
2. 核对Docker/Compose原restart策略和容器状态。对迁前确实运行、当前停止的hindsight，执行pct exec 118 -- docker compose -f /opt/hindsight/compose.yaml start，不用up拉镜像或重建。
3. 用pct exec 118 -- curl --fail http://127.0.0.1:9077/health做本地检查；已有记忆查询和认证客户端用原私有凭据通道，不将key写入参数或文档。
4. 若隔离状态下外部依赖不足而启动/验证失败，停止在本地验证未完成；先确定受控依赖验证路径，禁止临时放开生产客户端来绕过失败。
5. 验证完成后正常停CT，再按附录C unfence。核对源仍未注册/运行、管理身份与回退策略已就绪，再启动目标。
6. 用同一Compose文件start恢复此前运行的hindsight（若已运行则只核对），最后验证原客户端。此后所有回退默认走T1，不把“无生产客户端”当成没写过数据。


## 6. CT111：文件级恢复到新800GiB ZFS subvolume

进入T0_VERIFIED；按附录A仅退原注册，不执行§5的qmrestore示例。完成恢复和离线清单比对后为OFFLINE_VERIFIED，符合容量/回退账本/附录G内存准入后才能首次启动。

首次分配目标数据集之前的容量门槛：rpool可分配字节至少800GiB＋64GiB系统余量＋本次元数据/其他增量；恢复后不重复加计已分配的800GiB，改核实系统dataset实际可写余量。vmdata根盘8GiB已计入336GiB预算。无本地681GiB tar暂存，也不同时保留两份目标数据。源完整私有配置、rootfs/mp0真实卷和UID映射已登记，CT111的已证实无效unused0记录不处理。

按第3节停全部写入、停容器、生成T0，验证归档含rootfs和/srv/timemachine；按第5节仅退原注册。

```bash
# pve0 only; never --force. Explicit advanced restore maps EVERY mount point.
pct restore 111 "$T0_VOL" \
  --rootfs vmdata:8 \
  --mp0 local-zfs:800,mp=/srv/timemachine,backup=1 \
  --unprivileged 1 --onboot 0 --start 0
pct config 111
pvesm list local-zfs --vmid 111
```

从恢复输出和config读取实际subvol名称，核实它确属CT111且挂载/srv/timemachine，再设置含快照总限额。不要硬编码disk-0：

```bash
# pve0 only. DATASET must be the verified CT111 data dataset, never rpool or rpool/data.
: "${DATASET:?Set the exact verified CT111 data dataset}"
[[ "$DATASET" == rpool/data/subvol-111-* ]] || exit 1
zfs get -p used,available,referenced,quota,refquota,reservation "$DATASET"
zfs set quota=800G refquota=800G reservation=800G "$DATASET"
zfs get -p used,available,quota,refquota,reservation "$DATASET"
SYS_DATASET=$(findmnt -n -o SOURCE /)
[[ "$SYS_DATASET" == rpool/ROOT/* ]] || exit 1
zfs get -p available "$SYS_DATASET"
```

reservation/quota设置失败即停止，不降低系统余量；先保护数据，不为“通过”释放源盘。实际可用空间不是只看reservation扣除后的一个available数：账本同时列pool free/available、child used/reservation及实际系统dataset available；64GiB线以实际系统可写余量为准，不用zpool FREE替代。当前lost+found权限问题必须解释并补采；PVE restore所有warning都归档，不屏蔽。

容器仍停止时按附录B对比完整相对路径/内容/元数据清单；直接宿主挂载视图必须采用一致的UID映射口径。验证完成才隔离启动容器（SMB保持停止/生产链路封闭），核对df/挂载点、Samba配置、身份与权限，绝不能让SMB写入错误的空目录。按用户选定值通过既有Webmin/操作者把fruit:time machine max size改为760G；先核对部署版本单位，期望816043786240字节，ZFS硬限额保持858993459200字节，差额42949672960字节（40GiB）。私有保存原Samba配置及差异，运行testparm检查有效共享参数，按既有方式重载并从两Mac核对报告容量（允许客户端显示单位换算/取整，不把760字符串当字节证据）；不重跑1T bootstrap。确认元数据/写入余量及stop备份模式，仍报告800G或校验失败时禁止解除CT111网络栅栏。只在通过这些检查、目标有可用空间且源仍未注册时开放两Mac访问，分别完成历史识别、增量和文件恢复。


### CT111服务停止、核对与开放

1. 源已核实smbd.service active/enabled。目标全网卡断链后才首次启动
2. 用pct exec 111 -- systemctl stop smbd.service停止SMB，再pct exec 111 -- systemctl mask smbd.service，记录此mask为本次临时栅栏（不覆盖原本masked的服务）。核实/srv/timemachine真实挂载及无其他写入者
3. 私有保存systemctl is-active/is-enabled结果。完整性/本地testparm完成后，目标仍隔离运行时先按原状态撤销本次mask（只对本次由enabled转为masked的smbd执行unmask+enable，二者不启动服务），然后正常关机，再按上文unfence和启动。两Mac只在目标为唯一生产写入者后恢复备份。任何其他服务mask均遵守同样的原状态恢复，不批量unmask。

## 7. 管理同步与观察

生产切换前冻结相关Jenkins/apply；仅在隔离环境准备目标代码及定向计划。迁后核对Terraform provider/state/关联download_file与ansible_host、Ansible、NetBox、备份作业；先私有备份state，获得state写入授权后按附录E绑定。对已管理来宾要求无意外create/delete/replace/start；手工来宾维持手工ownership。不要对所有节点执行泛化apply来“刷新”。

PBS备份范围包括迁入pve0的guest和CT111数据盘；pve0常规列表移出已转移的VM108，pve2 VM108的新备份使用专用namespace/alias。原集群namespace和其他作业不整体改动。所有T0/T1验证后立即protected，新作业retention不得取消保护；周期备份作业维持既有disabled状态，周期作业的启用及其停机窗口另行批准。CT111的新获准备份固定stop模式，不创建占quota的ZFS备份快照；完成迁后手工恢复点及读取验证。

观察24–48h，包含两Mac备份、真实FunASR/Hindsight并发及原pve0业务。记录CPU排队、内存pressure/OOM、盘错误/延迟和系统空间；迁后常开guest的配置内存合计69GiB，仍超过约62.6GiB物理内存；不承诺所有guest同时用满配置内存。Windows保持关机。

pve1关机/原盘清理另行批准；源盘清单和配置归档保留到所有验收完成。若获准关pve1，关后核实pve0 quorate及见证获票；核实失败则重新开启pve1，禁止降低票数绕过。


阶段导航：离线校验通过为OFFLINE_VERIFIED；首次启动前先写入启动意图，成功或无法排除曾启动都按TARGET_FIRST_BOOTED/T1；服务隔离验证后为VERIFIED，解除栅栏并确认唯一权威写入者后为TARGET_WRITABLE，观察验收通过后为ACCEPTED。

## 附录A：注册交接工具草稿（仅内部API，未演练，禁止本轮运行）

这不是PVE公共CLI接口。采用它是为了同ID恢复同时保留原盘，避免guest destroy。操作者须先在合成guest上审阅、编译/功能演练并批准；失败就修订方案，不现场绕过。代码只归档/移除或恢复配置，不处理磁盘、ACL或firewall；这些仍单独核对。两个节点相关自动化须先冻结，再由单一操作者串行执行交接，原生配置锁不是全局跨节点锁。

将以下文本保存于已批准的私有目录，0600权限；参数为action(retire/restore)、kind(qemu/lxc)、VMID、预期源节点、私有归档路径、预期SHA256。执行前由操作者设置MIGRATION_REGISTRATION_APPROVED=YES；它不是迁移授权的替代。

```perl
use strict;
use warnings;
use Fcntl qw(O_WRONLY O_CREAT O_EXCL);
use Digest::SHA qw(sha256_hex);
use Sys::Hostname qw(hostname);
use PVE::Cluster;
use PVE::QemuConfig;
use PVE::QemuServer;
use PVE::LXC::Config;
use PVE::LXC;

my ($action, $kind, $id, $node, $archive, $expected) = @ARGV;
die "explicit approval required\n"
  unless ($ENV{MIGRATION_REGISTRATION_APPROVED} // '') eq 'YES';
die "bad input\n" unless defined($expected) && $expected =~ /^[0-9a-f]{64}$/
  && $id =~ /^\d+$/ && $id >= 100 && $kind =~ /^(qemu|lxc)$/
  && $action =~ /^(retire|restore)$/ && hostname() eq $node
  && $archive =~ m{^/root/migration-[^\n]+\.conf$};
my $class = $kind eq 'qemu' ? 'PVE::QemuConfig' : 'PVE::LXC::Config';
sub read_bytes {
  my ($p) = @_;
  open(my $f, '<:raw', $p) or die "read failed: $!\n";
  local $/; my $v = <$f>; close($f) or die "close failed\n";
  return $v;
}
PVE::Cluster::check_cfs_quorum();
$class->lock_config($id, sub {
  my $file = $class->config_file($id);
  my $running = $kind eq 'qemu'
    ? PVE::QemuServer::check_running($id, 1) : PVE::LXC::check_running($id);
  die "guest still running\n" if $running;
  if ($action eq 'retire') {
    my $conf = $class->load_config($id);
    $class->check_lock($conf);
    die "pending change\n" if ref($conf->{pending}) eq 'HASH' && keys %{$conf->{pending}};
    die "autostart must be disabled\n" if $conf->{onboot};
    my $raw = read_bytes($file);
    die "digest changed\n" unless sha256_hex($raw) eq $expected;
    sysopen(my $out, $archive, O_WRONLY|O_CREAT|O_EXCL, 0600)
      or die "archive must be new/private: $!\n";
    binmode($out); print {$out} $raw or die "write archive failed\n";
    close($out) or die "close archive failed\n";
    die "archive mismatch\n" unless sha256_hex(read_bytes($archive)) eq $expected;
    $class->destroy_config($id); # Only unlinks config in the verified installed version.
    die "registration remains\n" if -e $file;
  } else {
    my $list = PVE::Cluster::get_vmlist();
    die "ID still registered anywhere\n" if exists $list->{ids}->{$id};
    my $raw = read_bytes($archive);
    die "archive mismatch\n" unless sha256_hex($raw) eq $expected;
    my $conf = $kind eq 'qemu'
      ? PVE::QemuServer::parse_vm_config($file, $raw, 1)
      : PVE::LXC::Config::parse_pct_config($file, $raw, 1);
    $class->check_lock($conf); $conf->{onboot} = 0;
    $class->write_config($id, $conf);
  }
  print "registration $action completed; inspect cluster state before continuing\n";
});
```

恢复分配、退注册、回退均不是幂等重试命令；归档已存在/ID已存在/哈希变化/任务冲突时失败并检查实际阶段。源pve1与目标pve0的同ID切换必须由单一操作者串行控制；不能声称本地锁能防止另一节点的并发新建。

## 附录B：全量内容和元数据清单（文档内工具草稿）

在已批准的离线挂载视图运行；源须在退注册前采集。CT的pct mount/pct unmount属于本轮未执行的生产挂载写入，执行时需要授权。宿主源/目标挂载可用pct mount ID给出的实际路径，不猜路径；挂载后检查findmnt和每个rootfs/mp的真实volid。采集完正常unmount，不把活动数据库文件当一致性快照。

以下Python3标准库脚本存于批准的私有目录。id-map-json显式提供源/目标视图的映射：guest视图用uids/gids各[[0,0,4294967296]]；默认非特权宿主视图常为[[0,100000,65536]]，但必须从真实lxc.idmap核对，不能直接套用。数组元素为guest_start、host_start、length。只读源文件；输出及错误重定向到私有文件，退出非0或空清单均不通过。

```python
import argparse, base64, hashlib, json, os, stat, sys

def b64(value):
    return base64.b64encode(value).decode('ascii')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--id-map-json', required=True)
    args = ap.parse_args()
    with open(args.id_map_json, encoding='utf-8') as f:
        mapping = json.load(f)
    for key in ('uids', 'gids'):
        if not mapping.get(key):
            raise ValueError('explicit nonempty id map required')
        for segment in mapping[key]:
            if len(segment) != 3 or any(not isinstance(v, int) or v < 0 for v in segment) or segment[2] == 0:
                raise ValueError('invalid id-map segment')
    def identity(value, key):
        matches = [g + value - h for g, h, n in mapping[key] if h <= value < h + n]
        if len(matches) > 1:
            raise ValueError('overlapping id map')
        return matches[0] if matches else 'unmapped-host:' + str(value)
    root = os.path.abspath(os.fsencode(args.root))
    root_stat = os.lstat(root)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError('root must be a directory, not a symlink')
    links, count = {}, 0
    def visit(path, relative):
        nonlocal count
        st = os.lstat(path)
        if st.st_dev != root_stat.st_dev:
            raise RuntimeError('nested filesystem requires separate approved manifest')
        xattrs = {}
        for name in sorted(os.listxattr(path, follow_symlinks=False)):
            xattrs[b64(os.fsencode(name))] = b64(os.getxattr(path, name, follow_symlinks=False))
        row = {'path_b64': b64(relative), 'type': stat.S_IFMT(st.st_mode),
               'mode': stat.S_IMODE(st.st_mode), 'uid': identity(st.st_uid, 'uids'),
               'gid': identity(st.st_gid, 'gids'), 'mtime_ns': st.st_mtime_ns,
               'xattrs': xattrs}
        if stat.S_ISREG(st.st_mode):
            row['size'] = st.st_size
            digest = hashlib.sha256()
            with open(path, 'rb') as f:
                for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
                    digest.update(block)
            row['sha256'] = digest.hexdigest()
            after = os.lstat(path)
            if (st.st_size, st.st_mtime_ns, st.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise RuntimeError('file changed during manifest')
            if st.st_nlink > 1:
                row['hardlink_anchor_b64'] = links.setdefault((st.st_dev, st.st_ino), b64(relative))
                row['nlink'] = st.st_nlink
        elif stat.S_ISLNK(st.st_mode):
            row['target_b64'] = b64(os.readlink(path))
        elif not stat.S_ISDIR(st.st_mode):
            row['rdev'] = st.st_rdev
        print(json.dumps(row, ensure_ascii=True, sort_keys=True, separators=(',', ':')))
        count += 1
        if stat.S_ISDIR(st.st_mode):
            for name in sorted(os.listdir(path)):
                visit(os.path.join(path, name), name if relative == b'.' else relative + b'/' + name)
    visit(root, b'.')
    if count == 0:
        raise RuntimeError('empty manifest')
    print('manifest records=' + str(count), file=sys.stderr)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('MANIFEST FAILED: ' + repr(exc), file=sys.stderr)
        sys.exit(1)
```

Linux POSIX ACL以system.posix_acl_* xattr保存，脚本记录原始值而不改数据。**宿主视图的ACL内部ID并不因uid/gid字段归一化而自动转换**：源/目标ID映射必须完全一致后才能直接比对ACL原始值；映射不同则停止，不能按本脚本判断“相同”。如存在NFSv4 ACL、跨文件系统硬链接、ZFS特有ACL转换或不可读xattr，必须另定验证方法，不能降级忽略。

源与目标各采集一次，把工具版本（inventory.py的SHA256）、视图路径、映射文件摘要和退出码写入私有manifest。rootfs与每个数据集分别采集；rootfs中的已挂载mp不可重复遍历，按单文件系统界限报错后拆分明确采集根，不静默跳过。

```bash
# Named PVE host, approved offline view; all output stays private.
: "${OFFLINE_VIEW:?Set verified source or target dataset mount path}"
: "${ID_MAP:?Set the verified mapping JSON}"
: "${OUT:?Set a new private output path}"
[[ ! -e "$OUT" && ! -e "$OUT.stderr" ]] || exit 1
umask 077
if ! python3 "$PRIVATE_DIR/inventory.py" "$OFFLINE_VIEW" --id-map-json "$ID_MAP" >"$OUT" 2>"$OUT.stderr"; then
  exit 1
fi
# Continue only with a zero exit status and a final record count in the private stderr log.
test -s "$OUT"
sha256sum "$OUT"
```

源、目标清单通过批准的私有传输渠道集中到同一私有目录后用cmp逐字节比较；输入映射/视图口径相同，输出有稳定排序，不比较inode/dev/ctime/物理块数。差异用私有审阅工具定位path_b64对应路径并逐项解释；不要只留下cmp返回1而仍宣布通过。PVE恢复会有意改写某些系统配置时，变更前后具体路径和值须事先登记；不对/etc或全部rootfs做宽泛排除。空lost+found只有宿主已证明为空且双方登记同一排除策略后才可在专门采集视图排除，脚本默认不排除任何目录。

## 附录C：目标网络栅栏及服务恢复

所有网卡都必须处理；运行前核查不存在PCI/USB网络直通或未被netX覆盖的网络路径。恢复目标尚停止时调用fence；保存的是**目标最终预期桥/VLAN**配置，VM108先完成bridge映射。代码只在指定PVE节点由操作者运行，不用于Mac。

```python
import argparse, json, os, re, subprocess

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['fence', 'unfence'])
    p.add_argument('kind', choices=['qemu', 'lxc'])
    p.add_argument('vmid', type=int)
    p.add_argument('saved_network_json')
    a = p.parse_args()
    if os.environ.get('MIGRATION_WRITE_APPROVED') != 'YES':
        raise RuntimeError('explicit execution authorization required')
    cli = 'qm' if a.kind == 'qemu' else 'pct'
    status = subprocess.check_output([cli, 'status', str(a.vmid)], text=True).strip()
    if status != 'status: stopped':
        raise RuntimeError('guest must be stopped before changing the fence')
    node = subprocess.check_output(['hostname'], text=True).strip()
    path = '/nodes/' + node + '/' + a.kind + '/' + str(a.vmid) + '/config'
    cfg = json.loads(subprocess.check_output(['pvesh', 'get', path, '--output-format', 'json']))
    if any(key.startswith(('hostpci', 'usb', 'dev')) for key in cfg):
        raise RuntimeError('passthrough needs separate verified fencing')
    if a.action == 'fence':
        nets = {key: value for key, value in cfg.items() if re.fullmatch(r'net[0-9]+', key)}
        if not nets:
            raise RuntimeError('no network device found; inspect manually')
        saved = {'node': node, 'kind': a.kind, 'vmid': a.vmid, 'nets': nets}
        fd = os.open(a.saved_network_json, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(saved, f, sort_keys=True)
            f.flush(); os.fsync(f.fileno())
    else:
        with open(a.saved_network_json, encoding='utf-8') as f:
            saved = json.load(f)
        if (saved['node'], saved['kind'], saved['vmid']) != (node, a.kind, a.vmid):
            raise RuntimeError('saved network belongs to another guest/node')
        nets = saved['nets']
        if set(nets) != {key for key in cfg if re.fullmatch(r'net[0-9]+', key)}:
            raise RuntimeError('network topology changed')
    for key, original in sorted(nets.items()):
        value = original
        if a.action == 'fence':
            parts = [v for v in original.split(',') if not v.startswith('link_down=')]
            value = ','.join(parts + ['link_down=1'])
        subprocess.run([cli, 'set', str(a.vmid), '--' + key, value], check=True)
    current = json.loads(subprocess.check_output(['pvesh', 'get', path, '--output-format', 'json']))
    for key, original in nets.items():
        if a.action == 'fence':
            if 'link_down=1' not in current[key].split(','):
                raise RuntimeError('fence not effective for ' + key)
        elif current[key] != original:
            raise RuntimeError('restored network differs; inspect normalized API fields')
    print('network ' + a.action + ' complete; inspect current and pending config before boot')

if __name__ == '__main__':
    main()
```

若过程中任何set失败，guest保持停止；不要启动带部分栅栏的guest。检查current及pending配置都符合预期后再启动。首次启动即记权威转移并默认采用T1回退语义；只有无业务新写入的书面证据及操作者明确接受丢弃验证副作用，才可例外R0。隔离验证完成后先正常关机，再unfence，核实源仍未注册/停止、管理同步和T0/T1策略已就绪，再启动目标开写；不在运行中猜测网络热插拔。

```bash
# Target PVE, after offline integrity checks; fence.py is the reviewed appendix-C text.
MIGRATION_WRITE_APPROVED=YES python3 "$PRIVATE_DIR/fence.py" fence "$KIND" "$VMID" "$PRIVATE_DIR/target-network.json"
# Start only the chosen type, with all NICs link_down=1:
# qm start "$VMID"   OR   pct start "$VMID"
```

具体服务操作见§4、§5的CT118流程和§6；工具附录不作为另一份切换流程。

## 附录D：受保护恢复点与PBS命名空间

恢复点的稳定身份不是单一PVE volid，而是server/datastore/namespace/type/ID/timestamp/owner；清单同时记录源读alias与目标读alias、精确T0/T1 volid。pve2承载PBS VM100，VM108目标与它共享物理故障域；单一namespace不代表独立副本。用户已接受沿用该故障域；目标第一次启动前仍须验证恢复点可读及数据截止点。pve2不可达时不假定其本地盘或PBS可用，也不保证双机故障回退。

源集群沿用当前已核实的PBS namespace；T0/T1 protected防止手工或作业retention误删。pve2 VM108后续备份使用专用namespace，例如proxmox-consolidation/pve2-108（创建前检查未被其他用途占用）。创建专用PBS storage alias只服务VM108，不改pve2现有作业的全局namespace。读旧T0要用匹配其原namespace的恢复alias，不能用新namespace去找旧快照；不得凭相同vm/108认定是同一谱系。

在已批准、已存在的PBS客户端环境使用官方protected命令；不安装工具，不把密码/票据放入参数。认证通过已有私有运行时/文件描述符，repository只描述非密钥连接身份。PBS版本/客户端语法先核实；保护失败不得进入退注册或源旧卷释放。

```bash
# Approved PBS client environment only; this is a backup-metadata write.
: "${PBS_REPOSITORY:?Set verified server/datastore identity without passwords}"
: "${PBS_NAMESPACE_KIND:?Set root or named from the approved manifest}"
PBS_NS_ARGS=()
if [[ "$PBS_NAMESPACE_KIND" == named ]]; then
  : "${PBS_NAMESPACE:?Set the exact named namespace}"
  PBS_NS_ARGS=(--ns "$PBS_NAMESPACE")
elif [[ "$PBS_NAMESPACE_KIND" != root ]]; then
  exit 1
fi
: "${PBS_SNAPSHOT:?Set exact type/ID/timestamp, not merely the latest item}"
proxmox-backup-client snapshot protected update "$PBS_SNAPSHOT" true --repository "$PBS_REPOSITORY" "${PBS_NS_ARGS[@]}"
proxmox-backup-client snapshot protected show "$PBS_SNAPSHOT" --repository "$PBS_REPOSITORY" "${PBS_NS_ARGS[@]}"
```

根namespace的CLI表示随已安装版本核实：不接受空值隐式继承，若根应省略--ns，清单写明root并使用已核实的不带--ns命令，不能将字面字符串root当命名空间名。保护只是防误删，管理者仍可取消；取消保护、prune或源卷清理都需另行授权。源CT111盘的最终清理还必须有迁后数据盘备份及至少一次verify通过的恢复点。

## 附录E：确定的IaC重新收编流程（仅计划，未执行）

保持Terraform ownership，采用**服务文件中的直接adoption资源 + 精确state rm/import**。不修改共享模块lifecycle，不使用跨endpoint的moved猜测，不把资源转手工，也不把创建镜像重新download/import来“修复计划”。本轮不编辑Terraform业务代码和远端state。

| 服务 | 精确旧state地址 | 新直接资源及导入ID |
|---|---|---|
| VM108 | module.ubuntu_2604.proxmox_virtual_environment_vm.vm | proxmox_virtual_environment_vm.containerlab；pve2/108；provider=pve2 |
| CT111 | module.fileserver.proxmox_virtual_environment_container.lxc | proxmox_virtual_environment_container.fileserver；pve0/111；集群root provider |
| VM117 | module.proxmox_datacenter_manager.proxmox_virtual_environment_vm.vm | proxmox_virtual_environment_vm.proxmox_datacenter_manager；pve0/117；集群provider |

创建阶段镜像资源module.ubuntu_2604.proxmox_virtual_environment_download_file.image、module.proxmox_datacenter_manager.proxmox_virtual_environment_download_file.image只从state解除，**不删源镜像文件**。ansible_host原逻辑地址保留并更新实际节点/命名；服务outputs转为新直接资源引用。所有旧地址执行前与state list核对，不按module前缀批量rm。

实施人员先在本任务分支准备3个直接资源：据目标读回列现有CPU/RAM/磁盘/EFI/TPM/网络/Cloud-Init；VM108显式started=false/on_boot=false和现有MAC；CT111根8G、实际新mp0 volid、size=800G和既有非特权映射；3个资源都prevent_destroy=true。不填创建专用disk.file_id、clone、bootstrap password或重放初始密钥。仅在证实provider读不回某个创建字段时，才能只把该字段的最小路径加入该直接资源的lifecycle ignore_changes；禁止屏蔽node、disk/mount_point及运行状态以掩盖漂移。若import后仍replace，保持冻结、停止修订，不自动换ownership或apply。

取得整个iac-proxmox-lab state的独占写维护窗口，暂停该workspace所有apply/state写者（包括相关Jenkins）。state命令本身仍用backend lock；两条命令间的空隙由该维护窗口约束。保存私有state pull、地址/provider/ID清单及哈希；任何中断先检查实际state，不盲目重放或整体push旧备份。实际API/state访问是另行获准的维护工作，不作为无生产凭据的PR验证。

```bash
# Repository Docker Sandbox only, after target-specific state-write approval.
# The NEW direct-resource configuration must already exist with verified providers.
: "${PRIVATE_DIR:?Set approved private state evidence directory}"
umask 077
terraform state pull > "$PRIVATE_DIR/pre-adoption.tfstate"
# Example for the exact VM108 addresses; do not turn into a broad module removal.
terraform state rm 'module.ubuntu_2604.proxmox_virtual_environment_vm.vm'
terraform import proxmox_virtual_environment_vm.containerlab pve2/108
```

按同样精确表对CT111/VM117执行rm/import；仅解除实际存在的两项download_file state。新资源import后read-back目标endpoint/node/VMID/volume，对比完整plan及定向plan，保存私有摘要。**PBS VM100必须零动作**，包括agent/boot/keyboard/hostpci字段；bpg 0.70.0相关原位更新可能重启PBS，即使reboot=false也不能据此放行。整个计划任何意外create/delete/replace/start/reboot即停止，不以targeted apply掩盖全量风险。本流程没有授权terraform apply。

## 附录F：累计回退容量账本

权威认领规则已集中到validation-and-rollback.md“回退容量认领”。每个目标首次启动前完成累计认领；A/B/C定义见solution-design.md术语，不重复认领同一free。

## 附录G：启动与恢复资源停止线（按实测受控超配）

用户已选择按实测受控超配。常态69GiB来宾配置大于pve0约62.6GiB物理内存，不能承诺所有来宾同时用满。以下8/4/10GiB及PSI数值是本方案初始保守操作阈值，须现场验证其可操作性，不能当作压测证明或防OOM保证；不满足即暂停，不临场降低阈值。

任何新增启动，包括VM108在pve2的验收和Windows在pve0的短暂验证，先记录MemAvailable、已运行负载及ZFS有效ARC上限。启动线为MemAvailable≥待启动guest的配置上限＋8GiB，不能把guest尚未触碰的内存当永远不会使用。ARC配置为0时须读有效c_max，而非当成无占用；前序会话曾读pve0 zfs_arc_max约3.12GiB，执行前必须刷新。

pve2的MemAvailable是在PBS及其他guest已经运行的条件下读取，账本另列PBS的16GiB配置内存、VM108的32GiB配置内存、ARC和宿主余量；不能只核对物理RAM≥32GiB。PBS读写/verify与VM108高负载验收不并发。在pve0上，Windows（VM116）先于其他迁入guest完成验证并关机；全量hash、语音识别/Hindsight压力和开机验收不并行。

维护窗口由值守操作者每5秒读取/proc/meminfo的MemAvailable、/proc/pressure/memory及内核OOM记录，保留带时间戳采样，不安装新软件。PSI不可读或无人持续值守时停止后续启动，不以缺失数据判通过。对两个节点分别应用以下停止线：

| 条件 | 操作 |
|---|---|
| 新增启动前不满足guest配置内存＋8GiB，或上一轮压力事件尚未恢复 | 不启动下一台，不开始新的高负载验收 |
| MemAvailable低于8GiB持续60秒，或memory PSI some avg60≥10%持续60秒 | 暂停后续启动、开放写入及新增备份/校验/压力任务；停止发起新请求，检查增长来源；进行中的备份/校验仅按工具支持方式安全暂停/取消，不杀进程破坏证据 |
| MemAvailable低于4GiB持续15秒，或任何OOM/OOM kill | 当前验收失败，进入保全；先停当前尚未开放业务的验证guest（Windows/VM108若仍在验证，正常关机），再按变更单获准顺序优雅停止非关键写入服务/guest。记录数据截止点，恢复前复验受影响数据 |
| MemAvailable≥10GiB且PSI some avg60<10%连续15分钟，无新OOM | 操作者核实原因已处理后逐台恢复；每次启动仍满足配置内存＋8GiB，不能自动批量重启 |

生产服务停止范围在实施变更单中逐项批准；候选顺序为OpenBao测试VM112/113→FunASR请求及VM115→Hindsight写入及CT118。实施时先确认它们当前没有关键依赖，再批准实际顺序；HA等未列入的业务不擅自停止。本次对运行策略的选择不授权现在关闭任何服务；实施未包含必要停止范围时，不放行全体开写。无可安全停止的负载或压力继续恶化时，停在保全/故障处置状态，不强杀、不擅自降内存或增swap。

单台验证通过后至少稳定观察30分钟再纳入下一台；整体完成后观察24–48h并覆盖真实并发，记录MemAvailable最低值、PSI、OOM和业务响应。期间触发停止线即暂停验收，负载暂时停下不等于容量验收通过。备份存储I/O错误同样先阻止后续启动/开放写入并保全当前数据。
