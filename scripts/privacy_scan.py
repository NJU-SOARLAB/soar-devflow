#!/usr/bin/env python3
"""Scan repository files for accidental private data before open-source release.

Checks for Tailscale hostnames/IPs, real user home paths, concrete Feishu/Lark
tenant URLs, Feishu open_id/chat_id literals, private keys, and access tokens.
Exits with code 1 if any disallowed hit is found.
"""
import argparse
from collections import Counter
import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

PLACEHOLDER_USERS = {
    "user", "username", "your-user", "your_user", "you", "example",
    "<user>", "$user", "dev", "runner", "ubuntu",
}
PLACEHOLDER_DOMAINS = {
    "example.feishu.cn", "your-tenant.feishu.cn", "tenant.feishu.cn",
    "applink.feishu.cn", "feishu.cn", "open.feishu.cn",
    "example.larksuite.com", "your-tenant.larksuite.com", "larksuite.com",
    "example.larkoffice.com", "your-tenant.larkoffice.com", "larkoffice.com",
}
PLACEHOLDER_IDS = {
    "ou_xxx", "ou_example", "ou_000000", "oc_xxx", "oc_example", "oc_test", "oc_000000",
}

PATTERNS = {
    "tailscale-hostname": re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b", re.IGNORECASE),
    "tailscale-ip": re.compile(
        r"(?<![\d.])100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}(?![\d.])"
    ),
    "home-path": re.compile(r"/home/([A-Za-z0-9._$<>-]+)"),
    "macos-user-path": re.compile(r"/Users/([A-Za-z0-9._$<>-]+)"),
    "feishu-tenant-host": re.compile(
        r"\b[a-z0-9.-]+\.(?:feishu\.cn|larksuite\.com|larkoffice\.com)\b", re.IGNORECASE
    ),
    "feishu-open-or-chat-id": re.compile(r"\b(?:ou|oc)_[a-zA-Z0-9]{10,}\b"),
    "private-key": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    "access-token": re.compile(
        r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}"
        r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9_-]{32,})\b"
    ),
}

BINARY_SNIFF_BYTES = 8192


def collect_files(root: Path, include_untracked: bool) -> list[str]:
    if (root / ".git").exists():
        cmd = ["git", "-C", str(root), "ls-files", "-z"]
        out = subprocess.run(cmd, check=True, capture_output=True).stdout
        files = [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]
        if include_untracked:
            out2 = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard"],
                check=True, capture_output=True,
            ).stdout
            files += [p for p in out2.decode("utf-8", "surrogateescape").split("\0") if p]
        return sorted(set(files))
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts
    )


def read_text(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    data = path.read_bytes()
    if b"\0" in data[:BINARY_SNIFF_BYTES]:
        return None
    return data.decode("utf-8", "replace")


def keep_match(name: str, match: re.Match) -> bool:
    raw = match.group(0)
    if name in ("home-path", "macos-user-path"):
        return match.group(1).lower() not in PLACEHOLDER_USERS
    if name == "feishu-tenant-host":
        return raw.lower() not in PLACEHOLDER_DOMAINS
    if name == "feishu-open-or-chat-id":
        lower = raw.lower()
        return lower not in PLACEHOLDER_IDS and not lower.startswith(("ou_your", "oc_your", "ou_demo", "oc_demo", "ou_example", "oc_example"))
    return True


def scan(root: Path, files: list[str], allow_globs: list[str]) -> tuple[dict[str, dict[str, list[str]]], int]:
    hits: dict[str, dict[str, list[str]]] = {}
    skipped = 0
    for rel in files:
        if any(fnmatch.fnmatch(rel, pat) for pat in allow_globs):
            skipped += 1
            continue
        text = read_text(root / rel)
        if text is None:
            continue
        file_hits: dict[str, list[str]] = {}
        for name, pattern in PATTERNS.items():
            matched = [m.group(0) for m in pattern.finditer(text) if keep_match(name, m)]
            if matched:
                file_hits[name] = sorted(set(matched))
        if file_hits:
            hits[rel] = file_hits
    return hits, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allow", action="append", default=[], metavar="GLOB")
    parser.add_argument("--include-untracked", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    files = collect_files(args.root, args.include_untracked)
    hits, skipped = scan(args.root, files, args.allow)

    summary = Counter()
    for file_hits in hits.values():
        for pat, vals in file_hits.items():
            summary[pat] += len(vals)

    if args.json:
        print(json.dumps({
            "scanned": len(files),
            "skipped": skipped,
            "clean": not hits,
            "summary": dict(summary),
            "hits": hits,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Scanned {len(files)} files ({skipped} skipped).")
        if not hits:
            print("PASS: No private data or secrets detected.")
        else:
            print("FAIL: Potential private data detected:")
            for rel, file_hits in sorted(hits.items()):
                details = ", ".join(f"{k}={v}" for k, v in sorted(file_hits.items()))
                print(f"  {rel}: {details}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
