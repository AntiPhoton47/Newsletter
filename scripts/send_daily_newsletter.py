#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import smtplib
import ssl
from urllib.parse import urlparse
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

from issue_clock import resolve_issue_date


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
OUTPUT_DIR = ROOT / "output"


def display_label_for_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "source"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def issue_path_for(date_value: dt.date) -> Path:
    return ISSUES_DIR / f"{date_value.isoformat()}-daily-newsletter.md"


def find_latest_issue() -> Path:
    issues = sorted(ISSUES_DIR.glob("*-daily-newsletter.md"))
    if not issues:
        raise FileNotFoundError(f"No daily issues found in {ISSUES_DIR}")
    return issues[-1]


def render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(
        r"(?<![\">])(https?://[^\s<]+)",
        lambda match: f'<a href="{match.group(1)}">{display_label_for_url(match.group(1))}</a>',
        escaped,
    )
    return escaped


def render_meta_paragraph(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("**Link:**") or stripped.startswith("Link:"):
        url_match = re.search(r"(https?://\S+)", stripped)
        if url_match:
            url = url_match.group(1).rstrip(").,;")
            label = f"Read source at {display_label_for_url(url)}"
            return f'<p class="meta meta-link"><a class="link-chip" href="{url}">{html.escape(label)}</a></p>'
    return f'<p class="meta">{render_inline(text)}</p>'


def market_card_html(item: str) -> str:
    match = re.match(r"\*\*([^*]+)\:\*\*\s*(.+)", item)
    if match:
        label = render_inline(match.group(1))
        body = match.group(2)
    else:
        label = ""
        body = item

    trend_match = re.search(r",\s*((?:up|down|rose|fell).+)", body, flags=re.IGNORECASE)
    if trend_match:
        value = render_inline(body[: trend_match.start()].strip())
        detail = render_inline(trend_match.group(1).strip())
    else:
        value = render_inline(body)
        detail = ""

    trend_class = ""
    lowered = body.lower()
    if "up " in lowered or "rose" in lowered:
        trend_class = " up"
    elif "down " in lowered or "fell" in lowered:
        trend_class = " down"

    label_html = f'<div class="stat-label">{label}</div>' if label else ""
    detail_html = f'<div class="stat-detail{trend_class}">{detail}</div>' if detail else ""
    return f'<div class="market-tile">{label_html}<div class="stat-value">{value}</div>{detail_html}</div>'


def markdown_to_blocks(markdown_text: str) -> list[tuple[str, str | list[str]]]:
    blocks: list[tuple[str, str | list[str]]] = []
    lines = markdown_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("### "):
            blocks.append(("h3", stripped[4:]))
            i += 1
            continue
        if stripped.startswith("## "):
            blocks.append(("h2", stripped[3:]))
            i += 1
            continue
        if stripped.startswith("# "):
            blocks.append(("h1", stripped[2:]))
            i += 1
            continue
        if stripped.startswith("> "):
            quote_lines = [stripped[2:]]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote_lines.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("blockquote", " ".join(quote_lines)))
            continue
        image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if image_match:
            blocks.append(("img", f"{image_match.group(1)}|{image_match.group(2)}"))
            i += 1
            continue
        if stripped.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("ul", items))
            continue

        paragraph_lines = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i].rstrip()
            next_stripped = next_line.strip()
            if not next_stripped:
                i += 1
                break
            if next_stripped.startswith(("# ", "## ", "### ", "- ", "> ")):
                break
            paragraph_lines.append(next_stripped)
            i += 1
        blocks.append(("p", " ".join(paragraph_lines)))
    return blocks


