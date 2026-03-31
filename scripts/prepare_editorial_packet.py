#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

from generate_issue import build_markets_section
from issue_clock import resolve_issue_date


ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "sources.md"
SECTION_QUERIES_PATH = ROOT / "config" / "section_queries.json"
TEMPLATE_PATH = ROOT / "daily_issue_template.md"
BENCHMARK_PATH = ROOT / "issues" / "daily" / "2026-03-15-daily-newsletter.md"
CANDIDATES_DIR = ROOT / "data" / "candidates"
PACKETS_DIR = ROOT / "data" / "editorial_packets"
NOTES_DIR = ROOT / "data" / "research_notes"
ISSUES_DIR = ROOT / "issues" / "daily"


def display_date(issue_date: dt.date) -> str:
    return issue_date.strftime("%B %d, %Y")


def issue_path_for(issue_date: dt.date) -> Path:
    return ISSUES_DIR / f"{issue_date.isoformat()}-daily-newsletter.md"


def parse_sources_by_section(text: str) -> dict[str, list[str]]:
    in_by_section = False
    current_section: str | None = None
    result: dict[str, list[str]] = {}

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "## By Section":
            in_by_section = True
            current_section = None
            continue
        if stripped.startswith("## ") and stripped != "## By Section" and in_by_section:
            break
        if not in_by_section:
            continue
        if stripped.startswith("### "):
            current_section = stripped[4:].strip()
            result[current_section] = []
            continue
        if current_section and stripped.startswith("- "):
            result[current_section].append(stripped[2:].strip())

    return result


def load_candidate_snapshot(issue_date: dt.date) -> dict[str, list[dict[str, str]]]:
    path = CANDIDATES_DIR / f"{issue_date.isoformat()}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot: dict[str, list[dict[str, str]]] = {}
    for section, entries in payload.get("sections", {}).items():
        if not isinstance(entries, list):
            continue
        top_entries: list[dict[str, str]] = []
        for entry in entries[:3]:
            if not isinstance(entry, dict):
                continue
            top_entries.append(
                {
                    "title": str(entry.get("title", "")).strip(),
                    "publisher": str(entry.get("publisher", "")).strip(),
                    "link": str(entry.get("link", "")).strip(),
                }
            )
        if top_entries:
            snapshot[section] = top_entries
    return snapshot


def benchmark_stats(text: str) -> dict[str, object]:
    section_word_counts: dict[str, int] = {}
    matches = list(re.finditer(r"(?ms)^## (?P<section>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)", text))
    for match in matches:
        section = match.group("section").strip()
        body = match.group("body").strip()
        section_word_counts[section] = len(body.split())
    return {
        "word_count": len(text.split()),
        "source_count": text.count("**Source:**"),
        "link_count": text.count("**Link:**"),
        "section_word_counts": section_word_counts,
    }


def build_scaffold(issue_date: dt.date) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    template = template.replace("## YYYY-MM-DD", f"## {display_date(issue_date)}", 1)
    markets_section, _ = build_markets_section()
    rendered_markets = "\n".join(markets_section).strip()
    template = re.sub(
        r"(?ms)^## Markets & Economy\n.*?(?=^## |\Z)",
        rendered_markets + "\n\n",
        template,
        count=1,
    )
    return template.strip() + "\n"


