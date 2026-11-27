#!/usr/bin/env python3
"""Create one Feishu/Lark task + unique task doc + overview mount + task_documents.json atomically.

Workflow:
1. Read remote tasklist & sibling task_documents.json to check duplicates and compute next <PREFIX>-NN ID.
2. Create unique task document and move into Wiki (if space_id configured) so the final URL is known first.
3. Create native task (with exact short description pointing to the final doc URL, section, assignee, dates, deps).
4. Mount `<task task-id="..."/>` + adjacent document link under `待办 -> <section>` on the overview page.
5. Atomically register the task document in sibling `task_documents.json`.

Always preview with `--dry-run` first to verify task ID, section, and duplicate warnings.
"""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
from html import escape
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_sections import checked_update, fetch as fetch_doc, parse as parse_overview, section_settings
from sync_tasks import cli as default_cli, discover_config, paged_tasks, parse_task_id_and_title, read_sections, tz_for


def _extract_token(data: dict, *keys: str) -> str:
    for key in keys:
        cur = data
        for part in key.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, str) and cur:
            return cur
    return ""


def infer_prefix(config: dict, existing_summaries: list[str]) -> str:
    if config.get("task_prefix"):
        return str(config["task_prefix"]).strip().upper()
    for summary in existing_summaries:
        pid, _ = parse_task_id_and_title(summary)
        if "-" in pid:
            return pid.split("-", 1)[0].upper()
    return "TASK"


def next_task_id(prefix: str, existing_ids: list[str]) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)")
    max_num = 0
    width = 2
    for tid in existing_ids:
        match = pattern.match(tid.strip().upper())
        if match:
            digits = match.group(1)
            width = max(width, len(digits))
            max_num = max(max_num, int(digits))
    return f"{prefix}-{max_num + 1:0{width}d}"


def date_to_ms(date_str: str | None, tz: timezone, *, end_of_day: bool = False) -> dict | None:
    if not date_str:
        return None
    text = date_str.strip()
    if len(text) == 10:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(
            hour=23 if end_of_day else 0,
            minute=59 if end_of_day else 0,
            second=0,
            tzinfo=tz,
        )
        return {"timestamp": str(int(dt.timestamp() * 1000)), "is_all_day": True}
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return {"timestamp": str(int(dt.timestamp() * 1000)), "is_all_day": False}


def default_doc_xml(task_id: str, title: str, user_quote: str = "", quote_date: str = "") -> str:
    parts = [
        "<h1>目标与范围</h1>",
        f"<p>任务编号：{escape(task_id)}。{escape(title)}</p>",
    ]
    if user_quote:
        label = f"用户原话（{quote_date}）：" if quote_date else "用户原话："
        parts.extend(["<h1>用户原话</h1>", f"<p>{escape(label)}{escape(user_quote)}</p>"])
    parts.extend([
        "<h1>进度与交付记录</h1>",
        "<p>待实施并记录真实提交与测试证据。</p>",
        "<h1>验收标准与局限</h1>",
        "<p>以实际自动化测试结果与人工验收意见为准；未运行项与局限如实记录。</p>",
    ])
    return "\n".join(parts)


