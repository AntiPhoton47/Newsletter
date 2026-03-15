#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "section_queries.json"
DATA_DIR = ROOT / "data" / "candidates"
REQUEST_TIMEOUT = 8

LOW_VALUE_TITLE_PATTERNS = (
    r"^Nature\s*-\s*Nature$",
    r"^arXiv\.org e-Print archive\s*-\s*arXiv$",
    r"^MIT Technology Review Explains\s*-\s*MIT Technology Review$",
    r"^Nature Communications\s*-\s*Nature$",
    r"^Nature Reviews [A-Za-z &]+\s*-\s*Nature$",
    r"^Nature Neuroscience\s*-\s*Nature$",
    r"^Nature Mental Health\s*-\s*Nature$",
    r"^Nature Materials\s*-\s*Nature$",
    r"^Nature Electronics\s*-\s*Nature$",
    r"^UN Charter\s*-\s*",
    r"^Goal \d+\s*\|",
    r"^The Organisation for Economic Co-operation and Development\s*\|?\s*OECD",
    r"^Welcome to the United Nations",
)


def split_google_news_title(title: str) -> tuple[str, str]:
    if " - " in title:
        headline, publisher = title.rsplit(" - ", 1)
        return headline.strip(), publisher.strip()
    return title.strip(), ""


def is_low_value_title(title: str) -> bool:
    normalized = re.sub(r"\s+", " ", title).strip()
    return any(re.match(pattern, normalized, flags=re.IGNORECASE) for pattern in LOW_VALUE_TITLE_PATTERNS)


def google_news_rss_url(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_feed(url: str) -> list[dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            content = response.read()
    except Exception:
        insecure_context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=insecure_context) as response:
            content = response.read()
    root = ET.fromstring(content)
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = clean_html(item.findtext("description") or "")
        headline, publisher = split_google_news_title(title)
        if title and link and headline and not is_low_value_title(title):
            items.append(
                {
                    "title": headline,
                    "publisher": publisher,
                    "link": link,
                    "published": pub_date,
                    "summary": description,
                }
            )
    return items


def dedupe_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for entry in entries:
        key = (entry["title"], entry.get("publisher", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def rank_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    def score(entry: dict[str, str]) -> tuple[int, int]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        publisher = entry.get("publisher", "")
        specificity = len(title.split())
        has_summary = 1 if summary else 0
        source_bonus = 1 if publisher else 0
        return (has_summary + source_bonus, specificity)

    return sorted(entries, key=score, reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch section candidates from configured news queries.")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--max-per-query", type=int, default=5)
    args = parser.parse_args()

    issue_date = dt.date.today()
    if args.date:
        issue_date = dt.date.fromisoformat(args.date)

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload: dict[str, object] = {
        "date": issue_date.isoformat(),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sections": {}
    }

    for section, queries in config.items():
        section_entries: list[dict[str, str]] = []
        for query in queries:
            url = google_news_rss_url(query)
            try:
                items = fetch_feed(url)[: args.max_per_query]
            except Exception as exc:
                items = [{"title": f"Feed fetch failed for query: {query}", "link": "", "published": "", "summary": str(exc)}]
            for item in items:
                item["query"] = query
                item["source_type"] = "google-news-rss"
                section_entries.append(item)
        payload["sections"][section] = rank_entries(dedupe_entries(section_entries))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / f"{issue_date.isoformat()}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote candidates to {output_path}")


if __name__ == "__main__":
    main()
