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
    r"quote unavailable in this run",
    r"Live macro series unavailable",
    r"Insufficient sourced material for this section today\.",
    r"^\*\*Source:\*\* Source$",
    r"^### Nature$",
    r"^### Nature Communications$",
    r"^### arXiv\.org e-Print archive$",
    r"This issue was generated from the configured source pipeline and is intended as a strong first draft for daily review\.",
]

AI_STYLE_PATTERNS = [
    ("Formulaic significance scaffold", r"\b(?:That|This) matters because\b"),
    ("Formulaic summary scaffold", r"\bThe point is\b"),
    ("Formulaic summary scaffold", r"\bThe real question is\b"),
    ("Formulaic summary scaffold", r"\bThe important part is\b"),
    ("Formulaic summary scaffold", r"\bThis is the kind of\b"),
    ("Meta-evaluative framing", r"\bis (?:useful|interesting|important|valuable) because\b"),
    ("Meta-evaluative framing", r"\b(?:analysis|coverage|essay|feature|overview|paper|piece|report|story) is (?:useful|interesting|important|valuable)\b"),
    ("Comparative hand-holding", r"\bThe better\b"),
    ("Comparative hand-holding", r"\bThe stronger\b"),
    ("Generic reminder framing", r"\bis a reminder that\b"),
    ("Generic watchlist framing", r"\bworth watching because\b"),
    ("Generic escalation framing", r"\bbecomes more (?:useful|interesting|honest|serious)\b"),
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
SECTION_HEADING_PATTERN = re.compile(r"(?m)^## (?P<section>[^\n]+)$")
REQUIRED_SECTIONS = [
    "Markets & Economy",
    "Need To Know",
    "Research Watch",
    "World News",
    "Philosophy",
    "Biology",
    "Psychology and Neuroscience",
    "Health and Medicine",
    "Sociology and Anthropology",
    "Technology",
    "Robotics",
    "AI",
    "Engineering",
    "Mathematics",
    "Historical Discoveries",
    "Archaeology",
    "Tools You Can Use",
    "Entertainment",
    "Travel",
    "Idea Of The Day",
]
SHORT_TAKES_REQUIRED_SECTIONS = [
    "Research Watch",
    "World News",
    "Philosophy",
    "Biology",
    "Psychology and Neuroscience",
    "Health and Medicine",
    "Sociology and Anthropology",
    "Technology",
    "Robotics",
    "AI",
    "Engineering",
    "Mathematics",
    "Historical Discoveries",
    "Archaeology",
    "Tools You Can Use",
]
BREAKING_NEWS_REQUIRED_SECTIONS = [
    "World News",
]
MIN_SHORT_TAKES_ITEMS = 3
MIN_BREAKING_NEWS_ITEMS = 5


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


def find_missing_required_sections(text: str) -> list[str]:
    present_sections = {
        match.group("section").strip()
        for match in SECTION_HEADING_PATTERN.finditer(text)
    }
    return [section for section in REQUIRED_SECTIONS if section not in present_sections]


def find_missing_required_subsections(text: str) -> list[str]:
    findings: list[str] = []
    for section in SHORT_TAKES_REQUIRED_SECTIONS:
        match = re.search(rf"(?ms)^## {re.escape(section)}\n(?P<body>.*?)(?=^## |\Z)", text)
        if not match:
            continue
        body = match.group("body")
        short_takes_match = re.search(r"(?ms)^### Short Takes\n(?P<body>.*?)(?=^### |\Z)", body)
        if not short_takes_match:
            findings.append(f"Missing Short Takes subsection in: {section}")
            continue
        short_takes_count = sum(1 for line in short_takes_match.group("body").splitlines() if line.startswith("- "))
        if short_takes_count < MIN_SHORT_TAKES_ITEMS:
            findings.append(
                f"Short Takes has too few items in {section}: {short_takes_count} < {MIN_SHORT_TAKES_ITEMS}"
            )
    for section in BREAKING_NEWS_REQUIRED_SECTIONS:
        match = re.search(rf"(?ms)^## {re.escape(section)}\n(?P<body>.*?)(?=^## |\Z)", text)
        if not match:
            continue
        body = match.group("body")
        breaking_news_match = re.search(r"(?ms)^### Breaking News\n(?P<body>.*?)(?=^### |\Z)", body)
        if not breaking_news_match:
            findings.append(f"Missing Breaking News subsection in: {section}")
            continue
        breaking_news_count = sum(1 for line in breaking_news_match.group("body").splitlines() if line.startswith("- "))
        if breaking_news_count < MIN_BREAKING_NEWS_ITEMS:
            findings.append(
                f"Breaking News has too few items in {section}: {breaking_news_count} < {MIN_BREAKING_NEWS_ITEMS}"
            )
    return findings


def find_ai_style_patterns(text: str) -> list[str]:
    findings: list[str] = []
    for label, pattern in AI_STYLE_PATTERNS:
        regex = re.compile(pattern, flags=re.IGNORECASE)
        for match in regex.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            if end == -1:
                end = len(text)
            snippet = " ".join(text[start:end].strip().split())
            findings.append(f"{label}: {snippet}")
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

    missing_sections = find_missing_required_sections(text)
    for section in missing_sections:
        findings.append(f"Missing required section: {section}")

    findings.extend(find_missing_required_subsections(text))

    findings.extend(find_thin_main_entries(text))
    findings.extend(find_ai_style_patterns(text))

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
