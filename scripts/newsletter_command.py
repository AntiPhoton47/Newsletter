#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "newsletter_profile.json"


def load_profile(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Profile not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    subprocess.run(cmd, cwd=ROOT, check=True, env=merged_env)


def default_issue_date(profile: dict) -> str:
    timezone_name = str(profile.get("timezone") or os.environ.get("NEWSLETTER_TIMEZONE") or os.environ.get("TZ") or "UTC")
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tzinfo = dt.timezone.utc
    return dt.datetime.now(dt.timezone.utc).astimezone(tzinfo).date().isoformat()


def maybe_commit(issue_date: str, push: bool) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not status:
        print("No git changes to commit.")
        return

    run(["git", "add", "issues/daily", "output", "site", "data", "scripts", "config", "README.md"])
    run(["git", "commit", "-m", f"Update newsletter issue {issue_date}"])
    if push:
        run(["git", "push"])


def build_env(profile_path: Path, profile: dict) -> dict[str, str]:
    quality_policy = profile.get("quality_policy", {})
    env = {
        "NEWSLETTER_EDITORIAL_PROFILE_PATH": str(profile_path),
    }
    if profile.get("timezone"):
        env["NEWSLETTER_TIMEZONE"] = str(profile["timezone"])
        env["TZ"] = str(profile["timezone"])
    if "require_ai" in quality_policy:
        env["NEWSLETTER_REQUIRE_AI"] = "true" if quality_policy.get("require_ai") else "false"
    if "minimum_review_score" in quality_policy:
        env["NEWSLETTER_AI_REVIEW_MIN_SCORE"] = str(quality_policy.get("minimum_review_score"))
    return env


def run_prepare(issue_date: str, overwrite: bool, env: dict[str, str]) -> None:
    cmd = ["python3", "scripts/prepare_editorial_packet.py", "--date", issue_date]
    if overwrite:
        cmd.append("--overwrite")
    run(cmd, env=env)


def run_publish(issue_date: str, send_email: bool, env: dict[str, str]) -> None:
    run(["python3", "scripts/review_issue.py", "--date", issue_date], env=env)
    run(["python3", "scripts/ai_review_issue.py", "--date", issue_date], env=env)
    run(["python3", "scripts/send_daily_newsletter.py", "--date", issue_date, "--preview-html"], env=env)
    run(["python3", "scripts/build_archive.py"], env=env)
    if send_email:
        run(["python3", "scripts/send_daily_newsletter.py", "--date", issue_date], env=env)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Single-command entrypoint for generating, rendering, archiving, and optionally publishing the newsletter."
    )
    parser.add_argument("command", nargs="?", default="run", choices=["run", "prepare", "publish"], help="Command to execute.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today in the pipeline.")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE), help="Path to the newsletter profile JSON.")
    parser.add_argument("--send", action="store_true", help="Send the generated issue by email.")
    parser.add_argument("--git-commit", action="store_true", help="Commit generated newsletter changes.")
    parser.add_argument("--git-push", action="store_true", help="Push committed changes so GitHub Pages updates.")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not overwrite an existing issue for the date.")
    args = parser.parse_args()

    profile_path = Path(args.profile).expanduser()
    profile = load_profile(profile_path)
    defaults = profile.get("automation_defaults", {})

    overwrite = not args.no_overwrite if args.no_overwrite else bool(defaults.get("overwrite", True))
    send_email = args.send or bool(defaults.get("send_email", False))
    git_commit = args.git_commit or bool(defaults.get("git_commit", False))
    git_push = args.git_push or bool(defaults.get("git_push", False))
    if git_push:
        git_commit = True

    if args.date:
        issue_date = args.date
    else:
        issue_date = default_issue_date(profile)
    env = build_env(profile_path, profile)

    if args.command == "prepare":
        run_prepare(issue_date, overwrite=overwrite, env=env)
    elif args.command == "publish":
        run_publish(issue_date, send_email=send_email, env=env)
    else:
        cmd = ["python3", "scripts/run_daily_pipeline.py", "--date", issue_date]
        if overwrite:
            cmd.append("--overwrite")
        if send_email:
            cmd.append("--send")
        run(cmd, env=env)

    if git_commit:
        maybe_commit(issue_date, push=git_push)

    print("Remote newsletter command completed.")


if __name__ == "__main__":
    main()
