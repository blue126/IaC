# Phase 1 Claim Registry

此 registry 是 Phase 1 的闭集，不是自动发现机制。每条记录只允许一个 checked-in Markdown locator 和一个 checked-in YAML 标量 oracle；检测器不得从 runtime、Terraform state、Notion、Vault 或日志补全证据。

## Status contract

| Status | Deterministic condition | Required report data |
|---|---|---|
| `verified` | locator 恰好匹配一次，oracle key 恰好解析为一个标量，规范化后相等 | document locator、oracle path/key、非敏感 expected/observed value、revision/digest |
| `contradiction` | 两端均可唯一解析，但规范化后不相等 | 同上，以及两端值 |
| `indeterminate` | source 缺失、不可解析、locator 缺失或多次匹配、key 缺失/重复/非标量 | failure reason、可用的 path/locator、revision/digest；不得编造值 |

规范化只移除 Markdown code fence/table 的表示层并解析 YAML scalar；不得改写端口数字、版本字符串、大小写或语义等价关系。对于本 registry，原始标量的 exact equality 是唯一的 `verified` 条件。

## Closed claims

| ID | Document and stable locator | Oracle | Expected value | Dependencies |
|---|---|---|---|---|
| `service.netbox.port` | `docs/deployment/netbox-deployment.md` → `Configuration Variables` 表中 `netbox_port` 行 | `ansible/roles/netbox/defaults/main.yml` → `netbox_port` | `8080` | 该文档、该 defaults 文件 |
| `service.netbox.image` | `docs/deployment/netbox-deployment.md` → `Configuration Variables` 表中 `netbox_image` 行 | `ansible/roles/netbox/defaults/main.yml` → `netbox_image` | `netboxcommunity/netbox:v4.1.11` | 该文档、该 defaults 文件 |
| `service.llm-server.engine-version` | `docs/deployment/llm-server-deployment.md` → `defaults/main.yml — 关键变量` code block 中 `llm_server_engine_version` | `ansible/roles/llm-server/defaults/main.yml` → `llm_server_engine_version` | `f7923739` | 该文档、该 defaults 文件 |
| `service.llm-server.webui-port` | `docs/deployment/llm-server-deployment.md` → `defaults/main.yml — 关键变量` code block 中 `llm_server_webui_port` | `ansible/roles/llm-server/defaults/main.yml` → `llm_server_webui_port` | `3000` | 该文档、该 defaults 文件 |

## Required fixtures

The test suite must cover all of the following without contacting external services:

1. The four repository fixtures evaluate to `verified`.
2. A changed Markdown scalar evaluates to `contradiction` and identifies the document locator.
3. A changed YAML scalar evaluates to `contradiction` and identifies the oracle path/key.
4. A missing source, zero-match locator, multi-match locator, missing key, duplicate key, or non-scalar oracle evaluates to `indeterminate` with a specific reason.
5. Every serialised report uses only the values above and the structural fields in the status contract; it contains no secret-bearing field or unredacted input outside the registry.

## Excluded candidates

`docs/deployment/immich-deployment.md` is deliberately excluded: its stated port is not presently represented by a stable `immich_port` scalar in `ansible/roles/immich/defaults/main.yml`. Credentials, tokens, passwords, free-form notes, domains, runtime states, Terraform resource specifications and any value sourced from a secret file are also excluded, even if they appear in documentation.
