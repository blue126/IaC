---
title: Documentation / 文档
description: Repository architecture, guides, troubleshooting, learning notes, planning, agent, reference, and archived documents.
outputs: [HTML, RSS, print, markdown]
cascade:
  github_subdir: docs
  path_base_for_github_subdir:
    from: ".hugo-content/docs/(.*)"
    to: "$1"
---

此 section 直接挂载仓库 `docs/`，不会复制或改写源文档。使用左侧导航或搜索浏览内容。

This section mounts the repository `docs/` directory directly. Use the sidebar or search to browse the source documents.
