#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generate_issue import MARKET_TICKERS, build_macro_lines
from issue_clock import resolve_issue_date
from openai_pipeline import review_min_score, strict_publish


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
RESCUE_MIN_NON_OPTIONAL_SECTIONS_WITH_ENTRIES = 5
RESCUE_MIN_TOTAL_ENTRIES = 12
RESCUE_MIN_CORE_SECTIONS_WITH_ENTRIES = 3
MIN_CHECKED_SOURCE_COVERAGE_RATIO = 0.30
MIN_DIRECT_SOURCE_ENTRIES = 10
MAX_GOOGLE_WRAPPER_LINK_RATIO = 0.95
MAX_HIGH_SUPPORT_DUPLICATE_CLUSTERS = 5
HIGH_SUPPORT_DUPLICATE_CLUSTER_THRESHOLD = 5


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
    listed_source_count = 0
    checked_source_count = 0
    high_support_duplicate_clusters: list[str] = []
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
        source_coverage = section_meta.get("source_coverage", {}) if isinstance(section_meta, dict) else {}
        if isinstance(source_coverage, dict):
            listed_source_count += int(source_coverage.get("listed_source_count", 0) or 0)
            checked_source_count += int(source_coverage.get("checked_source_count", 0) or 0)
        story_clusters = section_meta.get("story_clusters", []) if isinstance(section_meta, dict) else []
        if isinstance(story_clusters, list):
            for cluster in story_clusters:
                if not isinstance(cluster, dict):
                    continue
                support_count = int(cluster.get("support_count", 0) or 0)
                if support_count >= HIGH_SUPPORT_DUPLICATE_CLUSTER_THRESHOLD:
                    high_support_duplicate_clusters.append(
                        f"{section}: {cluster.get('lead_title', '')} ({support_count} sources)"
                    )

    entries = [
        entry
        for section_entries in sections.values()
        if isinstance(section_entries, list)
        for entry in section_entries
        if isinstance(entry, dict)
    ]
    direct_source_entries = [
        entry for entry in entries
        if str(entry.get("source_type", "")) != "google-news-rss"
    ]
    google_wrapper_links = [
        str(entry.get("link", ""))
        for entry in entries
        if "news.google.com" in str(entry.get("link", ""))
    ]
    source_coverage_ratio = checked_source_count / listed_source_count if listed_source_count else 0.0
    google_wrapper_ratio = len(google_wrapper_links) / len(entries) if entries else 0.0

    findings: list[str] = []
    core_gaps: list[str] = []
    populated_core_sections = 0
    for section, minimum in CORE_SECTION_MINIMUMS.items():
        actual = section_entry_counts.get(section, 0)
        if actual > 0:
            populated_core_sections += 1
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
    if listed_source_count and source_coverage_ratio < MIN_CHECKED_SOURCE_COVERAGE_RATIO:
        findings.append(
            f"Too little listed-source coverage: {checked_source_count}/{listed_source_count} checked"
        )
    if len(direct_source_entries) < MIN_DIRECT_SOURCE_ENTRIES:
        findings.append(
            f"Too few direct-source/newsletter candidates: {len(direct_source_entries)}/{MIN_DIRECT_SOURCE_ENTRIES}"
        )
    if entries and google_wrapper_ratio > MAX_GOOGLE_WRAPPER_LINK_RATIO:
        findings.append(
            f"Too many unresolved Google News wrapper candidate links: {len(google_wrapper_links)}/{len(entries)}"
        )
    if len(high_support_duplicate_clusters) > MAX_HIGH_SUPPORT_DUPLICATE_CLUSTERS:
        findings.append(
            f"Too many high-support duplicate story clusters: {len(high_support_duplicate_clusters)}/{MAX_HIGH_SUPPORT_DUPLICATE_CLUSTERS}"
        )

    rescue_ready = (
        sections_with_entries >= RESCUE_MIN_NON_OPTIONAL_SECTIONS_WITH_ENTRIES
        and total_entries >= RESCUE_MIN_TOTAL_ENTRIES
        and populated_core_sections >= RESCUE_MIN_CORE_SECTIONS_WITH_ENTRIES
    )
    hard_fail = not rescue_ready and (
        total_entries == 0
        or sections_with_entries < 3
        or populated_core_sections < 2
    )

    return {
        "passed": len(findings) == 0,
        "findings": findings,
        "section_entry_counts": section_entry_counts,
        "total_entries": total_entries,
        "sections_with_entries": sections_with_entries,
        "populated_core_sections": populated_core_sections,
        "failed_queries": failed_queries,
        "empty_queries": empty_queries,
        "source_quality": {
            "listed_source_count": listed_source_count,
            "checked_source_count": checked_source_count,
            "checked_source_coverage_ratio": round(source_coverage_ratio, 4),
            "direct_source_entries": len(direct_source_entries),
            "google_wrapper_links": len(google_wrapper_links),
            "google_wrapper_link_ratio": round(google_wrapper_ratio, 4),
            "high_support_duplicate_clusters": high_support_duplicate_clusters,
        },
        "rescue_ready": rescue_ready,
        "hard_fail": hard_fail,
    }


def summarize_market_health(issue_date: dt.date) -> dict[str, object]:
    from generate_issue import build_markets_section  # Imported lazily to keep this module lightweight in tests.

    _lines, failures = build_markets_section(issue_date, allow_placeholders=False)
    quote_failures = list(failures["quotes"])
    macro_failures = list(failures["macro"])
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
            "quote unavailable in this run",
            "Live macro series unavailable",
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
    market_report = summarize_market_health(issue_date)
    findings = [*candidate_report["findings"], *market_report["findings"]]

    strict = strict_publish()
    if findings and (strict or not candidate_report["rescue_ready"]):
        cleanup_placeholder_artifacts(issue_date)
        write_failure_reports(issue_date, findings, candidate_report, market_report)
        print(f"Preflight failed for {issue_date.isoformat()}")
        if strict:
            print("- Strict publish mode is enabled; rescue-mode continuation is disabled.")
        for finding in findings:
            print(f"- {finding}")
        raise SystemExit(1)

    if findings:
        print(f"Preflight warnings for {issue_date.isoformat()} (continuing in rescue mode)")
        for finding in findings:
            print(f"- {finding}")
        return

    print(f"Preflight passed for {issue_date.isoformat()}")


if __name__ == "__main__":
    main()
