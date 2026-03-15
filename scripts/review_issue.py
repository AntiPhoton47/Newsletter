#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
REPORTS_DIR = ROOT / "data" / "reviews"


BAD_PATTERNS = [
    r"Feed fetch failed",
    r"\bnews\.google\.com\b",
    r"\bupdate manually\b",
    r"\bdata unavailable\b",
    r"^\*\*Source:\*\* Source$",
    r"^### Nature$",
    r"^### Nature Communications$",
    r"^### arXiv\.org e-Print archive$",
]


def review_text(text: str) -> dict[str, object]:
    findings: list[str] = []
    lines = text.splitlines()
    for pattern in BAD_PATTERNS:
        regex = re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
        if regex.search(text):
            findings.append(f"Matched bad pattern: {pattern}")

    if "## Quick Hits" in text:
        quick_hits_count = sum(1 for line in lines if line.startswith("- **") and "## Markets & Economy" not in line)
    else:
        quick_hits_count = 0
        findings.append("Missing Quick Hits section")

    section_count = sum(1 for line in lines if line.startswith("## ")) - 1
    if section_count < 10:
        findings.append("Issue has too few sections")

    passed = len(findings) == 0
    return {
        "passed": passed,
        "findings": findings,
        "quick_hits_count": quick_hits_count,
        "section_count": section_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run quality checks on a generated issue.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()

    issue_date = dt.date.today()
    if args.date:
        issue_date = dt.date.fromisoformat(args.date)

    issue_path = ISSUES_DIR / f"{issue_date.isoformat()}-daily-newsletter.md"
    text = issue_path.read_text(encoding="utf-8")
    report = review_text(text)
    report["date"] = issue_date.isoformat()
    report["issue"] = str(issue_path)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{issue_date.isoformat()}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if report["passed"]:
        print(f"Review passed: {issue_path}")
        return

    print(f"Review failed: {issue_path}")
    for finding in report["findings"]:
        print(f"- {finding}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
