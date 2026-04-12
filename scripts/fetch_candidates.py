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
SOURCES_PATH = ROOT / "sources.md"
DATA_DIR = ROOT / "data" / "candidates"
REQUEST_TIMEOUT = 8
MAX_FETCH_ATTEMPTS = 3
MAX_ENTRY_AGE_DAYS = 365
ENRICH_TOP_ENTRIES_PER_SECTION = 5
NEWSLETTER_LOOKBACK_LIMIT = 6
MAX_CLUSTER_REPORTS_PER_SECTION = 8
MAX_SOURCE_PROBES_PER_SECTION = 6
SOURCE_PROBE_MAX_PER_QUERY = 2

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

NATURE_BRIEFING_LIST_TEMPLATE = "https://www.nature.com/nature/articles?type=nature-briefing&year={year}"
MIT_DOWNLOAD_CATEGORY_SEARCH_URL = "https://www.technologyreview.com/wp-json/wp/v2/categories?search=download&per_page=10"
MIT_DOWNLOAD_POSTS_TEMPLATE = "https://www.technologyreview.com/wp-json/wp/v2/posts?categories={category_id}&per_page={limit}"
SUPERPOWER_SITEMAP_URL = "https://www.superpowerdaily.com/sitemap.xml"

NEWSLETTER_DEFAULT_SECTIONS = {
    "Nature Briefing": "Need To Know",
    "The Download": "Technology",
    "Superpower Daily": "AI",
}

DIRECT_SOURCE_MODES = {
    "Nature Briefing": "direct-newsletter-archive",
    "The Download": "direct-newsletter-api",
    "Superpower Daily": "direct-newsletter-sitemap",
}

SOURCE_QUERY_HINTS = {
    "1440 Daily Digest": ("site:join1440.com", "join1440.com", "site:1440", " 1440"),
    "AP News": ("site:apnews.com", "apnews.com"),
    "APS Physics": ("site:aps.org", "physics.aps.org"),
    "Al Jazeera English": ("site:aljazeera.com", "aljazeera.com"),
    "Anthropic": ("site:anthropic.com", "anthropic.com"),
    "BBC News": ("site:bbc.com", "site:bbc.co.uk", "bbc.com", "bbc.co.uk"),
    "Bloomberg": ("site:bloomberg.com", "bloomberg.com"),
    "CSIS": ("site:csis.org", "csis.org"),
    "CERN": ("site:cern.ch", "cern.ch"),
    "Council on Foreign Relations": ("site:cfr.org", "cfr.org"),
    "DeepMind Blog": ("site:deepmind.google", "deepmind.google"),
    "ESA": ("site:esa.int", "esa.int"),
    "European Commission": ("site:ec.europa.eu", "ec.europa.eu"),
    "Euronews": ("site:euronews.com", "euronews.com"),
    "Financial Times": ("site:ft.com", "ft.com"),
    "GitHub": ("site:github.com", "github.com"),
    "Google DeepMind": ("site:deepmind.google", "deepmind.google"),
    "IEEE Spectrum": ("site:spectrum.ieee.org", "spectrum.ieee.org"),
    "IMF": ("site:imf.org", "imf.org"),
    "IEA": ("site:iea.org", "iea.org"),
    "International Crisis Group": ("site:crisisgroup.org", "crisisgroup.org"),
    "JPL": ("site:jpl.nasa.gov", "jpl.nasa.gov"),
    "MIT Technology Review": ("site:technologyreview.com", "technologyreview.com"),
    "Morning Brew": ("site:morningbrew.com", "morningbrew.com"),
    "NASA": ("site:nasa.gov", "nasa.gov"),
    "NATO": ("site:nato.int", "nato.int"),
    "Nature": ("site:nature.com", "nature.com"),
    "Nature Briefing": ("site:nature.com", "nature.com"),
    "OECD": ("site:oecd.org", "oecd.org"),
    "OpenAI": ("site:openai.com", "openai.com"),
    "OpenAI Developers": ("site:openai.com", "developers.openai.com"),
    "Perimeter Institute": ("site:perimeterinstitute.ca", "perimeterinstitute.ca"),
    "Physics Magazine": ("site:physics.aps.org", "physics.aps.org"),
    "Physics World": ("site:physicsworld.com", "physicsworld.com"),
    "Politico Europe": ("site:politico.eu", "politico.eu"),
    "Quanta Magazine": ("site:quantamagazine.org", "quantamagazine.org"),
    "Reuters": ("site:reuters.com", "reuters.com"),
    "SAPIENS": ("site:sapiens.org", "sapiens.org"),
    "Semafor": ("site:semafor.com", "semafor.com"),
    "Superpower Daily": ("site:superpowerdaily.com", "superpowerdaily.com"),
    "The Download": ("site:technologyreview.com", "technologyreview.com"),
    "The Economist": ("site:economist.com", "economist.com"),
    "The Guardian": ("site:theguardian.com", "theguardian.com"),
    "The Verge": ("site:theverge.com", "theverge.com"),
    "UN OCHA": ("site:unocha.org", "site:ochaopt.org", "unocha.org", "ochaopt.org"),
    "UNHCR": ("site:unhcr.org", "unhcr.org"),
    "United Nations": ("site:un.org", "un.org"),
    "Wall Street Journal": ("site:wsj.com", "wsj.com"),
    "World Bank": ("site:worldbank.org", "worldbank.org"),
    "WHO": ("site:who.int", "who.int"),
    "arXiv": ("site:arxiv.org", "arxiv.org"),
}

