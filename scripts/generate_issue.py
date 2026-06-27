#!/usr/bin/env python3

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import re
import ssl
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

try:
    import certifi
except ImportError:  # pragma: no cover - optional dependency in some environments
    certifi = None

from fetch_candidates import decode_google_news_link, enrich_entries
from issue_clock import resolve_issue_date


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_DIR = ROOT / "data" / "candidates"
ISSUES_DIR = ROOT / "issues" / "daily"
MARKET_SNAPSHOTS_DIR = ROOT / "data" / "market_snapshots"
REQUEST_TIMEOUT = 8
REQUEST_MAX_TIME = 20
QUOTE_FETCH_WORKERS = 16
QUOTE_CACHE_MAX_AGE_DAYS = 7
MACRO_CACHE_MAX_AGE_DAYS = 31


SECTION_ORDER = [
    "Markets & Economy",
    "Need To Know",
    "Research Watch",
    "World News",
    "Philosophy",
    "Biology",
    "Psychology and Neuroscience",
    "Health and Medicine",
    "Sociology and Anthropology",
    "Technology",
    "Robotics",
    "AI",
    "Engineering",
    "Mathematics",
    "Historical Discoveries",
    "Archaeology",
    "Tools You Can Use",
    "Entertainment",
    "Travel",
    "Idea Of The Day",
]

LAST_THREE = {"Entertainment", "Travel", "Idea Of The Day"}
MIN_SHORT_TAKES_COUNT = 3
MIN_BREAKING_NEWS_COUNT = 5
DEFAULT_SECTION_COUNTS = {
    "Need To Know": (1, 0),
    "Research Watch": (2, 3),
    "World News": (3, 3),
    "Philosophy": (1, 3),
    "Biology": (1, 3),
    "Psychology and Neuroscience": (1, 3),
    "Health and Medicine": (1, 3),
    "Sociology and Anthropology": (1, 3),
    "Technology": (1, 3),
    "Robotics": (1, 3),
    "AI": (1, 3),
    "Engineering": (1, 3),
    "Mathematics": (1, 3),
    "Historical Discoveries": (1, 3),
    "Archaeology": (1, 3),
    "Tools You Can Use": (3, 4),
    "Entertainment": (0, 0),
    "Travel": (0, 0),
    "Idea Of The Day": (0, 0),
}

RESCUE_SECTION_FALLBACKS = {
    "Need To Know": ["Research Watch", "AI", "Technology", "Engineering", "Mathematics"],
    "Research Watch": ["Need To Know", "AI", "Technology", "Engineering", "Mathematics", "Biology"],
    "World News": ["Technology", "Engineering", "Markets & Economy"],
    "Philosophy": ["AI", "Need To Know", "Research Watch", "Mathematics"],
    "Biology": ["Health and Medicine", "Psychology and Neuroscience", "Research Watch"],
    "Psychology and Neuroscience": ["Health and Medicine", "Biology", "Research Watch"],
    "Health and Medicine": ["Biology", "Psychology and Neuroscience", "Research Watch"],
    "Sociology and Anthropology": ["World News", "AI", "Philosophy"],
    "Technology": ["Engineering", "AI", "Tools You Can Use", "Research Watch"],
    "Robotics": ["AI", "Engineering", "Technology"],
    "AI": ["Tools You Can Use", "Technology", "Research Watch", "Robotics"],
    "Engineering": ["Technology", "Research Watch", "Robotics"],
    "Mathematics": ["Research Watch", "Philosophy", "AI"],
    "Historical Discoveries": ["Archaeology", "World News"],
    "Archaeology": ["Historical Discoveries", "Biology"],
    "Tools You Can Use": ["AI", "Technology", "Research Watch"],
}


def load_candidates(issue_date: dt.date) -> dict:
    path = CANDIDATES_DIR / f"{issue_date.isoformat()}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def entry_key(entry: dict) -> tuple[str, str]:
    return (
        clean_title(str(entry.get("title", ""))),
        str(entry.get("publisher", "")).strip(),
    )


def clean_title(title: str) -> str:
    title = re.sub(r"\s*-\s*Google News$", "", title).strip()
    title = re.sub(r"^\[[0-9.]+\]\s*", "", title).strip()
    return title


TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "announces",
    "at",
    "after",
    "as",
    "by",
    "for",
    "from",
    "in",
    "into",
    "new",
    "now",
    "of",
    "on",
    "or",
    "over",
    "the",
    "to",
    "update",
    "with",
}


