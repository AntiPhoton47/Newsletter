#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generate_issue import MARKET_TICKERS, build_macro_lines
from issue_clock import resolve_issue_date
from openai_pipeline import review_min_score


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_DIR = ROOT / "data" / "candidates"
ISSUES_DIR = ROOT / "issues" / "daily"
OUTPUT_DIR = ROOT / "output"
REVIEWS_DIR = ROOT / "data" / "reviews"
AI_REVIEWS_DIR = ROOT / "data" / "ai_reviews"

OPTIONAL_SECTIONS = {"Entertainment", "Travel"}
CORE_SECTION_MINIMUMS = {
    "Need To Know": 1,
    "Research Watch": 2,
    "World News": 2,
    "AI": 1,
    "Tools You Can Use": 1,
}
MIN_NON_OPTIONAL_SECTIONS_WITH_ENTRIES = 10
MIN_TOTAL_ENTRIES = 30
MAX_FAILED_QUERIES = 3
MIN_AVAILABLE_QUOTES = 12
MIN_AVAILABLE_MACRO_LINES = 4


def issue_path_for(issue_date: dt.date) -> Path:
    return ISSUES_DIR / f"{issue_date.isoformat()}-daily-newsletter.md"


def preview_path_for(issue_date: dt.date) -> Path:
    return OUTPUT_DIR / f"{issue_date.isoformat()}-daily-newsletter.html"


