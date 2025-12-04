# ZFS 存储池迁移、扩容与重命名实战笔记

**日期**: 2025-12-04
**背景**: 将 Proxmox PVE (pve0) 上的单盘 1TB NVMe ZFS Pool (`msinvme1tpool`) 无缝迁移到双盘 2TB NVMe Mirror，并重命名为 `mainpool`。

## 1. 核心概念定义

在进行操作前，理解以下 ZFS 概念至关重要：

*   **Mirror (镜像)**: 类似于 RAID1。数据同时写入两块硬盘，提供冗余。读取速度翻倍，写入速度取决于较慢的那块盘。
*   **Resilver (重银/同步)**: 当新盘加入镜像或替换坏盘时，ZFS 将数据从现有盘复制到新盘的过程。NVMe 到 NVMe 的 Resilver 速度通常非常快。
*   **Autoexpand (自动扩容)**: ZFS Pool 的一个属性。当底层设备容量变大时（例如 1TB 换成 2TB），如果开启此属性，Pool 会自动利用新增的空间。
*   **Export / Import (导出/导入)**: 类似于 USB 的 "弹出" 和 "插入"。
    *   **Export**: 停止 Pool，清除内核中的挂载信息，将 Pool 标记为 "未使用"。这是**重命名** Pool 的唯一时机。
    *   **Import**: 扫描硬盘上的 ZFS 标签 (Label)，加载 Pool 并挂载。
*   **Proxmox Storage ID vs ZFS Pool Name**:
    *   **Storage ID** (如 `vmdata`): Proxmox 逻辑层面的名字，Terraform 和 VM 配置文件只认这个。
    *   **Pool Name** (如 `mainpool`): ZFS 文件系统层面的名字。
    *   **关系**: 在 `/etc/pve/storage.cfg` 中定义映射。只要映射改了，底层 Pool 名字怎么变，对上层应用都是透明的。

---

## 2. 完整操作流程

### 第一阶段：迁移数据 (建立临时镜像)
目标：将数据从旧的 1TB 盘 (`old_1t`) 复制到第一块新的 2TB 盘 (`new_2t_1`)。

1.  **Attach (加入新盘)**:
    ```bash
    zpool attach msinvme1tpool <old_1t_id> <new_2t_1_id>
    ```
    *   此时 Pool 变成了 1TB 的 Mirror。
    *   **注意**: 可用空间仍然是 1TB，受限于最小的盘。

2.  **Wait for Resilver (等待同步)**:
    ```bash
    zpool status -v
    ```
    *   等待 `resilvered` 完成。

### 第二阶段：移除旧盘与扩容
目标：下线旧盘，并释放新盘的 2TB 空间。

1.  **Detach (移除旧盘)**:
    ```bash
    zpool detach msinvme1tpool <old_1t_id>
    ```
    *   此时 Pool 变成了单盘 (`new_2t_1`)。

2.  **Expand (扩容)**:
    ```bash
    # 开启自动扩容属性
    zpool set autoexpand=on msinvme1tpool
    
    # 强制触发在线扩容 (针对新盘)
    zpool online -e msinvme1tpool <new_2t_1_id>
    ```
    *   此时 `zpool list` 应显示容量增长到 ~1.8TB。

### 第三阶段：重命名 (The Race Condition)
目标：将 `msinvme1tpool` 改名为 `mainpool`。这是最棘手的一步。

**挑战**: Proxmox 有一个后台服务，会不断扫描并自动导入它认识的 ZFS Pool。
**失败案例**:
```bash
zpool export msinvme1tpool
# ... (几秒钟后) ...
zpool import msinvme1tpool mainpool
# 报错: "no such pool available"
```
**原因**: 在你敲第二行命令之前，Proxmox 已经发现 Pool 被导出了，于是它**自动**帮你把它又导入回去了（还是用旧名字）。

**解决方案 (赢得竞速)**:
将导出和导入命令写在一行，用分号连接，瞬间完成：
```bash
zpool export msinvme1tpool; zpool import msinvme1tpool mainpool
```

### 第四阶段：更新配置与最终镜像
目标：让 Proxmox 识别新名字，并加入第二块 2TB 盘。

1.  **更新 Proxmox 映射**:
    编辑 `/etc/pve/storage.cfg`:
    ```auto
    zfspool: vmdata
            pool mainpool/vmdata  <-- 修改这里
            ...
    ```

2.  **Attach (加入第二块新盘)**:
    ```bash
    zpool attach mainpool <new_2t_1_id> <new_2t_2_id>
    ```
    *   再次等待 Resilver 完成。
    *   最终状态：2TB Mirror，名字叫 `mainpool`。

---

## 3. 故障排查 (Troubleshooting)

### 问题 1: `zpool export` 报错 "Command not found"
*   **原因**: 命令是在 Agent (本地容器) 执行的，而不是 SSH 到 PVE 宿主机执行的。
*   **解决**: 必须 `ssh root@<pve-ip>` 后执行 ZFS 命令。

### 问题 2: `zpool import` 找不到 Pool
*   **现象**: `zpool import` 显示 "no pools available"。
*   **排查**:
    1.  `lsblk`: 确认硬盘物理上还在。
    2.  `zdb -l /dev/nvme0n1p1`: 读取硬盘头部的 ZFS 标签。
        *   如果 `state: ACTIVE` 且 `hostname` 是本机，说明 Pool 被"非正常"锁定了（或者其实已经挂载了）。
*   **解决**:
    *   如果 Pool 确实未挂载但被标记为 Active（本机）：使用 `zpool import -f <guid>` 强制导入。
    *   验证安全性：对比 `hostid` 命令的输出和 `zdb` 输出的 `hostid`。如果一致，说明锁是本机持有的，强制导入是安全的。

### 问题 3: 缺少 NVMe 控制器
*   **现象**: 插了两块盘，`lsblk` 和 `lspci` 只看到一块。
*   **原因**: 硬件/BIOS 问题。
    *   M.2 插槽与 SATA 端口冲突。
    *   PCIe 通道拆分 (Bifurcation) 未开启。
    *   硬盘接触不良。

---

## 4. Terraform 的视角

在整个过程中，Terraform 代码**几乎不需要修改**。

*   **Before**: `storage_pool = "vmdata"` (指向 `msinvme1tpool`)
*   **After**: `storage_pool = "vmdata"` (指向 `mainpool`)

因为 Terraform 操作的是 Proxmox API，它只关心 Storage ID (`vmdata`)。只要我们在 `/etc/pve/storage.cfg` 里把 `vmdata` 指向了正确的底层 Pool，Terraform 就认为一切照旧。

**唯一需要做的是**:
如果 Terraform 状态文件里记录了旧的磁盘路径（包含旧 Pool 名字），可能需要运行 `terraform refresh` 来更新状态，防止 Terraform 认为磁盘路径变更而触发重建。