def blocks_to_html(blocks: Iterable[tuple[str, str | list[str]]]) -> str:
    parts: list[str] = []
    card_open = False
    current_section = ""
    investment_card_open = False
    for kind, value in blocks:
        if kind == "h1":
            if investment_card_open:
                parts.append("</div>")
                investment_card_open = False
            if card_open:
                parts.append("</div>")
                card_open = False
            parts.append(f'<h1 class="title">{render_inline(str(value))}</h1>')
        elif kind == "h2":
            if investment_card_open:
                parts.append("</div>")
                investment_card_open = False
            if card_open:
                parts.append("</div>")
            current_section = str(value).strip().lower()
            section_slug = re.sub(r"[^a-z0-9]+", "-", current_section).strip("-")
            parts.append(f'<div class="section-card section-card--{section_slug}">')
            card_open = True
            parts.append(f'<h2 class="section-title">{render_inline(str(value))}</h2>')
        elif kind == "h3":
            heading = str(value)
            if investment_card_open:
                parts.append("</div>")
                investment_card_open = False
            if current_section in {"markets & economy", "markets and economy"} and heading.strip().lower() == "upcoming investment opportunities":
                parts.append('<div class="investment-card">')
                investment_card_open = True
                parts.append(f'<h3 class="story-title">{render_inline(heading)}</h3>')
            else:
                parts.append(f'<h3 class="story-title">{render_inline(heading)}</h3>')
        elif kind == "p":
            text = str(value)
            if text.startswith("**Source:**") or text.startswith("**Link:**") or text.startswith("Link:"):
                parts.append(render_meta_paragraph(text))
            elif current_section in {"quick brew", "quick takes"}:
                parts.append(f'<p class="lede">{render_inline(text)}</p>')
            elif investment_card_open:
                parts.append(f'<p class="investment-copy">{render_inline(text)}</p>')
            else:
                parts.append(f'<p>{render_inline(text)}</p>')
        elif kind == "blockquote":
            parts.append(f'<blockquote>{render_inline(str(value))}</blockquote>')
        elif kind == "img":
            alt, src = str(value).split("|", 1)
            parts.append(
                '<figure class="feature-image">'
                f'<img src="{src}" alt="{html.escape(alt)}" />'
                f'<figcaption>{html.escape(alt)}</figcaption>'
                '</figure>'
            )
        elif kind == "ul":
            if current_section in {"markets & economy", "markets and economy"}:
                market_items = list(value)[:16]  # type: ignore[arg-type]
                econ_items = list(value)[16:]  # type: ignore[arg-type]
                market_cards = "".join(market_card_html(item) for item in market_items)
                econ_cards = "".join(
                    f'<div class="econ-row">{render_inline(item)}</div>'
                    for item in econ_items
                )
                parts.append(
                    '<div class="market-wrap">'
                    '<div class="market-panel">'
                    '<div class="panel-kicker">Markets</div>'
                    f'<div class="market-grid">{market_cards}</div>'
                    '</div>'
                    '<div class="econ-panel">'
                    '<div class="panel-kicker">Economic Data</div>'
                    f'<div class="econ-grid">{econ_cards}</div>'
                    '</div>'
                    '</div>'
                )
            elif current_section in {"quick brew", "quick takes"}:
                cards = "".join(
                    f'<div class="brief-card">{render_inline(item)}</div>'
                    for item in value  # type: ignore[arg-type]
                )
                parts.append(f'<div class="brief-grid">{cards}</div>')
            else:
                items = "".join(f"<li>{render_inline(item)}</li>" for item in value)  # type: ignore[arg-type]
                parts.append(f"<ul>{items}</ul>")
    if investment_card_open:
        parts.append("</div>")
    if card_open:
        parts.append("</div>")
    return "\n".join(parts)


