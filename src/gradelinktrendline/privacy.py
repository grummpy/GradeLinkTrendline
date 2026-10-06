"""Fixture scan: real-looking email addresses must use example.com."""

from __future__ import annotations

import re
from pathlib import Path

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pyc", ".sqlite"}


def disallowed_emails(text: str) -> list[str]:
    found: list[str] = []
    for match in EMAIL_RE.findall(text):
        domain = match.rsplit("@", 1)[1].lower().rstrip(".")
        if domain != "example.com":
            found.append(match)
    return found


def scan_tree(root: Path) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    if not root.exists():
        return problems
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for email in disallowed_emails(text):
            problems.append((str(path), email))
    return problems
