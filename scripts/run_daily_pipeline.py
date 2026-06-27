#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys

from issue_clock import resolve_issue_date
from openai_pipeline import ai_enabled, load_env_file, require_ai, strict_publish
from pipeline_manifest import RunManifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full daily newsletter pipeline.")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--send", action="store_true", help="Send the generated issue after building archive.")
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date).isoformat()

    load_env_file()
    if args.send:
        os.environ["NEWSLETTER_STRICT_PUBLISH"] = "true"
    use_ai = ai_enabled()
    run_ai_draft = use_ai or require_ai()
    manifest = RunManifest(
        resolve_issue_date(args.date),
        command="run_daily_pipeline",
        argv=["scripts/run_daily_pipeline.py", *sys.argv[1:]],
        strict_publish=strict_publish(),
    )
    manifest.set_publish_options(send_email=args.send, git_commit=False, git_push=False)

    fetch_cmd = ["python3", "scripts/fetch_candidates.py", "--date", issue_date]
    preflight_cmd = ["python3", "scripts/check_pipeline_inputs.py", "--date", issue_date]
    generate_cmd = ["python3", "scripts/generate_issue.py", "--date", issue_date]
    if args.overwrite:
        generate_cmd.append("--overwrite")
    ai_generate_cmd = ["python3", "scripts/ai_generate_issue.py", "--date", issue_date, "--overwrite"]
    preview_cmd = ["python3", "scripts/send_daily_newsletter.py", "--date", issue_date, "--preview-html"]
    archive_cmd = ["python3", "scripts/build_archive.py"]
    diff_cmd = ["python3", "scripts/editorial_diff_report.py", "--date", issue_date]
    review_cmd = ["python3", "scripts/review_issue.py", "--date", issue_date]
    ai_review_cmd = ["python3", "scripts/ai_review_issue.py", "--date", issue_date]

    try:
        manifest.run_stage("fetch_candidates", fetch_cmd)
        manifest.run_stage("preflight", preflight_cmd)
        manifest.run_stage("generate_issue", generate_cmd)
        if run_ai_draft:
            manifest.run_stage("ai_generate_issue", ai_generate_cmd)
        manifest.run_stage("editorial_diff", diff_cmd)
        manifest.run_stage("rule_review", review_cmd)
        manifest.run_stage("ai_review", ai_review_cmd)
        manifest.run_stage("preview_html", preview_cmd)
        manifest.run_stage("build_archive", archive_cmd)
        if args.send:
            manifest.run_stage("send_email", ["python3", "scripts/send_daily_newsletter.py", "--date", issue_date])
    except Exception as exc:
        manifest.finalize("failed", str(exc))
        raise
    manifest.finalize("passed")

    print("Daily pipeline completed.")


if __name__ == "__main__":
    main()