def load_candidates(issue_date: dt.date) -> dict:
    path = CANDIDATES_DIR / f"{issue_date.isoformat()}.json"
    if not path.exists():
        raise SystemExit(f"Candidates file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_candidate_health(payload: dict) -> dict[str, object]:
    sections = payload.get("sections", {})
    fetch_meta = payload.get("fetch", {})
    fetch_sections = fetch_meta.get("sections", {}) if isinstance(fetch_meta, dict) else {}
    section_entry_counts: dict[str, int] = {}
    total_entries = 0
    sections_with_entries = 0

    for section, entries in sections.items():
        if not isinstance(entries, list):
            continue
        count = len(entries)
        section_entry_counts[section] = count
        if section in OPTIONAL_SECTIONS:
            continue
        total_entries += count
        if count > 0:
            sections_with_entries += 1

    failed_queries: list[str] = []
    empty_queries: list[str] = []
    for section, section_meta in fetch_sections.items():
        queries = section_meta.get("queries", []) if isinstance(section_meta, dict) else []
        for query_meta in queries:
            query = str(query_meta.get("query", "")).strip()
            status = str(query_meta.get("status", "")).strip().lower()
            entry_count = int(query_meta.get("entry_count", 0) or 0)
            if status == "failed":
                failed_queries.append(f"{section}: {query}")
            elif status == "ok" and entry_count == 0:
                empty_queries.append(f"{section}: {query}")

    findings: list[str] = []
    core_gaps: list[str] = []
    for section, minimum in CORE_SECTION_MINIMUMS.items():
        actual = section_entry_counts.get(section, 0)
        if actual < minimum:
            core_gaps.append(f"{section} ({actual}/{minimum})")
    if core_gaps:
        findings.append("Core section coverage below minimum: " + ", ".join(core_gaps))
    if sections_with_entries < MIN_NON_OPTIONAL_SECTIONS_WITH_ENTRIES:
        findings.append(
            f"Too few populated non-optional sections: {sections_with_entries}/{MIN_NON_OPTIONAL_SECTIONS_WITH_ENTRIES}"
        )
    if total_entries < MIN_TOTAL_ENTRIES:
        findings.append(f"Too few total non-optional candidates: {total_entries}/{MIN_TOTAL_ENTRIES}")
    if len(failed_queries) > MAX_FAILED_QUERIES:
        findings.append(f"Too many failed source queries: {len(failed_queries)}/{MAX_FAILED_QUERIES}")

    return {
        "passed": len(findings) == 0,
        "findings": findings,
        "section_entry_counts": section_entry_counts,
        "total_entries": total_entries,
        "sections_with_entries": sections_with_entries,
        "failed_queries": failed_queries,
        "empty_queries": empty_queries,
    }


def summarize_market_health() -> dict[str, object]:
    quote_failures: list[str] = []
    for label, symbol in MARKET_TICKERS:
        from generate_issue import fetch_yahoo_quote  # Imported lazily to keep this module lightweight in tests.

        price, move = fetch_yahoo_quote(symbol)
        if price == "data unavailable" or move == "live quote unavailable":
            quote_failures.append(label)

    _, macro_failures = build_macro_lines(allow_placeholders=False)
    available_quotes = len(MARKET_TICKERS) - len(quote_failures)
    available_macro_lines = 5 - len(macro_failures)

    findings: list[str] = []
    if available_quotes < MIN_AVAILABLE_QUOTES:
        findings.append(f"Too few live market quotes available: {available_quotes}/{MIN_AVAILABLE_QUOTES}")
    if available_macro_lines < MIN_AVAILABLE_MACRO_LINES:
        findings.append(f"Too few live macro series available: {available_macro_lines}/{MIN_AVAILABLE_MACRO_LINES}")

    return {
        "passed": len(findings) == 0,
        "findings": findings,
        "available_quotes": available_quotes,
        "available_macro_lines": available_macro_lines,
        "quote_failures": quote_failures,
        "macro_failures": macro_failures,
    }


def write_failure_reports(issue_date: dt.date, findings: list[str], candidate_report: dict, market_report: dict) -> None:
    issue_path = issue_path_for(issue_date)
    review_report = {
        "passed": False,
        "stage": "preflight",
        "findings": findings,
        "candidate_summary": candidate_report,
        "market_summary": market_report,
        "date": issue_date.isoformat(),
        "issue": str(issue_path),
    }
    ai_review_report = {
        "passed": False,
        "ready_to_send": False,
        "overall_score": 0,
        "summary": "AI review skipped because pipeline preflight checks failed before issue generation.",
        "strengths": [],
        "findings": [
            {
                "severity": "high",
                "section": "Pipeline preflight",
                "issue": finding,
                "recommendation": "Restore source and market data coverage, then rerun the pipeline.",
            }
            for finding in findings
        ],
        "bias_assessment": "Not evaluated because no publication-ready draft was generated.",
        "recommended_action": "Fix upstream input availability before rerunning publication automation.",
        "date": issue_date.isoformat(),
        "issue": str(issue_path),
        "model": "skipped-preflight",
        "minimum_score": review_min_score(),
    }

    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    AI_REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / f"{issue_date.isoformat()}.json").write_text(
        json.dumps(review_report, indent=2),
        encoding="utf-8",
    )
    (AI_REVIEWS_DIR / f"{issue_date.isoformat()}.json").write_text(
        json.dumps(ai_review_report, indent=2),
        encoding="utf-8",
    )


def cleanup_placeholder_artifacts(issue_date: dt.date) -> None:
    issue_path = issue_path_for(issue_date)
    if issue_path.exists():
        text = issue_path.read_text(encoding="utf-8")
        explicit_placeholders = (
            "Feed fetch failed",
            "data unavailable",
            "**Source:** Source",
            "Insufficient sourced material for this section today.",
        )
        if any(token in text for token in explicit_placeholders):
            issue_path.unlink()

    preview_path = preview_path_for(issue_date)
    if preview_path.exists():
        preview_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preflight input checks before generating a newsletter issue.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)

    candidates = load_candidates(issue_date)
    candidate_report = summarize_candidate_health(candidates)
    market_report = summarize_market_health()
    findings = [*candidate_report["findings"], *market_report["findings"]]

    if findings:
        cleanup_placeholder_artifacts(issue_date)
        write_failure_reports(issue_date, findings, candidate_report, market_report)
        print(f"Preflight failed for {issue_date.isoformat()}")
        for finding in findings:
            print(f"- {finding}")
        raise SystemExit(1)

    print(f"Preflight passed for {issue_date.isoformat()}")


if __name__ == "__main__":
    main()
