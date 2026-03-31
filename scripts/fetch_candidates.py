#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from issue_clock import resolve_issue_date


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "section_queries.json"
DATA_DIR = ROOT / "data" / "candidates"
REQUEST_TIMEOUT = 8
MAX_FETCH_ATTEMPTS = 3
MAX_ENTRY_AGE_DAYS = 365
ENRICH_TOP_ENTRIES_PER_SECTION = 5

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
GOOGLE_BATCH_EXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
GOOGLE_DECODE_TEMPLATE = (
    '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
    '"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{token}",{timestamp},"{signature}"]'
)

DECODE_CACHE: dict[str, str] = {}
METADATA_CACHE: dict[str, dict[str, str]] = {}

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
    r"^Correction:",
    r"\bjob with\b",
    r"\bChief Architect\b",
    r"^Scientific Reports$",
    r"^Calls for papers\b",
    r"^My Courses\b",
    r"^Search Humanities and Social Sciences Communications\b",
    r"^Human Behavior CFP\b",
    r"^IEEE Is the Global Community for Technology Professionals$",
    r"^Directorate for Science, Technology and Innovation$",
    r"^Digital health$",
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


def fetch_bytes(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = MAX_FETCH_ATTEMPTS,
) -> bytes:
    request = urllib.request.Request(url, data=data, headers=headers or REQUEST_HEADERS)
    insecure_context = ssl._create_unverified_context()
    errors: list[str] = []
    content: bytes | None = None

    for attempt in range(1, attempts + 1):
        for label, context in (("default", None), ("insecure", insecure_context)):
            try:
                if context is None:
                    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                        content = response.read()
                else:
                    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=context) as response:
                        content = response.read()
                break
            except Exception as exc:
                errors.append(f"attempt {attempt} {label}: {exc}")
        if content is not None:
            break
        if attempt < attempts:
            time.sleep(attempt)

    if content is None:
        unique_errors = list(dict.fromkeys(errors))
        raise RuntimeError("; ".join(unique_errors) or f"failed to fetch {url}")

    return content


def parse_pub_date(text: str) -> dt.datetime | None:
    if not text:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def is_stale(pub_date: str, issue_date: dt.date) -> bool:
    parsed = parse_pub_date(pub_date)
    if parsed is None:
        return False
    age = issue_date - parsed.date()
    return age.days > MAX_ENTRY_AGE_DAYS


def looks_like_headline_only(summary: str, title: str, publisher: str) -> bool:
    normalized_summary = re.sub(r"\s+", " ", summary).strip().lower()
    normalized_title = re.sub(r"\s+", " ", title).strip().lower()
    normalized_publisher = re.sub(r"\s+", " ", publisher).strip().lower()
    if not normalized_summary:
        return True
    without_publisher = normalized_summary.replace(normalized_publisher, "").replace(" ", " ").strip(" -|")
    return normalized_summary == normalized_title or without_publisher == normalized_title or len(normalized_summary.split()) < 12


def extract_meta_content(page_html: str, field: str) -> str:
    patterns = {
        "description": (
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\']([^"\']+)["\']',
        ),
        "title": (
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            r"<title>([^<]+)</title>",
        ),
        "image": (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ),
    }
    for pattern in patterns[field]:
        match = re.search(pattern, page_html, flags=re.IGNORECASE)
        if match:
            return clean_html(html.unescape(match.group(1)))
    return ""


def extract_first_paragraph(page_html: str) -> str:
    for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", page_html, flags=re.IGNORECASE | re.DOTALL):
        paragraph = clean_html(html.unescape(match.group(1)))
        if len(paragraph.split()) < 14:
            continue
        lowered = paragraph.lower()
        if "javascript is disabled" in lowered or "cookie" in lowered:
            continue
        return paragraph
    return ""


def extract_google_news_token(link: str) -> str | None:
    parsed = urllib.parse.urlparse(link)
    if parsed.netloc != "news.google.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2] not in {"articles", "read"}:
        return None
    return parts[-1]


def decode_google_news_link(link: str) -> str:
    cached = DECODE_CACHE.get(link)
    if cached:
        return cached

    token = extract_google_news_token(link)
    if not token:
        return link

    signature = ""
    timestamp = ""
    for candidate_url in (f"https://news.google.com/articles/{token}", f"https://news.google.com/rss/articles/{token}"):
        try:
            page_html = fetch_bytes(candidate_url, attempts=1).decode("utf-8", errors="replace")
        except Exception:
            continue
        signature_match = re.search(r'data-n-a-sg="([^"]+)"', page_html)
        timestamp_match = re.search(r'data-n-a-ts="([^"]+)"', page_html)
        if signature_match and timestamp_match:
            signature = signature_match.group(1)
            timestamp = timestamp_match.group(1)
            break
    if not signature or not timestamp:
        return link

    payload = [
        "Fbv4je",
        GOOGLE_DECODE_TEMPLATE.format(token=token, timestamp=timestamp, signature=signature),
    ]
    body = f"f.req={urllib.parse.quote(json.dumps([[payload]]))}".encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        **REQUEST_HEADERS,
    }
    try:
        response_text = fetch_bytes(GOOGLE_BATCH_EXECUTE_URL, data=body, headers=headers, attempts=1).decode(
            "utf-8",
            errors="replace",
        )
        decoded_payload = json.loads(response_text.split("\n\n", 1)[1])[:-2]
        decoded_url = json.loads(decoded_payload[0][2])[1]
        if isinstance(decoded_url, str) and decoded_url.startswith("http"):
            DECODE_CACHE[link] = decoded_url
            return decoded_url
    except Exception:
        pass

    return link