def title_tokens(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", clean_title(text).lower())
    return {
        token
        for token in cleaned.split()
        if len(token) > 2 and token not in TITLE_STOPWORDS
    }


def titles_overlap(title_a: str, title_b: str) -> bool:
    key_a = lead_story_key(title_a)
    key_b = lead_story_key(title_b)
    if key_a and key_a == key_b:
        return True

    tokens_a = title_tokens(title_a)
    tokens_b = title_tokens(title_b)
    if not tokens_a or not tokens_b:
        return False

    overlap = len(tokens_a & tokens_b)
    return overlap >= 3 or (overlap / min(len(tokens_a), len(tokens_b))) >= 0.75


def strip_title_echo(title: str, summary: str) -> str:
    cleaned_title = clean_title(title)
    cleaned_summary = re.sub(r"\s+", " ", summary).strip()
    if not cleaned_title or not cleaned_summary:
        return cleaned_summary

    stripped = re.sub(
        rf"^{re.escape(cleaned_title)}(?:\s*[:\-;,]\s*|\s+)",
        "",
        cleaned_summary,
        flags=re.IGNORECASE,
    ).strip()
    if stripped and stripped[0].islower():
        stripped = stripped[0].upper() + stripped[1:]
    return stripped or cleaned_summary


def short_take_summary(entry: dict, limit: int = 180) -> str:
    summary = summarize(entry.get("summary") or "", limit)
    return strip_title_echo(str(entry.get("title", "")), summary)


def select_distinct_entries(
    entries: list[dict],
    *,
    blocked_titles: list[str] | None = None,
    limit: int,
) -> list[dict]:
    selected: list[dict] = []
    seen_titles = list(blocked_titles or [])

    for entry in entries:
        title = clean_title(str(entry.get("title", "")))
        if any(titles_overlap(title, existing) for existing in seen_titles):
            continue
        selected.append(entry)
        seen_titles.append(title)
        if len(selected) >= limit:
            break

    return selected


def summarize(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*&nbsp;\s*", " ", text)
    text = re.sub(r"\s+-\s+[A-Z][A-Za-z0-9 .&|/-]+$", "", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def lead_story_key(title: str) -> str:
    cleaned = clean_title(title).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    tokens = [token for token in cleaned.split() if token not in {"the", "a", "an", "new", "now", "after", "from", "with"}]
    return " ".join(tokens[:3])


def compact_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip().lower()
    return re.sub(r"[^a-z0-9 ]+", "", text)


def summary_quality(entry: dict) -> int:
    title = compact_text(clean_title(str(entry.get("title", ""))))
    summary = compact_text(summarize(str(entry.get("summary", "")), 320))
    if not summary:
        return -100
    score = len(summary)
    if summary == title or summary.startswith(title):
        score -= 250
    return score


def tool_entry_priority(entry: dict) -> tuple[int, int]:
    title = clean_title(str(entry.get("title", ""))).lower()
    link = preferred_link(str(entry.get("link", "")), str(entry.get("publisher", ""))).lower()
    publisher = str(entry.get("publisher", "")).lower()
    docs_penalty = 1 if "developers.openai.com" in link or title in {"building agents", "agents | openai api", "agent builder | openai api"} else 0
    product_bonus = 1 if any(host in link for host in ("github.com", "producthunt.com", "huggingface.co", "replicate.com", "modal.com", "vercel.com")) else 0
    publisher_bonus = 1 if publisher in {"github.com", "product hunt"} else 0
    return (product_bonus + publisher_bonus, -docs_penalty)


def source_label(link: str, publisher: str = "") -> str:
    if publisher:
        return publisher
    host = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
    return host or "Source"


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    verified_context = ssl.create_default_context(cafile=certifi.where()) if certifi else None
    errors: list[str] = []
    try:
        if verified_context is None:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=verified_context) as response:
            return response.read()
    except Exception as exc:
        errors.append(f"verified/default urllib: {exc}")
    try:
        insecure_context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=insecure_context) as response:
            return response.read()
    except Exception as exc:
        errors.append(f"insecure urllib: {exc}")

    curl_cmd = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--connect-timeout",
        str(REQUEST_TIMEOUT),
        "--max-time",
        str(REQUEST_MAX_TIME),
        "--user-agent",
        "Mozilla/5.0",
        url,
    ]
    curl_result = subprocess.run(curl_cmd, capture_output=True, check=False)
    if curl_result.returncode == 0:
        return curl_result.stdout

    curl_error = curl_result.stderr.decode("utf-8", errors="replace").strip() or f"curl exit {curl_result.returncode}"
    errors.append(f"curl: {curl_error}")
    raise RuntimeError("; ".join(errors))


def preferred_link(link: str, publisher: str = "") -> str:
    if not link:
        return PUBLISHER_URLS.get(publisher, "")
    return decode_google_news_link(link)


YAHOO_SYMBOLS = {
    "spy.us": "SPY",
    "qqq.us": "QQQ",
    "dia.us": "DIA",
    "vgk.us": "VGK",
    "ewj.us": "EWJ",
    "mchi.us": "MCHI",
    "inda.us": "INDA",
    "fxi.us": "FXI",
    "btcusd": "BTC-USD",
    "ethusd": "ETH-USD",
    "gld.us": "GLD",
    "uso.us": "USO",
    "nvda.us": "NVDA",
    "msft.us": "MSFT",
    "amzn.us": "AMZN",
    "googl.us": "GOOGL",
    "meta.us": "META",
    "avgo.us": "AVGO",
    "amd.us": "AMD",
    "mu.us": "MU",
    "tsla.us": "TSLA",
    "pltr.us": "PLTR",
    "arm.us": "ARM",
    "tsm.us": "TSM",
    "asml.us": "ASML",
    "now.us": "NOW",
    "crwd.us": "CRWD",
    "snow.us": "SNOW",
    "uber.us": "UBER",
    "hood.us": "HOOD",
    "rddt.us": "RDDT",
    "rtx.us": "RTX",
    "ba.us": "BA",
    "ge.us": "GE",
    "cat.us": "CAT",
    "xom.us": "XOM",
}

PUBLISHER_URLS = {
    "AP News": "https://apnews.com/",
    "arXiv": "https://arxiv.org/",
    "Bank of Japan": "https://www.boj.or.jp/en/",
    "BLS": "https://www.bls.gov/",
    "ECB": "https://www.ecb.europa.eu/",
    "Eurostat": "https://ec.europa.eu/eurostat/",
    "GitHub": "https://github.com/",
    "1440 Daily Digest": "https://join1440.com/",
    "IAI TV": "https://iai.tv/",
    "IEEE": "https://www.ieee.org/",
    "IMF": "https://www.imf.org/",
    "International Monetary Fund | IMF": "https://www.imf.org/",
    "IARC": "https://www.iarc.who.int/",
    "Lonely Planet": "https://www.lonelyplanet.com/",
    "MIT Technology Review": "https://www.technologyreview.com/",
    "Morning Brew": "https://www.morningbrew.com/",
    "Nature": "https://www.nature.com/",
    "Nature Briefing": "https://www.nature.com/briefing/briefing",
    "Nature Ecology & Evolution": "https://www.nature.com/natecolevol/",
    "Nature Electronics": "https://www.nature.com/natelectron/",
    "Nature Health": "https://www.nature.com/nathealth/",
    "Nature Materials": "https://www.nature.com/natmat/",
    "Nature Mental Health": "https://www.nature.com/natmentalhealth/",
    "Nature Neuroscience": "https://www.nature.com/neuro/",
    "Nature News": "https://www.nature.com/news/",
    "Nature Reviews Neuroscience": "https://www.nature.com/nrn/",
    "New Scientist": "https://www.newscientist.com/",
    "OECD": "https://www.oecd.org/",
    "OpenAI": "https://openai.com/",
    "OpenAlex Developers": "https://docs.openalex.org/",
    "PC Gamer": "https://www.pcgamer.com/",
    "Parade": "https://parade.com/",
    "Quanta Magazine": "https://www.quantamagazine.org/",
    "SAPIENS – Anthropology Magazine": "https://www.sapiens.org/",
    "Science | AAAS": "https://www.science.org/",
    "Scientific American": "https://www.scientificamerican.com/",
    "Semantic Scholar": "https://www.semanticscholar.org/product/api",
    "Superpower Daily": "https://www.superpowerdaily.com/",
    "The Download": "https://www.technologyreview.com/topic/download-newsletter/",
    "Tom’s Guide": "https://www.tomsguide.com/",
    "UNHCR": "https://www.unhcr.org/",
    "United Nations": "https://www.un.org/",
    "Variety": "https://variety.com/",
    "Welcome to the United Nations": "https://www.un.org/",
    "WHO": "https://www.who.int/",
    "World Economic Forum": "https://www.weforum.org/",
    "Going": "https://www.going.com/",
}

