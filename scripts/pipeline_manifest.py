#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "runs"
CANDIDATES_DIR = ROOT / "data" / "candidates"
MARKET_SNAPSHOTS_DIR = ROOT / "data" / "market_snapshots"
REVIEWS_DIR = ROOT / "data" / "reviews"
AI_REVIEWS_DIR = ROOT / "data" / "ai_reviews"
EDITORIAL_DIFFS_DIR = ROOT / "data" / "editorial_diffs"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def safe_json_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def days_between(issue_date: dt.date, date_text: str) -> int | None:
    try:
        return (issue_date - dt.date.fromisoformat(date_text[:10])).days
    except Exception:
        return None


def candidate_summary(issue_date: dt.date) -> dict[str, object]:
    payload = safe_json_load(CANDIDATES_DIR / f"{issue_date.isoformat()}.json")
    fetch = payload.get("fetch", {})
    summary = fetch.get("summary", {}) if isinstance(fetch, dict) else {}
    sections = payload.get("sections", {})
    entries = [
        entry
        for section_entries in sections.values()
        if isinstance(section_entries, list)
        for entry in section_entries
        if isinstance(entry, dict)
    ] if isinstance(sections, dict) else []

    direct_entries = [
        entry for entry in entries
        if str(entry.get("source_type", "")) != "google-news-rss"
    ]
    google_wrapper_links = [
        str(entry.get("link", ""))
        for entry in entries
        if "news.google.com" in str(entry.get("link", ""))
    ]

    source_sections = fetch.get("sections", {}) if isinstance(fetch, dict) else {}
    duplicate_clusters: list[dict[str, object]] = []
    if isinstance(source_sections, dict):
        for section, report in source_sections.items():
            if not isinstance(report, dict):
                continue
            for cluster in report.get("story_clusters", []):
                if not isinstance(cluster, dict):
                    continue
                if int(cluster.get("support_count", 0) or 0) >= 4:
                    duplicate_clusters.append(
                        {
                            "section": section,
                            "support_count": cluster.get("support_count", 0),
                            "lead_title": cluster.get("lead_title", ""),
                        }
                    )

    total_entries = len(entries)
    direct_ratio = (len(direct_entries) / total_entries) if total_entries else 0.0
    wrapper_ratio = (len(google_wrapper_links) / total_entries) if total_entries else 0.0
    return {
        "summary": summary,
        "total_entries": total_entries,
        "direct_entries": len(direct_entries),
        "direct_entry_ratio": round(direct_ratio, 4),
        "google_wrapper_links": len(google_wrapper_links),
        "google_wrapper_ratio": round(wrapper_ratio, 4),
        "duplicate_clusters": duplicate_clusters[:10],
    }


def market_summary(issue_date: dt.date) -> dict[str, object]:
    snapshot = safe_json_load(MARKET_SNAPSHOTS_DIR / f"{issue_date.isoformat()}.json")
    if not snapshot:
        return {"present": False}

    quote_ages: list[int] = []
    macro_ages: list[int] = []
    for entry in snapshot.get("quotes", {}).values():
        if isinstance(entry, dict):
            age = days_between(issue_date, str(entry.get("captured_on") or entry.get("as_of") or ""))
            if age is not None:
                quote_ages.append(age)
    for entry in snapshot.get("macro", {}).values():
        if isinstance(entry, dict):
            age = days_between(issue_date, str(entry.get("captured_on") or entry.get("as_of") or ""))
            if age is not None:
                macro_ages.append(age)

    return {
        "present": True,
        "quote_count": len(snapshot.get("quotes", {})) if isinstance(snapshot.get("quotes", {}), dict) else 0,
        "macro_count": len(snapshot.get("macro", {})) if isinstance(snapshot.get("macro", {}), dict) else 0,
        "max_quote_age_days": max(quote_ages) if quote_ages else None,
        "max_macro_age_days": max(macro_ages) if macro_ages else None,
    }


