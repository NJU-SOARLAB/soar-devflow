#!/usr/bin/env python3
"""Render a linked, read-only HTML5 Kanban + dual-timeline Gantt overview for Feishu/Lark docs."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

TEMPLATE = Path(__file__).resolve().parents[1] / "assets/overview_template.html"
DEFAULT_ALLOWED_HOSTS = ("feishu.cn", "larkoffice.com", "larksuite.com")
DEFAULT_STAGE_COLORS = [
    "#3370ff", "#149287", "#e47c3c", "#8057cf", "#2b8a57", "#c75d7e", "#7a8a9e",
]
TASK_ID_RE = re.compile(
    r"^(?:\[([^\]]+)\]|([A-Z][A-Z0-9]*-\d+[A-Z]?)(?=$|[\s:：\-—·]))\s*[:：\-—·]?\s*(.*)$"
)


def parse_task_id_and_title(summary: str) -> tuple[str, str]:
    text = (summary or "").strip()
    match = TASK_ID_RE.match(text)
    if not match:
        return "", text
    task_id = (match.group(1) or match.group(2) or "").strip()
    title = (match.group(3) or "").strip() or text
    return task_id, title


def _meta(config: dict) -> tuple[str, str, str]:
    vis = config.get("document_visualization") or {}
    title = vis.get("title") or f"{config.get('project', 'Project')} 项目推进总览"
    marker = vis.get("marker") or f"{re.sub(r'[^a-z0-9-]+', '-', (config.get('project') or 'project').lower()).strip('-')}-overview-v1"
    eyebrow = vis.get("eyebrow") or f"{(config.get('project') or 'SOAR DEVFLOW').upper().replace('-', ' ')} / DEVELOPMENT"
    return title, marker, eyebrow


def safe_url(value: str | None, allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS) -> str:
    value = value or ""
    match = re.search(r"https://[^\s)\]]+", value)
    value = match.group(0) if match else value
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return "#"
    if not any(parsed.hostname == d or parsed.hostname.endswith("." + d) for d in allowed_hosts):
        return "#"
    return value


def make_data(config: dict, tasks: dict, rows: dict, updates: dict) -> list[dict]:
    allowed_hosts = tuple(config.get("allowed_url_hosts") or DEFAULT_ALLOWED_HOSTS)
    parsed_meta = {guid: parse_task_id_and_title(task["summary"]) for guid, task in tasks.items()}
    id_names = {guid: (pid or title) for guid, (pid, title) in parsed_meta.items()}
    data = []
    for guid, task in tasks.items():
        row = rows[guid]
        fields = {**row, **updates[row["record_id"]]}
        status = (fields.get("执行状态") or ["未开始"])[0]
        if fields.get("任务已完成"):
            status = "已完成"
        identifier, title = parsed_meta[guid]
        names = [
            m.get("name") or (config.get("owner_name") if m.get("id") == config.get("owner_open_id") else "")
            for m in task.get("members", [])
            if m.get("role") == "assignee"
        ]
        document_url = safe_url(fields.get("飞书文档") or row.get("飞书文档"), allowed_hosts)
        task_url = safe_url(task.get("url"), allowed_hosts)
        data.append({
            "id": identifier,
            "title": title,
            "url": document_url if document_url != "#" else task_url,
            "task_url": task_url,
            "completed": bool(fields.get("任务已完成")),
            "status": status,
            "stage": (fields.get("阶段") or row.get("阶段") or ["未分阶段"])[0],
            "category": fields.get("领域分类") or "未分类",
            "priority": (fields.get("优先级") or row.get("优先级") or ["未分级"])[0],
            "start": (fields.get("计划开始") or "")[:10],
            "end": (fields.get("计划截止") or "")[:10],
            "ai_hours": fields.get("AI开发估算小时") if fields.get("AI开发估算小时") is not None else row.get("AI开发估算小时"),
            "ai_range": fields.get("AI工时范围") or row.get("AI工时范围") or "",
            "ai_start": (fields.get("AI计划开始") or row.get("AI计划开始") or "")[:10],
            "ai_end": (fields.get("AI计划交付") or row.get("AI计划交付") or "")[:10],
            "ai_start_time": (fields.get("AI计划开始") or row.get("AI计划开始") or "")[:16].replace("T", " "),
            "ai_end_time": (fields.get("AI计划交付") or row.get("AI计划交付") or "")[:16].replace("T", " "),
            "human_hours": fields.get("人工验收估算小时") if fields.get("人工验收估算小时") is not None else row.get("人工验收估算小时"),
            "wait": fields.get("验收与等待说明") or row.get("验收与等待说明") or "",
            "child": bool(task.get("parent_task_guid")),
            "owner": "、".join(n for n in names if n),
            "deps": [
                id_names.get(d["task_guid"], "清单外前置")
                for d in task.get("dependencies", [])
                if d.get("type") == "prev"
            ],
        })
    return sorted(data, key=lambda x: (x["start"] or "9999", x["id"]))


def _escape_json(value) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render(data: list[dict], config: dict, generated_at: str) -> str:
    title, marker, eyebrow = _meta(config)
    allowed_hosts = tuple(config.get("allowed_url_hosts") or DEFAULT_ALLOWED_HOSTS)
    base_url = config.get("base_url") or ""
    table_id = config.get("table_id") or ""
    base = f"{base_url}?table={table_id}" if base_url and table_id else ""
    kanban_view = config.get("kanban_view_id") or ""
    gantt_view = config.get("gantt_view_id") or ""
    stage_view = config.get("stage_view_id") or kanban_view
    priority_view = config.get("priority_view_id") or kanban_view
    ai_view = config.get("ai_view_id") or gantt_view

    def view_link(vid: str) -> str:
        return safe_url(f"{base}&view={vid}", allowed_hosts) if base and vid else "#"

    links = {
        "board": view_link(kanban_view),
        "stage": view_link(stage_view),
        "priority": view_link(priority_view),
        "gantt": view_link(gantt_view),
        "ai_gantt": view_link(ai_view),
        "tasks": safe_url(config.get("tasklist_url"), allowed_hosts),
    }

    vis = config.get("document_visualization") or {}
    stage_order = list(vis.get("stage_order") or config.get("stages") or [])
    stage_colors = dict(vis.get("stage_colors") or {})
    for idx, stage in enumerate(stage_order):
        stage_colors.setdefault(stage, DEFAULT_STAGE_COLORS[idx % len(DEFAULT_STAGE_COLORS)])

    ui_config = {
        "stageOrder": stage_order,
        "stageColors": stage_colors,
        "timeZone": config.get("timezone") or "Asia/Shanghai",
        "defaultGroup": vis.get("default_group") or ("stage" if stage_order else "priority"),
    }

    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in {
        "@@DATA@@": _escape_json(data),
        "@@LINKS@@": _escape_json(links),
        "@@UI_CONFIG@@": _escape_json(ui_config),
        "@@GENERATED@@": html.escape(generated_at),
        "@@MARKER@@": html.escape(marker),
        "@@TITLE@@": html.escape(title),
        "@@EYEBROW@@": html.escape(eyebrow),
    }.items():
        text = text.replace(key, value)
    return text


def find_widget(document: dict, title: str, marker: str) -> str | None:
    root = ET.fromstring("<root>" + document["content"] + "</root>")
    refs = document.get("reference_map", {}).get("html5-block", {})
    found = []
    for node in root.iter("html5-block"):
        ref = refs.get(node.attrib.get("data-ref", ""), {})
        if (title and title in node.attrib.get("alt", "")) or (marker and marker in ref.get("data", "")):
            found.append(node.attrib["id"])
    if len(found) > 1:
        raise RuntimeError("Multiple task overview blocks; reconcile before updating")
    return found[0] if found else None


def publish(config: dict, tasks: dict, rows: dict, updates: dict, cli, allow_create: bool = False) -> dict:
    title, marker, eyebrow = _meta(config)
    vis = config.get("document_visualization") or {}
    data = make_data(config, tasks, rows, updates)
    source = json.dumps({
        "tasks": data,
        "base_url": config.get("base_url"),
        "table_id": config.get("table_id"),
        "kanban_view_id": config.get("kanban_view_id"),
        "gantt_view_id": config.get("gantt_view_id"),
        "priority_view_id": config.get("priority_view_id"),
        "stage_view_id": config.get("stage_view_id"),
        "ai_view_id": config.get("ai_view_id"),
        "tasklist_url": config.get("tasklist_url"),
        "title": title,
        "eyebrow": eyebrow,
        "marker": marker,
        "default_group": vis.get("default_group"),
        "stages": vis.get("stage_order") or config.get("stages"),
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(source + TEMPLATE.read_bytes() + Path(__file__).read_bytes()).hexdigest()

    state_dir = Path(tempfile.gettempdir()) / f"soar-devflow-views-{os.getuid()}"
    state_dir.mkdir(mode=0o700, exist_ok=True)
    state_file = state_dir / f"{config['document_id']}.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    if state.get("checksum") == checksum and not allow_create:
        return {"status": "unchanged", "tasks": len(data)}

    document = cli(config, ["docs", "+fetch", "--doc", config["document_id"], "--detail", "full"])["document"]
    block_id = find_widget(document, title, marker)
    if not block_id and not allow_create:
        raise RuntimeError("Task overview block was removed; pass --allow-create-overview to insert it")

    offset = float(config.get("timezone_offset_hours", 8))
    tz = timezone(timedelta(hours=offset))
    sign = "+" if offset >= 0 else "-"
    generated = datetime.now(tz).strftime(f"%Y-%m-%d %H:%M UTC{sign}{abs(int(offset))}")

    with tempfile.TemporaryDirectory(prefix="soar-devflow-view-") as directory:
        path = Path(directory) / "overview.html"
        path.write_text(render(data, config, generated), encoding="utf-8")
        args = [
            "docs", "+update",
            "--doc", config["document_id"],
            "--doc-format", "xml",
            "--content", '<html5-block path="@./overview.html"/>',
        ]
        if block_id:
            args += ["--command", "block_replace", "--block-id", block_id]
        else:
            blocks = list(ET.fromstring("<root>" + document["content"] + "</root>"))
            h1_idx = next((idx for idx, x in enumerate(blocks) if x.tag == "h1"), None)
            anchor_id = (
                blocks[h1_idx - 1].attrib["id"]
                if (h1_idx and h1_idx > 0)
                else (blocks[0].attrib["id"] if blocks else "0")
            )
            args += ["--command", "block_insert_after", "--block-id", anchor_id]
        result = cli(config, args, cwd=directory)
    if result.get("result") != "success" or result.get("warnings"):
        raise RuntimeError(f"Visual overview update did not fully succeed: {result}")
    check = cli(config, ["docs", "+fetch", "--doc", config["document_id"], "--detail", "full"])["document"]
    verified_id = find_widget(check, title, marker)
    if not verified_id:
        raise RuntimeError("Updated overview not found on readback")
    state_file.write_text(
        json.dumps({"checksum": checksum, "block_id": verified_id, "generated_at": generated}, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"status": "updated", "tasks": len(data), "block_id": verified_id, "generated_at": generated}


def main() -> None:
    parser = argparse.ArgumentParser(description="Render standalone HTML5 overview from JSON fixture.")
    parser.add_argument("--data", type=Path, required=True, help="JSON file containing {config, tasks, generated_at}")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML file path")
    args = parser.parse_args()
    fixture = json.loads(args.data.read_text(encoding="utf-8"))
    html_text = render(
        fixture["tasks"],
        fixture.get("config", {}),
        fixture.get("generated_at", datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M UTC+8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")
    print(json.dumps({"written": str(args.output), "tasks": len(fixture["tasks"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
