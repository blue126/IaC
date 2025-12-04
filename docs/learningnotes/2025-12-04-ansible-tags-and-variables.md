# Ansible Tags 与变量作用域 (Variable Scope)

本文记录了在使用 Ansible Tags (`--tags`) 时遇到的 `undefined variable` 错误及其根本原因。

## 1. 问题现象
当我们尝试只运行 Playbook 的最后一步（打印摘要）时：
```bash
ansible-playbook deploy-netbox.yml --tags summary
```
报错：
```
fatal: [netbox]: FAILED! => {"msg": "The task includes an option with an undefined variable. The error was: 'docker_status' is undefined."}
```

## 2. 核心概念：Tags 的过滤机制
Ansible 的 `--tags` 选项是一个**过滤器**。
*   **默认行为**：运行 Playbook 中的所有任务。
*   **指定 Tag**：**只运行**带有该 Tag 的任务，**跳过**所有其他任务。

## 3. 原因分析
Ansible 的变量（通过 `register` 注册的）是在**运行时**生成的。

1.  **依赖链**：
    *   任务 A (`Check Docker service status`) -> 运行并注册变量 `docker_status`。
    *   任务 B (`Display deployment summary`) -> 使用变量 `{{ docker_status }}` 打印信息。

2.  **错误配置**：
    *   任务 A **没有** `summary` 标签。
    *   任务 B **有** `summary` 标签。

3.  **执行流程**：
    *   用户执行 `--tags summary`。
    *   Ansible **跳过** 任务 A（因为它没有标签）。结果：`docker_status` 变量从未被创建。
    *   Ansible **执行** 任务 B。
    *   任务 B 尝试读取 `docker_status`，发现它不存在 -> **报错 `undefined variable`**。

### 形象比喻：餐厅点单
这就好比去餐厅吃饭：
*   **任务 A (做菜)**：厨师做菜，产出“菜品”（变量）。
*   **任务 B (结账)**：服务员根据“菜品”计算价格并打印账单。
*   **Tag (只点结账)**：你跟服务员说“我只想要账单 (`--tags summary`)”。

**结果**：服务员会告诉你“没法结账”，因为你根本没让厨师“做菜”（任务 A 被跳过了），所以账单上是空的（Undefined Variable）。

**修复**：规定“只要点结账，必须先把菜做了”。即给“做菜”的任务也加上 `summary` 标签。

## 4. 解决方案
为了让任务 B 正常工作，必须确保它依赖的所有数据都已生成。

### 方法一：级联打标签 (本次采用)
将 `summary` 标签也加到所有生成数据的任务（任务 A）上。
```yaml
- name: Check Docker service status
  systemd: ...
  register: docker_status
  tags: [summary]  # <--- 加上这个

- name: Display deployment summary
  debug:
    msg: "{{ docker_status }}"
  tags: [summary]
```
这样运行 `--tags summary` 时，Ansible 会执行 A 和 B，变量就能正常传递了。

### 方法二：使用 `always` 标签
如果某些任务（如收集 Facts 或核心检查）必须每次都运行，可以给它们加上 `always` 标签。
```yaml
- name: Check Docker service status
  tags: [always]
```
带有 `always` 标签的任务即使在指定其他 tag 时也会被执行（除非显式跳过）。

## 5. 关键问答 (Q&A)

**Q: 为什么 `Gathering Facts` 步骤没有报错？**
A: `Gathering Facts` 是 Ansible 的隐式任务。虽然它受 tags 影响，但通常 Ansible 会智能处理。如果显式禁用了 `gather_facts: no` 或者它被跳过，依赖 `ansible_eth0` 等 facts 的任务也会报错。

**Q: 怎么知道哪些任务需要加标签？**
A: 顺藤摸瓜。看报错信息说缺哪个变量（如 `docker_status`），就去找注册那个变量的任务 (`register: docker_status`)，给它也加上标签。
