#!/usr/bin/env python3
"""Scaffold a SOAR DevFlow single-source VitePress documentation site in a target repo."""
import argparse
import json
from pathlib import Path
import shutil

DOCS_ASSETS = Path(__file__).resolve().parents[2] / "soar-devflow-docs/assets/vitepress-starter"


def scaffold(
    target: Path,
    title: str,
    description: str,
    languages: list[str],
    base: str,
    site_rel: str,
    config_rel: str,
    force: bool = False,
) -> dict:
    target = target.resolve()
    site_dir = target / site_rel
    config_path = target / config_rel
    if site_dir.exists() and any(site_dir.iterdir()) and not force:
        raise FileExistsError(f"{site_dir} is not empty; pass --force to overwrite starter files")

    bilingual = len(languages) > 1
    root_lang = languages[0]

    # Copy starter theme & package files
    (site_dir / ".vitepress/theme").mkdir(parents=True, exist_ok=True)
    (site_dir / "public/shots").mkdir(parents=True, exist_ok=True)
    (site_dir / "public/diagrams").mkdir(parents=True, exist_ok=True)
    (site_dir / "shots").mkdir(parents=True, exist_ok=True)

    for rel in ("package.json", ".vitepress/theme/index.js", ".vitepress/theme/lightbox.js", ".vitepress/theme/custom.css"):
        shutil.copy2(DOCS_ASSETS / rel, site_dir / rel)

    # Render config.mjs
    cfg_tpl = (DOCS_ASSETS / ".vitepress/config.mjs").read_text(encoding="utf-8")
    cfg_text = (
        cfg_tpl.replace("@@TITLE@@", title.replace("'", "\\'"))
        .replace("@@DESCRIPTION@@", description.replace("'", "\\'"))
        .replace("@@BASE@@", base)
        .replace("@@BILINGUAL@@", "true" if bilingual else "false")
    )
    (site_dir / ".vitepress/config.mjs").write_text(cfg_text, encoding="utf-8")

    # Coverage manifest
    coverage = {
        "guide/quickstart": {
            "section": "guide",
            "title_zh": "快速上手",
            "title_en": "Quickstart",
            "translation_revision": 1,
            "anchors": ["prerequisites", "steps", "troubleshooting"],
        },
        "reference/architecture": {
            "section": "reference",
            "title_zh": "系统架构与设计",
            "title_en": "Architecture & Design",
            "translation_revision": 1,
            "anchors": ["overview", "dataflow", "verification"],
        },
    }
    (site_dir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Landing & starter pages
    def write_lang_pages(lang: str, prefix_dir: Path) -> None:
        (prefix_dir / "guide").mkdir(parents=True, exist_ok=True)
        (prefix_dir / "reference").mkdir(parents=True, exist_ok=True)
        if lang == "zh":
            (prefix_dir / "index.md").write_text(
                f"---\nlayout: home\nhero:\n  name: {title}\n  text: 单源技术文档与教程站\n  tagline: {description}\n"
                f"  actions:\n    - theme: brand\n      text: 快速上手\n      link: /guide/quickstart\n"
                f"    - theme: alt\n      text: 系统架构\n      link: /reference/architecture\n---\n",
                encoding="utf-8",
            )
            (prefix_dir / "guide/quickstart.md").write_text(
                "---\ntranslationKey: guide/quickstart\nsourceRevision: 1\n---\n\n"
                f"# {title} 快速上手\n\n"
                "本教程面向首次使用本系统的开发者与操作者，说明如何从零完成环境准备、启动与验证。\n\n"
                "## 你将学会\n\n- 完成本地依赖安装与配置校验\n- 启动核心流程并验证预期输出\n- 排查最常见的环境与路径问题\n\n"
                "## 开始之前 {#prerequisites}\n\n请确认已安装所需运行时并拉取最新主干代码。\n\n"
                "## 分步操作 {#steps}\n\n```mermaid\nflowchart LR\n  A[准备环境] --> B[安装依赖]\n  B --> C[运行验证]\n  C --> D[查看结果]\n```\n\n"
                "1. 安装项目依赖并检查配置文件。\n2. 运行验证命令，确认全部基础检查通过。\n\n"
                "## 出了问题怎么办 {#troubleshooting}\n\n| 现象 | 可能原因 | 处理方式 |\n| --- | --- | --- |\n"
                "| 构建失败 | 依赖版本不一致 | 重新执行锁文件安装并核对运行时版本 |\n\n"
                "## 原理与相关说明\n\n关于模块边界与数据流设计，见 [系统架构与设计](../reference/architecture.md#overview)。\n",
                encoding="utf-8",
            )
            (prefix_dir / "reference/architecture.md").write_text(
                "---\ntranslationKey: reference/architecture\nsourceRevision: 1\n---\n\n"
                f"# {title} 系统架构与设计\n\n"
                "## 概述与边界 {#overview}\n\n"
                "本页说明系统的模块划分、数据流与核心不变量，帮助研发人员对照源码核实实现边界并复现验证。\n\n"
                "- **职责范围**：记录已落地模块的数据流、配置契约与关键假设。\n"
                "- **非目标**：过程进度、待办与验收记录保存在任务管理面板，不写入技术正文。\n\n"
                "## 数据流 {#dataflow}\n\n"
                "```mermaid\nflowchart TD\n  Input[输入与配置] --> Core[核心引擎]\n  Core --> Output[构建与产物]\n  Core --> Gate[确定性检查]\n```\n\n"
                "## 关键参数与实现位置\n\n"
                "| 参数 / 模块 | 默认值或职责 | 来源路径 |\n"
                "| --- | --- | --- |\n"
                "| 文档站配置 | 单源规则、多语言与质量门禁 | `.soar-devflow/docs.json` |\n\n"
                "## 如何验证 {#verification}\n\n"
                "运行仓库内自动化测试与文档站检查命令，确认检查通过后再合并或发布。若发现文档与实现偏差，请在“核查发现”中如实列出。\n\n"
                "操作步骤见 [快速上手](../guide/quickstart.md#steps)。\n",
                encoding="utf-8",
            )
        else:
            (prefix_dir / "index.md").write_text(
                f"---\nlayout: home\nhero:\n  name: {title}\n  text: Single-Source Docs & Tutorials\n  tagline: {description}\n"
                f"  actions:\n    - theme: brand\n      text: Quickstart\n      link: /en/guide/quickstart\n"
                f"    - theme: alt\n      text: Architecture\n      link: /en/reference/architecture\n---\n",
                encoding="utf-8",
            )
            (prefix_dir / "guide/quickstart.md").write_text(
                "---\ntranslationKey: guide/quickstart\nsourceRevision: 1\n---\n\n"
                f"# {title} Quickstart\n\n"
                "This tutorial walks first-time contributors through environment setup, running the core workflow, and verifying outputs.\n\n"
                "## What you will learn\n\n- Verify prerequisites and local configuration\n- Run the core workflow end-to-end\n- Diagnose common setup issues\n\n"
                "## Prerequisites {#prerequisites}\n\nEnsure required runtimes are installed and you are on the latest main branch.\n\n"
                "## Step-by-step {#steps}\n\n```mermaid\nflowchart LR\n  A[Prepare Env] --> B[Install Deps]\n  B --> C[Run Checks]\n  C --> D[Review Output]\n```\n\n"
                "1. Install dependencies and verify configuration.\n2. Run the verification suite and confirm all checks pass.\n\n"
                "## Troubleshooting {#troubleshooting}\n\n| Symptom | Likely Cause | Fix |\n| --- | --- | --- |\n"
                "| Build fails | Runtime version mismatch | Reinstall locked dependencies and verify runtime version |\n\n"
                "## Further reading\n\nSee [Architecture & Design](../reference/architecture.md#overview) for internals.\n",
                encoding="utf-8",
            )
            (prefix_dir / "reference/architecture.md").write_text(
                "---\ntranslationKey: reference/architecture\nsourceRevision: 1\n---\n\n"
                f"# {title} Architecture & Design\n\n"
                "## Overview & Boundaries {#overview}\n\n"
                "This reference documents module boundaries, data flow, and verification invariants against the current source tree.\n\n"
                "- **In scope**: Verified architecture, configuration contracts, and reproducible checks.\n"
                "- **Out of scope**: Live sprint status and review logs live in task documents, not technical prose.\n\n"
                "## Data Flow {#dataflow}\n\n"
                "```mermaid\nflowchart TD\n  Input[Inputs & Config] --> Core[Core Engine]\n  Core --> Output[Artifacts]\n  Core --> Gate[Deterministic Gates]\n```\n\n"
                "## Configuration & Implementation\n\n"
                "| Module / Key | Responsibility | Source Path |\n"
                "| --- | --- | --- |\n"
                "| Docs Workflow Config | Single-source rules and quality gates | `.soar-devflow/docs.json` |\n\n"
                "## Verification {#verification}\n\n"
                "Run the automated test suite and docs quality gates before merging. Record any discrepancies discovered against source code honestly.\n\n"
                "For operational steps, see [Quickstart](../guide/quickstart.md#steps).\n",
                encoding="utf-8",
            )

    write_lang_pages(root_lang, site_dir)
    for lang in languages[1:]:
        write_lang_pages(lang, site_dir / lang)

    # Starter shot manifest example
    (site_dir / "shots/example.json.disabled").write_text(
        json.dumps([
            {
                "id": "home-overview",
                "page": "/",
                "viewport": [1440, 900],
                "theme": "dark",
                "wait": 1500,
                "annotate": [{"selector": "h1", "label": "1"}],
                "caption": {"zh": "首页界面速览", "en": "Home page overview"},
            }
        ], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Write local docs.json config
    docs_cfg = {
        "site_dir": site_rel,
        "languages": languages,
        "root_language": root_lang,
        "coverage_file": "coverage.json",
        "single_source": {
            "enabled": True,
            "allowed_prefixes": [
                site_rel.rstrip("/") + "/",
                ".agents/skills/",
                ".claude/skills/",
                ".github/",
                ".soar-devflow/",
                "docs/development_management/",
                "docs/releases/",
                "docs/validation/",
            ],
            "allowed_files": [
                "README.md", "README.en.md", "AGENTS.md", "CLAUDE.md",
                "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
            ],
            "check_readme_duplication": True,
        },
        "quality": {
            "min_stub_chars": 200,
            "min_chars": {"zh": 300, "en": 300},
            "require_visual_in": ["guide", "reference"],
        },
        "shots": {
            "manifest_dir": f"{site_rel.rstrip('/')}/shots",
            "output_dir": f"{site_rel.rstrip('/')}/public/shots",
            "upstream_url": "http://127.0.0.1:5173",
            "static_dir": "",
            "routes": {},
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(docs_cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "site_dir": str(site_dir),
        "docs_config": str(config_path),
        "languages": languages,
        "base": base,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path.cwd(), help="Target repository root")
    parser.add_argument("--title", default="Project Docs", help="Documentation site title")
    parser.add_argument("--description", default="Engineering documentation and tutorials", help="Site description")
    parser.add_argument("--languages", default="zh,en", help="Comma-separated languages, e.g. zh or zh,en")
    parser.add_argument("--base", default="/docs/", help="VitePress base path")
    parser.add_argument("--site-dir", default="docs/site", help="Site directory relative to target")
    parser.add_argument("--config-path", default=".soar-devflow/docs.json", help="Docs workflow config path relative to target")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    result = scaffold(
        target=args.target,
        title=args.title,
        description=args.description,
        languages=langs,
        base=args.base,
        site_rel=args.site_dir,
        config_rel=args.config_path,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
