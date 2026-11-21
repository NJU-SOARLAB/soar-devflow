"""Unit tests for reconcile_sections.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/soar-devflow-tasks/scripts"))
from reconcile_sections import parse, plan, reconcile


def make_doc(active=True, duplicate=False, active_h="待办", done_h="已完成", prefix="任务文档："):
    pair = f'<task id="t" task-id="guid"/><p id="p">{prefix}<a href="https://example.feishu.cn/wiki/doc">PRJ-1</a></p>'
    return {
        "content": f'<h1 id="a">{active_h}</h1><h2 id="ac">算法</h2>'
        + (pair if active else "")
        + f'<h1 id="d">{done_h}</h1><h2 id="dc">算法</h2>'
        + (pair if not active or duplicate else "")
    }


class ReconcileSectionsTests(unittest.TestCase):
    def test_native_completion_is_sole_completion_source(self):
        tasks = {"guid": {"completed_at": "0", "_category": "算法", "status": "待人工验收"}}
        self.assertEqual(plan(make_doc(), tasks), ({}, []))
        tasks["guid"]["completed_at"] = "123"
        self.assertEqual(plan(make_doc(), tasks)[0], {(True, "算法"): ["guid"]})

    def test_reopened_task_returns_with_adjacent_link(self):
        tasks = {"guid": {"completed_at": "0", "_category": "算法"}}
        self.assertEqual(plan(make_doc(False), tasks)[0], {(False, "算法"): ["guid"]})
        entry = parse(make_doc(False))[1]["guid"]
        self.assertEqual(entry["ids"], ["t", "p"])

    def test_custom_english_headings_supported(self):
        cfg = {"document_task_sections": {"active_heading": "Active", "completed_heading": "Completed", "link_prefix": "Doc: "}}
        doc = make_doc(active=True, active_h="Active", done_h="Completed", prefix="Doc: ")
        tasks = {"guid": {"completed_at": "456", "_category": "算法"}}
        self.assertEqual(plan(doc, tasks, cfg)[0], {(True, "算法"): ["guid"]})

    def test_duplicates_and_missing_links_refuse_mutation(self):
        with self.assertRaises(ValueError):
            parse(make_doc(duplicate=True))
        with self.assertRaises(ValueError):
            parse({"content": make_doc()["content"].replace("任务文档：", "备注：")})

    def test_no_change_performs_no_writes(self):
        calls = []
        def cli(config, args):
            calls.append(args)
            return {"document": make_doc()}
        result = reconcile({"document_id": "doc"}, {"guid": {"completed_at": "0", "_category": "算法"}}, cli)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