def find_similar_tasks(title: str, existing: list[dict]) -> list[dict]:
    tokens = {tok for tok in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", title.lower()) if len(tok) >= 2}
    if not tokens:
        return []
    matches = []
    for item in existing:
        summary = item.get("summary", "")
        summary_l = summary.lower()
        overlap = [tok for tok in tokens if tok in summary_l]
        if len(overlap) >= max(2, len(tokens) // 2):
            matches.append({"guid": item.get("guid", ""), "summary": summary, "matched_tokens": sorted(overlap)})
    return matches[:5]


def update_task_documents_file(docs_path: Path, guid: str, entry: dict) -> None:
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = docs_path.with_name(docs_path.name + ".lock")
    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        data = json.loads(docs_path.read_text(encoding="utf-8")) if docs_path.is_file() else {}
        if not isinstance(data, dict):
            raise RuntimeError(f"Expected JSON object in {docs_path}")
        if isinstance(data.get("tasks"), dict) and ("version" in data or "date" in data):
            data["tasks"][guid] = {
                "task_id": entry.get("id", ""),
                "id": entry.get("id", ""),
                "title": entry.get("title", ""),
                "document_id": entry.get("document_id", ""),
                "node_token": entry.get("node_token", ""),
                "document_url": entry.get("url", ""),
                "url": entry.get("url", ""),
                "prepared": True,
                "linked": True,
            }
        else:
            data[guid] = entry
        fd, tmp = tempfile.mkstemp(dir=docs_path.parent, prefix=".task-docs-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False, indent=2)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, docs_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def create_task(
    config: dict,
    *,
    config_path: Path | None = None,
    title: str,
    section: str,
    task_id: str | None = None,
    start: str | None = None,
    due: str | None = None,
    assignee: str | None = None,
    parent_guid: str | None = None,
    prev_guids: list[str] | None = None,
    body_xml: str | None = None,
    user_quote: str = "",
    quote_date: str = "",
    existing_doc_id: str | None = None,
    skip_overview_mount: bool = False,
    dry_run: bool = False,
    cli_fn=default_cli,
) -> dict:
    if not title or not title.strip():
        raise ValueError("Task title must not be empty")
    title = title.strip()

    remote_items = paged_tasks(config, "tasklists", {"tasklist_guid": config["tasklist_guid"]}, cli_fn=cli_fn)
    # Also fetch remote sections to validate section name & GUID
    sections_by_guid = read_sections(config, cli_fn=cli_fn)
    sections_by_name = {name: guid for guid, name in sections_by_guid.items()}
    for name, guid in (config.get("sections") or {}).items():
        sections_by_name.setdefault(name, guid)

    if section not in sections_by_name:
        available = ", ".join(sorted(sections_by_name)) or "(none)"
        raise ValueError(f"Unknown section '{section}'. Available: {available}")
    section_guid = sections_by_name[section]

    docs_path = (config_path.parent / "task_documents.json") if config_path else None
    local_docs_raw = json.loads(docs_path.read_text(encoding="utf-8")) if (docs_path and docs_path.is_file()) else {}
    local_docs = (
        local_docs_raw["tasks"]
        if isinstance(local_docs_raw, dict)
        and isinstance(local_docs_raw.get("tasks"), dict)
        and ("version" in local_docs_raw or "date" in local_docs_raw)
        else local_docs_raw
    )

    existing_summaries = [item.get("summary", "") for item in remote_items]
    existing_ids = [parse_task_id_and_title(s)[0] for s in existing_summaries]
    existing_ids.extend(
        str(entry.get("id") or entry.get("task_id") or "")
        for entry in (local_docs.values() if isinstance(local_docs, dict) else [])
        if isinstance(entry, dict)
    )
    existing_ids = [i for i in existing_ids if i]

    prefix = infer_prefix(config, existing_summaries)
    resolved_id = (task_id or next_task_id(prefix, existing_ids)).strip()
    if resolved_id.upper() in {eid.upper() for eid in existing_ids}:
        raise ValueError(f"Task ID '{resolved_id}' already exists in remote tasklist or task_documents.json")

    summary = f"[{resolved_id}] {title}"
    similar = find_similar_tasks(title, remote_items)
    tz = tz_for(config)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    resolved_assignee = assignee if assignee is not None else (config.get("owner_open_id") or "")
    start_obj = date_to_ms(start or today, tz, end_of_day=False)
    due_obj = date_to_ms(due, tz, end_of_day=True) if due else None
    doc_xml = body_xml if body_xml is not None else default_doc_xml(
        resolved_id, title, user_quote=user_quote, quote_date=quote_date or today
    )

    plan = {
        "dry_run": dry_run,
        "id": resolved_id,
        "summary": summary,
        "section": section,
        "section_guid": section_guid,
        "assignee": resolved_assignee or None,
        "start": start or today,
        "due": due,
        "parent_guid": parent_guid,
        "prev_guids": list(prev_guids or []),
        "space_id": config.get("space_id") or "",
        "wiki_parent_token": config.get("document_node_token") or config.get("parent_node_token") or "",
        "overview_document_id": "" if skip_overview_mount else (config.get("document_id") or ""),
        "task_documents_path": str(docs_path) if docs_path else None,
        "possible_duplicates": similar,
    }
    if dry_run:
        return plan

    # 1. Create unique Feishu task document (or reuse an existing doc on retry)
    doc_res = {}
    if existing_doc_id:
        doc_id = existing_doc_id.strip()
        base_host = urlparse(config.get("document_url") or config.get("base_url") or "").netloc
        doc_url = f"https://{base_host}/docx/{doc_id}" if base_host else ""
    else:
        doc_res = cli_fn(config, [
            "docs", "+create",
            "--title", summary,
            "--doc-format", "xml",
            "--content", doc_xml,
        ])
        doc_id = _extract_token(doc_res, "document.document_id", "document_id", "doc_token", "obj_token")
        doc_url = _extract_token(doc_res, "document.url", "url", "doc_url")
    node_token = ""

    # 2. Move into Wiki BEFORE creating native task so native description gets final /wiki/... URL
    space_id = config.get("space_id") or ""
    wiki_parent = config.get("document_node_token") or config.get("parent_node_token") or ""
    if space_id and doc_id:
        move_args = ["wiki", "+move", "--obj-type", "docx", "--obj-token", doc_id, "--target-space-id", space_id]
        if wiki_parent:
            move_args += ["--target-parent-token", wiki_parent]
        moved = cli_fn(config, move_args)
        node_token = _extract_token(moved, "node.node_token", "node_token", "wiki_node.node_token")
        moved_url = _extract_token(moved, "node.url", "url", "wiki_node.url")
        if moved_url:
            doc_url = moved_url
        elif node_token:
            host = urlparse(doc_url or config.get("document_url") or "").netloc
            if host:
                doc_url = f"https://{host}/wiki/{node_token}"

    if not doc_url:
        raise RuntimeError(f"Task document created without URL: {doc_res}")

    # 3. Create native task (or subtask) with exact short description
    task_body: dict = {
        "summary": summary,
        "description": f"详情、进度与验收记录见任务文档：{doc_url}",
        "tasklists": [{"tasklist_guid": config["tasklist_guid"], "section_guid": section_guid}],
    }
    if resolved_assignee:
        task_body["members"] = [{"id": resolved_assignee, "type": "user", "role": "assignee"}]
    if start_obj:
        task_body["start"] = start_obj
    if due_obj:
        task_body["due"] = due_obj

    if parent_guid:
        sub_body = {k: v for k, v in task_body.items() if k != "tasklists"}
        task_res = cli_fn(config, [
            "task", "subtasks", "create",
            "--params", json.dumps({"task_guid": parent_guid}),
            "--data", json.dumps(sub_body, ensure_ascii=False),
        ])
        task_obj = task_res.get("subtask") or task_res.get("task") or task_res
    else:
        task_res = cli_fn(config, [
            "task", "tasks", "create",
            "--data", json.dumps(task_body, ensure_ascii=False),
        ])
        task_obj = task_res.get("task") or task_res

    task_guid = task_obj.get("guid") or _extract_token(task_res, "task.guid", "subtask.guid", "guid")
    task_url = task_obj.get("url") or f"https://applink.feishu.cn/client/todo/detail?guid={task_guid}"

    # Optional native prev dependencies
    if prev_guids:
        deps_payload = {
            "dependencies": [{"type": "prev", "task_guid": dep} for dep in prev_guids]
        }
        cli_fn(config, [
            "task", "tasks", "add_dependencies",
            "--params", json.dumps({"task_guid": task_guid}),
            "--data", json.dumps(deps_payload, ensure_ascii=False),
        ])

    # 4. Mount `<task>` + adjacent document link under `待办 -> <section>` on overview doc
    overview_mounted = False
    if not skip_overview_mount and config.get("document_id") and config.get("document_task_sections", {}).get("enabled", True):
        document = fetch_doc(config, cli_fn)
        headings, entries, _ = parse_overview(document, config)
        if task_guid not in entries:
            target_key = (False, section)
            if target_key not in headings:
                raise RuntimeError(f"Overview doc missing active section heading: {section}")
            _, link_prefix = section_settings(config)
            link_label = resolved_id or summary
            mount_xml = (
                f'<task task-id="{escape(task_guid, quote=True)}"/>\n'
                f'<p>{escape(link_prefix)}<a href="{escape(doc_url, quote=True)}">{escape(link_label)}</a></p>'
            )
            checked_update(config, cli_fn, [
                "--doc-format", "xml",
                "--command", "block_insert_after",
                "--block-id", headings[target_key],
                "--content", mount_xml,
            ])
            # Verify readback
            after_doc = fetch_doc(config, cli_fn)
            _, after_entries, _ = parse_overview(after_doc, config)
            if task_guid not in after_entries:
                raise RuntimeError("Mounted task reference not found on overview readback")
            overview_mounted = True

    # 5. Update sibling task_documents.json atomically
    if docs_path is not None:
        update_task_documents_file(docs_path, task_guid, {
            "id": resolved_id,
            "title": title,
            "document_id": doc_id,
            "node_token": node_token,
            "url": doc_url,
        })

    return {
        "dry_run": False,
        "id": resolved_id,
        "summary": summary,
        "task_guid": task_guid,
        "task_url": task_url,
        "section": section,
        "document_id": doc_id,
        "node_token": node_token,
        "doc_url": doc_url,
        "overview_mounted": overview_mounted,
        "task_documents_path": str(docs_path) if docs_path else None,
        "possible_duplicates": similar,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="Path to tasks.json / registry.json")
    parser.add_argument("--title", required=True, help="Task title without [ID] prefix")
    parser.add_argument("--section", required=True, help="Domain section name in the Feishu tasklist")
    parser.add_argument("--id", dest="task_id", default=None, help="Explicit task ID (auto-incremented if omitted)")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--due", default=None, help="Due date YYYY-MM-DD")
    parser.add_argument("--assignee", default=None, help="Assignee open_id (defaults to config owner_open_id)")
    parser.add_argument("--parent-guid", default=None, help="Optional parent task GUID to create a subtask")
    parser.add_argument("--prev-guid", action="append", default=[], help="Optional prerequisite task GUID (repeatable)")
    parser.add_argument("--body", default=None, help="Optional initial DocxXML content for the task document")
    parser.add_argument("--body-file", type=Path, default=None, help="Optional file with initial DocxXML content")
    parser.add_argument("--existing-doc-id", default=None, help="Reuse an existing Feishu document_id instead of creating a new doc")
    parser.add_argument("--user-quote", default="", help="Optional verbatim user request quote")
    parser.add_argument("--quote-date", default="", help="Date of user quote (YYYY-MM-DD)")
    parser.add_argument("--skip-overview-mount", action="store_true", help="Do not insert task block into overview doc")
    parser.add_argument("--dry-run", action="store_true", help="Preview ID, section, and duplicate warnings without writing")
    args = parser.parse_args()

    config_path = discover_config(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    body_xml = args.body_file.read_text(encoding="utf-8") if args.body_file else args.body
    result = create_task(
        config,
        config_path=config_path,
        title=args.title,
        section=args.section,
        task_id=args.task_id,
        start=args.start,
        due=args.due,
        assignee=args.assignee,
        parent_guid=args.parent_guid,
        prev_guids=args.prev_guid,
        body_xml=body_xml,
        user_quote=args.user_quote,
        quote_date=args.quote_date,
        existing_doc_id=args.existing_doc_id,
        skip_overview_mount=args.skip_overview_mount,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
