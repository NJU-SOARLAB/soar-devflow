#!/usr/bin/env python3
"""Install SOAR DevFlow skills into a project workspace or user global skill directories."""
import argparse
import json
import os
from pathlib import Path
import shutil

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_SRC = REPO_ROOT / "skills"
ALL_SKILLS = ("soar-devflow-setup", "soar-devflow-tasks", "soar-devflow-docs")


def install_skill(src: Path, dst: Path, mode: str) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        else:
            shutil.rmtree(dst)
    if mode == "symlink":
        dst.symlink_to(src.resolve())
        return "symlink"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"))
    return "copy"


def link_claude_mirror(agents_dir: Path, claude_dir: Path, skill_name: str) -> Path:
    claude_dir.mkdir(parents=True, exist_ok=True)
    target = claude_dir / skill_name
    if target.is_symlink() or target.exists():
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)
    rel = os.path.relpath(agents_dir / skill_name, claude_dir)
    target.symlink_to(rel)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path.cwd(), help="Target repo root (workspace) or home dir (global)")
    parser.add_argument("--scope", choices=("workspace", "global"), default="workspace")
    parser.add_argument("--mode", choices=("copy", "symlink"), default="copy", help="Copy files (portable) or symlink to cloned repo")
    parser.add_argument("--skills", default=",".join(ALL_SKILLS), help="Comma-separated skill names to install")
    parser.add_argument("--no-claude-link", action="store_true", help="Do not create .claude/skills symlinks")
    args = parser.parse_args()

    selected = [s.strip() for s in args.skills.split(",") if s.strip()]
    for name in selected:
        if name not in ALL_SKILLS:
            raise ValueError(f"Unknown skill '{name}'. Available: {', '.join(ALL_SKILLS)}")

    base = Path.home() if args.scope == "global" else args.target.resolve()
    agents_skills = base / ".agents/skills"
    claude_skills = base / ".claude/skills"
    installed = []

    for name in selected:
        src = SKILLS_SRC / name
        dst = agents_skills / name
        how = install_skill(src, dst, args.mode)
        entry = {"skill": name, "path": str(dst), "mode": how}
        if not args.no_claude_link:
            mirror = link_claude_mirror(agents_skills, claude_skills, name)
            entry["claude_link"] = str(mirror)
        installed.append(entry)

    print(json.dumps({"scope": args.scope, "base": str(base), "installed": installed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
