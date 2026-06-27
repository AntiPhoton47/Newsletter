#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pipeline_manifest import RunManifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "config" / "newsletter_profile.json"
REVIEWS_DIR = ROOT / "data" / "reviews"
AI_REVIEWS_DIR = ROOT / "data" / "ai_reviews"


def load_profile(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Profile not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def default_issue_date(profile: dict) -> str:
    timezone_name = str(profile.get("timezone") or os.environ.get("NEWSLETTER_TIMEZONE") or os.environ.get("TZ") or "UTC")
    try:
        tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tzinfo = dt.timezone.utc
    return dt.datetime.now(dt.timezone.utc).astimezone(tzinfo).date().isoformat()


def maybe_commit(issue_date: str, push: bool, manifest: RunManifest, env: dict[str, str]) -> None:
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

    manifest.run_stage("git_add", ["git", "add", "issues/daily", "output", "site", "data", "scripts", "config", "README.md"], env=env)
    manifest.run_stage("git_commit", ["git", "commit", "-m", f"Update newsletter issue {issue_date}"], env=env)
    if push:
        manifest.run_stage("git_push", ["git", "push"], env=env)


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


def run_prepare(issue_date: str, overwrite: bool, env: dict[str, str], manifest: RunManifest) -> None:
    cmd = ["python3", "scripts/prepare_editorial_packet.py", "--date", issue_date]
    if overwrite:
        cmd.append("--overwrite")
    manifest.run_stage("prepare_editorial_packet", cmd, env=env)


def run_publish(issue_date: str, send_email: bool, env: dict[str, str], manifest: RunManifest) -> None:
    manifest.run_stage("editorial_diff", ["python3", "scripts/editorial_diff_report.py", "--date", issue_date], env=env)
    manifest.run_stage("rule_review", ["python3", "scripts/review_issue.py", "--date", issue_date], env=env)
    manifest.run_stage("ai_review", ["python3", "scripts/ai_review_issue.py", "--date", issue_date], env=env)
    manifest.run_stage("preview_html", ["python3", "scripts/send_daily_newsletter.py", "--date", issue_date, "--preview-html"], env=env)
    manifest.run_stage("build_archive", ["python3", "scripts/build_archive.py"], env=env)
    if send_email:
        manifest.run_stage("send_email", ["python3", "scripts/send_daily_newsletter.py", "--date", issue_date], env=env)


def run_full_pipeline(issue_date: str, overwrite: bool, send_email: bool, env: dict[str, str], manifest: RunManifest) -> None:
    fetch_cmd = ["python3", "scripts/fetch_candidates.py", "--date", issue_date]
    preflight_cmd = ["python3", "scripts/check_pipeline_inputs.py", "--date", issue_date]
    generate_cmd = ["python3", "scripts/generate_issue.py", "--date", issue_date]
    if overwrite:
        generate_cmd.append("--overwrite")
    manifest.run_stage("fetch_candidates", fetch_cmd, env=env)
    manifest.run_stage("preflight", preflight_cmd, env=env)
    manifest.run_stage("generate_issue", generate_cmd, env=env)
    manifest.run_stage("ai_generate_issue", ["python3", "scripts/ai_generate_issue.py", "--date", issue_date, "--overwrite"], env=env)
    run_publish(issue_date, send_email=send_email, env=env, manifest=manifest)


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
    strict = send_email or git_commit or git_push or os.environ.get("CI", "").lower() == "true"
    if strict:
        env["NEWSLETTER_STRICT_PUBLISH"] = "true"

    manifest = RunManifest(
        dt.date.fromisoformat(issue_date),
        command=f"newsletter_command:{args.command}",
        argv=["scripts/newsletter_command.py", *sys.argv[1:]],
        strict_publish=strict,
    )
    manifest.set_publish_options(send_email=send_email, git_commit=git_commit, git_push=git_push)

    try:
        if args.command == "prepare":
            run_prepare(issue_date, overwrite=overwrite, env=env, manifest=manifest)
        elif args.command == "publish":
            run_publish(issue_date, send_email=send_email, env=env, manifest=manifest)
        else:
            run_full_pipeline(issue_date, overwrite=overwrite, send_email=send_email, env=env, manifest=manifest)

        if git_commit:
            maybe_commit(issue_date, push=git_push, manifest=manifest, env=env)
    except Exception as exc:
        manifest.finalize("failed", str(exc))
        raise
    manifest.finalize("passed")

    print("Remote newsletter command completed.")


if __name__ == "__main__":
    main()
