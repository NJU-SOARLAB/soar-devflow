#!/usr/bin/env python3
"""Mirror a project's native Feishu/Lark tasklist into Base, HTML5 overview, and doc sections.

Never completes/reopens native tasks, never deletes Base rows, and fails closed on
ambiguous remote state (pagination stalls, duplicate GUIDs, unlisted dependencies).
"""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

DEFAULT_CONFIG_CANDIDATES = (
    ".soar-devflow/tasks.json",
    "docs/development_management/registry.json",
)
DEFAULT_DOC_HOSTS = ("feishu.cn", "larkoffice.com", "larksuite.com")
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


def extract_doc_url(text: str | None, allowed_hosts: tuple[str, ...] = DEFAULT_DOC_HOSTS) -> str:
    if not text:
        return ""
    for match in re.finditer(r"https://[^\s)\]>\"']+", text):
        url = match.group(0).rstrip(".,;。；")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme == "https"
            and host
            and any(host == d or host.endswith("." + d) for d in allowed_hosts)
            and parsed.path.startswith(("/wiki/", "/docx/", "/docs/"))
        ):
            return url
    return ""


def load_task_documents(config_path: Path | None) -> dict[str, dict]:
    if config_path is None:
        return {}
    docs_path = config_path.parent / "task_documents.json"
    if not docs_path.is_file():
        return {}
    try:
        data = json.loads(docs_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("tasks"), dict) and ("version" in data or "date" in data):
        return data["tasks"]
    return data


def resolve_doc_url(
    task: dict,
    *,
    seed: dict | None = None,
    task_docs: dict[str, dict] | None = None,
    allowed_hosts: tuple[str, ...] = DEFAULT_DOC_HOSTS,
) -> str:
    guid = task.get("guid", "")
    doc_entry = (task_docs or {}).get(guid) or {}
    for candidate in (
        doc_entry.get("url"),
        doc_entry.get("document_url"),
        (seed or {}).get("doc_url"),
        extract_doc_url(task.get("description"), allowed_hosts),
    ):
        url = extract_doc_url(candidate, allowed_hosts) if candidate else ""
        if url:
            return url
    return ""


