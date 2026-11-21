"""Safety and state-transition checks for sync_tasks.py."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/soar-devflow-tasks/scripts"))
import sync_tasks as sync


class SyncTasksTests(unittest.TestCase):
    def task(self, **changes):
        return {
            "guid": "one",
            "summary": "[PRJ-01] Task one",
            "url": "https://applink.feishu.cn/client/todo/detail?guid=one",
            "members": [],
            "completed_at": "0",
            **changes,
        }

    def test_completion_and_reopen_follow_native_task(self):
        done = sync.mirror_fields(self.task(completed_at="123"), {}, {"one": "rec1"}, "2026-11-22T01:00:00+08:00")
        self.assertEqual(done["执行状态"], ["已完成"])
        self.assertTrue(done["任务已完成"])
        reopened = sync.mirror_fields(self.task(), {"执行状态": ["已完成"]}, {"one": "rec1"}, "2026-11-22T01:00:00+08:00")
        self.assertEqual(reopened["执行状态"], ["未开始"])
        self.assertFalse(reopened["任务已完成"])

    def test_unfinished_task_preserves_manual_review_state(self):
        fields = sync.mirror_fields(self.task(), {"执行状态": ["待人工验收"]}, {"one": "rec1"}, "2026-11-22T01:00:00+08:00")
        self.assertNotIn("执行状态", fields)
        self.assertNotIn("证据链接", fields)
        self.assertFalse(fields["任务已完成"])

    def test_dependencies_and_parent_use_record_ids(self):
        task = self.task(
            dependencies=[{"type": "prev", "task_guid": "two"}, {"type": "next", "task_guid": "three"}],
            parent_task_guid="two",
        )
        fields = sync.mirror_fields(task, {}, {"one": "rec1", "two": "rec2"}, "2026-11-22T01:00:00+08:00")
        self.assertEqual(fields["前置任务"], [{"id": "rec2"}])
        self.assertEqual(fields["父任务"], [{"id": "rec2"}])
        self.assertEqual(fields["层级"], ["子任务"])

    def test_unknown_dependency_and_duplicate_guid_fail_closed(self):
        with self.assertRaises(RuntimeError):
            sync.mirror_fields(self.task(dependencies=[{"type": "prev", "task_guid": "missing"}]), {}, {}, "now")
        with self.assertRaises(RuntimeError):
            sync.index_rows([{"Task GUID": "same"}, {"Task GUID": "same"}])

    def test_multiple_assignees_fail_closed_unless_configured(self):
        task = self.task(members=[{"id": n, "role": "assignee", "type": "user"} for n in ["a", "b"]])
        with self.assertRaises(RuntimeError):
            sync.mirror_fields(task, {}, {"one": "rec1"}, "now")
        ok = sync.mirror_fields(task, {}, {"one": "rec1"}, "now", config={"allow_multiple_assignees": True})
        self.assertEqual(len(ok["负责人"]), 2)

    def test_pagination_and_stalled_page_detection(self):
        pages = [
            {"items": [{"guid": "a"}], "has_more": True, "page_token": "next"},
            {"items": [{"guid": "b"}], "has_more": False},
        ]
        with patch.object(sync, "cli", side_effect=pages):
            self.assertEqual(len(sync.paged_tasks({}, "tasklists", {"tasklist_guid": "list"})), 2)
        with patch.object(sync, "cli", return_value=pages[0]):
            with self.assertRaises(RuntimeError):
                sync.paged_tasks({}, "tasklists", {})

    def test_dry_run_never_writes_and_keeps_orphans(self):
        with patch.object(sync, "read_tasks", return_value={"one": self.task()}), \
             patch.object(sync, "read_rows", return_value=[{"Task GUID": "one", "record_id": "rec1"},
                                                           {"Task GUID": "old", "record_id": "rec2"}]), \
             patch.object(sync, "cli") as cli:
            report = sync.sync({}, dry_run=True)
            cli.assert_not_called()
            self.assertEqual(report["orphaned_rows_preserved"], ["old"])

    def test_category_and_subtask_inheritance(self):
        parent = self.task(guid="parent", tasklists=[{"tasklist_guid": "project", "section_guid": "s1"}])
        child = self.task(parent_task_guid="parent")
        tasks = {"parent": parent, "one": child}
        sections = {"s1": "算法", "s2": "交互"}
        self.assertEqual(sync.task_category(child, tasks, "project", sections), "算法")
        child["tasklists"] = [{"tasklist_guid": "project", "section_guid": "s2"}]
        self.assertEqual(sync.task_category(child, tasks, "project", sections), "交互")

    def test_seed_process_fields_backfills_only_empty_fields(self):
        seed = {"one": {"stage": "阶段一", "priority": "P0·架构前置", "ai_hours": 1.5, "start": "2026-11-22", "due": "2026-11-23"}}
        fields = sync.mirror_fields(
            self.task(),
            {"阶段": ["已有阶段"]},
            {"one": "rec1"},
            "2026-11-22T10:00:00+08:00",
            seed_by_guid=seed,
        )
        self.assertNotIn("阶段", fields)
        self.assertEqual(fields["优先级"], ["P0·架构前置"])
        self.assertEqual(fields["AI开发估算小时"], 1.5)
        self.assertEqual(fields["AI计划开始"], "2026-11-22T09:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
