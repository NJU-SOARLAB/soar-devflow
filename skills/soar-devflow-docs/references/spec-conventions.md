# 规范页（`spec/`）、中英双语对齐与页面登记约定

## Frontmatter 与修订号

每个受 `coverage.json` 管理的页面顶部都写统一 frontmatter：

```yaml
---
translationKey: guide/quickstart
sourceRevision: 1
---
```

当 `languages` 包含多种语言（例如 `["zh", "en"]`）时：
- 修改任一语言正文，须同步更新其他语言，并同时递增 `coverage.json` 的 `translation_revision` 与各语言页的 `sourceRevision`。
- 所有被外部或站内链接引用的标题必须使用显式锚点（例如 `## 概述 {#overview}`），且各语言的显式锚点集合必须**完全一致**。
- `check_docs.py --check` 会机械校验：缺失译文、修订号错位、`@include` 偷懒、显式锚点不一致、断链、缺图与 Vue 未闭合尖括号。

## `coverage.json` 结构示例

```json
{
  "guide/quickstart": {
    "section": "guide",
    "title_zh": "快速上手",
    "title_en": "Quickstart",
    "translation_revision": 1,
    "anchors": ["prerequisites", "steps", "troubleshooting"]
  },
  "spec/config-schema": {
    "section": "spec",
    "group": "contracts",
    "title_zh": "配置契约",
    "title_en": "Config Contract",
    "translation_revision": 1,
    "anchors": ["tasks", "docs"]
  }
}
```

## 站外指针规则

当历史脚本或外部规则仍引用仓库中某份旧路径 Markdown 时，将正文迁入文档站后，原路径可保留最多 3 行指向 `docs/site/...` 的指针（不能包含正文段落），`check_docs.py` 会自动放行。
