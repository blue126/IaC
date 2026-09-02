---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - docs/PLANNING.md
  - docs/README.md
  - README.md
  - AGENTS.md
date: 2026-01-31
author: Will
project_name: IaC
---

# Product Brief: IaC CI/CD 学习项目

<!-- Content will be appended sequentially through collaborative workflow steps -->

## Executive Summary

本项目旨在为现有的 Homelab IaC 仓库引入基于 GitHub Actions 的 CI/CD 流水线。主要驱动力是提升个人技术竞争力，通过实践掌握现代 DevOps 自动化流程。项目将从基础的代码质量检查开始，逐步构建包含 PR 自动化、分支保护和潜在测试集成的完整 CI 体系，最终实现“提交即验证”的自动化闭环。

---

## Core Vision

### Problem Statement
当前 IaC 项目缺乏自动化验证机制，所有代码检查（Lint/Format/Validate）依赖手动执行。这不仅效率低下、容易遗漏，更重要的是，缺失 CI/CD 实践经验已成为求职和职业发展的瓶颈。

### Problem Impact
- **职业竞争力**：缺乏主流 DevOps 技能（GitHub Actions, Automated Pipelines）的实际操作经验。
- **代码质量**：依赖人工自觉进行验证，难以保证主分支代码的稳定性。
- **效率**：手动运行多个检查命令耗时且重复。

### Why Existing Solutions Fall Short
当前仅在文档（AGENTS.md）中定义了验证命令，完全依赖开发者自律。没有强制性的质量门禁，无法模拟真实的企业级开发流程。

### Proposed Solution
构建一个模拟企业级标准的 DevSecOps 流水线：
1. **基础设施**：引入 GitHub Actions 工作流。
2. **工作流变革**：强制实施 Git Flow（Feature Branch -> PR -> Merge），禁止直接推送到主分支。
3. **质量与安全**：集成 Ansible Lint, Terraform Format, 并在后期引入 tfsec 安全扫描。
4. **反馈循环**：建立 "Fail Fast" 机制，通过 PR 状态检查即时反馈代码问题。

### Key Differentiators
- **职业导向**：不仅实现自动化，更注重培养企业所需的 Git Flow 和 DevSecOps 协作习惯。
- **全栈覆盖**：同时覆盖 Terraform（基础设施）和 Ansible（配置管理）。
- **实战演练**：采用 "Break it to Fix it" 方法，通过修复失败的流水线来深入理解 CI 原理。

---

## Target Users

### Primary Users

#### The DevOps Learner (Will)
- **Role**: Junior DevOps Engineer Candidate & Homelab Owner
- **Context**: 拥有一定 IaC 基础，正在寻求职业突破，希望通过 Homelab 项目积累实战经验。
- **Motivations**: 
  - 渴望在面试中自信展示 CI/CD 技能。
  - 希望摆脱繁琐的手动验证流程，体验"自动化"的快感。
- **Pain Points**: 
  - 手动运行 `terraform validate` 和 `ansible-lint` 容易遗漏。
  - 缺乏真实的企业级协作流程经验（PR, Code Review）。
- **Success Vision**: 实现"提交代码后喝杯咖啡，CI 告诉我哪里错了"的自动化体验，并能向面试官清晰阐述整个流水线的设计思路。

### Secondary Users

#### The Virtual Interviewer (Evaluator)
- **Role**: 潜在雇主 / 技术面试官
- **Context**: 正在评估候选人的 GitHub 仓库，寻找代码规范和工程化能力的证据。
- **Key Interactions**: 
  - 查看 GitHub Actions 运行历史，判断项目是否"活着"且受到良好维护。
  - 检查 PR 记录，评估候选人的 Git Flow 规范。
  - 关注代码风格一致性和安全性（SecOps）。

#### The Future Maintainer (Future Will)
- **Role**: 系统维护者（3个月后的你）
- **Pain Points**: 容易遗忘复杂的部署细节，担心手动修改导致环境崩溃。
- **Needs**: 依赖 CI/CD 作为"安全网"（Safety Net），确保任何变更都不会破坏现有功能。

### User Journey

