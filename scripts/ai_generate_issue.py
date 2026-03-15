#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

from openai_pipeline import ai_enabled, call_openai_text, draft_model


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
CANDIDATES_DIR = ROOT / "data" / "candidates"
SELECTION_CRITERIA_PATH = ROOT / "selection_criteria.md"
AI_DRAFTS_DIR = ROOT / "data" / "ai_drafts"

REQUIRED_HEADINGS = [
    "## Quick Hits",
    "## Markets & Economy",
    "## Need To Know",
    "## Research Watch",
    "## World News",
    "## Philosophy",
    "## Biology",
    "## Psychology and Neuroscience",
    "## Health and Medicine",
    "## Sociology and Anthropology",
    "## Technology",
    "## Robotics",
    "## AI",
    "## Engineering",
    "## Mathematics",
    "## Historical Discoveries",
    "## Archaeology",
    "## Tools You Can Use",
    "## Entertainment",
    "## Travel",
    "## Idea Of The Day",
]


def issue_path_for(issue_date: dt.date) -> Path:
    return ISSUES_DIR / f"{issue_date.isoformat()}-daily-newsletter.md"


def extract_section(markdown_text: str, heading: str) -> str:
    pattern = rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)"
    match = re.search(pattern, markdown_text)
    if not match:
        raise ValueError(f"Missing section: {heading}")
    return match.group(0).rstrip()


def replace_section(markdown_text: str, heading: str, new_section: str) -> str:
    pattern = rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)"
    if not re.search(pattern, markdown_text):
        raise ValueError(f"Missing section to replace: {heading}")
    return re.sub(pattern, new_section.strip() + "\n\n", markdown_text, count=1)


def summarize_candidates(data: dict) -> str:
    lines: list[str] = []
    for section, entries in data.get("sections", {}).items():
        lines.append(f"[{section}]")
        for entry in entries[:5]:
            title = entry.get("title", "").strip()
            publisher = entry.get("publisher", "").strip()
            summary = re.sub(r"\s+", " ", entry.get("summary", "")).strip()
            link = entry.get("link", "").strip()
            preferred = entry.get("preferred_link", "").strip() or link
            lines.append(f"- Title: {title}")
            if publisher:
                lines.append(f"  Publisher: {publisher}")
            if summary:
                lines.append(f"  Summary: {summary[:280]}")
            if preferred:
                lines.append(f"  Link: {preferred}")
        lines.append("")
    return "\n".join(lines).strip()


def build_prompt(issue_date: dt.date, current_draft: str, candidates: dict, selection_criteria: str) -> str:
    return f"""You are the final editorial pass for a daily email newsletter called Frontier Threads.

Goal:
- Rewrite the current draft into a polished, ready-to-read newsletter for a technically sophisticated reader.
- Keep the output in Markdown only.
- Keep the section structure and heading hierarchy intact.
- Use the provided candidate stories and current draft only. Do not invent facts, titles, dates, sources, or links.

Editorial requirements:
- Write clearly, concisely, and with as little political or social bias as possible.
- Prefer analytical framing over rhetoric.
- Remove repetition, generic phrasing, and low-signal feed wording.
- Keep Quick Hits as one concise summary bullet for each section except the last three sections.
- Keep Short Takes distinct from main entries within the same section.
- Do not show raw bare URLs in prose.
- Keep source links as labeled Markdown links.
- Preserve the date `{issue_date.isoformat()}`.
- Preserve the Markets & Economy section exactly as authoritative data.

Validation requirements:
- Include every required section exactly once.
- Do not wrap the output in code fences.
- Do not add commentary before or after the newsletter.

Selection rubric:
{selection_criteria}

Candidate pool:
{summarize_candidates(candidates)}

Current draft:
{current_draft}
"""


def validate_issue(text: str) -> None:
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in text]
    if missing:
        raise ValueError("AI draft is missing required sections: " + ", ".join(missing))
    if "```" in text:
        raise ValueError("AI draft must not contain code fences")


def main() -> None:
    parser = argparse.ArgumentParser(description="Use OpenAI to polish the generated daily issue.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if not ai_enabled():
        print("AI drafting skipped: OPENAI_API_KEY or NEWSLETTER_USE_AI not set.")
        return

    issue_date = dt.date.today()
    if args.date:
        issue_date = dt.date.fromisoformat(args.date)

    issue_path = issue_path_for(issue_date)
    if not issue_path.exists():
        raise SystemExit(f"Issue does not exist: {issue_path}")

    current_draft = issue_path.read_text(encoding="utf-8")
    candidates_path = CANDIDATES_DIR / f"{issue_date.isoformat()}.json"
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    selection_criteria = SELECTION_CRITERIA_PATH.read_text(encoding="utf-8")
    authoritative_markets = extract_section(current_draft, "Markets & Economy")

    prompt = build_prompt(issue_date, current_draft, candidates, selection_criteria)
    rewritten = call_openai_text(prompt, draft_model()).strip()
    rewritten = rewritten.replace("\r\n", "\n").strip() + "\n"
    validate_issue(rewritten)
    rewritten = replace_section(rewritten, "Markets & Economy", authoritative_markets)

    AI_DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = AI_DRAFTS_DIR / f"{issue_date.isoformat()}.json"
    report_path.write_text(
        json.dumps(
            {
                "date": issue_date.isoformat(),
                "model": draft_model(),
                "issue": str(issue_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if issue_path.exists() and not args.overwrite:
        raise SystemExit(f"Issue already exists: {issue_path}. Use --overwrite to replace it.")
    issue_path.write_text(rewritten, encoding="utf-8")
    print(f"AI-polished issue written to {issue_path}")


if __name__ == "__main__":
    main()
