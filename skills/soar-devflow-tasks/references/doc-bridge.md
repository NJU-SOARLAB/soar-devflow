# 飞书过程管理与文档站的同源桥接

写一份源稿，按读者和用途呈现，消灭两份正文不同步的长期腐烂。

## 三类内容的分工

1. **过程与讨论 → 协同平台（飞书/Lark）**
   每任务唯一主文档集中需求、原话、进度、反馈、版本与验收。日常小修记入滚动小修文档，不零碎建单。
2. **完整技术阅读 → 仓库在线文档站（VitePress）**
   教程（`guide/`）、原理与设计说明（`reference/`）、接口与协议规范（`spec/`）只以仓库 `docs/site/` 为唯一维护源（见技能 `soar-devflow-docs`）。任务编号和过程流水不塞进技术正文；任务主文档链接到对应技术页面或锚点。
3. **精选技术资料 → 同源导入飞书在线文档**
   架构方案、关键算法、核心协议或团队评审必读文档，应允许在飞书直接阅读而不只给外链——但**必须由仓库同一 Markdown 源稿导出/导入**，禁止让 Agent 再手写第二份同义稿。

## Markdown 同源导入飞书

1. **默认路径（整份导入 docx）**：
   ```bash
   lark-cli drive +import --file ./docs/site/reference/architecture.md --type docx --name "系统架构设计" --as user --profile <profile>
   ```
   如需归档到知识库，再执行 `lark-cli wiki +move --obj-type docx --obj-token <token> --target-space-id <space_id> --target-parent-token <parent_node>`。
2. **含 Mermaid 图表需要原生白板时**：
   使用配套脚本将纯净 Markdown 子集转为 Lark DocxXML（Mermaid 代码块自动转为 `<whiteboard type="mermaid">`）：
   ```bash
   python3 <skills_dir>/soar-devflow-tasks/scripts/export_feishu.py ./source.md --output /tmp/doc.xml
   lark-cli docs +create --doc-format xml --content @/tmp/doc.xml --as user --profile <profile>
   ```
3. **更新已有精选文档**：
   导入命令会创建新文档；更新既有在线文档时应复用原资源、定点合并差异，保护远端人工修改与评论区，不重复创建同名副本。在文档顶部注明仓库源路径、源提交哈希与在线文档站入口。
