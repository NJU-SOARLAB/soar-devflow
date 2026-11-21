#!/usr/bin/env python3
"""Send one agent-declared task delivery notification to Feishu/Lark; no polling or scanning."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
import uuid

DEFAULT_CONFIG_CANDIDATES = (
    ".soar-devflow/notifications.json",
    "docs/development_management/notifications.json",
)
DEFAULT_DOC_HOSTS = ("feishu.cn", "larkoffice.com", "larksuite.com")
DEFAULT_FOOTER = "请在任务文档评论区集中反馈，再在当前开发 Agent 会话中触发处理。通知不代表额外验收或部署批准。"


class CallError(RuntimeError):
    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


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
        "No notification config found. Pass --config PATH or create .soar-devflow/notifications.json."
    )


def cli(config: dict, args: list[str], identity: str = "user", cwd: str | None = None) -> dict:
    cmd = ["lark-cli", *args, "--as", identity]
    if config.get("profile"):
        cmd.extend(["--profile", config["profile"]])
    try:
        with tempfile.TemporaryDirectory() as scratch:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(config.get("cli_timeout_seconds", 90)),
                cwd=cwd or scratch,
                env={
                    **os.environ,
                    "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
                    "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
                },
            )
    except subprocess.TimeoutExpired as exc:
        raise CallError("CLI timeout; response unknown", uncertain=True) from exc
    try:
        result = json.loads(proc.stdout if proc.returncode == 0 else proc.stderr)
    except (ValueError, TypeError) as exc:
        raise CallError("CLI returned no valid response", uncertain=True) from exc
    if proc.returncode or result.get("ok") is False:
        error = result.get("error", {})
        code = error.get("code")
        raise CallError(
            f"CLI {args[:2]} failed: {code} {error.get('message', 'unknown error')}",
            uncertain=code is None or code in (99991400, 99991500),
        )
    if result.get("format") == "ndjson":
        return result
    if result.get("ok") is not True:
        raise CallError("CLI success envelope missing", uncertain=True)
    return result["data"]


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def is_allowed_doc_url(url: str, allowed_hosts: tuple[str, ...] = DEFAULT_DOC_HOSTS) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    if not any(host == d or host.endswith("." + d) for d in allowed_hosts):
        return False
    return parsed.path.startswith(("/docx/", "/wiki/", "/docs/"))


def validate_delivery(delivery: dict, allowed_hosts: tuple[str, ...] = DEFAULT_DOC_HOSTS) -> None:
    required = (
        "task_guid", "task_document_url", "delivery_id", "status",
        "summary", "revision", "validation", "limitations",
    )
    for key in required:
        if not isinstance(delivery.get(key), str) or not delivery[key].strip():
            raise ValueError(f"Delivery requires a nonempty {key}")
        if len(delivery[key]) > 3000:
            raise ValueError(f"Delivery field too long: {key}")
    uuid.UUID(delivery["task_guid"])
    if not is_allowed_doc_url(delivery["task_document_url"], allowed_hosts):
        raise ValueError("task_document_url must be the actual Feishu/Lark task document")
    if delivery["status"] not in ("completed", "review", "partial"):
        raise ValueError("status must be completed, review or partial")
    if len(delivery["delivery_id"]) > 200:
        raise ValueError("delivery_id must be stable and at most 200 characters")
    documents = delivery.get("documents", [])
    if not isinstance(documents, list) or len(documents) > 6:
        raise ValueError("documents must be a list of at most six links")
    for doc in documents:
        if not isinstance(doc, dict) or not isinstance(doc.get("title"), str) or not doc["title"].strip():
            raise ValueError("Every document needs a title")
        if not isinstance(doc.get("url"), str) or not doc["url"].startswith("https://"):
            raise ValueError("Document links must be existing HTTPS URLs")


def get_project_task(config: dict, guid: str) -> dict:
    task = cli(config, ["task", "tasks", "get", "--params", json.dumps({"task_guid": guid})])["task"]
    current, seen = task, set()
    for _ in range(16):
        if current["guid"] in seen:
            raise RuntimeError("Task ancestry cycle")
        seen.add(current["guid"])
        if any(x["tasklist_guid"] == config["tasklist_guid"] for x in current.get("tasklists", [])):
            return task
        parent = current.get("parent_task_guid")
        if not parent:
            break
        current = cli(config, ["task", "tasks", "get", "--params", json.dumps({"task_guid": parent})])["task"]
    raise RuntimeError("Task does not belong to the authorized project list")


def message(task: dict, delivery: dict, config: dict | None = None) -> dict:
    if delivery["task_document_url"] not in task.get("description", ""):
        raise ValueError("Task document must match the link maintained in the native task description")
    done = int(task.get("completed_at") or 0) > 0
    if (delivery["status"] == "completed") != done:
        raise ValueError("Delivery status conflicts with native task completion; update task/evidence first")
    label = {"completed": "已完成", "review": "待验收", "partial": "阶段交付"}[delivery["status"]]
    lines = [
        delivery["summary"],
        "版本：" + delivery["revision"],
        "验证：" + delivery["validation"],
        "局限/未验收：" + delivery["limitations"],
    ]
    if not done:
        lines.append("原生任务保持未完成。")
    paragraphs = [[{"tag": "text", "text": line}] for line in lines]
    paragraphs.append([{"tag": "a", "text": "打开任务文档：详情、进度与反馈", "href": delivery["task_document_url"]}])
    paragraphs.append([{"tag": "a", "text": "原生任务：状态与排期", "href": task["url"]}])
    for doc in delivery.get("documents", []):
        paragraphs.append([{"tag": "a", "text": doc["title"], "href": doc["url"]}])
    footer = (config or {}).get("footer_note") or DEFAULT_FOOTER
    paragraphs.append([{"tag": "text", "text": footer}])
    return {"zh_cn": {"title": label + " · " + task["summary"], "content": paragraphs}}


def new_state(config: dict) -> dict:
    return {
        "version": 1,
        "destination": digest([config.get("profile") or "", config["chat_id"], config["tasklist_guid"]]),
        "events": {},
        "initialized_at": time.time(),
    }


def event_id_for(delivery: dict) -> str:
    return digest(["agent", delivery["task_guid"], delivery["delivery_id"]])


def existing_event(state: dict, delivery: dict) -> dict | None:
    event = state["events"].get(event_id_for(delivery))
    if event and event["payload_hash"] != digest(delivery):
        raise ValueError("delivery_id already used with different content; use a new ID for a revised delivery")
    return event


def enqueue(state: dict, task: dict, delivery: dict, config: dict | None = None) -> dict:
    event = existing_event(state, delivery)
    if event is None:
        event = {
            "task_guid": task["guid"],
            "delivery_id": delivery["delivery_id"],
            "payload_hash": digest(delivery),
            "status": "pending",
            "uuid": str(uuid.uuid4()),
            "attempts": 0,
            "next_attempt": 0,
            "content": message(task, delivery, config),
            "trigger": "agent",
        }
        state["events"][event_id_for(delivery)] = event
    return event


def save(path: Path, state: dict) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".notify-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(state, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def send(config: dict, event: dict) -> str:
    data = cli(
        config,
        [
            "im", "+messages-send",
            "--chat-id", config["chat_id"],
            "--msg-type", "post",
            "--content", json.dumps(event["content"], ensure_ascii=False),
            "--idempotency-key", event["uuid"],
        ],
        identity=config.get("send_as") or "bot",
    )
    if data.get("chat_id") != config["chat_id"] or not data.get("message_id"):
        raise CallError("Send response did not confirm destination and message ID", uncertain=True)
    return data["message_id"]


def deliver(config: dict, event: dict, persist, sender=send, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    if event["status"] == "sent":
        return {"status": "already_sent", "message_id": event["message_id"]}
    if event["status"] == "sending":
        event["status"] = "pending"
        event.setdefault("uncertain_since", event["attempted_at"])
    if event.get("uncertain_since") is not None and now - event["uncertain_since"] >= 3000:
        event["status"] = "needs_reconciliation"
        persist()
    if event["status"] != "pending":
        return {"status": event["status"]}
    if event.get("next_attempt", 0) > now:
        return {"status": "retry_later", "retry_after_seconds": int(event["next_attempt"] - now) + 1}
    event.update(status="sending", attempted_at=now, attempts=event["attempts"] + 1)
    persist()
    try:
        message_id = sender(config, event)
    except Exception as exc:
        event.update(status="pending", last_error=str(exc)[:1000], next_attempt=now + 60)
        if not isinstance(exc, CallError) or exc.uncertain:
            event.setdefault("uncertain_since", now)
        result = {"status": "failed", "error": event["last_error"], "retry_after_seconds": 60}
    else:
        event.update(status="sent", message_id=message_id, sent_at=now)
        result = {"status": "sent", "message_id": message_id}
    persist()
    return result


@contextmanager
def locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path.parent / "notify.lock", "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def validate_config(config: dict) -> None:
    if config.get("mode") != "agent":
        raise RuntimeError("Notification config must set mode='agent' (polling is intentionally unsupported)")
    chat_id = config.get("chat_id", "")
    if not isinstance(chat_id, str) or not chat_id.startswith("oc_"):
        raise RuntimeError("Notification config requires a Feishu/Lark group chat_id starting with 'oc_'")
    if not config.get("tasklist_guid"):
        raise RuntimeError("Notification config requires tasklist_guid")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="Path to notifications.json")
    parser.add_argument("--delivery", required=True, help="One delivery JSON file, or - for stdin")
    parser.add_argument("--dry-run", action="store_true", help="Validate without sending or mutating state")
    args = parser.parse_args()

    config_path = discover_config(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_config(config)

    allowed_hosts = tuple(config.get("allowed_doc_hosts") or DEFAULT_DOC_HOSTS)
    raw = sys.stdin.read() if args.delivery == "-" else Path(args.delivery).read_text(encoding="utf-8")
    delivery = json.loads(raw)
    validate_delivery(delivery, allowed_hosts)

    default_state = f"~/.local/state/soar-devflow/{config['tasklist_guid'][:12]}-notify.json"
    path = Path(config.get("state_path") or default_state).expanduser()
    with locked(path):
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else new_state(config)
        if state.get("version") != 1 or state["destination"] != new_state(config)["destination"]:
            raise RuntimeError("State version/destination mismatch; use a dedicated state_path per project")
        event = existing_event(state, delivery)
        if event and event["status"] == "sent":
            report = {"status": "already_sent", "message_id": event["message_id"]}
        else:
            task = get_project_task(config, delivery["task_guid"])
            content = message(task, delivery, config)
            if args.dry_run:
                report = {"status": "preview", "chat_id": config["chat_id"], "content": content}
            else:
                event = enqueue(state, task, delivery, config)
                state["mode"] = "agent"
                persist = lambda: save(path, state)
                persist()
                report = deliver(config, event, persist)
        report.update(task_guid=delivery["task_guid"], delivery_id=delivery["delivery_id"], dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False))
        if report["status"] not in ("sent", "already_sent", "preview"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
