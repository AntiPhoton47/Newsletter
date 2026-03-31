#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import ssl
import urllib.request
import urllib.parse
from pathlib import Path

from fetch_candidates import decode_google_news_link, enrich_entries
from issue_clock import resolve_issue_date


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_DIR = ROOT / "data" / "candidates"
ISSUES_DIR = ROOT / "issues" / "daily"
REQUEST_TIMEOUT = 8


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
DEFAULT_SECTION_COUNTS = {
    "Need To Know": (1, 0),
    "Research Watch": (2, 2),
    "World News": (2, 3),
    "Philosophy": (1, 2),
    "Biology": (1, 2),
    "Psychology and Neuroscience": (1, 2),
    "Health and Medicine": (1, 2),
    "Sociology and Anthropology": (1, 2),
    "Technology": (1, 2),
    "Robotics": (1, 2),
    "AI": (1, 2),
    "Engineering": (1, 2),
    "Mathematics": (1, 2),
    "Historical Discoveries": (1, 2),
    "Archaeology": (1, 2),
    "Tools You Can Use": (2, 2),
    "Entertainment": (0, 0),
    "Travel": (0, 0),
    "Idea Of The Day": (0, 0),
}


def load_candidates(issue_date: dt.date) -> dict:
    path = CANDIDATES_DIR / f"{issue_date.isoformat()}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def clean_title(title: str) -> str:
    title = re.sub(r"\s*-\s*Google News$", "", title).strip()
    title = re.sub(r"^\[[0-9.]+\]\s*", "", title).strip()
    return title


def summarize(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*&nbsp;\s*", " ", text)
    text = re.sub(r"\s+-\s+[A-Z][A-Za-z0-9 .&|/-]+$", "", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def source_label(link: str, publisher: str = "") -> str:
    if publisher:
        return publisher
    host = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
    return host or "Source"


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read()
    except Exception:
        insecure_context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT, context=insecure_context) as response:
            return response.read()


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
    "tsla.us": "TSLA",
    "pltr.us": "PLTR",
    "arm.us": "ARM"
}

PUBLISHER_URLS = {
    "AP News": "https://apnews.com/",
    "arXiv": "https://arxiv.org/",
    "Bank of Japan": "https://www.boj.or.jp/en/",
    "BLS": "https://www.bls.gov/",
    "ECB": "https://www.ecb.europa.eu/",
    "Eurostat": "https://ec.europa.eu/eurostat/",
    "GitHub": "https://github.com/",
    "IAI TV": "https://iai.tv/",
    "IEEE": "https://www.ieee.org/",
    "IMF": "https://www.imf.org/",
    "International Monetary Fund | IMF": "https://www.imf.org/",
    "IARC": "https://www.iarc.who.int/",
    "Lonely Planet": "https://www.lonelyplanet.com/",
    "MIT Technology Review": "https://www.technologyreview.com/",
    "Nature": "https://www.nature.com/",
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
MARKET_TICKERS = [
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
    ("NVIDIA (NVDA)", "nvda.us"),
    ("Tesla (TSLA)", "tsla.us"),
    ("Palantir (PLTR)", "pltr.us"),
    ("ARM Holdings (ARM)", "arm.us"),
]


def fetch_yahoo_quote(symbol: str) -> tuple[str, str]:
    yahoo_symbol = YAHOO_SYMBOLS.get(symbol, symbol.upper())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}?interval=1d&range=5d"
    try:
        payload = json.loads(fetch_url(url).decode("utf-8"))
    except Exception:
        return ("data unavailable", "live quote unavailable")

    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        close_v = float(meta["regularMarketPrice"])
        previous_close = float(meta.get("chartPreviousClose") or meta.get("previousClose"))
        move = ((close_v - previous_close) / previous_close) * 100 if previous_close else 0.0
        direction = "up" if move > 0 else "down" if move < 0 else "flat"
        return (f"{close_v:.2f}", f"{direction} {abs(move):.2f}%")
    except Exception:
        return ("data unavailable", "live quote unavailable")


