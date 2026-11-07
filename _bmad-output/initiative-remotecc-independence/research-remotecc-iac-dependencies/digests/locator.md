# Locator digest

在 aad7d3d 使用 git ls-tree / git grep 搜索顶层及 terraform、ansible、scripts、tests、.github、文档；排除 BMAD 计划，Q6 明确指定的旧记录除外。
Q1: docs/architecture/remotecc-layout.md:8 (RemoteCC) @ aad7d3d；.gitignore:36 (remotecc) @ aad7d3d。
Q2: terraform/remotecc/versions.tf:2 (cloud) @ aad7d3d；ansible/inventory/terraform-remotecc.yml:2 (project_path) @ aad7d3d。
Q3: ansible/playbooks/deploy-remotecc-ops.yml:50 (roles) @ aad7d3d；ansible/playbooks/deploy-oci-hub-terminal.yml:28 (src) @ aad7d3d。
Q4: ansible/roles/remotecc-ops-runtime/defaults/main.yml:15 (remotecc_ops_iac_root) @ aad7d3d。
Q5: scripts/ci/classify-pr.sh:63 (terraform_remotecc) @ aad7d3d；tests/oci-hub/prepare-ingress-terraform.py:10 (root) @ aad7d3d。
Q6: git log 回溯 versions.tf 和 layout，检查 c269b5b、1d0cda8 的实际 diff；单独检查指定 story 的 29cfbc1。
公开 git ls-tree 未包含 remotecc 私有源码；私有来源已由布局文档定位，不能据此称其不存在。
