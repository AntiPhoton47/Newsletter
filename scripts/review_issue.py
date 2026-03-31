#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from issue_clock import resolve_issue_date


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
    r"This issue was generated from the configured source pipeline and is intended as a strong first draft for daily review\.",
]

LOW_VALUE_TITLE_PATTERNS = [
    r"^Correction:",
    r"\bjob with\b",
    r"\bChief Architect\b",
    r"^Calls for papers\b",
    r"^My Courses\b",
    r"^Search Humanities and Social Sciences Communications\b",
    r"^Human Behavior CFP\b",
    r"^Scientific Reports$",
]

MAIN_ENTRY_PATTERN = re.compile(
    r"(?ms)^### (?P<title>[^\n]+)\n\n\*\*Source:\*\* (?P<source>[^\n]+)\n\n(?P<body>.+?)(?=\n\n\*\*Link:\*\*|\n\n### |\n\n## |\Z)"
)
QUICK_HITS_PATTERN = re.compile(r"(?ms)^## Quick Hits\n(?P<body>.*?)(?=^## |\Z)")


def normalize_compact(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(rf"\b(?:nature|arxiv|ap news|iai tv|github|quanta magazine|scientific reports|ieee spectrum|ieee|oecd|imf|world health organization \(who\)|who)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def quick_hits_count(text: str) -> int:
    match = QUICK_HITS_PATTERN.search(text)
    if not match:
        return 0
    body = match.group("body")
    return sum(1 for line in body.splitlines() if line.startswith("- **"))


def find_thin_main_entries(text: str) -> list[str]:
    findings: list[str] = []
    for match in MAIN_ENTRY_PATTERN.finditer(text):
        title = match.group("title").strip()
        body = match.group("body").strip()
        normalized_title = normalize_compact(title)
        normalized_body = normalize_compact(body)
        if any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in LOW_VALUE_TITLE_PATTERNS):
            findings.append(f"Low-value main entry title: {title}")
            continue
        if len(normalized_body) < 90:
            findings.append(f"Main entry is too thin: {title}")
            continue
        if normalized_body == normalized_title or normalized_body.startswith(normalized_title):
            findings.append(f"Main entry mostly repeats its headline: {title}")
    return findings


def review_text(text: str) -> dict[str, object]:
    findings: list[str] = []
    lines = text.splitlines()
    for pattern in BAD_PATTERNS:
        regex = re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)
        if regex.search(text):
            findings.append(f"Matched bad pattern: {pattern}")

    if "## Quick Hits" in text:
        section_quick_hits_count = quick_hits_count(text)
    else:
        section_quick_hits_count = 0
        findings.append("Missing Quick Hits section")
    if section_quick_hits_count and not 12 <= section_quick_hits_count <= 16:
        findings.append(f"Quick Hits count out of range: {section_quick_hits_count}")

    section_count = sum(1 for line in lines if line.startswith("## ")) - 1
    if section_count < 10:
        findings.append("Issue has too few sections")

    findings.extend(find_thin_main_entries(text))

    passed = len(findings) == 0
    return {
        "passed": passed,
        "findings": findings,
        "quick_hits_count": section_quick_hits_count,
        "section_count": section_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run quality checks on a generated issue.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)

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