SOURCE_NAME_ALIASES = {
    "GoodReads": ("Goodreads",),
    "Santa Fe Institute": ("Sante Fe Institute",),
    "UN OCHA": ("United Nations / OCHA", "OCHA"),
}

TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "more",
    "new",
    "now",
    "of",
    "on",
    "or",
    "our",
    "still",
    "that",
    "the",
    "their",
    "this",
    "to",
    "what",
    "when",
    "why",
    "with",
}

SECTION_KEYWORDS = {
    "Markets & Economy": (
        "economy",
        "economic",
        "market",
        "markets",
        "inflation",
        "rates",
        "tariff",
        "tariffs",
        "trade",
        "prices",
        "price",
        "supply chain",
        "ipo",
        "oil",
        "energy costs",
    ),
    "Need To Know": (
        "science",
        "scientists",
        "physics",
        "quantum",
        "relativity",
        "research",
        "researchers",
        "nasa",
        "moon",
        "space",
        "biology",
        "medicine",
        "climate",
        "technology",
        "policy",
    ),
    "Research Watch": (
        "paper",
        "study",
        "preprint",
        "experiment",
        "result",
        "discovery",
        "research",
        "researchers",
        "scientists",
        "finding",
        "findings",
    ),
    "World News": (
        "war",
        "conflict",
        "europe",
        "china",
        "iran",
        "ukraine",
        "sanctions",
        "migration",
        "humanitarian",
        "trade",
        "tariff",
        "tariffs",
        "geopolitics",
        "security",
    ),
    "Technology": (
        "technology",
        "chip",
        "chips",
        "semiconductor",
        "computing",
        "computer",
        "space",
        "satellite",
        "battery",
        "robot",
        "robotics",
        "data center",
        "data centres",
        "infrastructure",
        "manufacturing",
        "hardware",
    ),
    "AI": (
        "ai",
        "artificial intelligence",
        "model",
        "models",
        "llm",
        "openai",
        "anthropic",
        "deepmind",
        "agent",
        "agents",
        "chatgpt",
        "inference",
        "training",
        "gpu",
        "tpu",
    ),
    "Engineering": (
        "engineering",
        "manufacturing",
        "grid",
        "reactor",
        "satellite",
        "materials",
        "construction",
        "infrastructure",
        "battery",
        "launch",
        "mission",
    ),
    "Tools You Can Use": (
        "tool",
        "tools",
        "api",
        "sdk",
        "github",
        "open-source",
        "open source",
        "platform",
        "launch",
        "release",
        "copilot",
    ),
}

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
    r"^Most interesting$",
    r"^On the bubble$",
)


