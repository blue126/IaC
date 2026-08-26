#!/usr/bin/env python3
"""Prepare legacy Markdown for OINK without modifying the source docs."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs"
DESTINATION = ROOT / ".hugo-content/docs"
H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
TITLE_RE = re.compile(r"(?m)^title\s*:")


def display_title(value: str) -> str:
    value = re.sub(r"[`*_~]", "", value)
    value = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", value)
    return value.strip()


def fallback_title(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").title()


def prepare_markdown(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0 and TITLE_RE.search(text[4:end]):
            destination.write_text(text, encoding="utf-8")
            return

    lines = text.splitlines(keepends=True)
    title = ""
    heading_index = -1
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        match = None if fenced else H1_RE.match(line.rstrip("\r\n"))
        if match:
            title = display_title(match.group(1))
            heading_index = index
            break

    if not title:
        title = fallback_title(source)
    if heading_index >= 0:
        del lines[heading_index]
        if heading_index < len(lines) and not lines[heading_index].strip():
            del lines[heading_index]

    front_matter = f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\n---\n\n"
    destination.write_text(front_matter + "".join(lines), encoding="utf-8")


def main() -> None:
    shutil.rmtree(DESTINATION, ignore_errors=True)
    for source in sorted(SOURCE.rglob("*")):
        relative = source.relative_to(SOURCE)
        destination = DESTINATION / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.suffix.lower() == ".md":
            destination.parent.mkdir(parents=True, exist_ok=True)
            prepare_markdown(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    for directory in sorted(path for path in DESTINATION.rglob("*") if path.is_dir()):
        index = directory / "_index.md"
        if not index.exists():
            title = fallback_title(directory)
            index.write_text(
                f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\n"
                "page_context_menu: false\nannotation: false\n---\n",
                encoding="utf-8",
            )

    count = len(list(DESTINATION.rglob("*.md")))
    print(f"prepared {count} Markdown files under {DESTINATION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