#### The "Feature Development" Cycle
1. **Branching**: 用户为了添加新功能（如新 Ansible Role），创建特性分支 `feature/new-role`。
2. **Development**: 编写代码，可能无意中引入了格式错误或安全隐患。
3. **Automated Feedback**: 推送代码触发 GitHub Actions，CI 失败并报告 Lint 错误。
4. **Learning & Fix**: 用户根据 CI 日志定位问题，理解错误原因（学习点），修复并重新提交。
5. **Quality Gate**: 所有检查通过（全绿），用户创建 Pull Request。
6. **Merge**: 确认无误后合并至主分支，完成闭环。

这个旅程不仅是代码的流动，更是用户**技能成长的闭环**——从犯错到通过自动化反馈学习正确的做法。

---

## Success Metrics

### User Success Metrics (Learning & Confidence)
- **Deployment Confidence**: 确信主分支（Main Branch）上的任何代码都是经过验证的，不会因简单的语法或格式错误导致部署失败。
- **Interview Readiness**: 能够自信地向面试官解释 CI/CD 架构、Git Flow 流程以及如何处理自动化测试中的失败。
- **Skill Mastery**: 能够独立编写、调试和维护 GitHub Actions Workflow 文件，无需完全依赖模板。

### Business Objectives (Career Impact)
- **Resume Competitiveness**: 在 1 个月内将 "Experience with GitHub Actions & CI/CD Pipelines" 作为实战技能添加到简历中。
- **Portfolio Professionalism**: 将 IaC 仓库打造为展示 Engineering Excellence 的作品集，体现规范的提交记录和自动化流程。

### Key Performance Indicators (KPIs)
1. **Zero Direct Commits**: 主分支（Main）的直接提交次数降为 0，强制执行 PR 工作流。
2. **Quality Gate Pass Rate**: 最终实现主分支代码 100% 通过 Ansible Lint 和 Terraform Validation。
3. **Security Posture**: `tfsec` 扫描结果中无 High/Critical 级别的已知漏洞。
4. **Learning Milestone**: 成功落地并运行 3 个独立的工作流任务（Linting, PR Checks, Security Scanning）。

---

## MVP Scope

### Core Features (Phase 1: Foundation & Hygiene)
1. **GitHub Actions Workflow Infrastructure**
   - 创建 `.github/workflows/ci.yml` 配置文件。
   - 配置触发规则：针对 `main` 分支的 Push 事件和所有 Pull Request。
2. **Static Analysis Suite (The "Lint" Job)**
   - **Ansible**: 集成 `ansible-lint`，检查 Playbook 和 Role 的规范性。
   - **Terraform**: 集成 `terraform fmt -check`（格式检查）和 `terraform validate`（语法验证）。
   - **YAML**: 基础 YAML 语法检查。
3. **Process Enforcement**
   - 启用 GitHub Branch Protection Rules，禁止直接推送到 `main` 分支。
   - 强制要求 CI 状态检查通过（Status Checks Passed）方可合并 PR。

### Out of Scope for MVP
- **Security Scanning**: `tfsec` 和 Secret Scanning 将在 Phase 2 引入，MVP 阶段专注于代码功能性验证。
- **Automated Testing**: `molecule` (Ansible) 和 `terratest` (Terraform) 暂时不包括，避免初期复杂度过高。
- **Automated Deployment (CD)**: MVP 仅关注 Continuous Integration (验证)，不涉及自动部署到生产环境。
- **Notification Integrations**: 不配置 Slack/Discord 通知，仅依赖 GitHub 原生邮件提醒。

### MVP Success Criteria
- **Visual Feedback**: 提交代码后，能在 GitHub PR 页面清晰看到 Checks 部分的运行状态（Pass/Fail）。
- **Gate Enforcement**: 故意提交错误代码（如错误缩进）时，PR 必须被阻塞（Block Merge）；修复后自动解锁。
- **Workflow Stability**: 工作流能在 2 分钟内完成运行，无误报。

### Future Vision
- **Phase 2 (Security)**: 引入 `tfsec` 和 `trivy`，实现 DevSecOps 左移。
- **Phase 3 (Dry Run)**: 在 PR 评论中自动发布 `terraform plan` 和 `ansible-playbook --check` 的结果，辅助代码审查。
- **Phase 4 (Testing)**: 引入集成测试，在临时环境中验证部署逻辑。