def review_summary(issue_date: dt.date) -> dict[str, object]:
    rule_report = safe_json_load(REVIEWS_DIR / f"{issue_date.isoformat()}.json")
    ai_report = safe_json_load(AI_REVIEWS_DIR / f"{issue_date.isoformat()}.json")
    return {
        "rule_review": {
            "passed": rule_report.get("passed"),
            "finding_count": len(rule_report.get("findings", [])) if isinstance(rule_report.get("findings", []), list) else None,
        } if rule_report else {},
        "ai_review": {
            "passed": ai_report.get("passed"),
            "ready_to_send": ai_report.get("ready_to_send"),
            "overall_score": ai_report.get("overall_score"),
            "model": ai_report.get("model"),
            "minimum_score": ai_report.get("minimum_score"),
            "finding_count": len(ai_report.get("findings", [])) if isinstance(ai_report.get("findings", []), list) else None,
        } if ai_report else {},
    }


def editorial_diff_summary(issue_date: dt.date) -> dict[str, object]:
    report = safe_json_load(EDITORIAL_DIFFS_DIR / f"{issue_date.isoformat()}.json")
    if not report:
        return {}
    return {
        "word_count": report.get("issue", {}).get("word_count") if isinstance(report.get("issue"), dict) else None,
        "source_count": report.get("issue", {}).get("source_count") if isinstance(report.get("issue"), dict) else None,
        "benchmark_word_ratio": report.get("benchmark_comparison", {}).get("word_count_ratio") if isinstance(report.get("benchmark_comparison"), dict) else None,
        "benchmark_source_ratio": report.get("benchmark_comparison", {}).get("source_count_ratio") if isinstance(report.get("benchmark_comparison"), dict) else None,
        "repeated_main_titles": report.get("previous_issue_comparison", {}).get("repeated_main_titles", []) if isinstance(report.get("previous_issue_comparison"), dict) else [],
        "banned_phrase_count": len(report.get("banned_phrase_hits", [])) if isinstance(report.get("banned_phrase_hits"), list) else None,
    }


class RunManifest:
    def __init__(self, issue_date: dt.date, command: str, argv: list[str], strict_publish: bool = False) -> None:
        self.issue_date = issue_date
        self.path = RUNS_DIR / f"{issue_date.isoformat()}.json"
        self.payload: dict[str, object] = {
            "schema_version": 1,
            "date": issue_date.isoformat(),
            "command": command,
            "argv": argv,
            "strict_publish": strict_publish,
            "status": "running",
            "started_at": utc_now(),
            "completed_at": None,
            "git_sha": git_sha(),
            "stages": [],
            "publish": {
                "send_email": False,
                "git_commit": False,
                "git_push": False,
            },
            "failure_reason": "",
        }
        self.save()

    def save(self) -> None:
        self.payload["candidate_summary"] = candidate_summary(self.issue_date)
        self.payload["market_summary"] = market_summary(self.issue_date)
        self.payload["reviews"] = review_summary(self.issue_date)
        self.payload["editorial_diff"] = editorial_diff_summary(self.issue_date)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.payload, indent=2), encoding="utf-8")

    def set_publish_options(self, *, send_email: bool, git_commit: bool, git_push: bool) -> None:
        self.payload["publish"] = {
            "send_email": send_email,
            "git_commit": git_commit,
            "git_push": git_push,
        }
        self.save()

    def run_stage(self, name: str, cmd: list[str], env: dict[str, str] | None = None) -> None:
        started = time.monotonic()
        stage = {
            "name": name,
            "command": cmd,
            "started_at": utc_now(),
            "completed_at": None,
            "duration_seconds": None,
            "status": "running",
            "returncode": None,
            "error": "",
        }
        stages = self.payload.setdefault("stages", [])
        if isinstance(stages, list):
            stages.append(stage)
        self.save()

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        result = subprocess.run(cmd, cwd=ROOT, env=merged_env, check=False)
        stage["completed_at"] = utc_now()
        stage["duration_seconds"] = round(time.monotonic() - started, 3)
        stage["returncode"] = result.returncode
        if result.returncode == 0:
            stage["status"] = "passed"
            self.save()
            return

        stage["status"] = "failed"
        stage["error"] = f"Command exited with status {result.returncode}"
        self.payload["status"] = "failed"
        self.payload["failure_reason"] = f"{name}: {stage['error']}"
        self.save()
        raise subprocess.CalledProcessError(result.returncode, cmd)

    def finalize(self, status: str = "passed", failure_reason: str = "") -> None:
        self.payload["status"] = status
        self.payload["completed_at"] = utc_now()
        if failure_reason:
            self.payload["failure_reason"] = failure_reason
        self.save()