FRED_SERIES_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
CORE_MARKET_TICKERS = [
    ("S&P 500 (SPY)", "spy.us"),
    ("NASDAQ-100 (QQQ)", "qqq.us"),
    ("DOW (DIA)", "dia.us"),
    ("Europe (VGK)", "vgk.us"),
    ("Japan (EWJ)", "ewj.us"),
    ("China (MCHI)", "mchi.us"),
    ("India (INDA)", "inda.us"),
    ("China large-cap (FXI)", "fxi.us"),
    ("Bitcoin", "btcusd"),
    ("Ethereum", "ethusd"),
    ("Gold (GLD)", "gld.us"),
    ("Oil proxy (USO)", "uso.us"),
]
COMPANY_MOVER_POOL = [
    ("NVIDIA (NVDA)", "nvda.us"),
    ("Microsoft (MSFT)", "msft.us"),
    ("Amazon (AMZN)", "amzn.us"),
    ("Alphabet (GOOGL)", "googl.us"),
    ("Meta (META)", "meta.us"),
    ("Broadcom (AVGO)", "avgo.us"),
    ("AMD (AMD)", "amd.us"),
    ("Micron (MU)", "mu.us"),
    ("Tesla (TSLA)", "tsla.us"),
    ("Palantir (PLTR)", "pltr.us"),
    ("ARM Holdings (ARM)", "arm.us"),
    ("Taiwan Semiconductor (TSM)", "tsm.us"),
    ("ASML (ASML)", "asml.us"),
    ("ServiceNow (NOW)", "now.us"),
    ("CrowdStrike (CRWD)", "crwd.us"),
    ("Snowflake (SNOW)", "snow.us"),
    ("Uber (UBER)", "uber.us"),
    ("Robinhood (HOOD)", "hood.us"),
    ("Reddit (RDDT)", "rddt.us"),
    ("RTX (RTX)", "rtx.us"),
    ("Boeing (BA)", "ba.us"),
    ("GE Aerospace (GE)", "ge.us"),
    ("Caterpillar (CAT)", "cat.us"),
    ("Exxon Mobil (XOM)", "xom.us"),
]
MARKET_TICKERS = [*CORE_MARKET_TICKERS, *COMPANY_MOVER_POOL]
MACRO_SERIES = {
    "US CPI (YoY)": {
        "series_id": "CPIAUCSL",
        "source_live": "BLS via FRED",
        "source_fallback": "BLS via FRED",
        "url": "https://fred.stlouisfed.org/series/CPIAUCSL",
        "kind": "yoy",
    },
    "US unemployment rate": {
        "series_id": "UNRATE",
        "source_live": "BLS via FRED",
        "source_fallback": "BLS via FRED",
        "url": "https://fred.stlouisfed.org/series/UNRATE",
        "kind": "value_1",
    },
    "Fed funds rate": {
        "series_id": "FEDFUNDS",
        "source_live": "Federal Reserve via FRED",
        "source_fallback": "Federal Reserve via FRED",
        "url": "https://fred.stlouisfed.org/series/FEDFUNDS",
        "kind": "value_2",
    },
    "US 10-year Treasury": {
        "series_id": "DGS10",
        "source_live": "Treasury via FRED",
        "source_fallback": "Treasury via FRED",
        "url": "https://fred.stlouisfed.org/series/DGS10",
        "kind": "daily_2",
    },
    "Brent crude": {
        "series_id": "DCOILBRENTEU",
        "source_live": "EIA via FRED",
        "source_fallback": "EIA via FRED",
        "url": "https://fred.stlouisfed.org/series/DCOILBRENTEU",
        "kind": "oil_2",
    },
}


def iso_date(value: object) -> str:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def days_between(current: dt.date, other: str) -> int:
    try:
        return (current - dt.date.fromisoformat(other)).days
    except Exception:
        return 10**6


def market_snapshot_path(issue_date: dt.date) -> Path:
    return MARKET_SNAPSHOTS_DIR / f"{issue_date.isoformat()}.json"