def build_html_document(markdown_text: str, issue_date: dt.date) -> str:
    content_html = blocks_to_html(markdown_to_blocks(markdown_text))
    return f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Frontier Threads | {issue_date.isoformat()}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg:
        radial-gradient(circle at top right, rgba(249, 115, 22, 0.10), transparent 28%),
        linear-gradient(180deg, #fffaf5 0%, #f8fafc 55%, #f1f5f9 100%);
      --panel: rgba(255, 255, 255, 0.9);
      --panel-strong: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.94));
      --ink: #0f172a;
      --muted: rgba(51, 65, 85, 0.86);
      --line: rgba(148, 163, 184, 0.24);
      --line-strong: rgba(249, 115, 22, 0.30);
      --accent: #f97316;
      --accent-soft: rgba(249, 115, 22, 0.12);
      --accent-wash: linear-gradient(180deg, rgba(255,247,237,0.95), rgba(255,255,255,0.92));
      --link: #0ea5e9;
      --shadow: rgba(148, 163, 184, 0.14);
      --green: #15803d;
      --red: #dc2626;
      --masthead:
        radial-gradient(circle at top right, rgba(249, 115, 22, 0.12), transparent 30%),
        linear-gradient(135deg, rgba(37, 30, 34, 0.985), rgba(50, 44, 49, 0.97));
      --masthead-border: rgba(249, 115, 22, 0.38);
      --masthead-ink: #f8fafc;
      --masthead-muted: rgba(241, 245, 249, 0.9);
      --pill-bg: linear-gradient(135deg, rgba(14, 165, 233, 0.92), rgba(99, 102, 241, 0.9));
      --pill-ink: #eff6ff;
      --market-panel: linear-gradient(180deg, rgba(255,247,217,0.78), rgba(255,253,246,0.88));
      --market-tile: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(248,250,252,0.94));
      --econ-panel: linear-gradient(180deg, rgba(255,255,255,0.72), rgba(248,250,252,0.84));
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg:
          radial-gradient(circle at top right, rgba(249, 115, 22, 0.14), transparent 26%),
          linear-gradient(180deg, #111827 0%, #0f172a 55%, #020617 100%);
        --panel: rgba(15, 23, 42, 0.72);
        --panel-strong: linear-gradient(180deg, rgba(15,23,42,0.84), rgba(15,23,42,0.74));
        --ink: #f8fafc;
        --muted: rgba(226, 232, 240, 0.82);
        --line: rgba(148, 163, 184, 0.18);
        --line-strong: rgba(249, 115, 22, 0.42);
        --accent: #fb923c;
        --accent-soft: rgba(249, 115, 22, 0.14);
        --accent-wash: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.86));
        --link: #38bdf8;
        --shadow: rgba(2, 6, 23, 0.35);
        --green: #4ade80;
        --red: #fb7185;
        --masthead:
          radial-gradient(circle at top right, rgba(249, 115, 22, 0.14), transparent 30%),
          linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.94));
        --masthead-border: rgba(148, 163, 184, 0.24);
        --masthead-ink: #f8fafc;
        --masthead-muted: rgba(226, 232, 240, 0.86);
        --pill-bg: linear-gradient(135deg, rgba(18, 24, 38, 0.92), rgba(44, 64, 96, 0.82));
        --pill-ink: #f8fafc;
        --market-panel: linear-gradient(180deg, rgba(30,41,59,0.86), rgba(15,23,42,0.84));
        --market-tile: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.9));
        --econ-panel: linear-gradient(180deg, rgba(15,23,42,0.82), rgba(15,23,42,0.74));
      }}
    }}
    body {{
      margin: 0;
      padding: 24px 12px;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      line-height: 1.55;
    }}
    .shell {{
      max-width: 900px;
      margin: 0 auto;
    }}
    .masthead {{
      background: var(--masthead);
      color: var(--masthead-ink);
      border: 1px solid var(--masthead-border);
      border-radius: 28px;
      padding: 32px 32px 24px;
      box-shadow: 0 18px 40px rgba(24, 33, 47, 0.16);
    }}
    .eyebrow {{
      margin: 0 0 10px;
      font: 700 12px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--accent);
    }}
    .masthead h1 {{
      margin: 0;
      font-size: 42px;
      line-height: 1.02;
      letter-spacing: -0.03em;
    }}
    .masthead p {{
      margin: 12px 0 0;
      color: var(--masthead-muted);
      font-size: 17px;
      max-width: 680px;
    }}
    .content {{
      margin-top: 16px;
    }}
    .title {{
      display: none;
    }}
    .section-card {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px 26px;
      margin: 14px 0;
      box-shadow: 0 10px 24px var(--shadow);
      backdrop-filter: blur(8px);
      position: relative;
      overflow: hidden;
    }}
    .section-card::before {{
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.7), transparent 85%);
      opacity: 0.9;
    }}
    .section-title {{
      margin: 0 0 16px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
      color: var(--accent);
      font-size: 13px;
      line-height: 1.2;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .section-card--markets-economy {{
      background: var(--accent-wash);
      border-color: var(--line-strong);
    }}
    .story-title {{
      margin: 24px 0 10px;
      font-size: 26px;
      line-height: 1.18;
      letter-spacing: -0.02em;
      position: relative;
    }}
    .story-title:first-of-type {{
      margin-top: 8px;
    }}
    .story-title::after {{
      content: "";
      display: block;
      width: 52px;
      height: 3px;
      margin-top: 10px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.7));
      opacity: 0.85;
    }}
    p {{
      margin: 12px 0;
      font-size: 16px;
    }}
    .meta {{
      color: var(--muted);
      font-size: 14px;
      font-weight: 600;
    }}
    .meta-link {{
      margin-top: 14px;
    }}
    .link-chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--pill-bg);
      color: var(--pill-ink) !important;
      text-decoration: none;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.01em;
      box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
    }}
    .link-chip::after {{
      content: "↗";
      font-size: 12px;
      opacity: 0.9;
    }}
    .lede {{
      margin: 0;
      font-size: 17px;
      color: #243041;
    }}
    ul {{
      margin: 10px 0 16px 22px;
      padding: 0;
    }}
    li {{
      margin: 8px 0;
    }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 8px;
    }}
    .market-wrap {{
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 14px;
      margin-top: 10px;
    }}
    .market-panel,
    .econ-panel {{
      background: var(--market-panel);
      border: 1px solid var(--line-strong);
      border-radius: 20px;
      padding: 12px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
    }}
    .econ-panel {{
      background: var(--econ-panel);
      border-color: var(--line);
    }}
    .panel-kicker {{
      display: inline-block;
      margin-bottom: 12px;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--pill-bg);
      color: var(--pill-ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .market-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }}
    .market-tile {{
      background: var(--market-tile);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 10px 11px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
      position: relative;
      overflow: hidden;
    }}
    .market-tile::before {{
      content: "";
      position: absolute;
      inset: 0 0 auto 0;
      height: 4px;
      background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.72));
      opacity: 0.9;
    }}
    .stat-label {{
      margin: 4px 0 6px;
      font-size: 11px;
      font-weight: 700;
      color: var(--muted);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .stat-value {{
      font-size: 21px;
      font-weight: 800;
      line-height: 1.1;
      color: var(--ink);
      text-shadow: 0 1px 0 rgba(255,255,255,0.06);
    }}
    .stat-detail {{
      margin-top: 4px;
      font-size: 13px;
      font-weight: 700;
      color: var(--ink);
      opacity: 0.92;
    }}
    .stat-detail.up {{
      color: var(--green);
    }}
    .stat-detail.down {{
      color: var(--red);
    }}
    .econ-grid {{
      display: grid;
      gap: 10px;
    }}
    .econ-row {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 10px 12px;
      font-size: 14px;
      line-height: 1.45;
      position: relative;
      overflow: hidden;
    }}
    .investment-card {{
      margin-top: 16px;
      padding: 16px 18px 8px;
      border-radius: 20px;
      border: 1px solid var(--line-strong);
      background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,247,237,0.92));
      box-shadow: 0 10px 22px var(--shadow);
    }}
    .investment-card .story-title {{
      margin-top: 0;
    }}
    .investment-copy {{
      margin: 10px 0;
    }}
    .econ-row::before {{
      content: "";
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
      background: linear-gradient(180deg, var(--accent), rgba(14, 165, 233, 0.7));
    }}
    .brief-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .brief-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
      font-size: 15px;
      line-height: 1.45;
      position: relative;
      overflow: hidden;
    }}
    .brief-card::after {{
      content: "";
      position: absolute;
      right: -24px;
      bottom: -24px;
      width: 76px;
      height: 76px;
      border-radius: 50%;
      background: radial-gradient(circle, var(--accent-soft) 0%, rgba(249,115,22,0) 72%);
    }}
    blockquote {{
      margin: 18px 0;
      padding: 14px 18px;
      background: var(--accent-soft);
      border-left: 4px solid var(--accent);
      border-radius: 0 14px 14px 0;
      font-size: 18px;
    }}
    .feature-image {{
      margin: 16px 0 18px;
    }}
    .feature-image img {{
      display: block;
      width: 100%;
      max-height: 360px;
      object-fit: cover;
      border-radius: 20px;
      border: 1px solid var(--line);
      box-shadow: 0 14px 30px var(--shadow);
    }}
    .feature-image figcaption {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
    }}
    a {{
      color: var(--link);
    }}
    .footer {{
      color: var(--muted);
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      padding: 10px 6px 0;
      text-align: center;
    }}
    @media (max-width: 640px) {{
      body {{
        padding: 14px 8px;
      }}
      .masthead {{
        padding: 26px 20px 22px;
        border-radius: 18px;
      }}
      .masthead h1 {{
        font-size: 31px;
      }}
      .masthead p {{
        font-size: 16px;
      }}
      .section-card {{
        padding: 20px 18px;
        border-radius: 18px;
      }}
      .story-title {{
        font-size: 22px;
      }}
      p {{
        font-size: 16px;
      }}
      .market-wrap,
      .market-grid,
      .brief-grid {{
        grid-template-columns: 1fr;
      }}
      .market-panel,
      .econ-panel,
      .market-tile,
      .brief-card,
      .econ-row {{
        border-radius: 16px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="masthead">
      <p class="eyebrow">Daily Research Briefing</p>
      <h1>Frontier Threads</h1>
      <p>Science, technology, policy, and ideas worth your attention on {issue_date.strftime("%B %d, %Y")}.</p>
    </div>
    <div class="content">
      {content_html}
    </div>
    <div class="footer">
      <p>You are receiving this message because the local daily newsletter job is configured on this machine.</p>
    </div>
  </div>
</body>
</html>
"""


def build_plain_text(markdown_text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", markdown_text)
    text = text.replace("**", "").replace("*", "")
    return text


def send_email(subject: str, html_body: str, text_body: str) -> None:
    required = [
        "NEWSLETTER_SMTP_HOST",
        "NEWSLETTER_SMTP_PORT",
        "NEWSLETTER_SMTP_USERNAME",
        "NEWSLETTER_SMTP_PASSWORD",
        "NEWSLETTER_FROM",
        "NEWSLETTER_TO",
    ]
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ["NEWSLETTER_FROM"]
    message["To"] = os.environ["NEWSLETTER_TO"]
    if os.environ.get("NEWSLETTER_CC"):
        message["Cc"] = os.environ["NEWSLETTER_CC"]
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    host = os.environ["NEWSLETTER_SMTP_HOST"]
    port = int(os.environ["NEWSLETTER_SMTP_PORT"])
    username = os.environ["NEWSLETTER_SMTP_USERNAME"]
    password = os.environ["NEWSLETTER_SMTP_PASSWORD"]
    use_tls = os.environ.get("NEWSLETTER_SMTP_SECURITY", "starttls").lower()

    if use_tls == "ssl":
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(username, password)
            server.send_message(message)
        return

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        if use_tls == "starttls":
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()
        server.login(username, password)
        server.send_message(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render and send the daily newsletter.")
    parser.add_argument("--date", help="Issue date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--issue", help="Explicit path to a markdown issue file.")
    parser.add_argument("--preview-html", action="store_true", help="Write HTML preview without sending email.")
    parser.add_argument("--latest", action="store_true", help="Use the latest issue in the daily issues folder.")
    args = parser.parse_args()

    load_env_file(ROOT / ".env")
    issue_date = resolve_issue_date(args.date)

    if args.issue:
        issue_path = Path(args.issue).expanduser().resolve()
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", issue_path.name)
        if date_match:
            issue_date = dt.date.fromisoformat(date_match.group(1))
    elif args.latest:
        issue_path = find_latest_issue()
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", issue_path.name)
        if date_match:
            issue_date = dt.date.fromisoformat(date_match.group(1))
    else:
        issue_path = issue_path_for(issue_date)
        if not issue_path.exists():
            issue_path = find_latest_issue()
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", issue_path.name)
            if date_match:
                issue_date = dt.date.fromisoformat(date_match.group(1))

    markdown_text = issue_path.read_text(encoding="utf-8")
    html_body = build_html_document(markdown_text, issue_date)
    text_body = build_plain_text(markdown_text)
    subject_prefix = os.environ.get("NEWSLETTER_SUBJECT_PREFIX", "Frontier Threads")
    subject = f"{subject_prefix} | {issue_date.strftime('%B %d, %Y')}"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    preview_path = OUTPUT_DIR / f"{issue_date.isoformat()}-daily-newsletter.html"
    preview_path.write_text(html_body, encoding="utf-8")

    if args.preview_html:
        print(f"Preview written to {preview_path}")
        return

    send_email(subject, html_body, text_body)
    print(f"Sent {issue_path.name} to {os.environ.get('NEWSLETTER_TO')}")


if __name__ == "__main__":
    main()
