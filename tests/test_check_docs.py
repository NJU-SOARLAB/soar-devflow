"""Unit tests for check_docs.py universal documentation gatekeeper."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/soar-devflow-docs/scripts"))
import check_docs as cd


class CheckDocsTests(unittest.TestCase):
    def test_unclosed_vue_elements_detected_accurately(self):
        self.assertEqual(cd.unclosed_elements("the “<store>余量” donut"), ["store"])
        self.assertEqual(cd.unclosed_elements("missing <stage name> here"), ["stage"])
        ok = (
            "---\ntitle: <x>\n---\n`<tool>` <https://example.org> <br> <img src='a.png'> "
            "<b>bold</b> <span class='k' /> $j<i$\n\n$$\na<b\n$$\n\n```\n<store>\n```\n"
            "<!-- <draft> -->\n&lt;场景名称&gt;"
        )
        self.assertEqual(cd.unclosed_elements(ok), [])

    def test_bilingual_and_single_source_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "docs/site"
            (site / "guide").mkdir(parents=True)
            (site / "en/guide").mkdir(parents=True)
            (site / "public/img").mkdir(parents=True)
            (site / "public/img/a.png").write_bytes(b"png")

            coverage = {
                "guide/start": {
                    "section": "guide",
                    "title_zh": "开始",
                    "title_en": "Start",
                    "translation_revision": 1,
                    "anchors": ["intro"],
                }
            }
            (site / "coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
            zh_body = "---\ntranslationKey: guide/start\nsourceRevision: 1\n---\n\n# 开始\n\n## 介绍 {#intro}\n\n![图](/img/a.png)\n\n" + ("正文内容。" * 80)
            en_body = "---\ntranslationKey: guide/start\nsourceRevision: 1\n---\n\n# Start\n\n## Intro {#intro}\n\n![Pic](/img/a.png)\n\n" + ("Detailed guide text. " * 30)
            (site / "guide/start.md").write_text(zh_body, encoding="utf-8")
            (site / "en/guide/start.md").write_text(en_body, encoding="utf-8")

            cfg = {
                "site_dir": "docs/site",
                "languages": ["zh", "en"],
                "root_language": "zh",
                "single_source": {"enabled": True, "allowed_prefixes": ["docs/site/"], "allowed_files": ["README.md"]},
                "quality": {"min_stub_chars": 100, "min_chars": {"zh": 200, "en": 200}, "require_visual_in": ["guide"]},
            }
            report = cd.validate(root, site, cfg)
            self.assertTrue(report["passed"])
            self.assertEqual(report["pages"], 2)

            # Anchor mismatch fails closed
            (site / "en/guide/start.md").write_text(en_body + "\n## Extra {#only-en}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Explicit anchors differ"):
                cd.validate(root, site, cfg)

            # Restore and add stray outside markdown -> fails single-source
            (site / "en/guide/start.md").write_text(en_body, encoding="utf-8")
            (root / "stray_design.md").write_text("# Stray\n\n1\n2\n3\n4\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Technical Markdown outside"):
                cd.validate(root, site, cfg)

            # <=3-line pointer to docs/site passes
            (root / "stray_design.md").write_text("Moved to `docs/site/guide/start.md`.\n", encoding="utf-8")
            self.assertTrue(cd.validate(root, site, cfg)["passed"])

            # Documenting `@include` in inline code passes, while a real VitePress include directive fails
            (site / "guide/start.md").write_text(zh_body + "\nDo not use `@include`.\n", encoding="utf-8")
            self.assertTrue(cd.validate(root, site, cfg)["passed"])
            (site / "guide/start.md").write_text(zh_body + "\n<!--@include: ../en/guide/start.md-->\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "@include"):
                cd.validate(root, site, cfg)


if __name__ == "__main__":
    unittest.main()