def lock_path_for(config: dict, config_path: Path) -> Path:
    lock_seed = config.get("tasklist_guid") or str(config_path.resolve())
    key = hashlib.sha256(str(lock_seed).encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"soar-devflow-sync-{os.getuid()}-{key}.lock"


def discover_config(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve()
    cwd = Path.cwd().resolve()
    for base in (cwd, *cwd.parents):
        for rel in DEFAULT_CONFIG_CANDIDATES:
            candidate = base / rel
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(
        "No SOAR DevFlow task config found. Pass --config PATH or create .soar-devflow/tasks.json."
    )


def tz_for(config: dict) -> timezone:
    offset = config.get("timezone_offset_hours", 8)
    return timezone(timedelta(hours=float(offset)))


def cli(config: dict, args: list[str], cwd: str | None = None) -> dict:
    cmd = ["lark-cli", *args, "--as", "user"]
    if config.get("profile"):
        cmd.extend(["--profile", config["profile"]])
    with tempfile.TemporaryDirectory() as scratch:
        result = subprocess.run(
            cmd,
            cwd=cwd or scratch,
            capture_output=True,
            text=True,
            timeout=int(config.get("cli_timeout_seconds", 90)),
            env={
                **os.environ,
                "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
                "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
            },
        )
    if result.returncode:
        raise RuntimeError(f"lark-cli {args[0:2]} failed: {result.stderr or result.stdout}")
    response = json.loads(result.stdout)
    if response.get("format") == "ndjson" and "records_count" in response:
        return response
    if response.get("ok") is not True:
        raise RuntimeError(f"Unexpected response for {args[0:2]}: {response}")
    data = response["data"]
    if data.get("record_not_found") or data.get("ignored_fields"):
        raise RuntimeError(f"Partial Base write: {data}")
    return data


def paged_tasks(config: dict, resource: str, params: dict, cli_fn=None) -> list[dict]:
    run_cli = cli_fn or cli
    items, seen = [], set()
    while True:
        verb = "tasks" if resource == "tasklists" else "list"
        data = run_cli(config, ["task", resource, verb, "--params", json.dumps({**params, "page_size": 100})])
        items.extend(data.get("items", []))
        if not data.get("has_more"):
            return items
        token = data.get("page_token")
        if not token or token in seen:
            raise RuntimeError("Task pagination stalled; refusing an incomplete sync")
        seen.add(token)
        params = {**params, "page_token": token}


def read_sections(config: dict, cli_fn=None) -> dict[str, str]:
    run_cli = cli_fn or cli
    sections, seen = {}, set()
    params = {"resource_type": "tasklist", "resource_id": config["tasklist_guid"], "page_size": 100}
    while True:
        data = run_cli(config, ["task", "sections", "list", "--params", json.dumps(params)])
        for section in data.get("items", []):
            sections[section["guid"]] = section.get("name") or "未分类"
        if not data.get("has_more"):
            return sections
        token = data.get("page_token")
        if not token or token in seen:
            raise RuntimeError("Section pagination stalled; refusing an incomplete sync")
        seen.add(token)
        params["page_token"] = token


def task_category(task: dict, tasks: dict, tasklist_guid: str, sections: dict, visited=None) -> str:
    visited = set() if visited is None else visited
    if task["guid"] in visited:
        raise RuntimeError("Parent cycle while resolving task category")
    visited.add(task["guid"])
    for membership in task.get("tasklists", []):
        if membership["tasklist_guid"] != tasklist_guid:
            continue
        section_guid = membership.get("section_guid")
        if not section_guid:
            return "未分类"
        if section_guid not in sections:
            raise RuntimeError(f"Unknown project section: {section_guid}; retry a fresh snapshot")
        return sections[section_guid]
    parent = tasks.get(task.get("parent_task_guid"))
    return task_category(parent, tasks, tasklist_guid, sections, visited) if parent else "未分类"


def read_tasks(config: dict) -> dict[str, dict]:
    pending = paged_tasks(config, "tasklists", {"tasklist_guid": config["tasklist_guid"]})
    tasks = {}
    while pending:
        summary = pending.pop(0)
        guid = summary["guid"]
        if guid in tasks:
            continue
        task = cli(config, ["task", "tasks", "get", "--params", json.dumps({"task_guid": guid})])["task"]
        tasks[guid] = task
        if task.get("subtask_count", 0):
            pending.extend(paged_tasks(config, "subtasks", {"task_guid": guid}))
    sections = read_sections(config)
    for task in tasks.values():
        task["_category"] = task_category(task, tasks, config["tasklist_guid"], sections)
    return tasks


DEFAULT_BASE_READ_FIELDS = [
    "Task GUID", "任务", "任务已完成", "执行状态", "阶段", "领域分类",
    "计划开始", "计划截止", "负责人", "前置任务", "父任务", "优先级",
    "AI开发估算小时", "AI工时范围", "AI计划开始", "AI计划交付",
    "人工验收估算小时", "验收与等待说明", "飞书文档",
]


def read_rows(config: dict, directory: str) -> list[dict]:
    rows, offset = [], 0
    fields = list(config.get("base_read_fields") or DEFAULT_BASE_READ_FIELDS)
    while True:
        filename = f"records-{offset}.ndjson"
        args = [
            "base", "+record-list",
            "--base-token", config["base_token"],
            "--table-id", config["table_id"],
            "--format", "ndjson",
            "--output", filename,
            "--offset", str(offset),
            "--limit", "2000",
        ]
        for field in fields:
            args.extend(["--field-id", field])
        manifest = cli(config, args, cwd=directory)
        page = [json.loads(line) for line in (Path(directory) / filename).read_text(encoding="utf-8").splitlines() if line]
        if len(page) != manifest["records_count"]:
            raise RuntimeError("Base export count mismatch")
        rows.extend(page)
        if not manifest.get("has_more"):
            return rows
        next_offset = manifest.get("next_offset", offset + len(page))
        if next_offset <= offset:
            raise RuntimeError("Base pagination stalled")
        offset = next_offset


def index_rows(rows: list[dict]) -> dict[str, dict]:
    result = {}
    for row in rows:
        guid = row.get("Task GUID")
        if not guid:
            continue
        if guid in result:
            raise RuntimeError(f"Duplicate Task GUID in Base: {guid}; reconcile manually")
        result[guid] = row
    return result


def date_value(value: dict | None, tz: timezone) -> str | None:
    if not value or not value.get("timestamp") or value["timestamp"] == "0":
        return None
    date = datetime.fromtimestamp(int(value["timestamp"]) / 1000, tz)
    if value.get("is_all_day"):
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)
    return date.isoformat()


def mirror_fields(
    task: dict,
    current: dict,
    record_ids: dict[str, str],
    now: str,
    *,
    config: dict | None = None,
    seed_by_guid: dict | None = None,
    task_docs: dict[str, dict] | None = None,
) -> dict:
    cfg = config or {}
    tz = tz_for(cfg)
    allowed_hosts = tuple(cfg.get("allowed_url_hosts") or DEFAULT_DOC_HOSTS)
    done = int(task.get("completed_at") or 0) > 0
    assignees = [
        {"id": m["id"]}
        for m in task.get("members", [])
        if m.get("role") == "assignee" and m.get("type") == "user"
    ]
    if len(assignees) > 1 and not cfg.get("allow_multiple_assignees"):
        raise RuntimeError(f"Multiple task assignees: {task['guid']}; enable allow_multiple_assignees or update schema")
    fields = {
        "任务": task["summary"],
        "Task GUID": task["guid"],
        "任务已完成": done,
        "领域分类": task.get("_category", "未分类"),
        "任务链接": task["url"],
        "计划开始": date_value(task.get("start"), tz),
        "计划截止": date_value(task.get("due"), tz),
        "最近同步": now,
        "负责人": assignees,
    }
    if done:
        fields["执行状态"] = ["已完成"]
    elif current.get("执行状态") == ["已完成"]:
        fields["执行状态"] = ["未开始"]
    deps = [d["task_guid"] for d in task.get("dependencies", []) if d["type"] == "prev"]
    outside = set(deps) - record_ids.keys()
    if outside:
        raise RuntimeError(f"Dependencies outside project list: {outside}; add them to the list first")
    fields["前置任务"] = [{"id": record_ids[d]} for d in deps]
    parent = task.get("parent_task_guid")
    if parent and parent not in record_ids:
        raise RuntimeError(f"Parent task outside project list: {parent}")
    fields["父任务"] = [{"id": record_ids[parent]}] if parent else []
    fields["层级"] = ["子任务" if parent else "主任务"]

    seed = (seed_by_guid or {}).get(task["guid"])
    if not current.get("飞书文档"):
        doc_url = resolve_doc_url(task, seed=seed, task_docs=task_docs, allowed_hosts=allowed_hosts)
        if doc_url:
            fields["飞书文档"] = doc_url

    if seed:
        tz_suffix = now[-6:] if len(now) >= 6 and now[-6] in ("+", "-") else "+08:00"
        if not current.get("优先级") and seed.get("priority"):
            fields["优先级"] = [seed["priority"]]
        if not current.get("阶段") and seed.get("stage"):
            fields["阶段"] = [seed["stage"]]
        if current.get("AI开发估算小时") is None and seed.get("ai_hours") is not None:
            fields["AI开发估算小时"] = seed["ai_hours"]
        if not current.get("AI工时范围") and seed.get("ai_range"):
            fields["AI工时范围"] = seed["ai_range"]
        if current.get("人工验收估算小时") is None and seed.get("human_hours") is not None:
            fields["人工验收估算小时"] = seed["human_hours"]
        if not current.get("验收与等待说明") and seed.get("accept"):
            fields["验收与等待说明"] = seed["accept"]
        if not current.get("AI计划开始") and seed.get("start"):
            fields["AI计划开始"] = f"{seed['start']}T09:00:00{tz_suffix}"
        if not current.get("AI计划交付") and seed.get("due"):
            fields["AI计划交付"] = f"{seed['due']}T18:00:00{tz_suffix}"
    return fields


def sync(
    config: dict,
    dry_run: bool = False,
    allow_create_overview: bool = False,
    seed_process_fields: bool = False,
    task_docs: dict[str, dict] | None = None,
) -> dict:
    tasks = read_tasks(config)
    with tempfile.TemporaryDirectory(prefix="soar-devflow-sync-") as directory:
        rows = index_rows(read_rows(config, directory))
    missing = [task for guid, task in tasks.items() if guid not in rows]
    orphaned = [guid for guid in rows if guid not in tasks]
    seed_by_guid = {t["guid"]: t for t in config.get("tasks", []) if t.get("guid")}
    allowed_hosts = tuple(config.get("allowed_url_hosts") or DEFAULT_DOC_HOSTS)

    tz = tz_for(config)
    now = datetime.now(tz).isoformat(timespec="seconds")
    tz_suffix = now[-6:] if len(now) >= 6 and now[-6] in ("+", "-") else "+08:00"

    # Creation is separate from update to respect Base's asynchronous visibility.
    if missing:
        if not dry_run:
            for start in range(0, len(missing), 200):
                payload = []
                for task in missing[start:start + 200]:
                    parsed_id, _ = parse_task_id_and_title(task["summary"])
                    seed = seed_by_guid.get(task["guid"], {})
                    doc_url = resolve_doc_url(task, seed=seed, task_docs=task_docs, allowed_hosts=allowed_hosts)
                    row_payload = {
                        "任务": task["summary"],
                        "Task GUID": task["guid"],
                        "领域分类": task.get("_category", "未分类"),
                        "任务链接": task["url"],
                        "编号": parsed_id or "待编号",
                        "执行状态": ["未开始"],
                        "交付与验收": seed.get("acceptance") or task.get("description", ""),
                        "日期依据": "从原生任务发现；开发与验收估算在 Base 维护",
                    }
                    if seed.get("priority"):
                        row_payload["优先级"] = [seed["priority"]]
                    if seed.get("stage"):
                        row_payload["阶段"] = [seed["stage"]]
                    if seed.get("ai_hours") is not None:
                        row_payload["AI开发估算小时"] = seed["ai_hours"]
                    if seed.get("ai_range"):
                        row_payload["AI工时范围"] = seed["ai_range"]
                    if seed.get("human_hours") is not None:
                        row_payload["人工验收估算小时"] = seed["human_hours"]
                    if seed.get("accept"):
                        row_payload["验收与等待说明"] = seed["accept"]
                    if doc_url:
                        row_payload["飞书文档"] = doc_url
                    if seed.get("start"):
                        row_payload["AI计划开始"] = f"{seed['start']}T09:00:00{tz_suffix}"
                    if seed.get("due"):
                        row_payload["AI计划交付"] = f"{seed['due']}T18:00:00{tz_suffix}"
                    payload.append(row_payload)
                cli(config, [
                    "base", "+record-batch-create",
                    "--base-token", config["base_token"],
                    "--table-id", config["table_id"],
                    "--json", json.dumps({"create_records": payload}, ensure_ascii=False),
                ])
        return {
            "tasks": len(tasks),
            "new_rows": len(missing),
            "next_run_updates_links": True,
            "orphaned_rows_preserved": orphaned,
            "dry_run": dry_run,
        }

    record_ids = {guid: row["record_id"] for guid, row in rows.items()}
    updates = {
        record_ids[guid]: mirror_fields(
            task,
            rows[guid],
            record_ids,
            now,
            config=config,
            seed_by_guid=seed_by_guid if seed_process_fields else None,
            task_docs=task_docs,
        )
        for guid, task in tasks.items()
    }
    if not dry_run:
        entries = list(updates.items())
        for start in range(0, len(entries), 200):
            cli(config, [
                "base", "+record-batch-update",
                "--base-token", config["base_token"],
                "--table-id", config["table_id"],
                "--json", json.dumps({"update_records": dict(entries[start:start + 200])}, ensure_ascii=False),
            ])
    report = {
        "tasks": len(tasks),
        "updated_rows": len(updates),
        "dry_run": dry_run,
        "orphaned_rows_preserved": orphaned,
        "synced_at": now,
    }
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    if not dry_run and config.get("document_visualization", {}).get("enabled"):
        from render_overview import publish
        report["visualization"] = publish(
            config, tasks, rows, updates, cli, allow_create=allow_create_overview
        )
    if not dry_run and config.get("document_task_sections", {}).get("enabled"):
        from reconcile_sections import reconcile
        doc_urls = {}
        for guid, task in tasks.items():
            url = resolve_doc_url(
                task,
                seed=seed_by_guid.get(guid),
                task_docs=task_docs,
                allowed_hosts=allowed_hosts,
            ) or extract_doc_url(rows.get(guid, {}).get("飞书文档"), allowed_hosts)
            if url:
                doc_urls[guid] = url
        report["task_sections"] = reconcile(config, tasks, cli, doc_urls=doc_urls)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="Path to tasks.json / registry.json")
    parser.add_argument("--dry-run", action="store_true", help="Read remote state and report without writing")
    parser.add_argument("--allow-create-overview", action="store_true", help="Insert HTML5 overview block if absent")
    parser.add_argument("--seed-process-fields", action="store_true", help="Backfill empty process fields from config tasks[]")
    args = parser.parse_args()

    config_path = discover_config(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    task_docs = load_task_documents(config_path)
    lock_path = lock_path_for(config, config_path)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = sync(
            config,
            dry_run=args.dry_run,
            allow_create_overview=args.allow_create_overview,
            seed_process_fields=args.seed_process_fields,
            task_docs=task_docs,
        )
        print(json.dumps(result, ensure_ascii=False))
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
