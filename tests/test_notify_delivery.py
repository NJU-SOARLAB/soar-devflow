"""Unit tests for notify_delivery.py."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "skills/soar-devflow-tasks/scripts/notify_delivery.py"
sys.path.insert(0, str(FILE.parent))
import notify_delivery as n

CONFIG = {"profile": "custom-team", "chat_id": "oc_test_group", "tasklist_guid": "list-1", "mode": "agent"}
GUID = "27d6728e-39d1-41b8-9dc9-514b95d4390b"


class NotifyDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.state = n.new_state(CONFIG)
        self.task = {
            "guid": GUID,
            "summary": "[PRJ-10] Test delivery",
            "completed_at": "0",
            "url": "https://applink.feishu.cn/client/todo/detail?guid=" + GUID,
            "tasklists": [{"tasklist_guid": "list-1"}],
            "description": "详情见 https://example.larksuite.com/wiki/taskdoc",
        }
        self.delivery = {
            "task_guid": GUID,
            "delivery_id": "v1.0-rc1-review",
            "status": "review",
            "task_document_url": "https://example.larksuite.com/wiki/taskdoc",
            "summary": "Implemented module",
            "revision": "main abc1234",
            "validation": "unittest 18 passed",
            "limitations": "Manual UI review pending",
        }

    def test_any_profile_accepted_and_polling_rejected(self):
        n.validate_config(CONFIG)
        n.validate_config({**CONFIG, "profile": ""})
        with self.assertRaises(RuntimeError):
            n.validate_config({**CONFIG, "mode": "poll"})
        with self.assertRaises(RuntimeError):
            n.validate_config({**CONFIG, "chat_id": "bad"})

    def test_explicit_delivery_required(self):
        res = subprocess.run([sys.executable, str(FILE)], text=True, capture_output=True)
        self.assertEqual(res.returncode, 2)
        self.assertIn("--delivery", res.stderr)

    def test_feishu_and_lark_urls_supported(self):
        n.validate_delivery(self.delivery)
        n.validate_delivery({**self.delivery, "task_document_url": "https://example.feishu.cn/docx/abc"})
        n.validate_delivery({**self.delivery, "task_document_url": "https://example.larkoffice.com/wiki/abc"})
        with self.assertRaises(ValueError):
            n.validate_delivery({**self.delivery, "task_document_url": "https://evil.example/docx/abc"})

    def test_completion_conflict_rejected(self):
        with self.assertRaises(ValueError):
            n.message(self.task, {**self.delivery, "status": "completed"})
        completed = {**self.task, "completed_at": "123"}
        self.assertIn("已完成", n.message(completed, {**self.delivery, "status": "completed"})["zh_cn"]["title"])
        with self.assertRaises(ValueError):
            n.message(completed, self.delivery)

    def test_idempotent_dedup_and_content_mismatch_guard(self):
        event = n.enqueue(self.state, self.task, self.delivery)
        calls = []
        sender = lambda c, e: calls.append(e["uuid"]) or "om_test"
        n.deliver(CONFIG, event, lambda: None, sender, now=100)
        restarted = json.loads(json.dumps(self.state))
        same = n.enqueue(restarted, self.task, self.delivery)
        self.assertEqual(n.deliver(CONFIG, same, lambda: None, sender, now=200)["status"], "already_sent")
        self.assertEqual(len(calls), 1)
        with self.assertRaisesRegex(ValueError, "different content"):
            n.enqueue(self.state, self.task, {**self.delivery, "summary": "Changed"})

    def test_crash_reuses_uuid_and_holds_after_50_minutes(self):
        event = n.enqueue(self.state, self.task, self.delivery)
        event.update(status="sending", attempted_at=100)
        old_uuid = event["uuid"]
        calls = []
        n.deliver(CONFIG, event, lambda: None, lambda c, e: calls.append(e["uuid"]) or "om_old", now=120)
        self.assertEqual(calls, [old_uuid])
        event.update(status="sending", attempted_at=100)
        result = n.deliver(CONFIG, event, lambda: None, lambda *a: self.fail("must not send"), now=3100)
        self.assertEqual(result["status"], "needs_reconciliation")

    def test_persist_before_send_atomic_0600(self):
        event = n.enqueue(self.state, self.task, self.delivery)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            def sender(c, e):
                saved = json.loads(path.read_text(encoding="utf-8"))["events"][n.event_id_for(self.delivery)]
                self.assertEqual(saved["status"], "sending")
                return "om_ok"
            n.deliver(CONFIG, event, lambda: n.save(path, self.state), sender, now=100)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_targeted_task_ancestry_check(self):
        child = {**self.task, "tasklists": [], "parent_task_guid": "parent"}
        parent = {**self.task, "guid": "parent"}
        with patch.object(n, "cli", side_effect=[{"task": child}, {"task": parent}]) as api:
            self.assertEqual(n.get_project_task(CONFIG, GUID), child)
            self.assertEqual(api.call_count, 2)

    def test_cli_parses_json_error_from_stdout_on_nonzero_exit(self):
        fake = subprocess.CompletedProcess(
            args=["lark-cli"],
            returncode=1,
            stdout=json.dumps({"ok": False, "error": {"code": 99991663, "message": "invalid param"}}),
            stderr="",
        )
        with patch.object(n.subprocess, "run", return_value=fake):
            with self.assertRaises(n.CallError) as ctx:
                n.cli(CONFIG, ["im", "+messages-send"])
            self.assertIn("99991663", str(ctx.exception))
            self.assertFalse(ctx.exception.uncertain)

    def test_distinct_state_files_in_same_dir_do_not_contend_on_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            p1 = Path(directory) / "proj-a.json"
            p2 = Path(directory) / "proj-b.json"
            with n.locked(p1):
                with n.locked(p2):
                    self.assertTrue((Path(directory) / "proj-a.json.lock").exists())
                    self.assertTrue((Path(directory) / "proj-b.json.lock").exists())


if __name__ == "__main__":
    unittest.main()
