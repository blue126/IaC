# Q5

CI classifier 将共享模块变化关联到四个 root，并将 tests/oci-hub 的变化关联到 RemoteCC root。 `scripts/ci/classify-pr.sh:50-70 (terraform_remotecc) @ aad7d3d`

Terraform validator 限定 root 白名单，执行 fmt、init -backend=false、validate；未在这个脚本执行 plan/apply。 `scripts/ci/validate-terraform.sh:18-36 (selected_roots) @ aad7d3d`

Ansible validator 使用 CI 专用 inventory/config，撤销 Vault 环境变量，再 lint 与逐 playbook syntax-check；脚本会安装依赖，本轮没有执行它。 `scripts/ci/validate-ansible.sh:27-80 (ANSIBLE_CONFIG) @ aad7d3d`

OCI ingress 测试夹具实际复制 terraform/oci/oci-hub.tf，而不是 RemoteCC root；测试目录名不能直接当作资源归属。 `tests/oci-hub/prepare-ingress-terraform.py:7-11 (root) @ aad7d3d`

HAPI README 明确该目录不在 PR 校验内，需手工运行；列出的历史测试通过数不是本轮测试结果。 `tests/hapi-workspace/README.md:35-37 (Kasm网页客户端) @ aad7d3d`

上述为已检查范围；不是整个仓库的反向依赖穷举。全部按 load-bearing 进入验证。
