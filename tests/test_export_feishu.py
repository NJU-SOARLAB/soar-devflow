"""Unit tests for export_feishu.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/soar-devflow-tasks/scripts"))
import export_feishu as ef


class ExportFeishuTests(unittest.TestCase):
    def test_converts_frontmatter_mermaid_tables_and_links(self):
        md = (
            "---\ntranslationKey: ref/arch\nsourceRevision: 1\n---\n\n"
            "# System Architecture {#top}\n\n"
            "## Flow {#flow}\n\n"
            "See **core** `engine` at [Site](https://example.org/docs).\n\n"
            "```mermaid\nflowchart LR\n  A --> B\n```\n\n"
            "| Key | Value |\n| --- | --- |\n| mode | agent |\n"
        )
        xml = ef.render(md)
        self.assertIn("<title>System Architecture</title>", xml)
        self.assertIn('<h1 seq="auto">Flow</h1>', xml)
        self.assertIn('<whiteboard type="mermaid">', xml)
        self.assertIn('<a href="https://example.org/docs">Site</a>', xml)
        self.assertIn("<table>", xml)

    def test_relative_links_rejected_for_cloud_doc(self):
        with self.assertRaises(ValueError):
            ef.render("# Title\n\nSee [Local](./other.md).\n")


if __name__ == "__main__":
    unittest.main()
