# 本地项目配置 Schema 参考

SOAR DevFlow 把全部项目私有信息保存在目标业务仓库本地，推荐集中放在 `.soar-devflow/` 目录（同时兼容 `docs/development_management/` 旧目录结构）。所有文件均不含凭据，可安全提交进业务仓库 Git。

## 1. `.soar-devflow/tasks.json`

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `project` | 是 | 项目标识名（用于总览标题与眉标） |
| `task_prefix` | 是 | 任务编号前缀，如 `PRJ`、`CORE`、`APP` |
| `profile` | 否 | `lark-cli --profile` 名称；省略时使用 `lark-cli` 默认 profile |
| `timezone` / `timezone_offset_hours` | 否 | 默认 `Asia/Shanghai` / `8` |
| `tasklist_guid` / `tasklist_url` | 是 | 飞书原生任务清单 GUID 与跳转链接 |
| `base_token` / `base_url` / `table_id` | 是 | 飞书多维表格坐标 |
| `grid_view_id` / `kanban_view_id` / `stage_view_id` / `priority_view_id` / `gantt_view_id` / `ai_view_id` | 否 | Base 各视图 ID，用于在 HTML5 总览页生成直达按钮 |
| `space_id` / `parent_node_token` | 否 | 飞书知识库归档位置 |
| `document_id` / `document_node_token` / `document_url` | 否 | 项目任务汇总页文档坐标 |
| `minor_fixes_task_id` / `minor_fixes_guid` / `minor_fixes_url` | 否 | 滚动小修唯一任务与文档坐标 |
| `sections` | 否 | `{ "领域名": "section_guid" }` 映射缓存 |
| `stages` | 否 | 项目阶段有序数组，用于看板排序与配色 |
| `document_visualization` | 否 | `{ enabled, title, eyebrow, marker, default_group, stage_order, stage_colors }` |
| `document_task_sections` | 否 | `{ enabled, active_heading, completed_heading, link_prefix, completed_default_folded }` |
| `allow_multiple_assignees` | 否 | 默认 `false`（发现多人负责人时 fail-closed 报错提醒） |

## 2. `.soar-devflow/notifications.json`

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `mode` | 是 | 必须固定为 `"agent"`（不支持后台定时轮询） |
| `profile` | 否 | `lark-cli` profile |
| `chat_id` | 是 | 目标飞书/Lark 群 ID（`oc_...`） |
| `tasklist_guid` | 是 | 授权校验用的项目任务清单 GUID |
| `state_path` | 否 | 本机去重状态文件（默认 `~/.local/state/soar-devflow/<prefix>-notify.json`，绝不进 Git） |
| `send_as` | 否 | 默认 `"bot"` |
| `allowed_doc_hosts` | 否 | 允许的任务文档域名白名单，默认包含 `feishu.cn`、`larkoffice.com`、`larksuite.com` |
| `footer_note` | 否 | 群消息底部提示语 |

## 3. `.soar-devflow/docs.json`

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `site_dir` | 是 | VitePress 源目录（相对项目根，如 `docs/site` 或 `site`） |
| `languages` | 是 | 语言列表，如 `["zh"]` 或 `["zh", "en"]` |
| `root_language` | 否 | 若默认语言直接放在 `site_dir/` 根目录而非 `site_dir/zh/`，填 `"zh"`（与 VitePress `locales.root` 一致） |
| `single_source` | 否 | `{ enabled, allowed_prefixes, allowed_files, check_readme_duplication }` |
| `quality` | 否 | `{ min_chars: { zh: 2500, en: 4000 }, min_stub_chars: 250, require_visual_in: ["guide", "reference"] }` |
| `coverage_file` | 否 | 页面清单路径（相对 `site_dir`，默认 `coverage.json`） |
| `help_map_file` | 否 | 可选 UI 帮助锚点映射路径（如 `help-map.json`） |
| `release_catalog_file` | 否 | 可选发布说明数据源路径（如 `release-catalog.json`） |
| `shots` | 否 | 声明式截图配置 `{ manifest_dir, output_dir, upstream_url, static_dir, routes, theme_storage_key }` |