def fetch_fred_rows(series_id: str) -> list[tuple[str, str]]:
    url = FRED_SERIES_URL.format(series_id=urllib.parse.quote(series_id))
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            content = response.read().decode("utf-8")
    except Exception:
        insecure_context = ssl._create_unverified_context()
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT, context=insecure_context) as response:
            content = response.read().decode("utf-8")
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


def build_macro_lines(allow_placeholders: bool = True) -> tuple[list[str], list[str]]:
    lines: list[str] = []
    failures: list[str] = []

    try:
        cpi_date, cpi_yoy = latest_fred_yoy("CPIAUCSL")
        lines.append(
            f"- **US CPI (YoY):** {cpi_yoy:.1f}% as of {format_month(cpi_date)}. Source: [BLS via FRED](https://fred.stlouisfed.org/series/CPIAUCSL)"
        )
    except Exception:
        failures.append("US CPI (YoY)")
        if allow_placeholders:
            lines.append("- **US CPI (YoY):** Live macro series unavailable. Source: [BLS](https://www.bls.gov/)")

    try:
        unrate_date, unrate = latest_fred_value("UNRATE")
        lines.append(
            f"- **US unemployment rate:** {unrate:.1f}% as of {format_month(unrate_date)}. Source: [BLS via FRED](https://fred.stlouisfed.org/series/UNRATE)"
        )
    except Exception:
        failures.append("US unemployment rate")
        if allow_placeholders:
            lines.append("- **US unemployment rate:** Live macro series unavailable. Source: [BLS](https://www.bls.gov/)")

    try:
        fed_date, fed = latest_fred_value("FEDFUNDS")
        lines.append(
            f"- **Fed funds rate:** {fed:.2f}% as of {format_month(fed_date)}. Source: [Federal Reserve via FRED](https://fred.stlouisfed.org/series/FEDFUNDS)"
        )
    except Exception:
        failures.append("Fed funds rate")
        if allow_placeholders:
            lines.append("- **Fed funds rate:** Live macro series unavailable. Source: [Federal Reserve](https://www.federalreserve.gov/)")

    try:
        dgs10_date, dgs10 = latest_fred_value("DGS10")
        lines.append(
            f"- **US 10-year Treasury:** {dgs10:.2f}% latest daily close on {format_day(dgs10_date)}. Source: [Treasury via FRED](https://fred.stlouisfed.org/series/DGS10)"
        )
    except Exception:
        failures.append("US 10-year Treasury")
        if allow_placeholders:
            lines.append("- **US 10-year Treasury:** Live macro series unavailable. Source: [U.S. Treasury](https://home.treasury.gov/)")

    try:
        brent_date, brent = latest_fred_value("DCOILBRENTEU")
        lines.append(
            f"- **Brent crude:** ${brent:.2f}/barrel latest daily print on {format_day(brent_date)}. Source: [EIA via FRED](https://fred.stlouisfed.org/series/DCOILBRENTEU)"
        )
    except Exception:
        failures.append("Brent crude")
        if allow_placeholders:
            lines.append("- **Brent crude:** Live macro series unavailable. Source: [EIA](https://www.eia.gov/)")

    return lines, failures


def build_markets_section(allow_placeholders: bool = True) -> tuple[list[str], dict[str, list[str]]]:
    failures = {
        "quotes": [],
        "macro": [],
    }
    lines = ["## Markets & Economy", ""]
    for label, symbol in MARKET_TICKERS:
        price, move = fetch_yahoo_quote(symbol)
        available = price != "data unavailable" and move != "live quote unavailable"
        if not available:
            failures["quotes"].append(label)
            if not allow_placeholders:
                continue
        lines.append(f"- **{label}:** {price}, {move}.")
    macro_lines, macro_failures = build_macro_lines(allow_placeholders=allow_placeholders)
    failures["macro"].extend(macro_failures)
    lines.extend(macro_lines)
    lines.extend(
        [
            "",
            "### Upcoming Investment Opportunities",
            "",
            "Watch **NVIDIA**, **Broadcom**, **Micron**, and **Vertiv** for continued AI-infrastructure exposure; **Quanta Services**, **Eaton**, and **Siemens Energy** for grid modernization; and **ServiceNow**, **CrowdStrike**, and **ASML** for rate-sensitive quality growth and advanced-manufacturing exposure.",
            "",
        ]
    )
    return lines, failures


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


