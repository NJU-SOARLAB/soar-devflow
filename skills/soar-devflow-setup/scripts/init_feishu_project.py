#!/usr/bin/env python3
"""Bootstrap a complete Feishu/Lark project setup for SOAR DevFlow.

Creates:
1. Native tasklist + domain sections
2. Structured Base table (21 standard columns) + 5 views (Status/Stage/Priority Kanban + AI/Delivery Gantt)
3. Overview document with active/completed H1 + category H2 sections (moved into Wiki if space_id given)
4. Rolling minor-fix task (<PREFIX>-00) + its unique task document
5. Local config files (.soar-devflow/tasks.json, task_documents.json, optional notifications.json)

Always run with --dry-run first to inspect planned resources before creating them.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

DEFAULT_SECTIONS = ["架构与内核", "核心业务", "接口与工具", "验证与发布"]
DEFAULT_STAGES = [
    "阶段一·基线与架构",
    "阶段二·核心能力",
    "阶段三·集成与验收",
    "日常·滚动维护",
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def build_base_fields(stages: list[str]) -> tuple[list[dict], list[dict]]:
    """Return (initial_fields, link_fields) matching lark-cli +base-create / +field-create schema."""
    stage_options = [{"name": s} for s in stages]
    initial = [
        {"name": "任务", "type": "text"},
        {"name": "编号", "type": "text"},
        {"name": "Task GUID", "type": "text"},
        {"name": "任务已完成", "type": "checkbox"},
        {
            "name": "执行状态",
            "type": "select",
            "multiple": False,
            "default_value": ["未开始"],
            "options": [
                {"name": "未开始", "hue": "Gray", "lightness": "Lighter"},
                {"name": "进行中", "hue": "Blue", "lightness": "Light"},
                {"name": "待人工验收", "hue": "Orange", "lightness": "Light"},
                {"name": "阻塞", "hue": "Red", "lightness": "Light"},
                {"name": "已完成", "hue": "Green", "lightness": "Light"},
            ],
        },
        {
            "name": "阶段",
            "type": "select",
            "multiple": False,
            "options": stage_options,
        },
        {"name": "领域分类", "type": "text"},
        {
            "name": "优先级",
            "type": "select",
            "multiple": False,
            "options": [
                {"name": "P0·架构前置", "hue": "Purple", "lightness": "Light"},
                {"name": "P1·近期目标", "hue": "Orange", "lightness": "Light"},
                {"name": "P2·后续迭代", "hue": "Blue", "lightness": "Light"},
                {"name": "P3·外部依赖", "hue": "Gray", "lightness": "Lighter"},
            ],
        },
        {
            "name": "层级",
            "type": "select",
            "multiple": False,
            "options": [
                {"name": "主任务", "hue": "Blue", "lightness": "Lighter"},
                {"name": "子任务", "hue": "Turquoise", "lightness": "Lighter"},
            ],
        },
        {"name": "负责人", "type": "user", "multiple": False},
        {"name": "计划开始", "type": "datetime", "style": {"format": "yyyy-MM-dd"}},
        {"name": "计划截止", "type": "datetime", "style": {"format": "yyyy-MM-dd"}},
        {"name": "AI开发估算小时", "type": "number", "style": {"type": "plain", "precision": 1}},
        {"name": "AI工时范围", "type": "text"},
        {"name": "AI计划开始", "type": "datetime", "style": {"format": "yyyy-MM-dd HH:mm"}},
        {"name": "AI计划交付", "type": "datetime", "style": {"format": "yyyy-MM-dd HH:mm"}},
        {"name": "人工验收估算小时", "type": "number", "style": {"type": "plain", "precision": 1}},
        {"name": "验收与等待说明", "type": "text"},
        {"name": "交付与验收", "type": "text"},
        {"name": "日期依据", "type": "text"},
        {"name": "证据链接", "type": "text"},
        {"name": "代码库文档", "type": "text"},
        {"name": "任务链接", "type": "text", "style": {"type": "url"}},
        {"name": "飞书文档", "type": "text", "style": {"type": "url"}},
        {"name": "最近同步", "type": "datetime", "style": {"format": "yyyy-MM-dd HH:mm"}},
    ]
    link_fields = [
        {"name": "前置任务", "type": "link", "link_table": "__SELF__"},
        {"name": "父任务", "type": "link", "link_table": "__SELF__"},
    ]
    return initial, link_fields


def build_overview_xml(project: str, sections: list[str], minor_guid: str, minor_title: str, minor_url: str, minor_section: str) -> str:
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    lines = [
        f"<p>本页由 SOAR DevFlow 维护：上方为同源交互总览（看板 + 双口径甘特图），下方按领域挂载原生任务块与唯一主文档链接。</p>",
        "<h1>待办</h1>",
    ]
    for sec in sections:
        lines.append(f"<h2>{esc(sec)}</h2>")
        if sec == minor_section and minor_guid:
            lines.append(f'<task task-id="{esc(minor_guid)}"/>')
            lines.append(f'<p>任务文档：<a href="{esc(minor_url)}">{esc(minor_title)}</a></p>')
    lines.append("<h1>已完成</h1>")
    for sec in sections:
        lines.append(f"<h2>{esc(sec)}</h2>")
    return "\n".join(lines)


def run_cli(profile: str | None, args: list[str], cwd: str | None = None) -> dict:
    cmd = ["lark-cli", *args, "--as", "user"]
    if profile:
        cmd.extend(["--profile", profile])
    with tempfile.TemporaryDirectory() as scratch:
        proc = subprocess.run(
            cmd,
            cwd=cwd or scratch,
            capture_output=True,
            text=True,
            timeout=90,
            env={
                **os.environ,
                "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
                "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
            },
        )
    if proc.returncode:
        raise RuntimeError(f"lark-cli {args[:2]} failed: {proc.stderr or proc.stdout}")
    payload = json.loads(proc.stdout)
    if payload.get("ok") is not True:
        raise RuntimeError(f"Unexpected lark-cli response for {args[:2]}: {payload}")
    return payload["data"]


def _extract_token(data: dict, *keys: str) -> str:
    for key in keys:
        cur = data
        for part in key.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part)
            else:
                cur = None
                break
        if isinstance(cur, str) and cur:
            return cur
    return ""


def load_spec(args: argparse.Namespace) -> dict:
    spec = json.loads(args.spec.read_text(encoding="utf-8")) if args.spec else {}
    if args.project:
        spec["project"] = args.project
    if args.prefix:
        spec["task_prefix"] = args.prefix
    if args.profile is not None:
        spec["profile"] = args.profile
    if args.space_id is not None:
        spec["space_id"] = args.space_id
    if args.parent_node_token is not None:
        spec["parent_node_token"] = args.parent_node_token
    if args.chat_id is not None:
        spec["chat_id"] = args.chat_id
    if args.sections:
        spec["sections"] = [s.strip() for s in args.sections.split(",") if s.strip()]
    if args.stages:
        spec["stages"] = [s.strip() for s in args.stages.split(",") if s.strip()]
    if args.owner_open_id is not None:
        spec["owner_open_id"] = args.owner_open_id
    if args.owner_name is not None:
        spec["owner_name"] = args.owner_name
    if args.timezone:
        spec["timezone"] = args.timezone
    if args.output_dir:
        spec["output_dir"] = str(args.output_dir)

    if not spec.get("project"):
        raise ValueError("Project name is required (--project or spec.project)")
    spec.setdefault("task_prefix", re.sub(r"[^A-Z0-9]", "", spec["project"].upper())[:4] or "PRJ")
    spec.setdefault("sections", list(DEFAULT_SECTIONS))
    spec.setdefault("stages", list(DEFAULT_STAGES))
    spec.setdefault("timezone", "Asia/Shanghai")
    spec.setdefault("timezone_offset_hours", 8)
    spec.setdefault("output_dir", ".soar-devflow")
    return spec


def plan_summary(spec: dict) -> dict:
    initial_fields, link_fields = build_base_fields(spec["stages"])
    slug = slugify(spec["project"])
    prefix = spec["task_prefix"]
    return {
        "dry_run": True,
        "project": spec["project"],
        "task_prefix": prefix,
        "profile": spec.get("profile") or "(default)",
        "planned_remote_resources": {
            "tasklist_name": f"{spec['project']} 研发任务",
            "sections": spec["sections"],
            "base_name": f"{spec['project']} 研发推进表",
            "table_name": "研发任务总表",
            "field_count": len(initial_fields) + len(link_fields),
            "views": [
                {"name": "全部任务", "type": "grid"},
                {"name": "按执行状态看板", "type": "kanban", "group": "执行状态"},
                {"name": "按项目阶段看板", "type": "kanban", "group": "阶段"},
                {"name": "按优先级看板", "type": "kanban", "group": "优先级"},
                {"name": "交付与验收甘特", "type": "gantt", "timebar": ["计划开始", "计划截止"]},
                {"name": "AI 实施窗口甘特", "type": "gantt", "timebar": ["AI计划开始", "AI计划交付"]},
            ],
            "overview_doc_title": f"{spec['project']} 任务汇总与推进总览",
            "minor_fix_task": f"[{prefix}-00] 小修小补与日常维护滚动记录",
            "wiki_destination": {
                "space_id": spec.get("space_id") or "(personal drive)",
                "parent_node_token": spec.get("parent_node_token") or "(space root)",
            },
        },
        "planned_local_files": [
            f"{spec['output_dir']}/tasks.json",
            f"{spec['output_dir']}/task_documents.json",
            *([f"{spec['output_dir']}/notifications.json"] if spec.get("chat_id") else []),
        ],
        "overview_marker": f"{slug}-overview-v1",
    }


def bootstrap(spec: dict, cli_fn=run_cli, sync_fn=None) -> dict:
    profile = spec.get("profile") or None
    project = spec["project"]
    prefix = spec["task_prefix"]
    sections_list = list(spec["sections"])
    stages_list = list(spec["stages"])
    slug = slugify(project)
    out_dir = Path(spec["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create native tasklist
    tl_data = cli_fn(profile, ["task", "+tasklist-create", "--name", f"{project} 研发任务"])
    tasklist_guid = _extract_token(tl_data, "tasklist.guid", "guid", "tasklist_guid")
    tasklist_url = _extract_token(tl_data, "tasklist.url", "url") or f"https://applink.feishu.cn/client/todo/task_list?guid={tasklist_guid}"

    # 2. Create sections
    sections_map = {}
    for name in sections_list:
        sec_data = cli_fn(profile, [
            "task", "sections", "create",
            "--data", json.dumps({"name": name, "resource_type": "tasklist", "resource_id": tasklist_guid}, ensure_ascii=False),
        ])
        sections_map[name] = _extract_token(sec_data, "section.guid", "guid")

    # 3. Create Base + primary table schema
    initial_fields, link_fields = build_base_fields(stages_list)
    base_data = cli_fn(profile, [
        "base", "+base-create",
        "--name", f"{project} 研发推进表",
        "--table-name", "研发任务总表",
        "--time-zone", spec["timezone"],
        "--fields", json.dumps(initial_fields, ensure_ascii=False),
    ])
    base_token = _extract_token(base_data, "base_token", "app_token", "app.app_token")
    base_url = _extract_token(base_data, "url", "app.url")
    table_id = _extract_token(base_data, "table_id", "default_table_id", "app.default_table_id")

    # Add self-referencing link fields (前置任务, 父任务)
    resolved_links = [{**f, "link_table": table_id} for f in link_fields]
    cli_fn(profile, [
        "base", "+field-create",
        "--base-token", base_token,
        "--table-id", table_id,
        "--json", json.dumps(resolved_links, ensure_ascii=False),
    ])

    # 4. Create Kanban & Gantt views
    def create_view(name: str, vtype: str, group_field: str | None = None, timebar: tuple[str, str] | None = None) -> str:
        res = cli_fn(profile, [
            "base", "+view-create",
            "--base-token", base_token,
            "--table-id", table_id,
            "--json", json.dumps({"name": name, "type": vtype}, ensure_ascii=False),
        ])
        vid = _extract_token(res, "view_id", "view.view_id") or name
        if group_field:
            cli_fn(profile, [
                "base", "+view-set-group",
                "--base-token", base_token,
                "--table-id", table_id,
                "--view-id", vid,
                "--json", json.dumps({"group_config": [{"field": group_field, "desc": False}]}, ensure_ascii=False),
            ])
        if timebar:
            cli_fn(profile, [
                "base", "+view-set-timebar",
                "--base-token", base_token,
                "--table-id", table_id,
                "--view-id", vid,
                "--json", json.dumps({"start_time": timebar[0], "end_time": timebar[1], "title": "任务"}, ensure_ascii=False),
            ])
        return vid

    kanban_view_id = create_view("按执行状态看板", "kanban", group_field="执行状态")
    stage_view_id = create_view("按项目阶段看板", "kanban", group_field="阶段")
    priority_view_id = create_view("按优先级看板", "kanban", group_field="优先级")
    gantt_view_id = create_view("交付与验收甘特", "gantt", timebar=("计划开始", "计划截止"))
    ai_view_id = create_view("AI 实施窗口甘特", "gantt", timebar=("AI计划开始", "AI计划交付"))

    # 5. Create rolling minor-fix doc + native task
    minor_id = f"{prefix}-00"
    minor_title = f"[{minor_id}] 小修小补与日常维护滚动记录"
    minor_doc_body = (
        "<p>承接本项目日常一般性 bug 修复、小范围文案或参数微调；每次小修追加一条「日期 / 问题 / 修改提交 / 验证结果」。</p>"
        "<h1>滚动记录</h1>"
        "<p>（按时间倒序追加）</p>"
    )
    minor_doc = cli_fn(profile, [
        "docs", "+create",
        "--title", minor_title,
        "--doc-format", "xml",
        "--content", minor_doc_body,
    ])
    minor_doc_id = _extract_token(minor_doc, "document_id", "doc_token", "obj_token")
    minor_doc_url = _extract_token(minor_doc, "url", "doc_url")

    minor_section_name = sections_list[-1]
    minor_section_guid = sections_map[minor_section_name]
    minor_task_data = cli_fn(profile, [
        "task", "tasks", "create",
        "--data", json.dumps({
            "summary": minor_title,
            "description": f"详情、进度与验收记录见任务文档：{minor_doc_url}",
            "tasklists": [{"tasklist_guid": tasklist_guid, "section_guid": minor_section_guid}],
        }, ensure_ascii=False),
    ])
    minor_guid = _extract_token(minor_task_data, "task.guid", "guid")
    minor_task_url = _extract_token(minor_task_data, "task.url", "url") or f"https://applink.feishu.cn/client/todo/detail?guid={minor_guid}"

    # 6. Create overview document skeleton
    overview_xml = build_overview_xml(project, sections_list, minor_guid, minor_title, minor_doc_url, minor_section_name)
    overview_doc = cli_fn(profile, [
        "docs", "+create",
        "--title", f"{project} 任务汇总与推进总览",
        "--doc-format", "xml",
        "--content", overview_xml,
    ])
    overview_doc_id = _extract_token(overview_doc, "document_id", "doc_token", "obj_token")
    overview_doc_url = _extract_token(overview_doc, "url", "doc_url")
    overview_node_token = ""
    minor_node_token = ""

    # Optionally move overview doc, Base, and minor-fix doc into Wiki space
    space_id = spec.get("space_id") or ""
    parent_node_token = spec.get("parent_node_token") or ""
    if space_id:
        move_args = ["wiki", "+move", "--obj-type", "docx", "--obj-token", overview_doc_id, "--target-space-id", space_id]
        if parent_node_token:
            move_args += ["--target-parent-token", parent_node_token]
        moved_ov = cli_fn(profile, move_args)
        overview_node_token = _extract_token(moved_ov, "node_token", "node.node_token")
        overview_doc_url = _extract_token(moved_ov, "url", "node.url") or overview_doc_url

        if base_token:
            b_move = ["wiki", "+move", "--obj-type", "bitable", "--obj-token", base_token, "--target-space-id", space_id]
            if overview_node_token or parent_node_token:
                b_move += ["--target-parent-token", overview_node_token or parent_node_token]
            cli_fn(profile, b_move)

        m_move = ["wiki", "+move", "--obj-type", "docx", "--obj-token", minor_doc_id, "--target-space-id", space_id]
        if overview_node_token or parent_node_token:
            m_move += ["--target-parent-token", overview_node_token or parent_node_token]
        moved_m = cli_fn(profile, m_move)
        minor_node_token = _extract_token(moved_m, "node_token", "node.node_token")
        minor_doc_url = _extract_token(moved_m, "url", "node.url") or minor_doc_url

    # 7. Write local configuration files
    today = datetime.now(timezone(timedelta(hours=float(spec["timezone_offset_hours"])))).strftime("%Y-%m-%d")
    tasks_config = {
        "version": 1,
        "project": project,
        "task_prefix": prefix,
        "created_date": today,
        "profile": profile or "",
        "timezone": spec["timezone"],
        "timezone_offset_hours": spec["timezone_offset_hours"],
        "owner_open_id": spec.get("owner_open_id") or "",
        "owner_name": spec.get("owner_name") or "",
        "space_id": space_id,
        "parent_node_token": parent_node_token,
        "document_id": overview_doc_id,
        "document_node_token": overview_node_token,
        "document_url": overview_doc_url,
        "minor_fixes_task_id": minor_id,
        "minor_fixes_guid": minor_guid,
        "minor_fixes_url": minor_doc_url,
        "tasklist_guid": tasklist_guid,
        "tasklist_url": tasklist_url,
        "base_token": base_token,
        "base_url": base_url,
        "table_id": table_id,
        "kanban_view_id": kanban_view_id,
        "stage_view_id": stage_view_id,
        "priority_view_id": priority_view_id,
        "gantt_view_id": gantt_view_id,
        "ai_view_id": ai_view_id,
        "sections": sections_map,
        "stages": stages_list,
        "document_visualization": {
            "enabled": True,
            "kind": "html5-linked-overview",
            "title": f"{project} 项目推进总览",
            "eyebrow": f"{project.upper()} / DEVELOPMENT",
            "marker": f"{slug}-overview-v1",
            "default_group": "stage",
            "stage_order": stages_list,
        },
        "document_task_sections": {
            "enabled": True,
            "active_heading": "待办",
            "completed_heading": "已完成",
            "link_prefix": "任务文档：",
            "completed_default_folded": True,
        },
        "tasks": [
            {
                "id": minor_id,
                "title": "小修小补与日常维护滚动记录",
                "category": minor_section_name,
                "priority": "P2·后续迭代",
                "stage": stages_list[-1],
                "ai_hours": 0.5,
                "ai_range": "滚动累计",
                "human_hours": 0.5,
                "accept": "滚动留档",
                "guid": minor_guid,
                "url": minor_task_url,
                "doc_url": minor_doc_url,
                "doc_id": minor_doc_id,
                "node_token": minor_node_token,
            }
        ],
    }
    tasks_path = out_dir / "tasks.json"
    tasks_path.write_text(json.dumps(tasks_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    task_docs = {
        minor_guid: {
            "id": minor_id,
            "doc_id": minor_doc_id,
            "node_token": minor_node_token,
            "url": minor_doc_url,
        }
    }
    docs_map_path = out_dir / "task_documents.json"
    docs_map_path.write_text(json.dumps(task_docs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    notify_path = None
    if spec.get("chat_id"):
        notify_cfg = {
            "profile": profile or "",
            "chat_id": spec["chat_id"],
            "tasklist_guid": tasklist_guid,
            "state_path": f"~/.local/state/soar-devflow/{slug}-notify.json",
            "mode": "agent",
            "send_as": "bot",
        }
        notify_path = out_dir / "notifications.json"
        notify_path.write_text(json.dumps(notify_cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sync_result = None
    if sync_fn is not None:
        sync_result = sync_fn(tasks_config)

    return {
        "dry_run": False,
        "project": project,
        "tasks_config": str(tasks_path),
        "task_documents": str(docs_map_path),
        "notifications_config": str(notify_path) if notify_path else None,
        "tasklist_guid": tasklist_guid,
        "base_token": base_token,
        "table_id": table_id,
        "overview_document_id": overview_doc_id,
        "overview_url": overview_doc_url,
        "minor_fix_guid": minor_guid,
        "sync_result": sync_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, help="JSON spec file with project settings")
    parser.add_argument("--project", help="Project name")
    parser.add_argument("--prefix", help="Task ID prefix, e.g. PRJ")
    parser.add_argument("--profile", default=None, help="lark-cli profile name")
    parser.add_argument("--space-id", default=None, help="Optional Feishu Wiki space ID")
    parser.add_argument("--parent-node-token", default=None, help="Optional Wiki parent node token")
    parser.add_argument("--chat-id", default=None, help="Optional Feishu group chat_id (oc_...) for delivery notifications")
    parser.add_argument("--sections", help="Comma-separated domain section names")
    parser.add_argument("--stages", help="Comma-separated project stage names")
    parser.add_argument("--owner-open-id", default=None)
    parser.add_argument("--owner-name", default=None)
    parser.add_argument("--timezone", default=None)
    parser.add_argument("--output-dir", type=Path, default=None, help="Local config output dir (default .soar-devflow)")
    parser.add_argument("--dry-run", action="store_true", help="Print planned remote & local resources without mutating")
    parser.add_argument("--skip-initial-sync", action="store_true", help="Skip running sync_tasks after creation")
    args = parser.parse_args()

    spec = load_spec(args)
    if args.dry_run:
        print(json.dumps(plan_summary(spec), ensure_ascii=False, indent=2))
        return

    sync_fn = None
    if not args.skip_initial_sync:
        tasks_scripts = str(Path(__file__).resolve().parents[2] / "soar-devflow-tasks/scripts")
        if tasks_scripts not in sys.path:
            sys.path.insert(0, tasks_scripts)
        from sync_tasks import sync as run_sync
        sync_fn = lambda cfg: run_sync(cfg, dry_run=False, allow_create_overview=True, seed_process_fields=True)

    result = bootstrap(spec, cli_fn=run_cli, sync_fn=sync_fn)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
