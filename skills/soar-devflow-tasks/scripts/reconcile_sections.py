"""Keep native Feishu/Lark task references in active/completed sections without copying tasks."""
from html import escape
import json
import re
import tempfile
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


DEFAULT_DOC_HOSTS = ("feishu.cn", "larkoffice.com", "larksuite.com")
TASK_ID_RE = re.compile(
    r"^(?:\[([^\]]+)\]|([A-Z][A-Z0-9]*-\d+[A-Z]?)(?=$|[\s:：\-—·]))\s*[:：\-—·]?\s*(.*)$"
)


def _extract_doc_url(text: str | None, allowed_hosts: tuple[str, ...] = DEFAULT_DOC_HOSTS) -> str:
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


def _short_task_label(summary: str) -> str:
    text = (summary or "").strip()
    match = TASK_ID_RE.match(text)
    if match:
        tid = (match.group(1) or match.group(2) or "").strip()
        if tid:
            return tid
    return text or "任务"


def _sort_key_for_task(task: dict) -> tuple:
    summary = (task.get("summary") or "").strip()
    label = _short_task_label(summary)
    m = re.match(r"^([A-Z]+)-(\d+)([A-Z]?)$", label.upper())
    if m:
        return (0, m.group(1), int(m.group(2)), m.group(3), summary)
    return (1, "", 0, "", summary)


def section_settings(config: dict | None = None) -> tuple[dict[str, bool], str]:
    sec = (config or {}).get("document_task_sections") or {}
    active = sec.get("active_heading") or "待办"
    completed = sec.get("completed_heading") or "已完成"
    link_prefix = sec.get("link_prefix") or "任务文档："
    return {active: False, completed: True}, link_prefix


def parse(document: dict, config: dict | None = None):
    groups_map, link_prefix = section_settings(config)
    blocks = list(ET.fromstring("<root>" + document["content"] + "</root>"))
    headings, entries, groups = {}, {}, {}
    group = category = None
    for index, block in enumerate(blocks):
        label = "".join(block.itertext()).strip()
        if block.tag == "h1":
            group = groups_map.get(label)
            category = None
            if label in groups_map:
                if group in groups:
                    raise ValueError("Duplicate task group: " + label)
                groups[group] = block.attrib["id"]
        elif block.tag == "p":
            # Tolerate Feishu occasionally nesting an h1 group heading as a child of the preceding paragraph.
            for child in list(block):
                if child.tag == "h1":
                    child_label = "".join(child.itertext()).strip()
                    if child_label in groups_map:
                        g_val = groups_map[child_label]
                        if g_val in groups:
                            raise ValueError("Duplicate task group: " + child_label)
                        group = g_val
                        category = None
                        groups[g_val] = child.attrib.get("id", block.attrib.get("id", ""))
        elif block.tag == "h2" and group is not None:
            category = label
            key = (group, category)
            if key in headings:
                raise ValueError("Duplicate category in task group: " + label)
            headings[key] = block.attrib["id"]
        elif block.tag == "task":
            guid = block.attrib["task-id"]
            if guid in entries:
                raise ValueError("Duplicate native task reference: " + guid)
            if group is None or category is None:
                raise ValueError("Task outside managed categories: " + guid)
            following = blocks[index + 1] if index + 1 < len(blocks) else None
            if (
                following is None
                or following.tag != "p"
                or not "".join(following.itertext()).startswith(link_prefix)
                or len(list(following.iter("a"))) != 1
            ):
                raise ValueError("Task has no unique adjacent document link: " + guid)
            entries[guid] = {
                "key": (group, category),
                "ids": [block.attrib["id"], following.attrib["id"]],
                "url": next(following.iter("a")).attrib["href"],
            }
    if set(groups) != {False, True}:
        raise ValueError("Active/completed headings missing; explicit setup required")
    return headings, entries, groups


def plan(document: dict, tasks: dict, config: dict | None = None):
    headings, entries, _ = parse(document, config)
    moves, unknown = {}, []
    for guid, entry in entries.items():
        task = tasks.get(guid)
        if task is None:
            unknown.append(guid)
            continue  # Never drop references merely because a task left the list.
        target = (bool(int(task.get("completed_at") or 0)), task["_category"])
        if target not in headings:
            raise ValueError("Missing destination category: " + str(target))
        if target != entry["key"]:
            moves.setdefault(target, []).append(guid)
    return moves, unknown


def plan_mounts(document: dict, tasks: dict, config: dict | None = None) -> dict[tuple[bool, str], list[str]]:
    headings, entries, _ = parse(document, config)
    mounts: dict[tuple[bool, str], list[str]] = {}
    unmounted = [guid for guid in tasks if guid not in entries]
    # Sort descending so block_insert_after (which inserts immediately below h2) yields ascending order visually.
    for guid in sorted(unmounted, key=lambda g: _sort_key_for_task(tasks[g]), reverse=True):
        task = tasks[guid]
        target = (bool(int(task.get("completed_at") or 0)), task["_category"])
        if target not in headings:
            raise ValueError("Missing destination category: " + str(target))
        mounts.setdefault(target, []).append(guid)
    return mounts


def fetch(config: dict, cli):
    return cli(config, ["docs", "+fetch", "--doc", config["document_id"], "--detail", "full"])["document"]


def checked_update(config: dict, cli, args: list[str]):
    result = cli(config, ["docs", "+update", "--doc", config["document_id"], *args])
    if result.get("result") != "success" or result.get("warnings"):
        raise RuntimeError("Task section update did not fully succeed: " + str(result))
    return result