def fetch_article_metadata(link: str) -> dict[str, str]:
    cached = METADATA_CACHE.get(link)
    if cached is not None:
        return cached

    source_url = decode_google_news_link(link)
    try:
        page_html = fetch_bytes(source_url, attempts=1).decode("utf-8", errors="replace")
    except Exception:
        payload = {"resolved_link": source_url}
        METADATA_CACHE[link] = payload
        return payload

    payload = {
        "resolved_link": source_url,
        "resolved_title": extract_meta_content(page_html, "title"),
        "resolved_summary": extract_meta_content(page_html, "description") or extract_first_paragraph(page_html),
        "resolved_image": extract_meta_content(page_html, "image"),
    }
    METADATA_CACHE[link] = payload
    return payload


def enrich_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    for entry in entries[:ENRICH_TOP_ENTRIES_PER_SECTION]:
        link = entry.get("link", "").strip()
        if not link:
            continue
        if not looks_like_headline_only(entry.get("summary", ""), entry.get("title", ""), entry.get("publisher", "")) and "news.google.com" not in link:
            continue
        metadata = fetch_article_metadata(link)
        resolved_link = metadata.get("resolved_link", "").strip()
        resolved_summary = metadata.get("resolved_summary", "").strip()
        resolved_image = metadata.get("resolved_image", "").strip()
        if resolved_link:
            entry["link"] = resolved_link
        if resolved_summary:
            entry["summary"] = resolved_summary
        if resolved_image:
            entry["image_url"] = resolved_image
    return entries


def fetch_feed(url: str, issue_date: dt.date) -> list[dict[str, str]]:
    root = ET.fromstring(fetch_bytes(url))
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = clean_html(item.findtext("description") or "")
        headline, publisher = split_google_news_title(title)
        if title and link and headline and not is_low_value_title(title) and not is_stale(pub_date, issue_date):
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
    def score(entry: dict[str, str]) -> tuple[int, int, int]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        publisher = entry.get("publisher", "")
        published = parse_pub_date(entry.get("published", ""))
        specificity = len(title.split())
        has_summary = 1 if summary else 0
        source_bonus = 1 if publisher else 0
        recency = int(published.timestamp()) if published else 0
        return (has_summary + source_bonus, recency, specificity)

    return sorted(entries, key=score, reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch section candidates from configured news queries.")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--max-per-query", type=int, default=5)
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload: dict[str, object] = {
        "date": issue_date.isoformat(),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sections": {},
        "fetch": {
            "sections": {},
            "summary": {},
        },
    }

    total_queries = 0
    failed_queries = 0
    sections_with_entries = 0
    total_entries = 0

    for section, queries in config.items():
        section_entries: list[dict[str, str]] = []
        query_reports: list[dict[str, object]] = []
        for query in queries:
            total_queries += 1
            url = google_news_rss_url(query)
            try:
                items = fetch_feed(url, issue_date)[: args.max_per_query]
            except Exception as exc:
                items = []
                failed_queries += 1
                query_reports.append(
                    {
                        "query": query,
                        "status": "failed",
                        "entry_count": 0,
                        "error": str(exc),
                    }
                )
            else:
                query_reports.append(
                    {
                        "query": query,
                        "status": "ok",
                        "entry_count": len(items),
                    }
                )
            for item in items:
                item["query"] = query
                item["source_type"] = "google-news-rss"
                section_entries.append(item)
        ranked_entries = rank_entries(dedupe_entries(section_entries))
        if ranked_entries:
            sections_with_entries += 1
        total_entries += len(ranked_entries)
        failed_for_section = sum(1 for report in query_reports if report["status"] == "failed")
        section_status = "ok"
        if failed_for_section == len(query_reports) and query_reports:
            section_status = "failed"
        elif failed_for_section:
            section_status = "partial"
        payload["sections"][section] = ranked_entries
        payload["fetch"]["sections"][section] = {
            "status": section_status,
            "query_count": len(query_reports),
            "failed_queries": failed_for_section,
            "entry_count": len(ranked_entries),
            "queries": query_reports,
        }

    payload["fetch"]["summary"] = {
        "total_queries": total_queries,
        "failed_queries": failed_queries,
        "sections_with_entries": sections_with_entries,
        "total_entries": total_entries,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / f"{issue_date.isoformat()}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote candidates to {output_path}")


if __name__ == "__main__":
    main()