def build_short_takes(entries: list[dict]) -> list[str]:
    if not entries:
        return []
    lines = ["### Short Takes", ""]
    for entry in entries:
        title = clean_title(entry["title"])
        summary = summarize(entry.get("summary") or "", 140)
        publisher = entry.get("publisher", "")
        source = source_label(entry.get("link", ""), publisher)
        link = preferred_link(entry.get("link", ""), publisher)
        tail = f" [Source: {source}]({link})" if link else ""
        text = f"- **{title}:** {summary}{tail}" if summary else f"- **{title}.**{tail}"
        lines.append(text)
    lines.append("")
    return lines


def build_generic_section(section: str, entries: list[dict]) -> list[str]:
    lines = [f"## {section}", ""]
    if not entries:
        lines.append("No candidates available today.")
        lines.append("")
        return lines
    main_count, short_count = DEFAULT_SECTION_COUNTS.get(section, (1, 2))
    main_entries = entries[:main_count]
    enrich_entries(main_entries)
    short_entries = entries[main_count: main_count + short_count]
    for entry in main_entries:
        lines.extend(build_main_entry(entry))
    lines.extend(build_short_takes(short_entries))
    return lines


def build_entertainment_section(entries: list[dict]) -> list[str]:
    lines = ["## Entertainment", ""]
    categories = ["Movies", "Books", "TV Shows", "Video Games", "Concerts"]
    for category in categories:
        lines.append(f"### {category}")
        lines.append("")
        pool = entries[:2] if entries else []
        if pool:
            for entry in pool:
                title = clean_title(entry["title"])
                summary = summarize(entry.get("summary") or "", 120)
                publisher = entry.get("publisher", "")
                source = source_label(entry.get("link", ""), publisher)
                link = preferred_link(entry.get("link", ""), publisher)
                suffix = f" [Source: {source}]({link})" if link else ""
                lines.append(f"- **{title}:** {summary}{suffix}")
        else:
            lines.append("- Add current release manually. [Source](https://example.com)")
        lines.append("")
    return lines


def build_travel_section(entries: list[dict]) -> list[str]:
    lines = ["## Travel", "", "### Cool Place To Visit", ""]
    if entries:
        entry = entries[0]
        enrich_entries([entry])
        title = clean_title(entry["title"])
        summary = summarize(entry.get("summary") or "", 220)
        publisher = entry.get("publisher", "")
        source = source_label(entry.get("link", ""), publisher)
        link = preferred_link(entry.get("link", ""), publisher)
        lines.append(f"**{title}**")
        lines.append("")
        lines.append(f"{summary}" + (f" [Source: {source}]({link})" if link else ""))
    else:
        lines.append("**Add destination manually.** [Source](https://example.com)")
    lines.append("")
    return lines


def build_idea_section(entries: list[dict]) -> list[str]:
    lines = ["## Idea Of The Day", "", "### Concept to explain", ""]
    if entries:
        entry = entries[0]
        enrich_entries([entry])
        link = preferred_link(entry.get("link", ""), entry.get("publisher", ""))
        lines.append(
            f"Use today's strongest conceptual thread, for example from **{clean_title(entry['title'])}**, and explain it clearly in 1-2 paragraphs."
            + (f" [Source]({link})" if link else "")
        )
    else:
        lines.append("Explain one concept from the day's strongest science or mathematics story.")
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
        return ["The strongest developments are still being assembled from today's source mix."]

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
    market_lines, _ = build_markets_section()
    lines.extend(market_lines)

    for section in SECTION_ORDER[1:]:
        entries = sections.get(section, [])
        if section == "Entertainment":
            lines.extend(build_entertainment_section(entries))
        elif section == "Travel":
            lines.extend(build_travel_section(entries))
        elif section == "Idea Of The Day":
            lines.extend(build_idea_section(sections.get("Research Watch", [])))
        else:
            lines.extend(build_generic_section(section, entries))

    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    issue_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print(f"Wrote draft issue to {issue_path}")


if __name__ == "__main__":
    main()
