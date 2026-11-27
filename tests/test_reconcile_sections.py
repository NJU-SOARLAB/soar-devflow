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

    def test_auto_mounts_unmounted_tasks_into_active_and_completed_sections(self):
        state = {"content": make_doc(active=True)["content"]}

        def cli(config, args):
            if args[:2] == ["docs", "+fetch"]:
                return {"document": dict(state)}
            if args[:2] == ["docs", "+update"]:
                target_id = args[args.index("--block-id") + 1]
                inserted = args[args.index("--content") + 1]
                counter = [0]
                out_lines = []
                for line in inserted.splitlines():
                    counter[0] += 1
                    if line.startswith("<task "):
                        out_lines.append(line.replace("<task ", f'<task id="mt_{target_id}_{counter[0]}" '))
                    elif line.startswith("<p>"):
                        out_lines.append(line.replace("<p>", f'<p id="mp_{target_id}_{counter[0]}">'))
                    else:
                        out_lines.append(line)
                marker = f'<h2 id="{target_id}">算法</h2>'
                state["content"] = state["content"].replace(marker, marker + "".join(out_lines))
                return {"result": "success"}
            raise AssertionError(f"Unexpected call: {args}")

        tasks = {
            "guid": {"summary": "[PRJ-1] Existing", "completed_at": "0", "_category": "算法"},
            "g_open": {"summary": "[PRJ-2] New Open", "completed_at": "0", "_category": "算法", "url": "https://applink.feishu.cn/client/todo/detail?guid=g_open"},
            "g_done": {"summary": "[PRJ-3] New Done", "completed_at": "999", "_category": "算法", "url": "https://applink.feishu.cn/client/todo/detail?guid=g_done"},
        }
        res = reconcile(
            {"document_id": "doc"},
            tasks,
            cli,
            doc_urls={"g_open": "https://example.feishu.cn/wiki/open_doc"},
        )
        self.assertEqual(res["status"], "updated")
        self.assertEqual(res["mounted_tasks"], 2)
        self.assertEqual(res["unmounted_tasks"], [])
        self.assertEqual(res["mounted_without_doc"], ["g_done"])
        _, entries, _ = parse(state)
        self.assertEqual(entries["g_open"]["key"], (False, "算法"))
        self.assertEqual(entries["g_open"]["url"], "https://example.feishu.cn/wiki/open_doc")
        self.assertEqual(entries["g_done"]["key"], (True, "算法"))

    def test_tolerates_group_heading_nested_in_preceding_paragraph(self):
        doc = {
            "content": '<p id="intro">说明<h1 id="a">待办</h1></p><h2 id="ac">算法</h2>'
            '<task id="t" task-id="guid"/><p id="p">任务文档：<a href="https://example.feishu.cn/wiki/doc">PRJ-1</a></p>'
            '<h1 id="d">已完成</h1><h2 id="dc">算法</h2>'
        }
        headings, entries, groups = parse(doc)
        self.assertEqual(set(groups), {False, True})
        self.assertIn((False, "算法"), headings)
        self.assertEqual(entries["guid"]["key"], (False, "算法"))


if __name__ == "__main__":
    unittest.main()
