# Learning Notes Index

This directory contains learning notes and troubleshooting logs for the Infrastructure as Code (IaC) project.

## Notes List

### 2025-11-30

- **[LXC 与 VM 网络桥接拓扑学习笔记](./2025-11-30-lxc-vm-network-bridge.md)**
  - **Tags**: Linux Bridge, LXC, VM Networking, Netbox, Cable Modeling
  - **Summary**: Explains how VMs and LXC containers attach to vmbr1 using veth/tap, validates bridge mode vs port mapping, and documents NetBox modeling with interfaces and cables.

- **[Ansible 部署验证模式与 Immich 模块化重构](./2025-11-30-ansible-deployment-verification.md)**
  - **Tags**: Ansible, Verification, Health Checks, Immich, Service Patterns
  - **Summary**: Patterns for post-deployment verification (ports, services, HTTP, DB) and refactoring Immich into a reusable role structure.


- **[Terraform Proxmox Provider Crash & Versioning](./2025-11-30-terraform-proxmox-provider-crash.md)**
  - **Tags**: Terraform, Proxmox, Provider, Versioning, Troubleshooting
  - **Summary**: Troubleshooting a crash with the Terraform Proxmox provider, focusing on version compatibility issues and resolution strategies.

- **[Terraform Code Refactoring & State Alignment](./2025-11-30-terraform-refactoring-best-practices.md)**
  - **Tags**: Terraform, Refactoring, Modules, Import, State Management
  - **Summary**: Best practices for modularizing Terraform code, splitting resources, and aligning state with existing infrastructure using import and drift detection.

### 2025-11-29

- **[Netbox 4.1.11 部署：版本匹配与配置调试](2025-11-29-netbox-deployment-version-troubleshooting.md)**
  - **Tags**: Netbox, Docker, netbox-docker, Version Compatibility, Troubleshooting
  - **Summary**: Detailed guide on deploying Netbox 4.1.11 using Ansible and Docker Compose, covering version compatibility issues (v3.0.2 vs release), database connection fixes, and async timeout handling.

- **[Ansible 部署 Netbox 与 Docker Compose 最佳实践](2025-11-29-ansible-netbox-docker.md)**
  - **Tags**: Ansible, Docker, Netbox, Docker Compose, DevOps
  - **Summary**: Best practices for orchestrating Netbox deployment with Ansible, including directory structure, role design, and troubleshooting common Docker Compose issues.

### 2025-11-28

- **[Terraform 模块化重构、Netbox 部署与 Cloud-Init 深度调试](2025-11-28-terraform-modules-netbox-debugging.md)**
  - **Tags**: Terraform, Proxmox, Cloud-Init, Ansible, Netbox, Debugging
  - **Summary**: Deep dive into refactoring Terraform code into modules, debugging Cloud-Init configurations for Proxmox VMs, and initial Netbox integration steps.

- **[Terraform Learning Notes - Proxmox Deployment](2025-11-28-terraform-proxmox.md)**
  - **Tags**: Infrastructure as Code (IaC) with Terraform & Proxmox
  - **Summary**: Initial learning notes on setting up Terraform with the Proxmox provider, defining resources, and basic VM provisioning.
