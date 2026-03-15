#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path

from openai_pipeline import ai_enabled, load_env_file, require_ai


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full daily newsletter pipeline.")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--send", action="store_true", help="Send the generated issue after building archive.")
    args = parser.parse_args()

    issue_date = dt.date.today().isoformat()
    if args.date:
        issue_date = args.date

    load_env_file()
    use_ai = ai_enabled()

    fetch_cmd = ["python3", "scripts/fetch_candidates.py", "--date", issue_date]
    generate_cmd = ["python3", "scripts/generate_issue.py", "--date", issue_date]
    if args.overwrite:
        generate_cmd.append("--overwrite")
    ai_generate_cmd = ["python3", "scripts/ai_generate_issue.py", "--date", issue_date, "--overwrite"]
    preview_cmd = ["python3", "scripts/send_daily_newsletter.py", "--date", issue_date, "--preview-html"]
    archive_cmd = ["python3", "scripts/build_archive.py"]
    review_cmd = ["python3", "scripts/review_issue.py", "--date", issue_date]
    ai_review_cmd = ["python3", "scripts/ai_review_issue.py", "--date", issue_date]

    run(fetch_cmd)
    run(generate_cmd)
    if use_ai:
        run(ai_generate_cmd)
    elif require_ai():
        raise SystemExit("AI generation is required but OPENAI_API_KEY or NEWSLETTER_USE_AI is not configured.")
    run(review_cmd)
    if use_ai:
        run(ai_review_cmd)
    elif require_ai():
        raise SystemExit("AI review is required but OPENAI_API_KEY or NEWSLETTER_USE_AI is not configured.")
    run(preview_cmd)
    run(archive_cmd)
    if args.send:
        run(["python3", "scripts/send_daily_newsletter.py", "--date", issue_date])

    print("Daily pipeline completed.")


if __name__ == "__main__":
    main()
