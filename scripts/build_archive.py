#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
SITE_DIR = ROOT / "site"


def load_sender_module():
    path = ROOT / "scripts" / "send_daily_newsletter.py"
    spec = importlib.util.spec_from_file_location("send_daily_newsletter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_index(entries: list[tuple[dt.date, str, str]]) -> str:
    items = "\n".join(
        f'<li><a href="issues/{date.isoformat()}/index.html">{date.isoformat()}</a> <span>{title}</span></li>'
        for date, title, _ in entries
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Frontier Threads Archive</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 900px; margin: 0 auto; padding: 32px 18px; background: #f8fafc; color: #0f172a; }}
    h1 {{ margin-bottom: 10px; }}
    ul {{ padding-left: 18px; }}
    li {{ margin: 10px 0; }}
    span {{ color: #475569; margin-left: 8px; }}
    a {{ color: #0ea5e9; text-decoration: none; }}
  </style>
</head>
<body>
  <h1>Frontier Threads Archive</h1>
  <p>Published daily issues.</p>
  <ul>
    {items}
  </ul>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static archive pages for GitHub Pages.")
    parser.parse_args()

    sender = load_sender_module()
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[tuple[dt.date, str, str]] = []

    for issue_path in sorted(ISSUES_DIR.glob("*-daily-newsletter.md"), reverse=True):
        date = dt.date.fromisoformat(issue_path.name[:10])
        text = issue_path.read_text(encoding="utf-8")
        title = "Frontier Threads"
        for line in text.splitlines():
            if line.startswith("### ") and "The day's" not in line:
                title = line[4:].strip()
                break
        html = sender.build_html_document(text, date)
        out_dir = SITE_DIR / "issues" / date.isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "index.html"
        out_path.write_text(html, encoding="utf-8")
        entries.append((date, title, issue_path.name))

    index_html = build_index(entries)
    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"Built archive in {SITE_DIR}")


if __name__ == "__main__":
    main()
