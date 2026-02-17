# 学习笔记：MiniMax M2.5 LLM Server 部署经验教训

**日期**: 2026-02-16
**标签**: #LLM #Ansible #ESXi #GPU #Deployment #ik_llama.cpp

首次将 MiniMax M2.5 230B MoE 模型部署到 ESXi VM（双 RTX 3090 Passthrough + CPU-MoE 混合推理）的过程中，遇到了大量文档与实际不符、Ansible 模块兼容性、以及 VM 环境特殊性的问题。以下按类别总结。

---

## 1. 模型与引擎：文档过时是常态

### 1.1 模型仓库命名变更

**问题**：设计文档写的仓库名 `unsloth/MiniMax-2.5-GGUF`，实际已改为 `unsloth/MiniMax-M2.5-GGUF`（多了 `-M`）。

**教训**：HuggingFace 仓库名称可能在模型发布后调整。自动化脚本中不要硬编码仓库名，用变量管理，部署前先 `hf repo info` 验证仓库是否存在。

### 1.2 量化变体与分片数量

**问题**：设计文档基于 Q5_K_M（3 个分片），实际选用 UD-Q5_K_XL（5 个分片，~162GB）。分片数量差异导致模型完整性校验逻辑需要调整。

**教训**：不同量化变体的分片数量不同，且 Unsloth 的动态量化（UD）会将文件放在子目录中（如 `UD-Q5_K_XL/`）。下载后的目录结构需要实际验证，不能假设平铺在 `--local-dir` 根目录。

### 1.3 huggingface CLI 命令重命名

**问题**：`huggingface-cli download` 在 `huggingface_hub >= 0.28` 后改为 `hf download`。旧命令仍可用但新安装的版本默认只有 `hf`。

**教训**：Python 工具的 CLI 入口点可能随版本变化。Ansible task 中应使用 `hf` 而非 `huggingface-cli`，并在 `pip install` 后验证可执行文件路径。

### 1.4 ik_llama.cpp 参数变化

**问题**：
- `--flash-attn`：ik_llama.cpp 已默认启用，不需要（也不应该）手动指定
- `--fit on`：在当前版本中不是有效参数，指定会导致启动失败

**教训**：Fork 项目（ik_llama.cpp vs 标准 llama.cpp）的参数行为可能不同。部署前应查看 `--help` 输出确认参数有效性，而非照搬文档。

---

## 2. Ansible：模块兼容性与权限陷阱

### 2.1 `ansible.builtin.find` 的 `exclude_paths` 参数

**问题**：Ansible 2.17（ansible-core）的 `find` 模块不支持 `exclude_paths` 参数（该参数在更新版本才引入），导致模型分片计数 task 失败。

**教训**：不要假设最新文档中的参数在当前安装的 Ansible 版本可用。使用前 `ansible-doc -t module ansible.builtin.find` 确认支持的参数列表。对于简单的文件计数，`shell: ls ... | wc -l` 更可靠。

### 2.2 `become_user` + `async` 需要 ACL 包

**问题**：`become_user: llm` + `async` 组合下载模型时失败。Ansible 使用 `setfacl` 在临时文件上设置权限，但目标机器没装 `acl` 包。

**报错**：`Failed to set permissions on the temporary files Ansible needs to create when becoming an unprivileged user`

**教训**：任何使用 `become_user` 切换到非 root 用户的 task，目标机器必须安装 `acl` 包。在 `nvidia.yml` 的依赖安装中加入 `acl`。

### 2.3 `become_user` 需要合法 shell 和 HOME

**问题**：系统用户 `llm` 创建时 shell 为 `/usr/sbin/nologin`，导致 `become_user: llm` 时 Ansible 无法执行命令。

**教训**：如果 Ansible task 需要 `become_user` 到某个用户，该用户必须有可用的 shell（`/bin/bash`）。创建系统用户时用 `shell: /bin/bash` 而非默认的 `nologin`。同时需要显式设置 `environment` 中的 `HOME` 和 `PATH`。

### 2.4 NVMe 设备名解析正则

**问题**：`disk.yml` 中用 `regex_replace('[0-9]+$', '')` 提取磁盘名，对 `/dev/sda2` 有效但对 `/dev/nvme0n1p2` 无效（会错误截断 `nvme0n1` 为 `nvme0n`）。

**教训**：磁盘设备名有两种模式：`/dev/sdX2`（SCSI/SATA）和 `/dev/nvme0n1p2`（NVMe）。正则需要用 `p?[0-9]+$` 处理分区号前的可选 `p` 前缀。

---

## 3. ESXi VM 环境特殊性

### 3.1 CPU Governor 在 VM 中无效

**问题**：`cpupower frequency-set -g performance` 在 ESXi VM 中返回 rc=237（失败），因为 guest OS 无法控制 CPU 频率——这由 hypervisor 管理。

**教训**：VM 内的 CPU 调频由 ESXi 控制。`tuning.yml` 中的 cpupower 调用需要 `ignore_errors: true` 或 `failed_when` 处理，并在注释中说明原因。如需调频，应在 ESXi 侧设置 VM 的 CPU Reservation 和 Latency Sensitivity。

### 3.2 Transparent Huge Pages 控制

**问题**：`/sys/kernel/mm/transparent_hugepage/enabled` 在 VM 中可能返回 `[always] madvise never` 或不存在，取决于 VM 的内核配置。

