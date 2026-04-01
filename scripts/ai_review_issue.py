#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from issue_clock import resolve_issue_date
from openai_pipeline import ai_enabled, call_openai_json, review_min_score, review_model
from review_issue import review_text


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
REPORTS_DIR = ROOT / "data" / "ai_reviews"
SELECTION_CRITERIA_PATH = ROOT / "selection_criteria.md"
SOURCES_PATH = ROOT / "sources.md"
BENCHMARK_ISSUE_PATH = ROOT / "issues" / "daily" / "2026-03-15-daily-newsletter.md"


def issue_path_for(issue_date: dt.date) -> Path:
    return ISSUES_DIR / f"{issue_date.isoformat()}-daily-newsletter.md"


def build_prompt(issue_date: dt.date, issue_text: str, selection_criteria: str, sources_text: str, benchmark_issue: str) -> str:
    return f"""You are the release editor for Frontier Threads, a daily science, technology, world affairs, and ideas newsletter.

Review the following newsletter draft for publication readiness.

Evaluate on:
- factual conservatism and whether claims stay close to the provided titles/summaries
- clarity and usefulness
- section balance and duplication
- source quality and labeling
- internal consistency
- tone neutrality and avoidance of unnecessary political or social bias
- whether this is good enough for the user to wake up and read without manual cleanup
- whether the level of detail, explanatory substance, and editorial polish is at least on par with the benchmark March 15, 2026 issue

Scoring:
- overall_score: integer 0-100
- passed: true only if the issue is publication-ready
- ready_to_send: true only if you would allow automatic email delivery without human review

Return valid JSON with exactly these keys:
- passed
- ready_to_send
- overall_score
- summary
- strengths
- findings
- bias_assessment
- recommended_action

Rules for JSON:
- strengths: array of short strings
- findings: array of objects with keys severity, section, issue, recommendation
- severity must be one of high, medium, low

Minimum target score: {review_min_score()}
Issue date: {issue_date.isoformat()}

Selection criteria:
{selection_criteria}

Source registry:
{sources_text}

Benchmark issue:
{benchmark_issue}

Issue draft:
{issue_text}
"""


def validate_report(report: dict) -> dict:
    normalized = {
        "passed": bool(report.get("passed")),
        "ready_to_send": bool(report.get("ready_to_send")),
        "overall_score": int(report.get("overall_score", 0)),
        "summary": str(report.get("summary", "")).strip(),
        "strengths": report.get("strengths", []),
        "findings": report.get("findings", []),
        "bias_assessment": str(report.get("bias_assessment", "")).strip(),
        "recommended_action": str(report.get("recommended_action", "")).strip(),
    }
    if not isinstance(normalized["strengths"], list):
        normalized["strengths"] = []
    if not isinstance(normalized["findings"], list):
        normalized["findings"] = []
    return normalized


def build_local_fallback_report(issue_date: dt.date, issue_text: str, benchmark_issue: str) -> dict:
    rule_report = review_text(issue_text)
    issue_word_count = len(issue_text.split())
    benchmark_word_count = len(benchmark_issue.split()) if benchmark_issue.strip() else 0
    source_count = issue_text.count("**Source:**")
    benchmark_source_count = benchmark_issue.count("**Source:**") if benchmark_issue else 0

    findings: list[dict[str, str]] = []
    for finding in rule_report["findings"]:
        severity = "high"
        if "Quick Hits count out of range" in finding or "Issue has too few sections" in finding:
            severity = "medium"
        findings.append(
            {
                "severity": severity,
                "section": "Rule-based review",
                "issue": finding,
                "recommendation": "Tighten the draft or enrich candidate summaries before publication.",
            }
        )

    word_ratio = issue_word_count / benchmark_word_count if benchmark_word_count else 0.0
    source_ratio = source_count / benchmark_source_count if benchmark_source_count else 0.0

    if word_ratio < 0.65:
        findings.append(
            {
                "severity": "high",
                "section": "Editorial depth",
                "issue": f"Draft length is well below benchmark depth ({issue_word_count} words vs {benchmark_word_count}).",
                "recommendation": "Add explanatory detail and stronger section development before publishing.",
            }
        )
    if source_ratio < 0.65:
        findings.append(
            {
                "severity": "medium",
                "section": "Source density",
                "issue": f"Draft cites materially fewer main sources than the benchmark ({source_count} vs {benchmark_source_count}).",
                "recommendation": "Promote or add more fully sourced entries in the strongest sections.",
            }
        )

    score = 72
    score += min(10, max(0, int((word_ratio - 0.65) * 40)))
    score += min(8, max(0, int((source_ratio - 0.65) * 24)))
    score += 5 if rule_report["passed"] else 0
    score -= min(25, len(findings) * 4)
    score = max(0, min(100, score))

    high_findings = [finding for finding in findings if finding["severity"] == "high"]
    passed = score >= review_min_score() and not high_findings

    strengths: list[str] = []
    if rule_report["passed"]:
        strengths.append("Rule-based review passed without placeholder or feed-wrapper failures.")
    if word_ratio >= 0.8:
        strengths.append("Draft reaches most of the benchmark's explanatory length.")
    if source_ratio >= 0.8:
        strengths.append("Source density is close to the benchmark issue.")

    return {
        "passed": passed,
        "ready_to_send": passed,
        "overall_score": score,
        "summary": "Local fallback review used because the AI provider token is not configured.",
        "strengths": strengths,
        "findings": findings,
        "bias_assessment": "Local heuristic review checks structure and benchmark depth, but does not replace full model-based editorial judgment.",
        "recommended_action": "Publish only if the fallback report clears the benchmark-based thresholds; otherwise revise the draft.",
        "date": issue_date.isoformat(),
        "model": "local-heuristic",
        "minimum_score": review_min_score(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AI editorial review on a generated issue.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)

    issue_path = issue_path_for(issue_date)
    issue_text = issue_path.read_text(encoding="utf-8")
    selection_criteria = SELECTION_CRITERIA_PATH.read_text(encoding="utf-8")
    sources_text = SOURCES_PATH.read_text(encoding="utf-8")
    benchmark_issue = BENCHMARK_ISSUE_PATH.read_text(encoding="utf-8") if BENCHMARK_ISSUE_PATH.exists() else ""
    if ai_enabled():
        prompt = build_prompt(issue_date, issue_text, selection_criteria, sources_text, benchmark_issue)
        raw_report = call_openai_json(prompt, review_model())
        report = validate_report(raw_report)
        report["date"] = issue_date.isoformat()
        report["issue"] = str(issue_path)
        report["model"] = review_model()
        report["minimum_score"] = review_min_score()
    else:
        report = build_local_fallback_report(issue_date, issue_text, benchmark_issue)
        report["issue"] = str(issue_path)

    high_findings = [
        finding for finding in report["findings"]
        if isinstance(finding, dict) and str(finding.get("severity", "")).lower() == "high"
    ]
    report["passed"] = bool(report["passed"]) and report["overall_score"] >= review_min_score() and not high_findings
    report["ready_to_send"] = bool(report["ready_to_send"]) and report["passed"]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{issue_date.isoformat()}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if report["ready_to_send"]:
        print(f"Editorial review passed: {issue_path}")
        return

    print(f"Editorial review failed: {issue_path}")
    print(f"- Score: {report['overall_score']}")
    for finding in report["findings"]:
        if isinstance(finding, dict):
            severity = str(finding.get("severity", "unknown")).lower()
            section = finding.get("section", "unknown")
            issue = finding.get("issue", "")
            print(f"- {severity} [{section}]: {issue}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
