# Helper Scripts

Utility scripts for automation and maintenance tasks.

## Purpose

This directory contains shell scripts, Python scripts, or other utilities that support the IaC workflow but are not part of Ansible or Terraform configurations.

## Directory Structure

```
scripts/
├── jenkins/               # Jenkins webhook and pipeline testing scripts
│   ├── test-webhook-payload.sh       # Simulate NetBox webhook POST to Jenkins
│   ├── test-webhook-router.sh        # Automated test suite for Webhook Router
│   ├── create-webhook-router-job.groovy # Job DSL for Webhook-Router job
│   └── test-netbox-webhook.sh        # Python webhook listener for debugging
├── netbox/                # NetBox API integration scripts
│   ├── create-netbox-custom-fields.py # Create Custom Fields via API (Story 1.1)
│   └── fetch-planned-vms.py           # Fetch planned VMs from NetBox
├── pbs/                   # Proxmox Backup Server utilities
│   └── discover-pci-devices.sh        # PCI device discovery for GPU passthrough
├── gateway-backup/        # Gateway backups using the native PBS client
│   ├── gateway-backup.sh             # Settings, business definitions and sequential backup
│   ├── gateway-backup-ctl.sh         # SSH forced-command entry: start/status/cancel a detached batch
│   └── ha-gateway-backup.sh          # Home Assistant shell_command helper; token via SSH stdin
├── get-secrets.sh         # Extract Ansible Vault secrets to Terraform *.auto.tfvars
├── refresh-terraform-state.sh # Pull remote Terraform state for Ansible inventory
└── sync-to-notion.py      # Sync documentation to Notion (optional)
```

## Core Scripts

### Secrets Management
- **`get-secrets.sh`**: Extracts `vault_*` variables from Ansible Vault and writes them to Terraform `*.auto.tfvars` files. Ansible Vault is the single source of truth for all secrets.

### Terraform State
- **`refresh-terraform-state.sh`**: Pulls remote Terraform state from HCP Terraform Cloud for use in Ansible dynamic inventory.

### Cross-Service Integration
- **`sync-to-notion.py`**: Syncs Terraform state to Notion database for resource documentation. This script bridges multiple services (reads Terraform state, called by Jenkins Pipeline, writes to Notion API) and therefore lives at root level rather than in a single subdirectory.

## Subdirectories

### jenkins/
Scripts for testing and debugging Jenkins webhook integration (Epic 1: NetBox 数据建模与 Webhook 基础设施).

### netbox/
NetBox API client scripts for Custom Fields management, VM configuration fetching, and automation testing.

### pbs/
Proxmox Backup Server utilities for hardware discovery and configuration.

### gateway-backup/

`gateway-backup/gateway-backup.sh backup all` 按业务顺序备份网关的六项常规 Docker 业务，某项失败后继续其余业务，保留 `backup <business>` 单项入口；qnetd 在独立维护窗口执行。公共参数和七项业务定义集中在这一个脚本内，PBS Token 由控制器通过 `PBS_PASSWORD` 注入。备份明确使用 `--crypt-mode none`，仅保留 PBS 登录认证和 HTTPS，无需加密密钥。当前脚本尚未包含 OpenWrt 系统备份。

调用、恢复和系统备份范围见 [网关备份指南](../docs/guides/gateway-backup.md)。控制器经 SSH 强制命令调用 `gateway-backup-ctl.sh start|status|cancel <run_id>`，HA 侧由 `ha-gateway-backup.sh` 把 token 经标准输入传入。离线验证：`bash tests/gateway-backup/gateway-backup-test.sh`；控制器测试需要 Linux，命令见指南。2026-10-09 的版本已部署，小智真实备份通过，用户反馈已完成一次全业务备份；失败后继续、metadata 变更检测和控制器尚未部署。恢复演练暂缓，后续人工停服前先通知用户。
