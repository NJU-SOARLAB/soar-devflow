"""Unit tests for render_overview.py and overview_template.html."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/soar-devflow-tasks/scripts"))
import render_overview as views


class RenderOverviewTests(unittest.TestCase):
    def test_untrusted_urls_and_script_breakout_are_neutralized(self):
        self.assertEqual(views.safe_url("javascript:alert(1)"), "#")
        self.assertEqual(views.safe_url("https://feishu.cn.evil.test/task"), "#")
        self.assertEqual(views.safe_url("https://example.larksuite.com/wiki/abc"), "https://example.larksuite.com/wiki/abc")
        config = {
            "project": "demo-app",
            "base_url": "https://example.feishu.cn/base/token",
            "table_id": "tbl1",
            "tasklist_url": "https://applink.feishu.cn/client/todo/task_list?guid=list",
            "stages": ["阶段A", "阶段B"],
        }
        output = views.render([{"id": "D-1", "title": "</script><script>alert(1)</script>"}], config, "now")
        self.assertNotIn("</script><script>alert(1)", output)
        self.assertIn("\\u003c/script\\u003e", output)
        self.assertIn("阶段A", output)
        self.assertIn("demo-app-overview-v1", output)

    def test_native_completion_overrides_stale_manual_status(self):
        task = {
            "summary": "[PRJ-01] Example",
            "url": "https://applink.feishu.cn/task",
            "members": [],
            "dependencies": [{"type": "prev", "task_guid": "b"}],
        }
        row = {"record_id": "r", "执行状态": ["待人工验收"], "优先级": ["P0·架构前置"], "阶段": ["阶段一"]}
        update = {
            "r": {
                "任务已完成": True,
                "计划开始": "2026-11-22T00:00:00+08:00",
                "计划截止": "2026-11-23T00:00:00+08:00",
                "领域分类": "架构",
            }
        }
        data = views.make_data({}, {"a": task}, {"a": row}, update)
        self.assertEqual(data[0]["status"], "已完成")
        self.assertEqual(data[0]["stage"], "阶段一")
        self.assertEqual(data[0]["deps"], ["清单外前置"])

    def test_find_widget_rejects_duplicates(self):
        doc = {"content": '<html5-block id="x" alt="MyApp 项目推进总览"/>'}
        self.assertEqual(views.find_widget(doc, "MyApp 项目推进总览", "myapp-overview-v1"), "x")
        doc["content"] += '<html5-block id="y" alt="MyApp 项目推进总览"/>'
        with self.assertRaises(RuntimeError):
            views.find_widget(doc, "MyApp 项目推进总览", "myapp-overview-v1")

    def test_ai_and_acceptance_windows_stay_separate(self):
        task = {"summary": "[PRJ-15] Docs", "url": "https://applink.feishu.cn/task", "members": [], "dependencies": []}
        row = {
            "record_id": "r",
            "执行状态": ["进行中"],
            "AI开发估算小时": 2,
            "AI工时范围": "1–3小时",
            "AI计划开始": "2026-11-22T09:00:00+08:00",
            "AI计划交付": "2026-11-22T11:00:00+08:00",
            "人工验收估算小时": 1,
            "验收与等待说明": "待评审",
        }
        update = {
            "r": {
                "任务已完成": False,
                "计划开始": "2026-11-22T00:00:00+08:00",
                "计划截止": "2026-11-24T00:00:00+08:00",
                "领域分类": "文档",
            }
        }
        item = views.make_data({}, {"a": task}, {"a": row}, update)[0]
        self.assertEqual(item["ai_end"], "2026-11-22")
        self.assertEqual(item["end"], "2026-11-24")
        self.assertEqual(item["human_hours"], 1)

    def test_non_bracketed_task_ids_are_split_cleanly_without_duplicating_title(self):
        tasks = {
            "a": {"summary": "PRJ-52：前端性能优化", "url": "https://applink.feishu.cn/t1", "members": [], "dependencies": []},
            "b": {"summary": "PRJ-50 Space title", "url": "https://applink.feishu.cn/t2", "members": [], "dependencies": [{"type": "prev", "task_guid": "a"}]},
            "c": {"summary": "Plain unnumbered item", "url": "https://applink.feishu.cn/t3", "members": [], "dependencies": []},
        }
        rows = {k: {"record_id": f"r{k}", "执行状态": ["未开始"]} for k in tasks}
        updates = {f"r{k}": {"任务已完成": False, "领域分类": "前端"} for k in tasks}
        by_title = {item["title"]: item for item in views.make_data({}, tasks, rows, updates)}
        self.assertEqual(by_title["前端性能优化"]["id"], "PRJ-52")
        self.assertEqual(by_title["Space title"]["id"], "PRJ-50")
        self.assertEqual(by_title["Space title"]["deps"], ["PRJ-52"])
        self.assertEqual(by_title["Plain unnumbered item"]["id"], "")


if __name__ == "__main__":
    unittest.main()
