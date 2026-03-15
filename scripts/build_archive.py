#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
SITE_DIR = ROOT / "site"


CONFIG_YML = """title: Frontier Threads
description: Daily newsletter archive for science, technology, world affairs, and ideas.
baseurl: ""
url: ""
markdown: kramdown
highlighter: rouge
collections:
  issues:
    output: true
defaults:
  - scope:
      path: ""
      type: "issues"
    values:
      layout: issue
"""


DEFAULT_LAYOUT = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% if page.title %}{{ page.title }} | {% endif %}{{ site.title }}</title>
  <meta name="description" content="{{ page.summary | default: site.description | escape }}">
  <link rel="stylesheet" href="{{ '/assets/site.css' | relative_url }}">
</head>
<body>
  <div class="site-shell">
    <header class="site-header">
      <a class="brand" href="{{ '/' | relative_url }}">{{ site.title }}</a>
      <nav class="site-nav">
        <a href="{{ '/' | relative_url }}">Current Issue</a>
        <a href="{{ '/archive/' | relative_url }}">Archive</a>
      </nav>
    </header>
    <main class="page-content">
      {{ content }}
    </main>
  </div>
  <script>
    window.frontierThreadsConfig = {{
      baseUrl: {{ site.baseurl | jsonify }}
    }};
  </script>
  <script src="{{ '/assets/search.js' | relative_url }}"></script>
</body>
</html>
"""


ISSUE_LAYOUT = """---
layout: default
---
<article class="issue-page">
  <div class="issue-hero">
    <p class="issue-kicker">Daily Issue</p>
    <h1>{{ page.display_date }}</h1>
    <p class="issue-summary">{{ page.summary }}</p>
    <div class="issue-actions">
      <a class="button" href="{{ '/archive/' | relative_url }}">Browse archive</a>
      <a class="button button-secondary" href="{{ '/search.json' | relative_url }}">Search index</a>
    </div>
  </div>
  <div class="issue-content">
    {{ content }}
  </div>
</article>
"""


HOME_PAGE = """---
layout: default
title: Current Issue
permalink: /
---
{% assign latest = site.issues | sort: 'issue_date' | reverse | first %}
{% assign recent = site.issues | sort: 'issue_date' | reverse %}
<section class="landing-hero">
  <p class="issue-kicker">Frontier Threads</p>
  <h1>The current newsletter, plus a searchable archive.</h1>
  <p class="landing-copy">Read the latest issue first, then jump into older editions by date or keyword.</p>
</section>

{% if latest %}
<section class="current-issue-card">
  <div class="card-kicker">Latest Issue</div>
  <h2><a href="{{ latest.url | relative_url }}">{{ latest.display_date }}</a></h2>
  <p>{{ latest.summary }}</p>
  <div class="issue-actions">
    <a class="button" href="{{ latest.url | relative_url }}">Read current issue</a>
    <a class="button button-secondary" href="{{ '/archive/' | relative_url }}">Open archive</a>
  </div>
</section>
{% endif %}

<section class="search-panel">
  <div class="card-kicker">Archive Search</div>
  <h2>Find past coverage fast</h2>
  <p>Search by topic, section, person, research area, country, or company.</p>
  <input id="newsletter-search-input" class="search-input" type="search" placeholder="Search past newsletters by keyword">
  <div id="newsletter-search-status" class="search-status"></div>
  <div id="newsletter-search-results" class="search-results"></div>
</section>

<section class="archive-preview">
  <div class="card-kicker">Recent Issues</div>
  <div class="archive-list">
    {% for issue in recent limit: 12 %}
    <article class="archive-item">
      <h3><a href="{{ issue.url | relative_url }}">{{ issue.display_date }}</a></h3>
      <p>{{ issue.summary }}</p>
    </article>
    {% endfor %}
  </div>
</section>
"""


ARCHIVE_PAGE = """---
layout: default
title: Archive
permalink: /archive/
---
{% assign issues = site.issues | sort: 'issue_date' | reverse %}
<section class="landing-hero">
  <p class="issue-kicker">Archive</p>
  <h1>Browse and search every issue.</h1>
  <p class="landing-copy">The archive is filterable in the browser and backed by a generated keyword index.</p>
</section>

<section class="search-panel">
  <div class="card-kicker">Keyword Search</div>
  <input id="newsletter-search-input" class="search-input" type="search" placeholder="Search all archived issues">
  <div id="newsletter-search-status" class="search-status"></div>
  <div id="newsletter-search-results" class="search-results"></div>
</section>

