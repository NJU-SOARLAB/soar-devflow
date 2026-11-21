"""Keep native Feishu/Lark task references in active/completed sections without copying tasks."""
import json
import tempfile
import xml.etree.ElementTree as ET


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


def reconcile(config: dict, tasks: dict, cli) -> dict:
    document = fetch(config, cli)
    moves, unknown = plan(document, tasks, config)
    _, before, _ = parse(document, config)
    if not moves:
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

    remaining, _ = plan(document, tasks, config)
    if remaining:
        raise RuntimeError("Task grouping did not converge")
    return {
        "status": "updated",
        "tasks": len(before),
        "moved_tasks": sum(map(len, moves.values())),
        "backup": backup_path,
        "unlisted_references_preserved": unknown,
        "unmounted_tasks": sorted(set(tasks) - set(before)),
    }