def load_market_snapshot(issue_date: dt.date) -> dict | None:
    path = market_snapshot_path(issue_date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_latest_market_snapshot(issue_date: dt.date) -> dict | None:
    if not MARKET_SNAPSHOTS_DIR.exists():
        return None
    snapshots = sorted(
        path for path in MARKET_SNAPSHOTS_DIR.glob("*.json") if path.stem <= issue_date.isoformat()
    )
    if not snapshots:
        return None
    try:
        return json.loads(snapshots[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def save_market_snapshot(issue_date: dt.date, snapshot: dict) -> None:
    MARKET_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    market_snapshot_path(issue_date).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def fetch_yahoo_quote_snapshot(symbol: str) -> dict[str, object] | None:
    yahoo_symbol = YAHOO_SYMBOLS.get(symbol, symbol.upper())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}?interval=1d&range=5d"
    try:
        payload = json.loads(fetch_url(url).decode("utf-8"))
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        close_v = float(meta["regularMarketPrice"])
        previous_close = float(meta.get("chartPreviousClose") or meta.get("previousClose"))
        move_pct = ((close_v - previous_close) / previous_close) * 100 if previous_close else 0.0
        direction = "up" if move_pct > 0 else "down" if move_pct < 0 else "flat"
        market_time = meta.get("regularMarketTime")
        if market_time:
            as_of = dt.datetime.fromtimestamp(int(market_time), tz=dt.timezone.utc).date().isoformat()
        else:
            as_of = dt.datetime.now(dt.timezone.utc).date().isoformat()
        return {
            "symbol": symbol,
            "price": f"{close_v:.2f}",
            "move": f"{direction} {abs(move_pct):.2f}%",
            "price_value": close_v,
            "move_pct": abs(move_pct),
            "direction": direction,
            "as_of": as_of,
            "origin": "live",
        }
    except Exception:
        return None


def render_quote_line(label: str, entry: dict[str, object], issue_date: dt.date) -> str:
    suffix = ""
    if entry.get("origin") == "cache":
        as_of = str(entry.get("as_of", ""))
        if as_of:
            suffix = f" (latest cached close from {format_day(as_of)})"
        else:
            suffix = " (latest cached close)"
    return f"- **{label}:** {entry['price']}, {entry['move']}{suffix}."


def render_macro_line(label: str, entry: dict[str, object]) -> str:
    source_label_text = str(entry["source"])
    source_url = str(entry["url"])
    kind = str(entry["kind"])
    value = float(entry["value"])
    as_of = str(entry["as_of"])
    cached_suffix = ""
    if entry.get("origin") == "cache":
        cached_suffix = " (cached)"

    if kind == "yoy":
        return f"- **{label}:** {value:.1f}% as of {format_month(as_of)}{cached_suffix}. Source: [{source_label_text}]({source_url})"
    if kind == "value_1":
        return f"- **{label}:** {value:.1f}% as of {format_month(as_of)}{cached_suffix}. Source: [{source_label_text}]({source_url})"
    if kind == "value_2":
        return f"- **{label}:** {value:.2f}% as of {format_month(as_of)}{cached_suffix}. Source: [{source_label_text}]({source_url})"
    if kind == "daily_2":
        return f"- **{label}:** {value:.2f}% latest daily close on {format_day(as_of)}{cached_suffix}. Source: [{source_label_text}]({source_url})"
    if kind == "oil_2":
        return f"- **{label}:** ${value:.2f}/barrel latest daily print on {format_day(as_of)}{cached_suffix}. Source: [{source_label_text}]({source_url})"
    return f"- **{label}:** {value}{cached_suffix}. Source: [{source_label_text}]({source_url})"


def fetch_yahoo_quote(symbol: str) -> tuple[str, str]:
    snapshot = fetch_yahoo_quote_snapshot(symbol)
    if snapshot is None:
        return ("data unavailable", "live quote unavailable")
    return (str(snapshot["price"]), str(snapshot["move"]))


def parse_move_percent(move: str) -> float | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)%", move)
    if not match:
        return None
    return float(match.group(1))


def select_company_movers(
    issue_date: dt.date | None = None,
    allow_placeholders: bool = True,
    min_count: int = 2,
    max_count: int = 4,
) -> tuple[list[tuple[str, str, str]], list[str], dict[str, dict[str, object]]]:
    current_issue_date = issue_date or resolve_issue_date(None)
    exact_snapshot = load_market_snapshot(current_issue_date)
    cached_snapshot = load_latest_market_snapshot(current_issue_date)
    movers: list[tuple[str, str, str, float]] = []
    failures: list[str] = []
    selected_entries = resolve_quote_entries(COMPANY_MOVER_POOL, current_issue_date, cached_snapshot, exact_snapshot)

    for label, _symbol in COMPANY_MOVER_POOL:
        snapshot = selected_entries.get(label)
        if snapshot is None:
            failures.append(label)
            continue
        move_pct = float(snapshot.get("move_pct", 0.0))
        movers.append((label, str(snapshot["price"]), str(snapshot["move"]), move_pct))

    movers.sort(key=lambda item: (item[3], item[0]), reverse=True)
    notable = [item for item in movers if item[3] >= 1.5]
    if len(notable) >= min_count:
        selected = notable[:max_count]
    else:
        selected = movers[: max(min_count, min(max_count, len(movers)))]

    selected_labels = {label for label, _, _, _ in selected}
    rendered = [(label, price, move) for label, price, move, _ in selected]

    if not allow_placeholders:
        return rendered[:max_count], failures, {label: selected_entries[label] for label, _, _ in rendered}

    return rendered[:max_count], failures, {label: selected_entries[label] for label, _, _ in rendered}


def fetch_fred_rows(series_id: str) -> list[tuple[str, str]]:
    url = FRED_SERIES_URL.format(series_id=urllib.parse.quote(series_id))
    content = fetch_url(url).decode("utf-8", errors="replace")
    reader = csv.DictReader(content.splitlines())
    rows: list[tuple[str, str]] = []
    if not reader.fieldnames or len(reader.fieldnames) < 2:
        return rows
    date_key, value_key = reader.fieldnames[0], reader.fieldnames[1]
    for row in reader:
        value = row.get(value_key, "")
        if not value or value == ".":
            continue
        rows.append((row[date_key], value))
    return rows


def latest_fred_value(series_id: str) -> tuple[str, float]:
    rows = fetch_fred_rows(series_id)
    if not rows:
        raise ValueError(f"No rows returned for {series_id}")
    date_str, value = rows[-1]
    return (date_str, float(value))


def latest_fred_yoy(series_id: str) -> tuple[str, float]:
    rows = fetch_fred_rows(series_id)
    if len(rows) < 13:
        raise ValueError(f"Not enough rows returned for {series_id}")
    current_date, current_value = rows[-1]
    previous_value = float(rows[-13][1])
    yoy = ((float(current_value) / previous_value) - 1.0) * 100 if previous_value else 0.0
    return (current_date, yoy)


def format_month(date_str: str) -> str:
    return dt.date.fromisoformat(date_str).strftime("%b. %Y")


def format_day(date_str: str) -> str:
    return dt.date.fromisoformat(date_str).strftime("%b. %d, %Y")


INVESTMENT_THEME_LIBRARY = [
    {
        "id": "ai_infrastructure",
        "label": "AI infrastructure",
        "mover_labels": {
            "NVIDIA (NVDA)",
            "Broadcom (AVGO)",
            "Micron (MU)",
            "AMD (AMD)",
            "ARM Holdings (ARM)",
            "Taiwan Semiconductor (TSM)",
            "ASML (ASML)",
        },
        "watch_names": [
            "NVIDIA",
            "Broadcom",
            "Micron",
            "AMD",
            "ARM Holdings",
            "Taiwan Semiconductor",
            "ASML",
            "Vertiv",
        ],
        "signal_terms": ["networking silicon", "HBM supply", "advanced packaging", "lithography"],
        "regime_terms": ["capex durability", "pricing power", "supply bottlenecks"],
    },
    {
        "id": "power_and_grid",
        "label": "Power and grid infrastructure",
        "mover_labels": {
            "Caterpillar (CAT)",
            "Exxon Mobil (XOM)",
        },
        "watch_names": [
            "Quanta Services",
            "Eaton",
            "Vertiv",
            "Siemens Energy",
            "Caterpillar",
            "Exxon Mobil",
        ],
        "signal_terms": ["transmission spend", "cooling demand", "power-management budgets", "backlog conversion"],
        "regime_terms": ["electrification demand", "energy costs", "grid constraints"],
    },
    {
        "id": "resilient_software",
        "label": "Resilient enterprise software",
        "mover_labels": {
            "ServiceNow (NOW)",
            "CrowdStrike (CRWD)",
            "Snowflake (SNOW)",
            "Uber (UBER)",
        },
        "watch_names": [
            "ServiceNow",
            "CrowdStrike",
            "Snowflake",
            "Uber",
        ],
        "signal_terms": ["renewal quality", "seat expansion", "security budgets", "automation demand"],
        "regime_terms": ["rate sensitivity", "margin discipline", "budget resilience"],
    },
    {
        "id": "aerospace_defense",
        "label": "Aerospace and defense",
        "mover_labels": {
            "RTX (RTX)",
            "Boeing (BA)",
            "GE Aerospace (GE)",
        },
        "watch_names": [
            "RTX",
            "Boeing",
            "GE Aerospace",
        ],
        "signal_terms": ["order-book quality", "aftermarket resilience", "fleet renewal", "execution discipline"],
        "regime_terms": ["geopolitical strain", "industrial backlog", "program execution"],
    },
]


def build_macro_lines(
    allow_placeholders: bool = True,
    issue_date: dt.date | None = None,
) -> tuple[list[str], list[str], dict[str, float | None], dict[str, dict[str, object]]]:
    current_issue_date = issue_date or resolve_issue_date(None)
    exact_snapshot = load_market_snapshot(current_issue_date)
    cached_snapshot = load_latest_market_snapshot(current_issue_date)
    lines: list[str] = []
    failures: list[str] = []
    metrics: dict[str, float | None] = {
        "cpi_yoy": None,
        "unemployment": None,
        "fed_funds": None,
        "ten_year": None,
        "brent": None,
    }
    entries: dict[str, dict[str, object]] = {}

    for label, config in MACRO_SERIES.items():
        entry: dict[str, object] | None = None
        if exact_snapshot:
            maybe_entry = exact_snapshot.get("macro", {}).get(label)
            if isinstance(maybe_entry, dict):
                entry = maybe_entry
        try:
            if entry is None:
                if config["kind"] == "yoy":
                    as_of, value = latest_fred_yoy(str(config["series_id"]))
                else:
                    as_of, value = latest_fred_value(str(config["series_id"]))
                entry = {
                    "label": label,
                    "kind": config["kind"],
                    "value": value,
                    "as_of": as_of,
                    "source": config["source_live"],
                    "url": config["url"],
                    "origin": "live",
                    "captured_on": current_issue_date.isoformat(),
                }
        except Exception:
            cached_entry = None
            if cached_snapshot:
                maybe_entry = cached_snapshot.get("macro", {}).get(label)
                if isinstance(maybe_entry, dict) and days_between(current_issue_date, str(maybe_entry.get("captured_on", ""))) <= MACRO_CACHE_MAX_AGE_DAYS:
                    cached_entry = {**maybe_entry, "origin": "cache"}
            if cached_entry is not None:
                entry = cached_entry
            elif entry is None:
                failures.append(label)
                continue

        entries[label] = entry
        if label == "US CPI (YoY)":
            metrics["cpi_yoy"] = float(entry["value"])
        elif label == "US unemployment rate":
            metrics["unemployment"] = float(entry["value"])
        elif label == "Fed funds rate":
            metrics["fed_funds"] = float(entry["value"])
        elif label == "US 10-year Treasury":
            metrics["ten_year"] = float(entry["value"])
        elif label == "Brent crude":
            metrics["brent"] = float(entry["value"])
        lines.append(render_macro_line(label, entry))

    return lines, failures, metrics, entries


def parse_numeric(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except Exception:
        return None


def extract_previous_investment_section(issue_date: dt.date) -> str:
    previous_issues = sorted(
        path for path in ISSUES_DIR.glob("*-daily-newsletter.md")
        if path.stem < f"{issue_date.isoformat()}-daily-newsletter"
    )
    if not previous_issues:
        return ""
    previous_text = previous_issues[-1].read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^### Upcoming Investment Opportunities\n(?P<body>.*?)(?=^## |\Z)",
        previous_text,
    )
    return match.group("body").strip() if match else ""


def recent_theme_mentions(theme: dict[str, object], previous_section: str) -> int:
    text = previous_section.lower()
    return sum(1 for name in theme["watch_names"] if str(name).lower() in text)


def format_company_list(names: list[str]) -> str:
    if not names:
        return ""
    bolded = [f"**{name}**" for name in names]
    if len(bolded) == 1:
        return bolded[0]
    if len(bolded) == 2:
        return f"{bolded[0]} and {bolded[1]}"
    return ", ".join(bolded[:-1]) + f", and {bolded[-1]}"


def format_plain_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def select_investment_themes(
    company_movers: list[tuple[str, str, str]],
    macro_metrics: dict[str, float | None],
    quote_snapshot: dict[str, dict[str, float | None | str]],
    previous_section: str,
) -> list[dict[str, object]]:
    selected_labels = {label for label, _price, _move in company_movers}
    oil_move = quote_snapshot.get("Oil proxy (USO)", {}).get("move_pct")
    qqq_move = quote_snapshot.get("NASDAQ-100 (QQQ)", {}).get("move_pct")

    scored: list[dict[str, object]] = []
    for theme in INVESTMENT_THEME_LIBRARY:
        score = sum(2 for label in theme["mover_labels"] if label in selected_labels)
        if theme["id"] == "ai_infrastructure":
            if (qqq_move or 0) >= 0:
                score += 1
        elif theme["id"] == "power_and_grid":
            if (macro_metrics.get("brent") or 0) >= 85:
                score += 2
            if (oil_move or 0) >= 2:
                score += 1
            if (macro_metrics.get("ten_year") or 0) >= 4.0:
                score += 1
        elif theme["id"] == "resilient_software":
            if (macro_metrics.get("fed_funds") or 99) <= 4.0:
                score += 1
            if (macro_metrics.get("unemployment") or 99) < 5.0:
                score += 1
        elif theme["id"] == "aerospace_defense":
            if (macro_metrics.get("brent") or 0) >= 85:
                score += 1
            if (oil_move or 0) >= 2:
                score += 1

        repeated_recently = recent_theme_mentions(theme, previous_section) >= 2
        effective_score = score - 2 if repeated_recently and score < 4 else score
        scored.append(
            {
                **theme,
                "score": score,
                "effective_score": effective_score,
                "repeated_recently": repeated_recently,
            }
        )

    ranked = sorted(
        scored,
        key=lambda item: (int(item["effective_score"]), int(item["score"]), str(item["id"])),
        reverse=True,
    )
    chosen = [item for item in ranked if int(item["effective_score"]) > 0][:2]
    if len(chosen) < 2:
        fallback = [item for item in ranked if item not in chosen][: 2 - len(chosen)]
        chosen.extend(fallback)
    return chosen


def theme_paragraph(theme: dict[str, object], macro_metrics: dict[str, float | None], index: int) -> str:
    companies = format_company_list(list(theme["watch_names"])[:4])
    signal_terms = format_plain_list(list(theme["signal_terms"])[:3])
    regime_terms = format_plain_list(list(theme["regime_terms"])[:3])
    label = str(theme["label"])
    repeated_recently = bool(theme.get("repeated_recently"))

    opener = f"{label} still looks worth watching"
    if repeated_recently:
        opener += " because the current regime still supports the thesis"
    else:
        opener += " because today's signals point there more clearly than the previous issue did"

    sentence = (
        f"{opener}. Watch {companies} for evidence on {signal_terms}; the real question is whether "
        f"{regime_terms} keep translating into durable earnings power rather than just short-term momentum."
    )

    if index == 1:
        sentence += " " + build_regime_sentence(macro_metrics)
    return sentence


def build_regime_sentence(macro_metrics: dict[str, float | None]) -> str:
    ten_year = macro_metrics.get("ten_year")
    brent = macro_metrics.get("brent")
    fed_funds = macro_metrics.get("fed_funds")
    cpi_yoy = macro_metrics.get("cpi_yoy")

    fragments: list[str] = []
    if ten_year is not None:
        fragments.append(f"the 10-year Treasury is still around {ten_year:.2f}%")
    if brent is not None:
        fragments.append(f"Brent is near ${brent:.2f}")
    if fed_funds is not None:
        fragments.append(f"the Fed funds rate is {fed_funds:.2f}%")
    if cpi_yoy is not None:
        fragments.append(f"headline CPI is running near {cpi_yoy:.1f}% year over year")

    if not fragments:
        return (
            "Across any cluster, the useful discipline is to track the variables that can actually change the thesis: "
            "rates, energy costs, backlog quality, pricing power, and whether capex survives contact with tighter budgets."
        )

    joined = "; ".join(fragments[:3])
    return (
        f"Across any cluster, keep the regime in view: {joined}. That is why the right watchlist is one tied to "
        "constraint variables, not just recent momentum."
    )


def build_investment_opportunities(
    issue_date: dt.date,
    company_movers: list[tuple[str, str, str]],
    macro_metrics: dict[str, float | None],
    quote_snapshot: dict[str, dict[str, float | None | str]],
) -> list[str]:
    previous_section = extract_previous_investment_section(issue_date)
    themes = select_investment_themes(company_movers, macro_metrics, quote_snapshot, previous_section)
    paragraphs: list[str] = []

    for index, theme in enumerate(themes[:2]):
        paragraphs.append(theme_paragraph(theme, macro_metrics, index))

    if not paragraphs:
        paragraphs.append(build_regime_sentence(macro_metrics))

    lines = ["### Upcoming Investment Opportunities", ""]
    for paragraph in paragraphs:
        lines.append(paragraph)
        lines.append("")
    return lines


def build_markets_section(issue_date: dt.date, allow_placeholders: bool = True) -> tuple[list[str], dict[str, list[str]]]:
    failures = {
        "quotes": [],
        "macro": [],
    }
    lines = ["## Markets & Economy", ""]
    exact_snapshot = load_market_snapshot(issue_date)
    cached_snapshot = load_latest_market_snapshot(issue_date)
    quote_snapshot: dict[str, dict[str, float | None | str]] = {}
    quote_entries = resolve_quote_entries(CORE_MARKET_TICKERS, issue_date, cached_snapshot, exact_snapshot)
    for label, _symbol in CORE_MARKET_TICKERS:
        entry = quote_entries.get(label)
        if entry is None:
            failures["quotes"].append(label)
            continue
        quote_snapshot[label] = {
            "price": parse_numeric(str(entry["price"])),
            "move": str(entry["move"]),
            "move_pct": float(entry.get("move_pct", 0.0)),
        }
        lines.append(render_quote_line(label, entry, issue_date))
    company_movers, company_failures, company_entries = select_company_movers(issue_date=issue_date, allow_placeholders=allow_placeholders)
    failures["quotes"].extend(company_failures)
    for label, price, move in company_movers:
        entry = company_entries.get(label)
        if entry is None:
            continue
        quote_entries[label] = entry
        lines.append(render_quote_line(label, entry, issue_date))
    macro_lines, macro_failures, macro_metrics, macro_entries = build_macro_lines(allow_placeholders=allow_placeholders, issue_date=issue_date)
    failures["macro"].extend(macro_failures)
    lines.extend(macro_lines)
    save_market_snapshot(
        issue_date,
        {
            "date": issue_date.isoformat(),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "quotes": {
                label: {
                    **entry,
                    "captured_on": str(entry.get("captured_on", issue_date.isoformat())),
                }
                for label, entry in quote_entries.items()
            },
            "macro": {
                label: {
                    **entry,
                    "captured_on": str(entry.get("captured_on", issue_date.isoformat())),
                }
                for label, entry in macro_entries.items()
            },
        },
    )
    lines.extend(["", *build_investment_opportunities(issue_date, company_movers, macro_metrics, quote_snapshot)])
    return lines, failures


def resolve_quote_entries(
    ticker_pairs: list[tuple[str, str]],
    issue_date: dt.date,
    cached_snapshot: dict | None,
    exact_snapshot: dict | None = None,
) -> dict[str, dict[str, object]]:
    resolved: dict[str, dict[str, object]] = {}
    remaining_pairs: list[tuple[str, str]] = []

    for label, symbol in ticker_pairs:
        if exact_snapshot:
            maybe_entry = exact_snapshot.get("quotes", {}).get(label)
            if isinstance(maybe_entry, dict):
                resolved[label] = maybe_entry
                continue
        remaining_pairs.append((label, symbol))

    def resolve_one(label: str, symbol: str) -> tuple[str, dict[str, object] | None]:
        snapshot = fetch_yahoo_quote_snapshot(symbol)
        if snapshot is None and cached_snapshot:
            maybe_entry = cached_snapshot.get("quotes", {}).get(label)
            if isinstance(maybe_entry, dict) and days_between(issue_date, str(maybe_entry.get("captured_on", ""))) <= QUOTE_CACHE_MAX_AGE_DAYS:
                snapshot = {**maybe_entry, "origin": "cache"}
        return label, snapshot

    if not remaining_pairs:
        return resolved

    with cf.ThreadPoolExecutor(max_workers=min(QUOTE_FETCH_WORKERS, max(1, len(remaining_pairs)))) as executor:
        futures = [executor.submit(resolve_one, label, symbol) for label, symbol in remaining_pairs]
        for future in cf.as_completed(futures):
            label, snapshot = future.result()
            if snapshot is not None:
                resolved[label] = snapshot

    return resolved


def build_main_entry(entry: dict) -> list[str]:
    title = clean_title(entry["title"])
    summary = summarize(entry.get("summary") or "No summary available.")
    publisher = entry.get("publisher", "")
    source = source_label(entry.get("link", ""), publisher)
    link = preferred_link(entry.get("link", ""), publisher)
    return [
        f"### {title}",
        "",
        f"**Source:** {source}",
        "",
        summary,
        "",
        f"**Link:** [Read at {source}]({link})" if link else "",
        "",
    ]


def collect_candidate_pool(
    section: str,
    sections: dict[str, list[dict]],
    used_keys: set[tuple[str, str]],
    *,
    include_self: bool = True,
    limit: int = 6,
) -> list[dict]:
    ordered_sections: list[str] = []
    if include_self:
        ordered_sections.append(section)
    ordered_sections.extend(RESCUE_SECTION_FALLBACKS.get(section, []))
    ordered_sections.extend(
        candidate_section
        for candidate_section in SECTION_ORDER
        if candidate_section not in ordered_sections and candidate_section not in {"Markets & Economy"}
    )

    pool: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for candidate_section in ordered_sections:
        for entry in sections.get(candidate_section, []):
            key = entry_key(entry)
            if not key[0] or key in seen or key in used_keys:
                continue
            seen.add(key)
            pool.append(entry)
            if len(pool) >= limit:
                return pool
    return pool


def build_short_takes(entries: list[dict]) -> list[str]:
    if not entries:
        return []
    lines = ["### Short Takes", ""]
    for entry in entries:
        title = clean_title(entry["title"])
        summary = short_take_summary(entry, 180)
        publisher = entry.get("publisher", "")
        source = source_label(entry.get("link", ""), publisher)
        link = preferred_link(entry.get("link", ""), publisher)
        tail = f" [Source: {source}]({link})" if link else ""
        text = f"- **{title}:** {summary}{tail}" if summary else f"- **{title}.**{tail}"
        lines.append(text)
    lines.append("")
    return lines


def build_breaking_news(entries: list[dict]) -> list[str]:
    if not entries:
        return []
    lines = ["### Breaking News", ""]
    for entry in entries:
        title = clean_title(entry["title"])
        summary = short_take_summary(entry, 160)
        publisher = entry.get("publisher", "")
        source = source_label(entry.get("link", ""), publisher)
        link = preferred_link(entry.get("link", ""), publisher)
        tail = f" [{source}]({link})" if link else ""
        text = f"- **{title}:** {summary}{tail}" if summary else f"- **{title}.**{tail}"
        lines.append(text)
    lines.append("")
    return lines


def build_tools_section(
    entries: list[dict],
    *,
    sections: dict[str, list[dict]] | None = None,
    used_keys: set[tuple[str, str]] | None = None,
) -> list[str]:
    lines = ["## Tools You Can Use", ""]
    local_used_keys = used_keys if used_keys is not None else set()
    available_entries = [entry for entry in entries if entry_key(entry) not in local_used_keys]
    if sections is not None:
        fallback_pool = collect_candidate_pool("Tools You Can Use", sections, local_used_keys, include_self=False, limit=10)
        seen_keys = {entry_key(entry) for entry in available_entries}
        for entry in fallback_pool:
            key = entry_key(entry)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            available_entries.append(entry)
    if not available_entries:
        lines.append("Insufficient sourced material for this section today.")
        lines.append("")
        return lines

    available_entries = sorted(available_entries, key=tool_entry_priority, reverse=True)

    main_entries = available_entries[:3]
    enrich_entries(main_entries)
    for entry in main_entries:
        title = clean_title(entry["title"])
        summary = summarize(entry.get("summary") or "", 200)
        publisher = entry.get("publisher", "")
        source = source_label(entry.get("link", ""), publisher)
        link = preferred_link(entry.get("link", ""), publisher)
        local_used_keys.add(entry_key(entry))
        lines.extend(
            [
                f"### {title}",
                "",
                summary or "Useful tool worth opening directly.",
                "",
                f"**Link:** [Open tool]({link})" if link else (f"**Link:** [Read at {source}]({link})" if link else ""),
                "",
            ]
        )

    short_entries = available_entries[3:7]
    if short_entries:
        lines.append("### Short Takes")
        lines.append("")
        for entry in short_entries:
            title = clean_title(entry["title"])
            summary = summarize(entry.get("summary") or "", 120)
            publisher = entry.get("publisher", "")
            source = source_label(entry.get("link", ""), publisher)
            link = preferred_link(entry.get("link", ""), publisher)
            local_used_keys.add(entry_key(entry))
            tail = f" [Open tool]({link})" if link else (f" [Source: {source}]({link})" if link else "")
            lines.append(f"- **{title}:** {summary}{tail}" if summary else f"- **{title}.**{tail}")
        lines.append("")
    return lines


def build_generic_section(
    section: str,
    entries: list[dict],
    *,
    sections: dict[str, list[dict]] | None = None,
    used_keys: set[tuple[str, str]] | None = None,
) -> list[str]:
    lines = [f"## {section}", ""]
    local_used_keys = used_keys if used_keys is not None else set()
    available_entries = [entry for entry in entries if entry_key(entry) not in local_used_keys]
    main_count, short_count = DEFAULT_SECTION_COUNTS.get(section, (1, 2))
    required_total = main_count + short_count
    if section == "World News":
        required_total += MIN_BREAKING_NEWS_COUNT
    if sections is not None and len(available_entries) < required_total:
        fallback_pool = collect_candidate_pool(
            section,
            sections,
            local_used_keys,
            include_self=False,
            limit=max(required_total - len(available_entries), 0) + 12,
        )
        seen_keys = {entry_key(entry) for entry in available_entries}
        for entry in fallback_pool:
            key = entry_key(entry)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            available_entries.append(entry)
    if not available_entries:
        lines.append("Insufficient sourced material for this section today.")
        lines.append("")
        return lines
    ranked_entries = sorted(available_entries, key=summary_quality, reverse=True)
    main_entries = ranked_entries[:main_count]
    enrich_entries(main_entries)
    main_keys = {entry_key(entry) for entry in main_entries}
    remaining_entries = [entry for entry in ranked_entries if entry_key(entry) not in main_keys]
    breaking_entries: list[dict] = []
    if section == "World News":
        breaking_entries = remaining_entries[:MIN_BREAKING_NEWS_COUNT]
        breaking_keys = {entry_key(entry) for entry in breaking_entries}
        remaining_entries = [entry for entry in remaining_entries if entry_key(entry) not in breaking_keys]
    short_entries = select_distinct_entries(
        remaining_entries,
        blocked_titles=[clean_title(str(entry.get("title", ""))) for entry in main_entries],
        limit=short_count,
    )
    for entry in [*main_entries, *breaking_entries, *short_entries]:
        local_used_keys.add(entry_key(entry))
    for entry in main_entries:
        lines.extend(build_main_entry(entry))
    if breaking_entries:
        lines.extend(build_breaking_news(breaking_entries))
    lines.extend(build_short_takes(short_entries))
    return lines


def build_entertainment_section(
    entries: list[dict],
    *,
    sections: dict[str, list[dict]] | None = None,
    used_keys: set[tuple[str, str]] | None = None,
) -> list[str]:
    lines = ["## Entertainment", ""]
    local_used_keys = used_keys if used_keys is not None else set()
    available_entries = [entry for entry in entries if entry_key(entry) not in local_used_keys]
    if not available_entries and sections is not None:
        available_entries = collect_candidate_pool("Entertainment", sections, local_used_keys, include_self=False, limit=3)
    if not available_entries:
        lines.append("Insufficient sourced material for this section today.")
        lines.append("")
        return lines

    lines.extend(["### What Looks Worth Your Attention", ""])
    shortlist: list[dict] = []
    seen_story_keys: set[str] = set()
    for entry in available_entries:
        story_key = lead_story_key(entry.get("title", ""))
        if story_key and story_key in seen_story_keys:
            continue
        if story_key:
            seen_story_keys.add(story_key)
        shortlist.append(entry)
        if len(shortlist) >= 6:
            break
    for entry in shortlist:
        title = clean_title(entry["title"])
        summary = summarize(entry.get("summary") or "", 140)
        publisher = entry.get("publisher", "")
        source = source_label(entry.get("link", ""), publisher)
        link = preferred_link(entry.get("link", ""), publisher)
        local_used_keys.add(entry_key(entry))
        suffix = f" [Source: {source}]({link})" if link else ""
        lines.append(f"- **{title}:** {summary}{suffix}" if summary else f"- **{title}.**{suffix}")
    lines.append("")
    return lines


def build_travel_section(
    entries: list[dict],
    *,
    sections: dict[str, list[dict]] | None = None,
    used_keys: set[tuple[str, str]] | None = None,
) -> list[str]:
    lines = ["## Travel", ""]
    local_used_keys = used_keys if used_keys is not None else set()
    available_entries = [entry for entry in entries if entry_key(entry) not in local_used_keys]
    if not available_entries and sections is not None:
        available_entries = collect_candidate_pool("Travel", sections, local_used_keys, include_self=False, limit=1)
    if available_entries:
        entry = available_entries[0]
        local_used_keys.add(entry_key(entry))
        enrich_entries([entry])
        title = clean_title(entry["title"])
        lines.append(f"### {title}")
        lines.append("")
        summary = summarize(entry.get("summary") or "", 220)
        publisher = entry.get("publisher", "")
        source = source_label(entry.get("link", ""), publisher)
        link = preferred_link(entry.get("link", ""), publisher)
        image_url = entry.get("image_url", "").strip()
        if image_url:
            lines.append(f"![{title}]({image_url})")
            lines.append("")
        lines.append(f"**{title}**")
        lines.append("")
        lines.append(f"{summary}" + (f" [Source: {source}]({link})" if link else ""))
    else:
        lines.extend(["### Travel Brief", "", "Insufficient sourced material for this section today."])
    lines.append("")
    return lines


def build_idea_section(
    entries: list[dict],
    *,
    sections: dict[str, list[dict]] | None = None,
    used_keys: set[tuple[str, str]] | None = None,
) -> list[str]:
    lines = ["## Idea Of The Day", ""]
    local_used_keys = used_keys if used_keys is not None else set()
    available_entries = [entry for entry in entries if entry_key(entry) not in local_used_keys]
    if not available_entries and sections is not None:
        available_entries = collect_candidate_pool("Idea Of The Day", sections, local_used_keys, include_self=False, limit=1)
    if available_entries:
        entry = available_entries[0]
        local_used_keys.add(entry_key(entry))
        enrich_entries([entry])
        title = clean_title(entry["title"])
        lines.append(f"### {title}")
        lines.append("")
        summary = summarize(entry.get("summary") or "", 220)
        link = preferred_link(entry.get("link", ""), entry.get("publisher", ""))
        lines.append(summary + (f" [Source]({link})" if link else ""))
    else:
        lines.extend(["### Concept Brief", "", "Insufficient sourced material for this section today."])
    lines.append("")
    return lines


def build_quick_hits(sections: dict[str, list[dict]]) -> list[str]:
    lines = ["## Quick Hits", ""]
    for section in SECTION_ORDER:
        if section in LAST_THREE or section == "Markets & Economy":
            continue
        entries = sections.get(section, [])
        if not entries:
            continue
        title = clean_title(entries[0]["title"])
        lines.append(f"- **{section}:** {title}.")
    lines.append("")
    return lines


def build_overview(sections: dict[str, list[dict]]) -> list[str]:
    highlighted_sections = [
        section
        for section in ("Need To Know", "Research Watch", "World News", "Technology", "AI", "Tools You Can Use")
        if sections.get(section)
    ][:3]
    if not highlighted_sections:
        highlighted_sections = [
            section
            for section in SECTION_ORDER[1:]
            if section in sections and sections.get(section)
        ][:3]
    if not highlighted_sections:
        return ["Today's issue depends on stronger sourced material before a useful thematic overview can be written."]

    lead_entries = [sections[section][0] for section in highlighted_sections]
    enrich_entries(lead_entries)

    sentences: list[str] = []
    for index, (section, entry) in enumerate(zip(highlighted_sections, lead_entries)):
        title = clean_title(entry["title"])
        summary = summarize(entry.get("summary") or "", 180)
        sentence = summary or title
        if index == 0:
            sentences.append(f"Today's lead signal comes from {section.lower()}: {sentence}.")
        else:
            sentences.append(f"In {section.lower()}, {sentence}.")
    return sentences[:3]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a draft daily issue from fetched candidates.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    issue_date = resolve_issue_date(args.date)

    candidates = load_candidates(issue_date)
    sections = candidates.get("sections", {})
    issue_path = ISSUES_DIR / f"{issue_date.isoformat()}-daily-newsletter.md"
    if issue_path.exists() and not args.overwrite:
        raise SystemExit(f"Issue already exists: {issue_path}. Use --overwrite to replace it.")

    lines = [
        "# Frontier Threads",
        "",
        f"## {issue_date.isoformat()}",
        "",
        "### The day's most interesting developments in science, technology, and ideas",
        "",
        *build_overview(sections),
        "",
    ]
    lines.extend(build_quick_hits(sections))
    market_lines, _ = build_markets_section(issue_date)
    lines.extend(market_lines)
    used_keys: set[tuple[str, str]] = set()

    for section in SECTION_ORDER[1:]:
        entries = sections.get(section, [])
        if section == "Entertainment":
            lines.extend(build_entertainment_section(entries, sections=sections, used_keys=used_keys))
        elif section == "Travel":
            lines.extend(build_travel_section(entries, sections=sections, used_keys=used_keys))
        elif section == "Idea Of The Day":
            lines.extend(build_idea_section(sections.get("Research Watch", []), sections=sections, used_keys=used_keys))
        elif section == "Tools You Can Use":
            lines.extend(build_tools_section(entries, sections=sections, used_keys=used_keys))
        else:
            lines.extend(build_generic_section(section, entries, sections=sections, used_keys=used_keys))

    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    issue_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"Wrote draft issue to {issue_path}")


if __name__ == "__main__":
    main()