<section class="archive-preview">
  <div class="card-kicker">All Issues</div>
  <div class="archive-list" id="newsletter-archive-list">
    {% for issue in issues %}
    <article class="archive-item" data-date="{{ issue.issue_date }}" data-summary="{{ issue.summary | escape }}">
      <h3><a href="{{ issue.url | relative_url }}">{{ issue.display_date }}</a></h3>
      <p>{{ issue.summary }}</p>
    </article>
    {% endfor %}
  </div>
</section>
"""


SITE_CSS = """
:root {
  color-scheme: light dark;
  --bg: linear-gradient(180deg, #fffaf5 0%, #f8fafc 48%, #eef2f7 100%);
  --panel: rgba(255, 255, 255, 0.92);
  --panel-strong: rgba(255, 255, 255, 0.96);
  --ink: #0f172a;
  --muted: #475569;
  --line: rgba(148, 163, 184, 0.24);
  --accent: #f97316;
  --accent-2: #0ea5e9;
  --shadow: rgba(15, 23, 42, 0.1);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: linear-gradient(180deg, #111827 0%, #0f172a 55%, #020617 100%);
    --panel: rgba(15, 23, 42, 0.82);
    --panel-strong: rgba(15, 23, 42, 0.9);
    --ink: #f8fafc;
    --muted: #cbd5e1;
    --line: rgba(148, 163, 184, 0.18);
    --accent: #fb923c;
    --accent-2: #38bdf8;
    --shadow: rgba(2, 6, 23, 0.35);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
a { color: var(--accent-2); text-decoration: none; }
a:hover { text-decoration: underline; }
.site-shell { max-width: 1120px; margin: 0 auto; padding: 24px 14px 56px; }
.site-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding: 18px 20px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: 0 10px 26px var(--shadow);
}
.brand {
  color: var(--ink);
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.site-nav {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.site-nav a {
  color: var(--muted);
  font-weight: 600;
}
.page-content { display: grid; gap: 16px; }
.landing-hero,
.search-panel,
.archive-preview,
.current-issue-card,
.issue-hero,
.issue-content {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 24px;
  box-shadow: 0 10px 28px var(--shadow);
}
.landing-hero,
.search-panel,
.archive-preview,
.current-issue-card,
.issue-hero {
  padding: 26px;
}
.issue-content { padding: 10px; overflow: hidden; }
.issue-kicker,
.card-kicker {
  margin: 0 0 10px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.landing-hero h1,
.issue-hero h1,
.current-issue-card h2,
.search-panel h2 {
  margin: 0;
  line-height: 1.05;
  letter-spacing: -0.03em;
}
.landing-hero h1 { font-size: clamp(2rem, 4vw, 3.5rem); max-width: 14ch; }
.issue-hero h1 { font-size: clamp(2rem, 4vw, 3.25rem); }
.current-issue-card h2,
.search-panel h2 { font-size: clamp(1.5rem, 3vw, 2.2rem); }
.landing-copy,
.issue-summary,
.current-issue-card p,
.search-panel p {
  margin: 12px 0 0;
  max-width: 68ch;
  color: var(--muted);
}
.issue-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 0 16px;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--accent), #fb7185);
  color: white;
  font-weight: 700;
  text-decoration: none;
}
.button:hover { text-decoration: none; filter: brightness(1.02); }
.button-secondary {
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--line);
}
.archive-list,
.search-results {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}
.archive-item,
.search-result {
  padding: 18px;
  background: var(--panel-strong);
  border: 1px solid var(--line);
  border-radius: 18px;
}
.archive-item h3,
.search-result h3 {
  margin: 0;
  font-size: 1.1rem;
}
.archive-item p,
.search-result p {
  margin: 8px 0 0;
  color: var(--muted);
}
.search-input {
  width: 100%;
  margin-top: 16px;
  min-height: 48px;
  padding: 0 16px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: rgba(255,255,255,0.72);
  color: var(--ink);
  font: inherit;
}
@media (prefers-color-scheme: dark) {
  .search-input { background: rgba(15, 23, 42, 0.7); }
}
.search-status {
  margin-top: 10px;
  color: var(--muted);
  font-size: 0.95rem;
}
.search-section {
  margin-top: 6px;
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.issue-page { display: grid; gap: 16px; }
.issue-content .shell {
  max-width: none;
  margin: 0;
}
.issue-content .masthead {
  margin: 0;
}
@media (max-width: 760px) {
  .site-header { flex-direction: column; align-items: flex-start; }
  .site-shell { padding-inline: 10px; }
  .landing-hero,
  .search-panel,
  .archive-preview,
  .current-issue-card,
  .issue-hero { padding: 20px; }
}
"""


SEARCH_JS = """(function () {
  const input = document.getElementById('newsletter-search-input');
  const results = document.getElementById('newsletter-search-results');
  const status = document.getElementById('newsletter-search-status');
  if (!input || !results || !status) return;

  const baseUrl = (window.frontierThreadsConfig && window.frontierThreadsConfig.baseUrl) || '';
  const searchUrl = `${baseUrl}/search.json`;
  let items = [];

  function render(matches, query) {
    if (!query) {
      results.innerHTML = '';
      status.textContent = 'Type to search all archived issues.';
      return;
    }

    status.textContent = `${matches.length} result${matches.length === 1 ? '' : 's'} for "${query}".`;
    results.innerHTML = matches.slice(0, 50).map((item) => {
      return `
        <article class="search-result">
          <div class="search-section">${item.date}</div>
          <h3><a href="${baseUrl}${item.url}">${item.display_date}</a></h3>
          <p>${item.summary}</p>
        </article>
      `;
    }).join('');
  }

  function search(query) {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      render([], '');
      return;
    }
    const matches = items.filter((item) => item.search_text.toLowerCase().includes(normalized));
    render(matches, normalized);
  }

  fetch(searchUrl)
    .then((response) => response.json())
    .then((data) => {
      items = Array.isArray(data) ? data : [];
      status.textContent = `Search ${items.length} archived issue${items.length === 1 ? '' : 's'}.`;
    })
    .catch(() => {
      status.textContent = 'Search index failed to load.';
    });

  input.addEventListener('input', function () {
    search(input.value);
  });
})();"""


def load_sender_module():
    path = ROOT / "scripts" / "send_daily_newsletter.py"
    spec = importlib.util.spec_from_file_location("send_daily_newsletter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def plain_text(markdown_text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", markdown_text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_#>`-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def extract_metadata(markdown_text: str, issue_date: dt.date, sender) -> dict[str, str]:
    lines = markdown_text.splitlines()
    summary = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("## "):
            continue
        if stripped.startswith("### ") and "The day's" in stripped:
            continue
        summary = stripped
        break
    if not summary:
        summary = "Daily newsletter covering science, technology, world affairs, and ideas."
    content_html = sender.blocks_to_html(sender.markdown_to_blocks(markdown_text))
    return {
        "title": "Frontier Threads",
        "display_date": issue_date.strftime("%B %d, %Y"),
        "issue_date": issue_date.isoformat(),
        "summary": summary,
        "content_html": content_html,
        "search_text": plain_text(markdown_text),
        "url": f"/issues/{issue_date.isoformat()}/",
    }


def issue_document(entry: dict[str, str]) -> str:
    return (
        "---\n"
        f'layout: issue\n'
        f'title: "{yaml_escape(entry["title"])}"\n'
        f'issue_date: "{entry["issue_date"]}"\n'
        f'display_date: "{yaml_escape(entry["display_date"])}"\n'
        f'summary: "{yaml_escape(entry["summary"])}"\n'
        f'permalink: "{entry["url"]}"\n'
        "---\n"
        f'{entry["content_html"]}\n'
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_search_index(entries: list[dict[str, str]]) -> str:
    payload = [
        {
            "date": entry["issue_date"],
            "display_date": entry["display_date"],
            "title": entry["title"],
            "summary": entry["summary"],
            "url": entry["url"],
            "search_text": entry["search_text"],
        }
        for entry in sorted(entries, key=lambda item: item["issue_date"], reverse=True)
    ]
    return json.dumps(payload, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Jekyll-based archive source tree for GitHub Pages.")
    parser.parse_args()

    sender = load_sender_module()
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, str]] = []
    for issue_path in sorted(ISSUES_DIR.glob("*-daily-newsletter.md")):
        issue_date = dt.date.fromisoformat(issue_path.name[:10])
        markdown_text = issue_path.read_text(encoding="utf-8")
        entry = extract_metadata(markdown_text, issue_date, sender)
        entries.append(entry)
        write_text(SITE_DIR / "_issues" / f"{issue_date.isoformat()}.md", issue_document(entry))

    write_text(SITE_DIR / "_config.yml", CONFIG_YML)
    write_text(SITE_DIR / "_layouts" / "default.html", DEFAULT_LAYOUT)
    write_text(SITE_DIR / "_layouts" / "issue.html", ISSUE_LAYOUT)
    write_text(SITE_DIR / "index.html", HOME_PAGE)
    write_text(SITE_DIR / "archive.html", ARCHIVE_PAGE)
    write_text(SITE_DIR / "assets" / "site.css", SITE_CSS.strip() + "\n")
    write_text(SITE_DIR / "assets" / "search.js", SEARCH_JS.strip() + "\n")
    write_text(SITE_DIR / "search.json", build_search_index(entries))

    print(f"Built Jekyll archive source in {SITE_DIR}")


if __name__ == "__main__":
    main()
