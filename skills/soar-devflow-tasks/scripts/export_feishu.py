#!/usr/bin/env python3
"""Export a clean Markdown subset to Feishu/Lark DocxXML with native Mermaid whiteboards."""
import argparse
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def inline(value: str) -> str:
    pattern = r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))"
    result = []
    for part in re.split(pattern, value):
        if part.startswith("**") and part.endswith("**"):
            result.append("<b>" + escape(part[2:-2]) + "</b>")
        elif part.startswith("`") and part.endswith("`"):
            result.append("<span>" + escape(part[1:-1]) + "</span>")
        elif (link := re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part)):
            label, target = link.groups()
            if not target.startswith(("https://", "http://")):
                raise ValueError("Cloud links must be explicit HTTP(S) URLs: " + target)
            result.append('<a href="' + escape(target, quote=True) + '">' + escape(label) + "</a>")
        else:
            result.append(escape(part))
    return "".join(result)


def render(source: str) -> str:
    source = re.sub(r"\A---.*?---\s*\n", "", source, flags=re.S)
    lines = source.splitlines()
    blocks = []
    i = 0
    title_seen = False
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("# "):
            if title_seen or blocks:
                raise ValueError("Expected a unique leading H1 document title")
            title_text = re.sub(r"\s*\{#[^}]+\}\s*$", "", line[2:])
            blocks.append("<title>" + inline(title_text) + "</title>")
            title_seen = True
            i += 1
        elif (heading := re.fullmatch(r"(#{2,7}) (.+)", line)):
            level = len(heading[1]) - 1
            heading_text = re.sub(r"\s*\{#[^}]+\}\s*$", "", heading[2])
            blocks.append(f'<h{level} seq="auto">' + inline(heading_text) + f"</h{level}>")
            i += 1
        elif line.startswith("```"):
            language = line[3:].strip()
            start = i + 1
            i = start
            while i < len(lines) and lines[i] != "```":
                i += 1
            if i == len(lines):
                raise ValueError("Unterminated code fence")
            content = escape("\n".join(lines[start:i]))
            if language == "mermaid":
                blocks.append('<whiteboard type="mermaid">\n' + content + "\n</whiteboard>")
            else:
                language = {"sh": "bash", "yml": "yaml"}.get(language, language or "plaintext")
                blocks.append('<pre lang="' + escape(language, quote=True) + '"><code>' + content + "</code></pre>")
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                    rows.append(cells)
                i += 1
            if not rows or any(len(row) != len(rows[0]) for row in rows):
                raise ValueError("Invalid Markdown table")
            table = ["<table><thead><tr>"]
            table.extend('<th background-color="light-gray"><p>' + inline(c) + "</p></th>" for c in rows[0])
            table.append("</tr></thead><tbody>")
            for row in rows[1:]:
                table.append("<tr>" + "".join("<td><p>" + inline(c) + "</p></td>" for c in row) + "</tr>")
            table.append("</tbody></table>")
            blocks.append("".join(table))
        elif re.match(r"(?:- |\d+\. )", line):
            ordered = not line.startswith("- ")
            tag = "ol" if ordered else "ul"
            pattern = r"\d+\. (.*)" if ordered else r"- (.*)"
            items = []
            while i < len(lines) and (item := re.fullmatch(pattern, lines[i])):
                items.append("<li>" + inline(item[1]) + "</li>")
                i += 1
            blocks.append("<" + tag + ">" + "".join(items) + "</" + tag + ">")
        else:
            paragraph = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"(?:#|```|\||- |\d+\. )", lines[i]):
                paragraph.append(lines[i])
                i += 1
            blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
    if not title_seen:
        raise ValueError("Missing leading # title")
    xml = "\n\n".join(blocks) + "\n"
    ET.fromstring("<document>" + xml + "</document>")
    return xml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(render(args.source.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
