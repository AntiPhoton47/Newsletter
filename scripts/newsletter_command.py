#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Single-command entrypoint for generating, rendering, archiving, and optionally publishing the newsletter."
    )
    parser.add_argument("command", nargs="?", default="run", choices=["run"], help="Command to execute.")
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

    env = {
        "NEWSLETTER_EDITORIAL_PROFILE_PATH": str(profile_path),
    }

    cmd = ["python3", "scripts/run_daily_pipeline.py"]
    if args.date:
        cmd.extend(["--date", args.date])
        issue_date = args.date
    else:
        issue_date = "today"
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
