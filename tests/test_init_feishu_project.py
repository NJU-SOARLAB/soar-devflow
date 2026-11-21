"""Unit tests for init_feishu_project.py bootstrapper."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/soar-devflow-setup/scripts"))
import init_feishu_project as init_mod


class InitFeishuProjectTests(unittest.TestCase):
    def test_plan_summary_includes_all_resources(self):
        spec = {
            "project": "Atlas Sim",
            "task_prefix": "ATL",
            "profile": "team",
            "sections": ["内核", "接口"],
            "stages": ["阶段一", "日常"],
            "timezone": "Asia/Shanghai",
            "timezone_offset_hours": 8,
            "output_dir": ".soar-devflow",
            "chat_id": "oc_example_chat",
        }
        plan = init_mod.plan_summary(spec)
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["planned_remote_resources"]["minor_fix_task"], "[ATL-00] 小修小补与日常维护滚动记录")
        self.assertGreaterEqual(plan["planned_remote_resources"]["field_count"], 20)
        self.assertIn(".soar-devflow/notifications.json", plan["planned_local_files"])

    def test_mocked_bootstrap_creates_configs_and_views(self):
        calls = []
        view_counter = [0]
        doc_counter = [0]

        def fake_cli(profile, args, cwd=None):
            calls.append((profile, args[:2]))
            cmd = tuple(args[:2])
            if cmd == ("task", "+tasklist-create"):
                return {"tasklist": {"guid": "tl-1", "url": "https://applink.feishu.cn/client/todo/task_list?guid=tl-1"}}
            if cmd == ("task", "sections"):
                name = json.loads(args[args.index("--data") + 1])["name"]
                return {"section": {"guid": f"sec-{name}"}}
            if cmd == ("base", "+base-create"):
                return {"base_token": "b-1", "table_id": "tbl-1", "url": "https://example.feishu.cn/base/b-1"}
            if cmd == ("base", "+field-create"):
                fields = json.loads(args[args.index("--json") + 1])
                self.assertEqual([f["name"] for f in fields], ["前置任务", "父任务"])
                self.assertTrue(all(f["link_table"] == "tbl-1" for f in fields))
                return {"created": 2}
            if cmd == ("base", "+view-create"):
                view_counter[0] += 1
                return {"view_id": f"vew-{view_counter[0]}"}
            if cmd in (("base", "+view-set-group"), ("base", "+view-set-timebar")):
                return {"ok": True}
            if cmd == ("docs", "+create"):
                doc_counter[0] += 1
                return {"document_id": f"doc-{doc_counter[0]}", "url": f"https://example.feishu.cn/docx/doc-{doc_counter[0]}"}
            if cmd == ("task", "tasks"):
                return {"task": {"guid": "minor-guid", "url": "https://applink.feishu.cn/client/todo/detail?guid=minor-guid"}}
            if cmd == ("wiki", "+move"):
                tok = args[args.index("--obj-token") + 1]
                return {"node_token": f"node-{tok}", "url": f"https://example.feishu.cn/wiki/node-{tok}"}
            raise AssertionError(f"Unexpected command: {args}")

        with tempfile.TemporaryDirectory() as tmp:
            spec = {
                "project": "Atlas Sim",
                "task_prefix": "ATL",
                "profile": "team",
                "space_id": "70001",
                "parent_node_token": "root-node",
                "chat_id": "oc_example_chat",
                "sections": ["内核", "工程"],
                "stages": ["阶段一", "日常"],
                "timezone": "Asia/Shanghai",
                "timezone_offset_hours": 8,
                "output_dir": str(Path(tmp) / ".soar-devflow"),
            }
            res = init_mod.bootstrap(spec, cli_fn=fake_cli, sync_fn=lambda cfg: {"synced": True})
            self.assertEqual(res["tasklist_guid"], "tl-1")
            self.assertEqual(res["sync_result"], {"synced": True})
            tasks_cfg = json.loads(Path(res["tasks_config"]).read_text(encoding="utf-8"))
            self.assertEqual(tasks_cfg["minor_fixes_task_id"], "ATL-00")
            self.assertEqual(tasks_cfg["document_node_token"], "node-doc-2")
            self.assertEqual(tasks_cfg["document_visualization"]["marker"], "atlas-sim-overview-v1")
            notify_cfg = json.loads(Path(res["notifications_config"]).read_text(encoding="utf-8"))
            self.assertEqual(notify_cfg["mode"], "agent")
            self.assertEqual(notify_cfg["chat_id"], "oc_example_chat")


if __name__ == "__main__":
    unittest.main()
