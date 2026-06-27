#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter
from pathlib import Path

from issue_clock import resolve_issue_date
from review_issue import AI_STYLE_PATTERNS, REQUIRED_SECTIONS, find_missing_required_sections


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
REPORTS_DIR = ROOT / "data" / "editorial_diffs"
DEFAULT_PROFILE_PATH = ROOT / "config" / "newsletter_profile.json"


SECTION_PATTERN = re.compile(r"(?ms)^## (?P<section>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)")
MAIN_ENTRY_PATTERN = re.compile(r"(?m)^### (?P<title>[^\n]+)$")
SOURCE_PATTERN = re.compile(r"(?m)^\*\*Source:\*\* (?P<source>[^\n]+)$")
LINK_PATTERN = re.compile(r"\]\(https?://[^)]+\)")


def issue_path_for(issue_date: dt.date) -> Path:
    return ISSUES_DIR / f"{issue_date.isoformat()}-daily-newsletter.md"


def benchmark_issue_path() -> Path:
    profile_path = Path(os.environ.get("NEWSLETTER_EDITORIAL_PROFILE_PATH", str(DEFAULT_PROFILE_PATH))).expanduser()
    if profile_path.exists():
        try:
            payload = json.loads(profile_path.read_text(encoding="utf-8"))
            benchmark_rel = payload.get("quality_policy", {}).get("benchmark_issue")
            if benchmark_rel:
                return (ROOT / str(benchmark_rel)).resolve()
        except Exception:
            pass
    return ROOT / "issues" / "daily" / "2026-04-13-daily-newsletter.md"


def previous_issue_path(issue_date: dt.date) -> Path | None:
    paths = sorted(
        path for path in ISSUES_DIR.glob("*-daily-newsletter.md")
        if path.stem < f"{issue_date.isoformat()}-daily-newsletter"
    )
    return paths[-1] if paths else None


def section_bodies(text: str) -> dict[str, str]:
    return {match.group("section").strip(): match.group("body").strip() for match in SECTION_PATTERN.finditer(text)}


def normalize_title(title: str) -> str:
    title = re.sub(r"^\[[0-9.]+\]\s*", "", title)
    title = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return re.sub(r"\s+", " ", title).strip()


def main_titles(text: str) -> list[str]:
    titles = []
    for match in MAIN_ENTRY_PATTERN.finditer(text):
        title = match.group("title").strip()
        if title.lower() in {"short takes", "breaking news", "upcoming investment opportunities", "private-market watchlist"}:
            continue
        titles.append(title)
    return titles


def quick_hits_count(text: str) -> int:
    match = re.search(r"(?ms)^## Quick Hits\n(?P<body>.*?)(?=^## |\Z)", text)
    if not match:
        return 0
    return sum(1 for line in match.group("body").splitlines() if line.startswith("- **"))


def source_counts(text: str) -> Counter[str]:
    return Counter(match.group("source").strip() for match in SOURCE_PATTERN.finditer(text))


def describe_issue(text: str) -> dict[str, object]:
    sections = section_bodies(text)
    sources = source_counts(text)
    top_sources = sources.most_common(8)
    source_total = sum(sources.values())
    return {
        "word_count": len(text.split()),
        "source_count": source_total,
        "link_count": len(LINK_PATTERN.findall(text)),
        "section_count": len(sections),
        "quick_hits_count": quick_hits_count(text),
        "section_word_counts": {section: len(body.split()) for section, body in sections.items()},
        "missing_required_sections": find_missing_required_sections(text),
        "top_sources": [{"source": source, "count": count} for source, count in top_sources],
        "top_source_share": round(top_sources[0][1] / source_total, 4) if top_sources and source_total else 0.0,
        "main_titles": main_titles(text),
    }


def ratio(value: int, baseline: int) -> float | None:
    if not baseline:
        return None
    return round(value / baseline, 4)


def banned_phrase_hits(text: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for label, pattern in AI_STYLE_PATTERNS:
        regex = re.compile(pattern, flags=re.IGNORECASE)
        for match in regex.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            if end == -1:
                end = len(text)
            hits.append(
                {
                    "label": label,
                    "snippet": " ".join(text[start:end].strip().split()),
                }
            )
    return hits


def build_report(issue_date: dt.date) -> dict[str, object]:
    issue_path = issue_path_for(issue_date)
    issue_text = issue_path.read_text(encoding="utf-8")
    benchmark_path = benchmark_issue_path()
    benchmark_text = benchmark_path.read_text(encoding="utf-8") if benchmark_path.exists() else ""
    previous_path = previous_issue_path(issue_date)
    previous_text = previous_path.read_text(encoding="utf-8") if previous_path else ""

    issue_stats = describe_issue(issue_text)
    benchmark_stats = describe_issue(benchmark_text) if benchmark_text else {}
    previous_titles = {normalize_title(title): title for title in main_titles(previous_text)}
    repeated_titles = [
        title for title in issue_stats["main_titles"]
        if normalize_title(str(title)) in previous_titles
    ] if isinstance(issue_stats.get("main_titles"), list) else []

    comparison = {}
    if benchmark_stats:
        comparison = {
            "benchmark_issue": str(benchmark_path),
            "word_count_ratio": ratio(int(issue_stats["word_count"]), int(benchmark_stats["word_count"])),
            "source_count_ratio": ratio(int(issue_stats["source_count"]), int(benchmark_stats["source_count"])),
            "link_count_ratio": ratio(int(issue_stats["link_count"]), int(benchmark_stats["link_count"])),
            "section_count_delta": int(issue_stats["section_count"]) - int(benchmark_stats["section_count"]),
            "quick_hits_delta": int(issue_stats["quick_hits_count"]) - int(benchmark_stats["quick_hits_count"]),
        }

    return {
        "date": issue_date.isoformat(),
        "issue_path": str(issue_path),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "issue": issue_stats,
        "benchmark": benchmark_stats,
        "benchmark_comparison": comparison,
        "previous_issue_comparison": {
            "previous_issue": str(previous_path) if previous_path else "",
            "repeated_main_titles": repeated_titles,
        },
        "banned_phrase_hits": banned_phrase_hits(issue_text),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write an editorial benchmark and previous-issue diff report.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)
    report = build_report(issue_date)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{issue_date.isoformat()}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote editorial diff report to {report_path}")


if __name__ == "__main__":
    main()
