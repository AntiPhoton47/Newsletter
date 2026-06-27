#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
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
MAIN_HEADING_PATTERN = re.compile(r"(?m)^### (?P<title>[^\n]+)$")
SECTION_PATTERN = re.compile(r"(?ms)^## (?P<section>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)")
SHORT_TAKE_HEADING_PATTERN = re.compile(r"(?ms)^### Short Takes\n(?P<body>.*?)(?=^### |\Z)")
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


def normalize_title_for_repeat_check(title: str) -> str:
    title = re.sub(r"^\[[0-9.]+\]\s*", "", title)
    title = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return re.sub(r"\s+", " ", title).strip()


def title_tokens(title: str) -> set[str]:
    normalized = normalize_title_for_repeat_check(title)
    stopwords = {
        "a",
        "an",
        "and",
        "announces",
        "at",
        "after",
        "as",
        "by",
        "for",
        "from",
        "in",
        "into",
        "new",
        "now",
        "of",
        "on",
        "or",
        "over",
        "the",
        "to",
        "update",
        "with",
    }
    return {
        token
        for token in normalized.split()
        if len(token) > 2 and token not in stopwords
    }


def titles_overlap(title_a: str, title_b: str) -> bool:
    normalized_a = normalize_title_for_repeat_check(title_a)
    normalized_b = normalize_title_for_repeat_check(title_b)
    if normalized_a and normalized_a == normalized_b:
        return True

    tokens_a = title_tokens(title_a)
    tokens_b = title_tokens(title_b)
    if not tokens_a or not tokens_b:
        return False

    overlap = len(tokens_a & tokens_b)
    return overlap >= 3 or (overlap / min(len(tokens_a), len(tokens_b))) >= 0.75


def main_entry_titles(text: str) -> list[str]:
    titles = []
    for match in MAIN_HEADING_PATTERN.finditer(text):
        title = match.group("title").strip()
        if title.lower() in {"short takes", "breaking news", "upcoming investment opportunities", "private-market watchlist"}:
            continue
        titles.append(title)
    return titles


def previous_issue_text(issue_date: dt.date) -> str:
    previous_issues = sorted(
        path for path in ISSUES_DIR.glob("*-daily-newsletter.md")
        if path.stem < f"{issue_date.isoformat()}-daily-newsletter"
    )
    if not previous_issues:
        return ""
    return previous_issues[-1].read_text(encoding="utf-8")


def find_repeated_main_entries(text: str, issue_date: dt.date | None) -> list[str]:
    if issue_date is None:
        return []
    previous_text = previous_issue_text(issue_date)
    if not previous_text:
        return []
    previous_titles = {normalize_title_for_repeat_check(title) for title in main_entry_titles(previous_text)}
    repeated = [
        title for title in main_entry_titles(text)
        if normalize_title_for_repeat_check(title) in previous_titles
    ]
    return [f"Main entry repeats previous issue title without an explicit repeat allowance: {title}" for title in repeated]


def strip_trailing_link(text: str) -> str:
    return re.sub(r"\s*\[[^\]]+\]\([^)]+\)\s*$", "", text).strip()


def parse_short_take_line(line: str) -> tuple[str, str]:
    content = line[2:].strip()
    match = re.match(r"^\*\*(?P<title>.+?)\*\*(?P<detail>.*)$", content)
    if not match:
        return ("", strip_trailing_link(content))

    raw_title = match.group("title").strip()
    detail = strip_trailing_link(match.group("detail").strip())
    if raw_title.endswith(":") and detail:
        return (raw_title.rstrip(":.;"), detail)
    if not detail and (len(raw_title.split()) >= 8 or "," in raw_title):
        return ("", strip_trailing_link(raw_title))
    return (raw_title.rstrip(":.;"), detail)


def find_short_take_quality_issues(text: str) -> list[str]:
    findings: list[str] = []

    for section_match in SECTION_PATTERN.finditer(text):
        section = section_match.group("section").strip()
        body = section_match.group("body")

        main_titles = [
            match.group("title").strip()
            for match in MAIN_HEADING_PATTERN.finditer(body)
            if match.group("title").strip().lower() not in {
                "short takes",
                "breaking news",
                "upcoming investment opportunities",
                "private-market watchlist",
            }
        ]

        short_takes_match = SHORT_TAKE_HEADING_PATTERN.search(body)
        if not short_takes_match:
            continue

        seen_short_take_titles: list[str] = []
        for raw_line in short_takes_match.group("body").splitlines():
            if not raw_line.startswith("- "):
                continue

            title, detail = parse_short_take_line(raw_line)
            label = title or raw_line[2:].strip()
            if title and any(titles_overlap(title, main_title) for main_title in main_titles):
                findings.append(f"Short Take duplicates a main entry in {section}: {title}")
            if title and any(titles_overlap(title, existing) for existing in seen_short_take_titles):
                findings.append(f"Short Take repeats another short take in {section}: {title}")
            if title:
                seen_short_take_titles.append(title)

            normalized_detail = normalize_compact(detail)
            if len(normalized_detail) < 40 or len(normalized_detail.split()) < 6:
                findings.append(f"Short Take is too thin in {section}: {label}")
                continue
            if title and (
                normalized_detail == normalize_compact(title)
                or normalized_detail.startswith(normalize_compact(title))
            ):
                findings.append(f"Short Take mostly repeats its headline in {section}: {title}")

    return findings


def review_text(text: str, issue_date: dt.date | None = None) -> dict[str, object]:
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
    findings.extend(find_short_take_quality_issues(text))
    findings.extend(find_ai_style_patterns(text))
    findings.extend(find_repeated_main_entries(text, issue_date))

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
    report = review_text(text, issue_date)
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