def fold_headings(config: dict, cli, block_ids: list[str]):
    """Collapse completed section headings using the Feishu Docx batch_update API."""
    body = {
        "requests": [
            {"block_id": block_id, "update_text_style": {"style": {"folded": True}, "fields": [3]}}
            for block_id in block_ids
        ]
    }
    result = cli(
        config,
        [
            "api", "PATCH",
            "/open-apis/docx/v1/documents/" + config["document_id"] + "/blocks/batch_update",
            "--data", json.dumps(body),
        ],
    )
    data = result.get("data", result)
    if result.get("code", 0) != 0:
        raise RuntimeError("Could not fold completed headings: " + str(result))
    blocks = data.get("blocks", [])
    folded = {
        b["block_id"]
        for b in blocks
        if any(
            v.get("style", {}).get("folded") is True
            for k, v in b.items()
            if k.startswith("heading") and isinstance(v, dict)
        )
    }
    if set(block_ids) != folded:
        raise RuntimeError("Fold response did not confirm all headings")


def reconcile(
    config: dict,
    tasks: dict,
    cli,
    *,
    doc_urls: dict[str, str] | None = None,
) -> dict:
    document = fetch(config, cli)
    moves, unknown = plan(document, tasks, config)
    sec_cfg = (config or {}).get("document_task_sections") or {}
    auto_mount = sec_cfg.get("auto_mount", True)
    mounts = plan_mounts(document, tasks, config) if auto_mount else {}
    _, before, _ = parse(document, config)

    if not moves and not mounts:
        return {
            "status": "unchanged",
            "tasks": len(before),
            "unlisted_references_preserved": unknown,
            "unmounted_tasks": sorted(set(tasks) - set(before)),
        }

    with tempfile.NamedTemporaryFile(
        mode="w", prefix="soar-devflow-sections-before-", suffix=".json", delete=False, encoding="utf-8"
    ) as backup:
        json.dump(document, backup, ensure_ascii=False)
        backup_path = backup.name

    # 1. Move already-mounted tasks whose completion state or category changed.
    for target, guids in moves.items():
        headings, current, _ = parse(document, config)
        source_ids = [block_id for guid in guids for block_id in current[guid]["ids"]]
        checked_update(
            config,
            cli,
            [
                "--command", "block_move_after",
                "--block-id", headings[target],
                "--src-block-ids", ",".join(source_ids),
            ],
        )
        document = fetch(config, cli)
        _, after, _ = parse(document, config)
        if set(after) != set(before) or any(after[g]["url"] != before[g]["url"] for g in before):
            raise RuntimeError("Task/link preservation check failed; backup: " + backup_path)
        if any(after[g]["key"] != target for g in guids):
            raise RuntimeError("Task references did not reach their destination")

    # 2. Auto-mount tasks that exist in the tasklist but were never mounted on the overview doc.
    mounted_guids: list[str] = []
    mounted_without_doc: list[str] = []
    if mounts:
        _, link_prefix = section_settings(config)
        allowed_hosts = tuple((config or {}).get("allowed_url_hosts") or DEFAULT_DOC_HOSTS)
        for target, guids in mounts.items():
            headings, current_before_mount, _ = parse(document, config)
            # Chunk inserts so each DocxXML payload stays compact and reliable.
            for start in range(0, len(guids), 10):
                batch = guids[start:start + 10]
                xml_chunks = []
                for guid in batch:
                    task = tasks[guid]
                    label = _short_task_label(task.get("summary", ""))
                    doc_url = (doc_urls or {}).get(guid) or _extract_doc_url(task.get("description"), allowed_hosts)
                    if doc_url:
                        href = doc_url
                        link_text = label
                    else:
                        href = task.get("url") or f"https://applink.feishu.cn/client/todo/detail?guid={guid}"
                        link_text = f"{label}（待补文档）"
                        mounted_without_doc.append(guid)
                    xml_chunks.append(
                        f'<task task-id="{escape(guid, quote=True)}"/>\n'
                        f'<p>{escape(link_prefix)}<a href="{escape(href, quote=True)}">{escape(link_text)}</a></p>'
                    )
                checked_update(
                    config,
                    cli,
                    [
                        "--doc-format", "xml",
                        "--command", "block_insert_after",
                        "--block-id", headings[target],
                        "--content", "\n".join(xml_chunks),
                    ],
                )
                document = fetch(config, cli)
                _, after_mount, _ = parse(document, config)
                if any(g not in after_mount or after_mount[g]["key"] != target for g in batch):
                    raise RuntimeError("Mounted task references missing on readback; backup: " + backup_path)
                if any(after_mount[g]["url"] != current_before_mount[g]["url"] for g in current_before_mount):
                    raise RuntimeError("Existing task link altered during mount; backup: " + backup_path)
                current_before_mount = after_mount
                mounted_guids.extend(batch)

    remaining, _ = plan(document, tasks, config)
    if remaining:
        raise RuntimeError("Task grouping did not converge")
    _, final_entries, _ = parse(document, config)
    result = {
        "status": "updated",
        "tasks": len(final_entries),
        "moved_tasks": sum(map(len, moves.values())),
        "mounted_tasks": len(mounted_guids),
        "backup": backup_path,
        "unlisted_references_preserved": unknown,
        "unmounted_tasks": sorted(set(tasks) - set(final_entries)),
    }
    if mounted_without_doc:
        result["mounted_without_doc"] = sorted(mounted_without_doc)
    return result
