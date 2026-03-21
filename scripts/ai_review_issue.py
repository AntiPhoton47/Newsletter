#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from openai_pipeline import ai_enabled, call_openai_json, review_min_score, review_model


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AI editorial review on a generated issue.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    args = parser.parse_args()

    if not ai_enabled():
        print("AI review skipped: OPENAI_API_KEY or NEWSLETTER_USE_AI not set.")
        return

    issue_date = dt.date.today()
    if args.date:
        issue_date = dt.date.fromisoformat(args.date)

    issue_path = issue_path_for(issue_date)
    issue_text = issue_path.read_text(encoding="utf-8")
    selection_criteria = SELECTION_CRITERIA_PATH.read_text(encoding="utf-8")
    sources_text = SOURCES_PATH.read_text(encoding="utf-8")
    benchmark_issue = BENCHMARK_ISSUE_PATH.read_text(encoding="utf-8") if BENCHMARK_ISSUE_PATH.exists() else ""
    prompt = build_prompt(issue_date, issue_text, selection_criteria, sources_text, benchmark_issue)
    raw_report = call_openai_json(prompt, review_model())
    report = validate_report(raw_report)
    report["date"] = issue_date.isoformat()
    report["issue"] = str(issue_path)
    report["model"] = review_model()
    report["minimum_score"] = review_min_score()

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
        print(f"AI review passed: {issue_path}")
        return

    print(f"AI review failed: {issue_path}")
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