def split_google_news_title(title: str) -> tuple[str, str]:
    if " - " in title:
        headline, publisher = title.rsplit(" - ", 1)
        return headline.strip(), publisher.strip()
    return title.strip(), ""


def is_low_value_title(title: str, headline: str = "", publisher: str = "") -> bool:
    normalized = re.sub(r"\s+", " ", title).strip()
    normalized_headline = re.sub(r"\s+", " ", headline or title).strip()
    if any(re.match(pattern, normalized, flags=re.IGNORECASE) for pattern in LOW_VALUE_TITLE_PATTERNS):
        return True
    if normalized_headline.lower() in {"most interesting", "on the bubble"}:
        return True
    return False


def google_news_rss_url(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_sources_by_section(text: str) -> dict[str, list[str]]:
    in_by_section = False
    current_section: str | None = None
    result: dict[str, list[str]] = {}

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
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


def normalize_source_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def source_aliases(source: str) -> tuple[str, ...]:
    aliases = [source, *SOURCE_NAME_ALIASES.get(source, ())]
    return tuple(dict.fromkeys(alias.strip() for alias in aliases if alias.strip()))


def query_matches_source(query: str, source: str) -> bool:
    lowered_query = query.lower()
    hints = SOURCE_QUERY_HINTS.get(source, ())
    if any(hint.lower() in lowered_query for hint in hints):
        return True

    normalized_query = normalize_source_name(query)
    for alias in source_aliases(source):
        alias_tokens = [token for token in normalize_source_name(alias).split() if len(token) > 2]
        if alias_tokens and all(token in normalized_query for token in alias_tokens):
            return True
    return False


def preferred_source_query_hint(source: str) -> str:
    hints = SOURCE_QUERY_HINTS.get(source, ())
    for hint in hints:
        if hint.startswith("site:"):
            return hint
    return hints[0] if hints else ""


def build_source_probe_query(section: str, source: str) -> str | None:
    hint = preferred_source_query_hint(source)
    if not hint:
        return None
    keywords = list(dict.fromkeys(SECTION_KEYWORDS.get(section, ())))[:4]
    if not keywords:
        return hint
    keyword_clause = " OR ".join(keywords)
    return f"({keyword_clause}) {hint}"


def build_source_probe_queries(section: str, listed_sources: list[str], configured_queries: list[str]) -> list[tuple[str, str]]:
    probes: list[tuple[str, str]] = []
    for source in listed_sources:
        if source in DIRECT_SOURCE_MODES:
            continue
        if any(query_matches_source(query, source) for query in configured_queries):
            continue
        probe_query = build_source_probe_query(section, source)
        if not probe_query:
            continue
        probes.append((source, probe_query))
        if len(probes) >= MAX_SOURCE_PROBES_PER_SECTION:
            break
    return probes


def canonical_entry_source(entry: dict[str, str]) -> str:
    newsletter_source = str(entry.get("newsletter_source", "")).strip()
    publisher = str(entry.get("publisher", "")).strip()
    if newsletter_source:
        return newsletter_source
    if publisher == "United Nations / OCHA":
        return "UN OCHA"
    return publisher


def sources_match(entry_source: str, listed_source: str) -> bool:
    normalized_entry = normalize_source_name(entry_source)
    for alias in source_aliases(listed_source):
        if normalized_entry == normalize_source_name(alias):
            return True
    return False


def source_quality(entry: dict[str, str]) -> int:
    source_type = str(entry.get("source_type", ""))
    if source_type.startswith("newsletter"):
        return 3
    if source_type == "google-news-rss":
        return 1
    return 2


def title_tokens(title: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return {
        token
        for token in normalized.split()
        if len(token) > 2 and token not in TITLE_STOPWORDS and not token.isdigit()
    }


def cluster_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    if overlap == 0:
        return 0.0
    return max(overlap / min(len(left), len(right)), overlap / len(left | right))


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
    normalized = text.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
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
        "published": (
            r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+name=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
            r'"datePublished":"([^"]+)"',
            r"<time[^>]+datetime=['\"]([^'\"]+)['\"]",
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
        "resolved_published": extract_meta_content(page_html, "published"),
    }
    METADATA_CACHE[link] = payload
    return payload


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def fetch_json(url: str) -> object:
    return json.loads(fetch_bytes(url).decode("utf-8", errors="replace"))


def score_newsletter_section(entry: dict[str, str], section: str) -> int:
    title = re.sub(r"^[^:]+:\s*", "", entry.get("title", "").strip().lower())
    summary = entry.get("summary", "").strip().lower()
    score = 0
    if NEWSLETTER_DEFAULT_SECTIONS.get(entry.get("newsletter_source", "")) == section:
        score += 2
    for keyword in SECTION_KEYWORDS.get(section, ()):
        if keyword in title:
            score += 2
        elif keyword in summary:
            score += 1
    return score


def classify_newsletter_entry(entry: dict[str, str]) -> str | None:
    scored = [(section, score_newsletter_section(entry, section)) for section in SECTION_KEYWORDS]
    best_section, best_score = max(scored, key=lambda item: item[1], default=("", 0))
    if best_score <= 0:
        return None
    return best_section


def fetch_nature_briefing_entries(issue_date: dt.date) -> list[dict[str, str]]:
    listing_url = NATURE_BRIEFING_LIST_TEMPLATE.format(year=issue_date.year)
    listing_html = fetch_bytes(listing_url).decode("utf-8", errors="replace")
    matches = list(
        re.finditer(
            r'<a href="(?P<href>/articles/d41586-[^"]+)"[^>]*>(?P<title>[^<]+)</a>',
            listing_html,
            flags=re.IGNORECASE,
        )
    )
    entries: list[dict[str, str]] = []
    for match in matches[:NEWSLETTER_LOOKBACK_LIMIT]:
        snippet = listing_html[max(0, match.start() - 500) : min(len(listing_html), match.end() + 2200)]
        summary_match = re.search(r'<div[^>]+data-test="article-description"[^>]*>.*?<p>(.*?)</p>', snippet, flags=re.IGNORECASE | re.DOTALL)
        date_match = re.search(r'<time[^>]+datetime="([^"]+)"', snippet, flags=re.IGNORECASE)
        published = (date_match.group(1) if date_match else "").strip()
        if published and is_stale(published, issue_date):
            continue
        entries.append(
            {
                "title": clean_html(html.unescape(match.group("title"))),
                "publisher": "Nature Briefing",
                "newsletter_source": "Nature Briefing",
                "link": urllib.parse.urljoin(listing_url, match.group("href")),
                "published": published,
                "summary": clean_html(html.unescape(summary_match.group(1))) if summary_match else "",
                "source_type": "newsletter-archive",
            }
        )
    return entries


def discover_mit_download_category_id() -> int:
    payload = fetch_json(MIT_DOWNLOAD_CATEGORY_SEARCH_URL)
    if not isinstance(payload, list):
        raise RuntimeError("MIT Technology Review category lookup returned unexpected payload")
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("slug") == "download-newsletter" or item.get("name") == "The Download":
            category_id = item.get("id")
            if isinstance(category_id, int):
                return category_id
    raise RuntimeError("Could not find The Download category id")


def fetch_mit_download_entries(issue_date: dt.date) -> list[dict[str, str]]:
    category_id = discover_mit_download_category_id()
    payload = fetch_json(MIT_DOWNLOAD_POSTS_TEMPLATE.format(category_id=category_id, limit=NEWSLETTER_LOOKBACK_LIMIT))
    if not isinstance(payload, list):
        raise RuntimeError("MIT Technology Review posts lookup returned unexpected payload")
    entries: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        published = str(item.get("date_gmt") or item.get("date") or "").strip()
        if published and is_stale(published, issue_date):
            continue
        title = clean_html(html.unescape(str(item.get("title", {}).get("rendered", ""))))
        summary = clean_html(html.unescape(str(item.get("excerpt", {}).get("rendered", ""))))
        if not summary:
            summary = clean_html(html.unescape(str(item.get("content", {}).get("rendered", ""))))[:420]
        link = str(item.get("link", "")).strip()
        if not title or not link:
            continue
        entries.append(
            {
                "title": title,
                "publisher": "The Download",
                "newsletter_source": "The Download",
                "link": link,
                "published": published,
                "summary": summary,
                "source_type": "newsletter-api",
            }
        )
    return entries


def fetch_superpower_entries(issue_date: dt.date) -> list[dict[str, str]]:
    root = ET.fromstring(fetch_bytes(SUPERPOWER_SITEMAP_URL))
    candidates: list[tuple[str, str]] = []
    for node in root.findall(".//{*}url"):
        loc = (node.findtext("{*}loc") or "").strip()
        lastmod = (node.findtext("{*}lastmod") or "").strip()
        if "/p/" not in loc:
            continue
        candidates.append((loc, lastmod))
    candidates.sort(key=lambda item: item[1], reverse=True)

    entries: list[dict[str, str]] = []
    for link, lastmod in candidates[:NEWSLETTER_LOOKBACK_LIMIT]:
        if lastmod and is_stale(lastmod, issue_date):
            continue
        metadata = fetch_article_metadata(link)
        title = metadata.get("resolved_title", "").strip()
        summary = metadata.get("resolved_summary", "").strip()
        published = metadata.get("resolved_published", "").strip() or lastmod
        if not title:
            continue
        entries.append(
            {
                "title": title,
                "publisher": "Superpower Daily",
                "newsletter_source": "Superpower Daily",
                "link": metadata.get("resolved_link", "").strip() or link,
                "published": published,
                "summary": summary,
                "image_url": metadata.get("resolved_image", "").strip(),
                "source_type": "newsletter-sitemap",
            }
        )
    return entries


def fetch_newsletter_archive_entries(issue_date: dt.date) -> tuple[dict[str, list[dict[str, str]]], dict[str, dict[str, object]]]:
    section_entries: dict[str, list[dict[str, str]]] = {}
    reports: dict[str, dict[str, object]] = {}
    fetchers = (
        ("Nature Briefing", fetch_nature_briefing_entries),
        ("The Download", fetch_mit_download_entries),
        ("Superpower Daily", fetch_superpower_entries),
    )

    for source_name, fetcher in fetchers:
        try:
            entries = fetcher(issue_date)
        except Exception as exc:
            reports[source_name] = {
                "status": "failed",
                "entry_count": 0,
                "matched_sections": {},
                "error": str(exc),
            }
            continue

        matched_sections: dict[str, int] = {}
        for entry in entries:
            section = classify_newsletter_entry(entry)
            if not section:
                continue
            matched_sections[section] = matched_sections.get(section, 0) + 1
            section_entries.setdefault(section, []).append(entry)

        reports[source_name] = {
            "status": "ok",
            "entry_count": len(entries),
            "matched_entry_count": sum(matched_sections.values()),
            "matched_sections": matched_sections,
        }

    return section_entries, reports


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
        if title and link and headline and not is_low_value_title(title, headline, publisher) and not is_stale(pub_date, issue_date):
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


def build_story_clusters(entries: list[dict[str, str]]) -> list[dict[str, object]]:
    clusters: list[dict[str, object]] = []

    for entry in entries:
        tokens = title_tokens(entry.get("title", ""))
        best_index = -1
        best_score = 0.0
        for idx, cluster in enumerate(clusters):
            score = cluster_similarity(tokens, cluster["tokens"])  # type: ignore[arg-type]
            if score > best_score:
                best_score = score
                best_index = idx
        if best_index >= 0 and best_score >= 0.6:
            clusters[best_index]["members"].append(entry)  # type: ignore[index]
            clusters[best_index]["tokens"] = set(clusters[best_index]["tokens"]) | tokens  # type: ignore[index]
            continue
        clusters.append({"tokens": tokens, "members": [entry]})

    reports: list[dict[str, object]] = []
    for cluster_id, cluster in enumerate(clusters, start=1):
        members = cluster["members"]  # type: ignore[assignment]
        ranked_members = sorted(
            members,
            key=lambda item: (
                len(str(item.get("summary", "")).split()),
                source_quality(item),
                int(parse_pub_date(item.get("published", "")).timestamp()) if parse_pub_date(item.get("published", "")) else 0,
                len(item.get("title", "").split()),
            ),
            reverse=True,
        )
        lead = ranked_members[0]
        publishers = sorted({canonical_entry_source(member) for member in members if canonical_entry_source(member)})
        for member in members:
            member["cluster_id"] = cluster_id
            member["cluster_support"] = len(publishers)
            member["cluster_lead_title"] = lead.get("title", "")
        reports.append(
            {
                "cluster_id": cluster_id,
                "lead_title": str(lead.get("title", "")).strip(),
                "lead_source": canonical_entry_source(lead),
                "support_count": len(publishers),
                "member_count": len(members),
                "sources": publishers,
                "member_titles": [str(member.get("title", "")).strip() for member in ranked_members[:4]],
            }
        )
    return reports


def build_source_coverage(
    section: str,
    listed_sources: list[str],
    query_reports: list[dict[str, object]],
    entries: list[dict[str, str]],
    newsletter_reports: dict[str, dict[str, object]],
) -> dict[str, object]:
    coverage_items: list[dict[str, object]] = []
    checked_count = 0

    for source in listed_sources:
        matched_query_reports = [
            report for report in query_reports if query_matches_source(str(report.get("query", "")), source)
        ]
        query_matches = [str(report.get("query", "")) for report in matched_query_reports]
        direct_mode = DIRECT_SOURCE_MODES.get(source)
        direct_report = newsletter_reports.get(source)
        matched_entries = [entry for entry in entries if sources_match(canonical_entry_source(entry), source)]
        access_modes = []
        if query_matches:
            access_modes.append("query-discovery")
        if direct_mode:
            access_modes.append(direct_mode)
        if not access_modes:
            access_modes.append("listed-no-fetch-path")

        status = "listed"
        notes: list[str] = []
        if direct_mode and direct_report:
            direct_status = str(direct_report.get("status", ""))
            if direct_status == "ok":
                status = "checked"
            elif direct_status == "failed":
                status = "direct-fetch-failed"
                notes.append(str(direct_report.get("error", "")).strip())
        if matched_query_reports:
            if any(str(report.get("status", "")) == "ok" for report in matched_query_reports):
                status = "checked" if status in {"listed", "checked"} else status
            elif status == "listed":
                status = "query-failed"
                notes.append("Mapped section queries failed for this source in the current run.")
        if query_matches and not matched_entries and status == "checked":
            notes.append("Source was checked but did not surface section candidates in this run.")
        if query_matches:
            status = "checked" if status in {"listed", "checked"} else status
        if status == "listed" and not query_matches and not direct_mode:
            notes.append("No direct fetcher or section query currently maps to this source.")
        if status == "checked":
            checked_count += 1

        coverage_items.append(
            {
                "source": source,
                "status": status,
                "access_modes": access_modes,
                "matched_entry_count": len(matched_entries),
                "matched_titles": [str(entry.get("title", "")).strip() for entry in matched_entries[:3]],
                "matching_queries": query_matches,
                "notes": [note for note in notes if note],
            }
        )

    return {
        "listed_source_count": len(listed_sources),
        "checked_source_count": checked_count,
        "uncovered_sources": [item["source"] for item in coverage_items if item["status"] != "checked"],
        "sources": coverage_items,
    }


def rank_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    def score(entry: dict[str, str]) -> tuple[int, int, int]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        publisher = entry.get("publisher", "")
        published = parse_pub_date(entry.get("published", ""))
        specificity = len(title.split())
        has_summary = 1 if summary else 0
        source_bonus = source_quality(entry)
        cluster_support = int(entry.get("cluster_support", 1))
        recency = int(published.timestamp()) if published else 0
        return (cluster_support, has_summary + source_bonus, recency, specificity)

    return sorted(entries, key=score, reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch section candidates from configured news queries.")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--max-per-query", type=int, default=5)
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    sources_by_section = parse_sources_by_section(SOURCES_PATH.read_text(encoding="utf-8"))
    newsletter_entries, newsletter_reports = fetch_newsletter_archive_entries(issue_date)
    payload: dict[str, object] = {
        "date": issue_date.isoformat(),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sections": {},
        "fetch": {
            "sections": {},
            "newsletter_sources": newsletter_reports,
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
                        "kind": "configured",
                        "status": "failed",
                        "entry_count": 0,
                        "error": str(exc),
                    }
                )
            else:
                query_reports.append(
                    {
                        "query": query,
                        "kind": "configured",
                        "status": "ok",
                        "entry_count": len(items),
                    }
                )
            for item in items:
                item["query"] = query
                item["source_type"] = "google-news-rss"
                section_entries.append(item)
        for source, query in build_source_probe_queries(section, sources_by_section.get(section, []), queries):
            total_queries += 1
            url = google_news_rss_url(query)
            try:
                items = fetch_feed(url, issue_date)[: min(args.max_per_query, SOURCE_PROBE_MAX_PER_QUERY)]
            except Exception as exc:
                items = []
                failed_queries += 1
                query_reports.append(
                    {
                        "query": query,
                        "source": source,
                        "kind": "source-probe",
                        "status": "failed",
                        "entry_count": 0,
                        "error": str(exc),
                    }
                )
            else:
                query_reports.append(
                    {
                        "query": query,
                        "source": source,
                        "kind": "source-probe",
                        "status": "ok",
                        "entry_count": len(items),
                    }
                )
            for item in items:
                item["query"] = query
                item["source_type"] = "google-news-rss"
                section_entries.append(item)
        section_entries.extend(newsletter_entries.get(section, []))
        deduped_entries = dedupe_entries(section_entries)
        story_clusters = build_story_clusters(deduped_entries)
        ranked_entries = rank_entries(deduped_entries)
        source_coverage = build_source_coverage(
            section,
            sources_by_section.get(section, []),
            query_reports,
            ranked_entries,
            newsletter_reports,
        )
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
            "newsletter_entry_count": len(newsletter_entries.get(section, [])),
            "queries": query_reports,
            "source_coverage": source_coverage,
            "story_clusters": story_clusters[:MAX_CLUSTER_REPORTS_PER_SECTION],
        }

    payload["fetch"]["summary"] = {
        "total_queries": total_queries,
        "failed_queries": failed_queries,
        "source_probe_queries": sum(
            sum(1 for query in section_report["queries"] if str(query.get("kind", "")) == "source-probe")
            for section_report in payload["fetch"]["sections"].values()  # type: ignore[union-attr]
        ),
        "sections_with_entries": sections_with_entries,
        "total_entries": total_entries,
        "newsletter_entries": sum(len(entries) for entries in newsletter_entries.values()),
        "listed_sources": sum(len(entries) for entries in sources_by_section.values()),
        "checked_sources": sum(
            int(section_report["source_coverage"]["checked_source_count"])
            for section_report in payload["fetch"]["sections"].values()  # type: ignore[union-attr]
        ),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / f"{issue_date.isoformat()}.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote candidates to {output_path}")


if __name__ == "__main__":
    main()
