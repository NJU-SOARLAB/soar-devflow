#!/usr/bin/env python3
"""Universal deterministic gatekeeper for SOAR DevFlow single-source VitePress docs sites.

Validates:
- Single-source Markdown discipline (no stray technical docs or README paragraph copies)
- Vue template unclosed HTML-like tags in prose (which break VitePress builds)
- Coverage manifest completeness, frontmatter translationKey/sourceRevision, no @include shortcuts
- Minimum content length and visual presence (image / Mermaid / SVG) for guides & references
- Image asset existence, internal link validity, and explicit anchor parity across languages
- Optional UI help-map validation and release-catalog page generation
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

DEFAULT_CONFIG_CANDIDATES = (
    ".soar-devflow/docs.json",
    "docs/site/docs.config.json",
    "site/docs.config.json",
)
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img",
    "input", "link", "meta", "param", "source", "track", "wbr",
}


def discover_config(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve()
    cwd = Path.cwd().resolve()
    for base in (cwd, *cwd.parents):
        for rel in DEFAULT_CONFIG_CANDIDATES:
            candidate = base / rel
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(
        "No docs workflow config found. Pass --config PATH or create .soar-devflow/docs.json."
    )


def resolve_repo_root(config_path: Path, config: dict) -> Path:
    if config.get("repo_root"):
        return (config_path.parent / config["repo_root"]).resolve()
    # Try git top-level first, else walk up from config path
    probe = config_path.parent
    try:
        top = subprocess.check_output(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        if top:
            return Path(top).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if config_path.parent.name in (".soar-devflow", "site"):
        return config_path.parent.parent.resolve()
    return config_path.parent.resolve()


def page_path(site_dir: Path, language: str, root_language: str | None, key: str) -> Path:
    if root_language and language == root_language:
        return site_dir / (key + ".md")
    return site_dir / language / (key + ".md")


def unclosed_elements(text: str) -> list[str]:
    """Return HTML-like tag names opened more often than closed in prose.

    VitePress compiles Markdown as Vue templates, so unescaped placeholders like
    '<store>余量' or '<stage name>' break the build unless quoted as code or '&lt;...&gt;'.
    """
    body = re.sub(r"\A---.*?---", "", text, flags=re.S)
    body = re.sub(r"^(```|~~~).*?^\1", " ", body, flags=re.S | re.M)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"\$\$.*?\$\$|\$[^$\n]+\$", " ", body, flags=re.S)
    body = re.sub(r"(`+)(?:(?!\1).)+?\1", " ", body, flags=re.S)
    balance: dict[str, int] = {}
    for close, name, rest in re.findall(r"<(/?)([A-Za-z][\w-]*)(?![\w-]*[:@])([^<>]*)>", body):
        name_l = name.lower()
        if name_l not in VOID_ELEMENTS and not rest.rstrip().endswith("/"):
            balance[name_l] = balance.get(name_l, 0) + (-1 if close else 1)
    return sorted(name for name, count in balance.items() if count > 0)


def single_source_errors(root: Path, site_dir: Path, cfg: dict) -> list[str]:
    ss = cfg.get("single_source") or {}
    if not ss.get("enabled", True):
        return []

    site_rel = site_dir.relative_to(root).as_posix().rstrip("/") + "/"
    allowed_prefixes = tuple(set(ss.get("allowed_prefixes") or ()) | {site_rel})
    allowed_files = set(ss.get("allowed_files") or (
        "README.md", "README.en.md", "AGENTS.md", "CLAUDE.md",
        "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md",
    ))

    if (root / ".git").exists():
        raw = subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "--", "*.md"],
            text=True,
        )
        files = [line for line in raw.splitlines() if line]
    else:
        files = sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*.md")
            if "node_modules" not in p.parts and ".git" not in p.parts
        )

    errors, readmes = [], []
    for name in files:
        path = root / name
        if not path.is_file() or name.startswith(allowed_prefixes) or name in allowed_files:
            if path.is_file() and path.name == "README.md" and not name.startswith(site_rel):
                readmes.append(path)
            continue
        if path.name == "README.md":
            readmes.append(path)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        nonempty = [line for line in text.splitlines() if line.strip()]
        if len(nonempty) <= 3 and site_rel.rstrip("/") in text:
            continue  # Allowed pointer stub
        errors.append(f"Technical Markdown outside {site_rel.rstrip('/')} (move into site or leave <=3-line pointer): {name}")

    if ss.get("check_readme_duplication", True) and readmes:
        def prose_only(md_text: str) -> str:
            return re.sub(r"^(```|~~~).*?^\1", "", md_text, flags=re.S | re.M)

        paragraphs = {
            p.strip()
            for rpath in readmes
            for p in prose_only(rpath.read_text(encoding="utf-8", errors="replace")).split("\n\n")
            if len(p.strip()) >= 160
        }
        for page in sorted(site_dir.rglob("*.md")):
            if "node_modules" in page.parts or ".vitepress" in page.parts:
                continue
            ptext = prose_only(page.read_text(encoding="utf-8", errors="replace"))
            for paragraph in paragraphs:
                if paragraph in ptext:
                    errors.append(f"Site page duplicates README paragraph: {page.relative_to(root).as_posix()}")
                    break
    return errors


def validate(root: Path, site_dir: Path, config: dict) -> dict:
    languages = list(config.get("languages") or ["zh"])
    root_language = config.get("root_language")
    coverage_path = site_dir / (config.get("coverage_file") or "coverage.json")
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))

    quality = config.get("quality") or {}
    min_stub = int(quality.get("min_stub_chars", 200))
    min_chars = quality.get("min_chars") or {"zh": 2500, "en": 4000}
    require_visual_in = set(quality.get("require_visual_in") or ["guide", "reference"])

    errors: list[str] = []
    checked_pages = 0

    for key, info in coverage.items():
        anchors_by_lang: dict[str, set[str]] = {}
        for lang in languages:
            path = page_path(site_dir, lang, root_language, key)
            if not path.exists():
                errors.append(f"Missing page ({lang}): {path.relative_to(root).as_posix()}")
                continue
            checked_pages += 1
            text = path.read_text(encoding="utf-8")
            rev = info.get("translation_revision")
            if rev is not None:
                if f"translationKey: {key}" not in text or f"sourceRevision: {rev}" not in text:
                    errors.append(f"Frontmatter translationKey/sourceRevision mismatch: {path.relative_to(root).as_posix()}")
            body = re.sub(r"\A---.*?---", "", text, flags=re.S)
            unclosed = unclosed_elements(text)
            if unclosed:
                errors.append(
                    f"Unclosed Vue/HTML-like tag in prose (quote as code or &lt;...&gt;): "
                    f"{path.relative_to(root).as_posix()}: <{'>, <'.join(unclosed)}>"
                )
            # Detect real VitePress include directives outside fenced/inline code.
            no_code = re.sub(r"^(```|~~~).*?^\1", " ", body, flags=re.S | re.M)
            no_code = re.sub(r"(`+)(?:(?!\1).)+?\1", " ", no_code, flags=re.S)
            if re.search(r"<!--\s*@include:|^\s*@include\b", no_code, flags=re.M):
                errors.append(f"Page uses @include instead of holding its own content: {path.relative_to(root).as_posix()}")
            if len(body.strip()) < min_stub:
                errors.append(f"Page content below stub threshold ({min_stub} chars): {path.relative_to(root).as_posix()}")
            if info.get("section") in require_visual_in:
                minimum = int(min_chars.get(lang, min_stub))
                if len(body.strip()) < minimum:
                    errors.append(f"Guide/reference page below {minimum} chars: {path.relative_to(root).as_posix()}")
                if not re.search(r"!\[[^\]]*\]\(|```mermaid|<svg|<img|<iframe", body):
                    errors.append(f"Guide/reference page lacks screenshot/diagram/visual: {path.relative_to(root).as_posix()}")

            # Verify public image references
            for image in re.findall(r"!\[[^\]]*\]\((/[^)\s]+)\)", text):
                if not (site_dir / "public" / image.lstrip("/")).is_file():
                    errors.append(f"Missing public image {image} referenced in {path.relative_to(root).as_posix()}")

            # Verify required anchors
            anchors_by_lang[lang] = set(re.findall(r"\{#([^}]+)\}", text))
            for anchor in info.get("anchors", []):
                if "{#" + anchor + "}" not in text:
                    errors.append(f"Missing required anchor #{anchor} in {path.relative_to(root).as_posix()}")

            # Verify internal markdown links (ignoring code blocks & inline code)
            prose_for_links = re.sub(r"^(```|~~~).*?^\1", " ", body, flags=re.S | re.M)
            prose_for_links = re.sub(r"(`+)(?:(?!\1).)+?\1", " ", prose_for_links, flags=re.S)
            for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)", prose_for_links):
                if target.startswith(("http:", "https:", "mailto:", "#")):
                    continue
                filename, _, anchor = target.partition("#")
                if filename.startswith("/"):
                    # Could be a public asset or a VitePress clean route
                    pub_candidate = (site_dir / "public" / filename.lstrip("/")).resolve()
                    route_rel = filename.lstrip("/").rstrip("/")
                    md_candidates = [
                        (site_dir / (route_rel + ".md")).resolve(),
                        (site_dir / route_rel / "index.md").resolve(),
                    ]
                    if pub_candidate.is_relative_to(site_dir) and pub_candidate.is_file():
                        continue
                    resolved = next((c for c in md_candidates if c.is_relative_to(site_dir) and c.is_file()), None)
                    if not resolved:
                        errors.append(f"Broken root link in {path.relative_to(root).as_posix()}: {target}")
                        continue
                    if anchor and "{#" + anchor + "}" not in resolved.read_text(encoding="utf-8"):
                        errors.append(f"Missing target anchor {target} in {path.relative_to(root).as_posix()}")
                    continue
                link = (path.parent / filename).resolve()
                if not link.is_relative_to(site_dir) or not link.is_file():
                    errors.append(f"Broken/external relative link in {path.relative_to(root).as_posix()}: {target}")
                elif anchor and "{#" + anchor + "}" not in link.read_text(encoding="utf-8"):
                    errors.append(f"Missing link anchor {target} referenced in {path.relative_to(root).as_posix()}")

        if len(anchors_by_lang) > 1:
            base_lang = languages[0]
            base_anchors = anchors_by_lang.get(base_lang, set())
            for other in languages[1:]:
                diff = base_anchors ^ anchors_by_lang.get(other, set())
                if diff:
                    errors.append(f"Explicit anchors differ between {base_lang}/{other} on {key}: {', '.join(sorted(diff))}")

    errors.extend(single_source_errors(root, site_dir, config))

    # Optional help-map verification
    help_map_rel = config.get("help_map_file")
    help_count = 0
    if help_map_rel:
        hp = site_dir / help_map_rel
        if hp.is_file():
            help_map = json.loads(hp.read_text(encoding="utf-8"))
            help_count = len(help_map)
            for hkey, target in help_map.items():
                page, _, anchor = target.partition("#")
                if page not in coverage or (anchor and anchor not in coverage[page].get("anchors", [])):
                    errors.append(f"Invalid help-map target for {hkey}: {target}")

    if errors:
        raise ValueError("\n".join(errors))

    return {
        "passed": True,
        "pages": checked_pages,
        "languages": languages,
        "help_ids": help_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="Path to docs.json config")
    parser.add_argument("--check", action="store_true", help="Run all gates without running npm run build")
    parser.add_argument("--build", action="store_true", help="Run gates and then invoke VitePress build")
    args = parser.parse_args()

    config_path = discover_config(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    root = resolve_repo_root(config_path, config)
    site_dir = (root / config["site_dir"]).resolve()

    try:
        report = validate(root, site_dir, config)
    except ValueError as exc:
        print(f"Docs validation failed:\n{exc}", file=sys.stderr)
        return 1

    if args.build and not args.check:
        subprocess.run(["npm", "run", "build"], cwd=site_dir, check=True)
        sources = sorted(p for p in site_dir.rglob("*.md") if "node_modules" not in p.parts and ".vitepress" not in p.parts)
        report["source_sha256"] = hashlib.sha256(b"".join(p.read_bytes() for p in sources)).hexdigest()
        report["built"] = True

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
