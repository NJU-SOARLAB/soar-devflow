"""Unit tests for create_task.py."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/soar-devflow-tasks/scripts"))
import create_task as ct


class CreateTaskTests(unittest.TestCase):
    def base_config(self):
        return {
            "project": "demo-proj",
            "task_prefix": "PRJ",
            "profile": "team",
            "owner_open_id": "ou_example_owner",
            "space_id": "70001",
            "document_id": "ov-doc-1",
            "document_node_token": "ov-node-1",
            "tasklist_guid": "tl-1",
            "sections": {"内核": "sec-core", "工作台": "sec-ui"},
            "document_task_sections": {
                "enabled": True,
                "active_heading": "待办",
                "completed_heading": "已完成",
                "link_prefix": "任务文档：",
            },
        }

    def test_next_task_id_and_dry_run_duplicate_detection(self):
        cfg = self.base_config()
        remote_items = [
            {"guid": "g1", "summary": "[PRJ-01] 初始内核"},
            {"guid": "g2", "summary": "PRJ-09：前端 WebGL 渲染优化"},
        ]

        def fake_cli(config, args, cwd=None):
            if args[:3] == ["task", "tasklists", "tasks"]:
                return {"items": remote_items, "has_more": False}
            if args[:3] == ["task", "sections", "list"]:
                return {"items": [{"guid": "sec-core", "name": "内核"}, {"guid": "sec-ui", "name": "工作台"}], "has_more": False}
            raise AssertionError(f"dry_run must not mutate: {args}")

        plan = ct.create_task(
            cfg,
            title="前端 WebGL 性能优化",
            section="工作台",
            due="2026-11-30",
            dry_run=True,
            cli_fn=fake_cli,
        )
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["id"], "PRJ-10")
        self.assertEqual(plan["summary"], "[PRJ-10] 前端 WebGL 性能优化")
        self.assertEqual(len(plan["possible_duplicates"]), 1)
        self.assertEqual(plan["possible_duplicates"][0]["guid"], "g2")

    def test_live_create_moves_wiki_first_mounts_overview_and_updates_task_documents(self):
        cfg = self.base_config()
        overview_state = {
            "content": '<h1 id="h1a">待办</h1><h2 id="h2core">内核</h2><h2 id="h2ui">工作台</h2>'
                       '<h1 id="h1d">已完成</h1><h2 id="h2core_d">内核</h2><h2 id="h2ui_d">工作台</h2>'
        }
        call_order = []
        created_task_body = {}

        def fake_cli(config, args, cwd=None):
            call_order.append(tuple(args[:2]))
            if args[:3] == ["task", "tasklists", "tasks"]:
                return {"items": [{"guid": "g1", "summary": "[PRJ-05] Existing"}], "has_more": False}
            if args[:3] == ["task", "sections", "list"]:
                return {"items": [{"guid": "sec-core", "name": "内核"}, {"guid": "sec-ui", "name": "工作台"}], "has_more": False}
            if args[:2] == ["docs", "+create"]:
                return {"document": {"document_id": "doc-new", "revision_id": 1, "url": "https://example.feishu.cn/docx/doc-new"}}
            if args[:2] == ["wiki", "+move"]:
                return {"node": {"node_token": "node-new"}}
            if args[:3] == ["task", "tasks", "create"]:
                created_task_body.update(json.loads(args[args.index("--data") + 1]))
                return {"task": {"guid": "guid-new", "url": "https://applink.feishu.cn/client/todo/detail?guid=guid-new"}}
            if args[:2] == ["docs", "+fetch"]:
                return {"document": dict(overview_state)}
            if args[:2] == ["docs", "+update"]:
                self.assertEqual(args[args.index("--block-id") + 1], "h2ui")
                inserted = args[args.index("--content") + 1]
                # Simulate inserting blocks with IDs after h2ui
                inserted_with_ids = inserted.replace("<task ", '<task id="t_new" ').replace("<p>", '<p id="p_new">')
                overview_state["content"] = overview_state["content"].replace(
                    '<h2 id="h2ui">工作台</h2>',
                    '<h2 id="h2ui">工作台</h2>' + inserted_with_ids,
                )
                return {"result": "success"}
            raise AssertionError(f"Unexpected call: {args}")

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / ".soar-devflow/tasks.json"
            cfg_path.parent.mkdir(parents=True)
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

            res = ct.create_task(
                cfg,
                config_path=cfg_path,
                title="工作台前端性能优化",
                section="工作台",
                due="2026-11-30",
                user_quote="优化前端 WebGL 性能",
                cli_fn=fake_cli,
            )
            self.assertFalse(res["dry_run"])
            self.assertEqual(res["id"], "PRJ-06")
            self.assertEqual(res["doc_url"], "https://example.feishu.cn/wiki/node-new")
            self.assertTrue(res["overview_mounted"])
            # Wiki move must happen BEFORE native task creation so description holds the final /wiki/ URL
            self.assertLess(call_order.index(("wiki", "+move")), call_order.index(("task", "tasks")))
            self.assertIn("https://example.feishu.cn/wiki/node-new", created_task_body["description"])
            docs_map = json.loads((cfg_path.parent / "task_documents.json").read_text(encoding="utf-8"))
            self.assertEqual(docs_map["guid-new"]["id"], "PRJ-06")
            self.assertEqual(docs_map["guid-new"]["url"], "https://example.feishu.cn/wiki/node-new")

    def test_unknown_section_and_duplicate_id_rejected(self):
        cfg = self.base_config()

        def fake_cli(config, args, cwd=None):
            if args[:3] == ["task", "tasklists", "tasks"]:
                return {"items": [{"guid": "g1", "summary": "[PRJ-01] First"}], "has_more": False}
            if args[:3] == ["task", "sections", "list"]:
                return {"items": [{"guid": "sec-core", "name": "内核"}], "has_more": False}
            raise AssertionError(args)

        with self.assertRaisesRegex(ValueError, "Unknown section"):
            ct.create_task(cfg, title="X", section="不存在", dry_run=True, cli_fn=fake_cli)
        with self.assertRaisesRegex(ValueError, "already exists"):
            ct.create_task(cfg, title="X", section="内核", task_id="PRJ-01", dry_run=True, cli_fn=fake_cli)

    def test_nested_task_documents_preserves_wrapper_and_detects_task_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp) / "task_documents.json"
            td.write_text(json.dumps({"version": 1, "tasks": {"g0": {"task_id": "PRJ-08"}}}), encoding="utf-8")
            ct.update_task_documents_file(td, "g1", {"id": "PRJ-09", "title": "New", "url": "https://example.feishu.cn/wiki/n"})
            saved = json.loads(td.read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], 1)
            self.assertEqual(saved["tasks"]["g1"]["task_id"], "PRJ-09")
            self.assertEqual(saved["tasks"]["g1"]["document_url"], "https://example.feishu.cn/wiki/n")


if __name__ == "__main__":
    unittest.main()