**教训**：THP 控制命令需要先检查文件存在性，并用 `changed_when` 判断实际状态是否改变。同时应通过 `tmpfiles.d` 或内核参数持久化设置。

### 3.3 磁盘自动扩展

**问题**：Terraform 创建的 VM 磁盘为 500GB，但 Ubuntu 安装时的分区可能只用了一部分。需要在 Ansible 中自动扩展分区和文件系统。

**教训**：`growpart` + `resize2fs`（ext4）或 `xfs_growfs`（xfs）组合可以在线扩展。但需要检测当前文件系统类型再选择工具，不能硬编码。

---

## 4. 工作流与自动化

### 4.1 大文件下载的幂等性

**问题**：162GB 模型下载耗时长，网络中断后需要能断点续传。`hf download` 内置 SHA256 校验和断点续传，但 Ansible 的 `async` + `poll` 模式下超时处理需要额外配置。

**教训**：大文件下载 task 应该：
1. 用 `async` 设置足够长的超时（如 14400 秒 = 4 小时）
2. 用 `creates:` 或 `stat` 做幂等性判断，避免重复下载
3. 下载完成后用文件数量或大小做断言，而非仅检查第一个分片

### 4.2 编译环境的 PATH 问题

**问题**：`cmake` 编译 ik_llama.cpp 时找不到 `nvcc`，因为 CUDA 安装在 `/usr/local/cuda/bin/`，不在默认 PATH 中。

**教训**：涉及 CUDA 的编译 task 必须在 `environment` 中显式添加 CUDA 路径：
```yaml
environment:
  PATH: "/usr/local/cuda/bin:{{ ansible_env.PATH }}"
```

### 4.3 NVIDIA 驱动的 apt-mark hold

**问题**：`ubuntu-drivers autoinstall` 安装的驱动包名不一定是 `nvidia-driver-550`，可能是 `nvidia-driver-550-server` 或其他变体。硬编码包名的 `apt-mark hold` 会静默失败。

**教训**：先用 `dpkg -l | grep nvidia-driver` 检测实际安装的包名，再动态 hold。Ansible 中用 `register` + `regex_search` 提取实际包名。

### 4.4 ik_llama.cpp 版本回归导致垃圾输出

**问题**：ik_llama.cpp 最新版（commit `528cadb0`，GLM-5 support）对 MiniMax M2.5 产生完全不可用的垃圾输出（重复 `|Bild|Bild|` 等无意义 token）。所有 API 端点（`/v1/chat/completions`、`/completion`）均受影响，排除了 reasoning-format 和 chat template 的嫌疑。

**根因**：ik_llama.cpp 在 commit `f7923739`（build 4081，"Be more careful with having set the device before using a stream"）之后的提交引入了影响 MiniMax M2.5 MoE 推理的回归。社区（[ubergarm/MiniMax-M2.5-GGUF#11](https://huggingface.co/ubergarm/MiniMax-M2.5-GGUF/discussions/11)）确认了这个问题。

**教训**：
1. Fork 项目的最新版不一定对所有模型架构稳定。MoE 模型（如 MiniMax M2.5）对推理引擎版本特别敏感
2. 部署后必须做推理 smoke test 验证输出质量，不能仅验证服务启动和 health check
3. Ansible role 中应通过版本锁定变量（`llm_server_engine_version`）固定已验证的 commit hash
4. 使用构建版本标记文件（`build/.ik-version`）追踪当前构建对应的源码版本，自动检测版本不匹配并触发重建

**修复**：`llm_server_engine_version: "f7923739"` 固定到已知可用版本。

---

## 5. 代码审查中发现的通用模式

### 5.1 Ansible assert 的 success_msg 防御

**问题**：`success_msg` 中引用的嵌套字典字段（如 `inference_result.json.usage.total_tokens`）在某些场景下可能不存在，导致 assert task 本身报错。

**修复**：使用 `| default({})` 逐层防御：
```yaml
success_msg: >-
  ({{ (inference_result.json.usage | default({})).total_tokens | default('N/A') }} tokens)
```

### 5.2 changed_when 的语义准确性

**问题**：`cpupower frequency-set` 即使在 VM 中成功执行（实际未改变任何状态），`changed_when: rc == 0` 会报告 changed，产生噪音。

**修复**：对于状态声明类命令（设 governor、写 sysctl），如果无法可靠检测状态是否实际改变，使用 `changed_when: false` 比错误的 `changed_when: rc == 0` 更诚实。

---

## 总结：部署 checklist 补充项

基于以上经验，部署前的 checklist 应额外包含：

- [ ] 验证 HuggingFace 仓库名和量化变体是否存在
- [ ] 确认 `hf` CLI 可用（而非 `huggingface-cli`）
- [ ] 目标机器安装 `acl` 包
- [ ] 系统用户 shell 为 `/bin/bash`（如需 `become_user`）
- [ ] NVMe 设备名兼容性测试
- [ ] VM 环境中 cpupower 的容错处理
- [ ] CUDA PATH 在编译 environment 中声明
- [ ] NVIDIA 驱动包名动态检测后 hold
- [ ] ik_llama.cpp 版本固定到已验证 commit（当前：`f7923739`）
- [ ] 部署后推理 smoke test 验证输出质量（不仅仅检查 health）
