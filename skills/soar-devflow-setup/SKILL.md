---
name: soar-devflow-setup
description: 交互式配置 SOAR DevFlow 大项目开发管理与文档工作流：检查环境、确认项目偏好、安装技能、一键创建飞书任务清单/多维表格/看板甘特/汇总页、生成 VitePress 文档站并写入本地配置。
---

# SOAR DevFlow — 交互式安装与初始化

当用户希望在新仓库或已有项目中接入 SOAR DevFlow（或把 GitHub 链接发给 Agent 要求配置整套流程）时，按本流程执行。

## 基本原则

- **先自己查环境，再一次性问清楚**：不要逐题刷屏，也不要替用户瞎猜飞书知识库、群号或任务前缀。
- **创建远端飞书资源前先跑 `--dry-run`**：把计划创建的清单、表格和页面列给用户确认后再正式执行。
- **项目配置存在目标仓库本地**：项目自己的飞书链接、表格 ID 和文档目录都写在目标仓库 `.soar-devflow/` 下；账号登录态由本机 `lark-cli` 管理，不写入 Git。

## 五步初始化剧本

### 第 1 步：环境与仓库预检

在目标项目根目录运行只读检查：
1. 检查目标目录是否为 Git 仓库，以及是否已有 `AGENTS.md` / `CLAUDE.md`、`docs/site/`、`.soar-devflow/` 或 `docs/development_management/`。
2. 检查运行时依赖：
   - `python3 --version`（需 >= 3.10）
   - `node -v` 与 `npm -v`（文档站与截图工具需 >= 18）
   - `which lark-cli && lark-cli --version`（启用飞书过程管理时需要）
   - 若已安装 `lark-cli`，检查可用 profile（不打印任何密钥/Token）。

### 第 2 步：交互式访谈（一次问清关键偏好）

参考 [访谈问题清单](references/interview-questions.md)，根据预检结果只问尚未明确的问题：
1. **启用模块**：完整模式（过程管理 + 文档站）、仅过程管理、还是仅文档站？
2. **项目标识**：项目名称、任务编号前缀（如 `CORE` / `APP` / `BOT`）、工作区路径或配置目录（默认 `.soar-devflow/`）。
3. **若启用飞书过程管理**：
   - 使用的 `lark-cli` profile（若尚未安装/登录，先指导用户执行 `npx @larksuite/cli@latest install` 并完成登录）
   - 是**一键新建**飞书全套资源，还是**接入已有**任务清单/多维表格/汇总页？
   - 领域分组名称（如 `架构与内核`、`核心算法`、`交互与前端`、`工程与发布`）与项目阶段列表
   - 知识空间 ID（`space_id`）及父节点 token（可留空先建在个人云盘），以及可选交付通知群 `chat_id`（`oc_...`）
4. **若启用文档站**：
   - 语言模式：仅中文还是中英双语（自动检查中英文小标题锚点对齐）？
   - 站点标题、部署路径前缀（如 `/docs/` 或 `/<repo>/`）、是否启用声明式截图工具（Playwright）？

### 第 3 步：安装 Skills 到目标工作区或全局

```bash
python3 <soar-devflow-repo>/skills/soar-devflow-setup/scripts/install_skills.py \
  --target <target-repo-or-home> \
  --scope workspace   # 或 global
```
脚本会自动把 `soar-devflow-setup`、`soar-devflow-tasks`、`soar-devflow-docs` 安装到 `.agents/skills/` 并为 `.claude/skills/` 创建相对软链接（或安装到全局 `~/.agents/skills/`），避免不同 Agent 宿主重复维护副本。

### 第 4 步：执行一键脚手架与远端初始化

1. **初始化飞书过程管理**（若启用且选择新建）：
   - 先运行 `--dry-run` 展示计划创建的任务清单、sections、21 列多维表格、5 个看板/甘特视图、汇总页和滚动小修任务：
     ```bash
     python3 <skills_dir>/soar-devflow-setup/scripts/init_feishu_project.py \
       --spec /tmp/soar-devflow-init.json --dry-run
     ```
   - 经用户确认后去掉 `--dry-run` 执行，自动在目标项目写出 `.soar-devflow/tasks.json`、`.soar-devflow/task_documents.json` 与（如提供群号）`.soar-devflow/notifications.json`，并运行首次同步生成 HTML5 互动总览块。
2. **初始化 VitePress 文档站**（若启用）：
   ```bash
   python3 <skills_dir>/soar-devflow-setup/scripts/init_docs_site.py \
     --target <target-repo> \
     --title "<项目名>" \
     --languages zh,en \
     --base /docs/
   ```
   自动生成 `docs/site/`（含中文 MiniSearch、Mermaid、KaTeX、图片灯箱、`coverage.json`、样例教程与说明页）以及 `.soar-devflow/docs.json`。
3. **写入 `AGENTS.md` / `CLAUDE.md` 极简入口**：
   将 `templates/AGENTS.snippet.md` 的 6 行工作流声明追加到目标仓库的 `AGENTS.md`（若已存在则不覆盖既有内容，只追加或更新 SOAR DevFlow 段落）。

### 第 5 步：端到端验收与交付摘要

全部落地后必须真实执行检查并向用户汇报结果：
- 若启用飞书：`python3 <skills_dir>/soar-devflow-tasks/scripts/sync_tasks.py --dry-run`（以及 `notify_delivery.py --dry-run` 若配置了群通知）
- 若启用文档站：`python3 <skills_dir>/soar-devflow-docs/scripts/check_docs.py --check` 与 `cd docs/site && npm install && npm run build`
- 输出清晰清单：本地生成的文件路径、飞书清单/多维表格/汇总页链接、下一步如何创建第一个真实任务或写第一篇教程。