def build_notes_scaffold(issue_date: dt.date, sources_by_section: dict[str, list[str]]) -> str:
    lines = [
        f"# Frontier Threads Research Notes",
        "",
        f"Date: {issue_date.isoformat()}",
        f"Issue file: {issue_path_for(issue_date)}",
        "",
        "Use this file to capture the strongest source-backed items before writing the final issue.",
        "",
    ]
    for section, sources in sources_by_section.items():
        lines.extend([f"## {section}", ""])
        if sources:
            lines.append("Preferred sources:")
            lines.extend(f"- {source}" for source in sources)
            lines.append("")
        lines.extend(
            [
                "Candidate items:",
                "- Title:",
                "- Why it matters:",
                "- Source:",
                "- Link:",
                "- Notes:",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_packet_markdown(
    issue_date: dt.date,
    sources_by_section: dict[str, list[str]],
    section_queries: dict[str, list[str]],
    candidate_snapshot: dict[str, list[dict[str, str]]],
    benchmark: dict[str, object],
    scaffold_path: Path,
    notes_path: Path,
) -> str:
    lines = [
        "# Frontier Threads Editorial Packet",
        "",
        f"- Date: `{issue_date.isoformat()}`",
        f"- Display date: `{display_date(issue_date)}`",
        f"- Issue path: `{issue_path_for(issue_date)}`",
        f"- Benchmark issue: `{BENCHMARK_PATH}`",
        f"- Issue scaffold: `{scaffold_path}`",
        f"- Research notes scaffold: `{notes_path}`",
        f"- Publish command: `python3 scripts/newsletter_command.py publish --date {issue_date.isoformat()} --git-commit --git-push`",
        "",
        "## Benchmark",
        "",
        f"- Overall word count: `{benchmark['word_count']}`",
        f"- Main source count: `{benchmark['source_count']}`",
        f"- Main link count: `{benchmark['link_count']}`",
        "",
        "## Required References",
        "",
        "- `daily_workflow.md`",
        "- `daily_issue_template.md`",
        "- `selection_criteria.md`",
        "- `sources.md`",
        "- `story_scorecard.md`",
        "- `config/newsletter_profile.json`",
        f"- `{BENCHMARK_PATH.relative_to(ROOT)}`",
        "",
        "## Run Instructions",
        "",
        "1. Read the required references and the benchmark issue before drafting.",
        "2. Use the source registry below as the default source-of-truth for section research.",
        "3. Search the listed sources directly and prefer source pages over Google wrapper pages.",
        "4. Write the final issue in the production issue path, using the scaffold only as a starting structure.",
        "5. Preserve the Markets & Economy section unless you are fixing an obvious formatting problem.",
        "6. Only run the publish command once the issue is publication-ready.",
        "",
        "## Section Source Registry",
        "",
    ]

    for section, sources in sources_by_section.items():
        lines.append(f"### {section}")
        lines.append("")
        if sources:
            lines.append("Preferred sources:")
            lines.extend(f"- {source}" for source in sources)
            lines.append("")
        queries = section_queries.get(section, [])
        if queries:
            lines.append("Discovery queries:")
            lines.extend(f"- `{query}`" for query in queries)
            lines.append("")
        snapshot = candidate_snapshot.get(section, [])
        if snapshot:
            lines.append("Current discovery snapshot:")
            for entry in snapshot:
                publisher = f" ({entry['publisher']})" if entry.get("publisher") else ""
                lines.append(f"- {entry['title']}{publisher}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a source-first editorial packet for a daily newsletter run.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today in the configured timezone.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing scaffold and packet files.")
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)

    fetch_error = ""
    try:
        subprocess.run(
            ["python3", "scripts/fetch_candidates.py", "--date", issue_date.isoformat()],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        fetch_error = (exc.stderr or exc.stdout or str(exc)).strip()

    sources_by_section = parse_sources_by_section(SOURCES_PATH.read_text(encoding="utf-8"))
    section_queries = json.loads(SECTION_QUERIES_PATH.read_text(encoding="utf-8"))
    candidate_snapshot = load_candidate_snapshot(issue_date)
    benchmark = benchmark_stats(BENCHMARK_PATH.read_text(encoding="utf-8"))

    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    scaffold_path = PACKETS_DIR / f"{issue_date.isoformat()}-issue-scaffold.md"
    notes_path = NOTES_DIR / f"{issue_date.isoformat()}.md"
    packet_md_path = PACKETS_DIR / f"{issue_date.isoformat()}.md"
    packet_json_path = PACKETS_DIR / f"{issue_date.isoformat()}.json"

    if args.overwrite or not scaffold_path.exists():
        scaffold_path.write_text(build_scaffold(issue_date), encoding="utf-8")
    if args.overwrite or not notes_path.exists():
        notes_path.write_text(build_notes_scaffold(issue_date, sources_by_section), encoding="utf-8")

    packet_markdown = build_packet_markdown(
        issue_date,
        sources_by_section,
        section_queries,
        candidate_snapshot,
        benchmark,
        scaffold_path,
        notes_path,
    )
    if fetch_error:
        packet_markdown += f"\nFetch warning: {fetch_error}\n"
    packet_md_path.write_text(packet_markdown, encoding="utf-8")
    packet_json_path.write_text(
        json.dumps(
            {
                "date": issue_date.isoformat(),
                "display_date": display_date(issue_date),
                "issue_path": str(issue_path_for(issue_date)),
                "benchmark_issue": str(BENCHMARK_PATH),
                "scaffold_path": str(scaffold_path),
                "notes_path": str(notes_path),
                "publish_command": f"python3 scripts/newsletter_command.py publish --date {issue_date.isoformat()} --git-commit --git-push",
                "sources_by_section": sources_by_section,
                "section_queries": section_queries,
                "candidate_snapshot": candidate_snapshot,
                "benchmark": benchmark,
                "fetch_warning": fetch_error,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote editorial packet to {packet_md_path}")
    print(f"Wrote packet JSON to {packet_json_path}")
    print(f"Wrote issue scaffold to {scaffold_path}")
    print(f"Wrote research notes scaffold to {notes_path}")


if __name__ == "__main__":
    main()
