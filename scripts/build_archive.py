#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ISSUES_DIR = ROOT / "issues" / "daily"
SITE_DIR = ROOT / "site"
CURATIONS_PATH = ROOT / "config" / "site_curations.json"
PERSONAL_SITE_ASSETS = ROOT.parent / "PersonalWebsite" / "PersonalSite" / "assets" / "images"


def config_yml(baseurl: str = "", site_url: str = "") -> str:
    return f"""title: Frontier Threads
description: Daily newsletter archive for science, technology, world affairs, and ideas.
baseurl: "{baseurl}"
url: "{site_url}"
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
  <script>
    (function () {
      const key = "mm-theme";
      const saved = localStorage.getItem(key);
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      const mode = saved || (prefersDark ? "dark" : "light");
      document.documentElement.dataset.themeMode = mode;
    })();
  </script>
</head>
<body id="top">
  {% assign latest_issue = site.issues | sort: 'issue_date' | reverse | first %}
  <div class="site-shell">
    <header class="site-header">
      <a class="brand" href="{{ '/' | relative_url }}">{{ site.title }}</a>
      <nav class="site-nav">
        <button class="theme-toggle" type="button" onclick="toggleTheme()" aria-label="Toggle light and dark mode" title="Toggle theme">
          <span class="theme-toggle__icon" aria-hidden="true">◐</span>
          <span class="theme-toggle__label">Theme</span>
        </button>
        <a href="{% if latest_issue %}{{ latest_issue.url | relative_url }}{% else %}{{ '/' | relative_url }}{% endif %}">Current Issue</a>
        <a href="{{ '/archive/' | relative_url }}">Archive</a>
        <a href="{{ '/search/' | relative_url }}">Search</a>
      </nav>
    </header>
    <main class="page-content">
      {{ content }}
    </main>
    <footer class="page-footer">
      <div class="page-footer-follow">
        <ul class="social-icons">
          <li><strong>Newsletter</strong></li>
          <li><a href="{{ '/feed.xml' | relative_url }}">RSS Feed</a></li>
          <li><a href="{{ '/sitemap/' | relative_url }}">Sitemap</a></li>
        </ul>
      </div>
      <div class="page-footer-copyright">&copy; {{ 'now' | date: '%Y' }} Frontier Threads. Powered by Jekyll.</div>
    </footer>
  </div>
  <script>
    window.frontierThreadsConfig = {
      baseUrl: "{{ site.baseurl }}"
    };
  </script>
  <script>
    (function () {
      const key = "mm-theme";

      function apply(mode) {
        document.documentElement.dataset.themeMode = mode;
        localStorage.setItem(key, mode);
        window.dispatchEvent(new CustomEvent("themechange", { detail: { mode } }));
      }

      window.toggleTheme = function () {
        const current = document.documentElement.dataset.themeMode === "dark" ? "dark" : "light";
        apply(current === "light" ? "dark" : "light");
      };

      const saved = localStorage.getItem(key);
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      apply(saved || (prefersDark ? "dark" : "light"));
    })();
  </script>
  <script src="{{ '/assets/search.js' | relative_url }}"></script>
</body>
</html>
"""


ISSUE_LAYOUT = """---
layout: default
---
<article class="issue-page">
  <div class="shell newsletter-shell">
    <div class="masthead">
      <p class="eyebrow">Frontier Threads</p>
      <h1>{{ page.title }}</h1>
      <p>Science, technology, policy, and ideas worth your attention on {{ page.display_date }}.</p>
      <div class="issue-meta-bar">
        <span class="meta-pill">{{ page.display_date }}</span>
        <span class="meta-pill">{{ page.display_time }}</span>
        <span class="meta-pill">{{ page.reading_time }} min read</span>
      </div>
      <div class="taxonomy-row">
        {% if page.categories and page.categories.size > 0 %}
        {% for category in page.categories %}
        <span class="taxonomy-chip taxonomy-chip--category">{{ category }}</span>
        {% endfor %}
        {% endif %}
        {% if page.tags and page.tags.size > 0 %}
        {% for tag in page.tags %}
        <span class="taxonomy-chip">{{ tag }}</span>
        {% endfor %}
        {% endif %}
      </div>
    </div>
    <div class="content issue-content">
      {{ content }}
    </div>
    <div class="footer">
      <p>Browse the archive or use search to revisit previous editions.</p>
      <p><a class="back-to-top" href="#top">Return to top</a></p>
    </div>
  </div>
</article>
"""


HOME_PAGE = """---
layout: default
title: Current Issue
permalink: /
---
{% assign features = site.data.site_features %}
{% assign latest = features.latest_issue %}
<section class="hero-banner" style="background-image: url('{{ '/assets/images/newsletter-hero.jpg' | relative_url }}');">
  <div class="hero-banner__overlay"></div>
  <div class="hero-banner__content">
    <p class="issue-kicker">Frontier Threads</p>
    <h1>The day’s reading, with a long memory.</h1>
    <p class="landing-copy">Welcome to Frontier Threads: a daily briefing across science, technology, ideas, markets, and world events, built to be read in the moment and revisited later.</p>
    <div class="hero-stat-row">
      <span class="meta-pill">{{ features.issue_count }} issues indexed</span>
      {% if latest %}
      <span class="meta-pill">Latest: {{ latest.display_date }}</span>
      {% endif %}
    </div>
  </div>
</section>

<section class="search-panel search-panel--top">
  <div class="card-kicker">Search The Archive</div>
  <h2>Start anywhere in the archive</h2>
  <p>Look up topics, papers, researchers, companies, technologies, regions, and recurring themes across past editions.</p>
  <div class="quick-filter-group">
    <div class="quick-filter-label">Popular tags</div>
    <div class="quick-filter-bar">
      {% for tag in features.top_tags limit: 8 %}
      <button type="button" class="filter-chip" data-search-tag="{{ tag.name }}">{{ tag.name }} <span>{{ tag.count }}</span></button>
      {% endfor %}
    </div>
  </div>
  <input id="newsletter-search-input" class="search-input" type="search" aria-label="Search past newsletters by keyword" placeholder="Search past newsletters by keyword">
  <div id="newsletter-search-status" class="search-status"></div>
  <div id="newsletter-search-results" class="search-results"></div>
</section>

<section class="pin-section">
  <section class="home-carousel-section">
  <div class="home-carousel-section__header">
    <div>
      <p class="section-kicker">Pinned</p>
      <h2>Start with the essentials</h2>
      <p class="home-carousel-section__lede">A consistent set of entry points: the newest issue, archive browsing, search, and the feed.</p>
    </div>
    <div class="home-carousel-section__actions">
      <div class="carousel-controls">
        <button type="button" class="carousel-controls__button" data-carousel-prev="pinned-cards" aria-label="Previous">
          <span aria-hidden="true">&larr;</span>
        </button>
        <button type="button" class="carousel-controls__button" data-carousel-next="pinned-cards" aria-label="Next">
          <span aria-hidden="true">&rarr;</span>
        </button>
      </div>
    </div>
  </div>
  <div class="home-carousel" data-carousel-track="pinned-cards">
    {% for item in features.pinned %}
    <article class="feature-card carousel-card">
      <div class="card-badges">
        <span class="result-badge">Pinned</span>
        {% if item.featured %}<span class="result-badge result-badge--accent">Featured</span>{% endif %}
      </div>
      <div class="search-section">{{ item.primary_category | default: 'Pinned' }}</div>
      <h3><a href="{{ item.url | relative_url }}">{{ item.title }}</a></h3>
      <p class="card-meta">
        {% if item.kind == 'issue' %}
        {{ item.published_label }} · {{ item.reading_time }} min read
        {% else %}
        Site page
        {% endif %}
      </p>
      <p>{{ item.summary }}</p>
      <div class="card-tags">
        {% for tag in item.tags limit: 3 %}
        <span class="taxonomy-chip">{{ tag }}</span>
        {% endfor %}
      </div>
    </article>
    {% endfor %}
  </div>
  </section>
</section>

<section class="archive-preview">
  <section class="home-carousel-section">
  <div class="home-carousel-section__header">
    <div>
      <p class="section-kicker">Featured Issues</p>
      <h2>Reopen the strongest recent editions</h2>
      <p class="home-carousel-section__lede">Curated issue picks rather than a raw latest-first list, so discovery stays intentional.</p>
    </div>
    <div class="home-carousel-section__actions">
      <a class="home-carousel-section__see-all" href="{{ '/archive/' | relative_url }}">See all issues</a>
      <div class="carousel-controls">
        <button type="button" class="carousel-controls__button" data-carousel-prev="featured-issues" aria-label="Previous">
          <span aria-hidden="true">&larr;</span>
        </button>
        <button type="button" class="carousel-controls__button" data-carousel-next="featured-issues" aria-label="Next">
          <span aria-hidden="true">&rarr;</span>
        </button>
      </div>
    </div>
  </div>
  <div class="home-carousel archive-list" data-carousel-track="featured-issues">
    {% for issue in features.featured_issues %}
    <article class="archive-item carousel-card">
      <div class="card-badges"><span class="result-badge result-badge--accent">Featured</span></div>
      <div class="search-section">{{ issue.primary_category | default: 'Issue' }}</div>
      <h3><a href="{{ issue.url | relative_url }}">{{ issue.title }}</a></h3>
      <p class="card-meta">{{ issue.published_label }} · {{ issue.reading_time }} min read</p>
      <p>{{ issue.summary }}</p>
      <div class="card-tags">
        {% for tag in issue.tags limit: 3 %}
        <span class="taxonomy-chip">{{ tag }}</span>
        {% endfor %}
      </div>
    </article>
    {% endfor %}
  </div>
  </section>
</section>

<section class="discovery-section">
  <section class="home-carousel-section">
  <div class="home-carousel-section__header">
    <div>
      <p class="section-kicker">Discovery</p>
      <h2>Browse by recurring themes</h2>
      <p class="home-carousel-section__lede">Discovery now uses the same tag and category metadata that powers search, archive filters, and featured picks.</p>
    </div>
    <div class="home-carousel-section__actions">
      <div class="carousel-controls">
        <button type="button" class="carousel-controls__button" data-carousel-prev="discovery-cards" aria-label="Previous">
          <span aria-hidden="true">&larr;</span>
        </button>
        <button type="button" class="carousel-controls__button" data-carousel-next="discovery-cards" aria-label="Next">
          <span aria-hidden="true">&rarr;</span>
        </button>
      </div>
    </div>
  </div>
  <div class="home-carousel" data-carousel-track="discovery-cards">
    {% for topic in features.discovery_topics %}
    <article class="feature-card carousel-card">
      <div class="search-section">{{ topic.primary_category }}</div>
      <h3><a href="{{ topic.url | relative_url }}">{{ topic.title }}</a></h3>
      <p>{{ topic.summary }}</p>
    </article>
    {% endfor %}
  </div>
  </section>
</section>

<section class="rss-section">
  <div class="rss-card">
    <div>
      <div class="card-kicker">Subscribe</div>
      <h2>Follow the newsletter like a publication stream</h2>
      <p>Use the RSS feed if you want each new issue to appear in a reader alongside journals, blogs, and other sources you already track.</p>
    </div>
    <div class="issue-actions">
      <a class="button" href="{{ '/feed.xml' | relative_url }}">Open RSS feed</a>
      <a class="button button-secondary" href="{{ '/search/' | relative_url }}">Search newsletters</a>
    </div>
  </div>
</section>
"""


ARCHIVE_PAGE = """---
layout: default
title: Archive
permalink: /archive/
---
{% assign issues = site.issues | sort: 'issue_date' | reverse %}
{% assign features = site.data.site_features %}
<section class="landing-hero">
  <p class="issue-kicker">Archive</p>
  <h1>Browse and search every issue.</h1>
  <p class="landing-copy">The archive now uses the same tagging, categories, featured picks, and search metadata across every page.</p>
</section>

<section class="search-panel">
  <div class="card-kicker">Archive Filters</div>
  <div class="quick-filter-group">
    <div class="quick-filter-label">Browse by tag</div>
    <div class="quick-filter-bar">
      {% for tag in features.top_tags limit: 10 %}
      <button type="button" class="filter-chip" data-search-tag="{{ tag.name }}">{{ tag.name }} <span>{{ tag.count }}</span></button>
      {% endfor %}
    </div>
  </div>
  <div class="archive-date-panel">
    <div class="quick-filter-label">Browse by date</div>
    <div class="date-filter-grid">
      <label class="date-filter-field">
        <span>Year</span>
        <select id="newsletter-year-select" class="filter-select">
          <option value="">All years</option>
          {% for year in features.archive_years %}
          <option value="{{ year.value }}">{{ year.label }} ({{ year.count }})</option>
          {% endfor %}
        </select>
      </label>
      <label class="date-filter-field">
        <span>Month</span>
        <select id="newsletter-month-select" class="filter-select">
          <option value="">All months</option>
          {% for month in features.archive_months %}
          <option value="{{ month.value }}">{{ month.label }} ({{ month.count }})</option>
          {% endfor %}
        </select>
      </label>
      <label class="date-filter-field">
        <span>From</span>
        <input id="newsletter-date-from" class="filter-input" type="date" min="{{ features.min_issue_date }}" max="{{ features.max_issue_date }}">
      </label>
      <label class="date-filter-field">
        <span>To</span>
        <input id="newsletter-date-to" class="filter-input" type="date" min="{{ features.min_issue_date }}" max="{{ features.max_issue_date }}">
      </label>
    </div>
    <div class="quick-filter-group quick-filter-group--tight">
      <div class="quick-filter-label">Jump to common ranges</div>
      <div class="quick-filter-bar">
        {% for month in features.archive_months limit: 6 %}
        <button type="button" class="filter-chip" data-search-month="{{ month.value }}">{{ month.label }} <span>{{ month.count }}</span></button>
        {% endfor %}
        {% for year in features.archive_years limit: 3 %}
        <button type="button" class="filter-chip" data-search-year="{{ year.value }}">{{ year.label }} <span>{{ year.count }}</span></button>
        {% endfor %}
        <button type="button" class="filter-chip filter-chip--ghost" id="newsletter-clear-filters">Clear filters</button>
      </div>
    </div>
  </div>
  <div class="filter-controls">
    <select id="newsletter-sort-select" class="filter-select">
      <option value="newest">Newest first</option>
      <option value="oldest">Oldest first</option>
      <option value="title">Title A-Z</option>
      <option value="reading">Longest read</option>
    </select>
    <select id="newsletter-category-select" class="filter-select">
      <option value="">All categories</option>
    </select>
    <input id="newsletter-tag-input" class="filter-input" type="search" aria-label="Filter archive by tag" placeholder="Filter by tag">
  </div>
  <input id="newsletter-search-input" class="search-input" type="search" aria-label="Search all archived issues" placeholder="Search all archived issues">
  <div id="newsletter-search-status" class="search-status"></div>
  <div id="newsletter-search-results" class="search-results"></div>
</section>

<section class="archive-preview">
  <div class="home-carousel-section__header">
    <div>
      <p class="section-kicker">Featured</p>
      <h2>Editorially highlighted issues</h2>
      <p class="home-carousel-section__lede">These same picks appear on the homepage and in the search index.</p>
    </div>
  </div>
  <div class="archive-list archive-list--compact">
    {% for issue in features.featured_issues limit: 3 %}
    <article class="archive-item archive-item--featured">
      <div class="card-badges"><span class="result-badge result-badge--accent">Featured</span></div>
      <div class="search-section">{{ issue.primary_category | default: 'Issue' }}</div>
      <h3><a href="{{ issue.url | relative_url }}">{{ issue.title }}</a></h3>
      <p class="card-meta">{{ issue.published_label }} · {{ issue.reading_time }} min read</p>
      <p>{{ issue.summary }}</p>
      <div class="card-tags">
        {% for tag in issue.tags limit: 4 %}
        <span class="taxonomy-chip">{{ tag }}</span>
        {% endfor %}
      </div>
    </article>
    {% endfor %}
  </div>
</section>

<section class="archive-preview">
  <div class="home-carousel-section__header">
    <div>
      <p class="section-kicker">All Issues</p>
      <h2>Browse the full run</h2>
    </div>
  </div>
  <div class="archive-list archive-grid" id="newsletter-archive-list">
    {% for issue in issues %}
    <article class="archive-item" data-date="{{ issue.issue_date }}" data-summary="{{ issue.summary | escape }}" data-category="{{ issue.primary_category | escape }}" data-tags="{{ issue.tags | join: ',' | escape }}" data-reading-time="{{ issue.reading_time }}" data-title="{{ issue.title | escape }}">
      <div class="search-section">{{ issue.primary_category | default: 'Issue' }}</div>
      <h3><a href="{{ issue.url | relative_url }}">{{ issue.title }}</a></h3>
      <p class="card-meta">{{ issue.published_label }} · {{ issue.reading_time }} min read</p>
      <p>{{ issue.summary }}</p>
      <div class="card-tags">
        {% for tag in issue.tags limit: 4 %}
        <span class="taxonomy-chip">{{ tag }}</span>
        {% endfor %}
      </div>
    </article>
    {% endfor %}
  </div>
</section>
"""


SEARCH_PAGE = """---
layout: default
title: Search
permalink: /search/
---
{% assign features = site.data.site_features %}
<section class="landing-hero">
  <p class="issue-kicker">Search</p>
  <h1>Search the newsletter archive.</h1>
  <p class="landing-copy">Use keywords for topics, people, companies, fields, papers, or places and jump straight into matching issues.</p>
</section>

<section class="search-panel search-panel--page">
  <div class="card-kicker">Keyword Search</div>
  <h2>Find relevant issues quickly</h2>
  <div class="quick-filter-group">
    <div class="quick-filter-label">Popular tags</div>
    <div class="quick-filter-bar">
      {% for tag in features.top_tags limit: 10 %}
      <button type="button" class="filter-chip" data-search-tag="{{ tag.name }}">{{ tag.name }} <span>{{ tag.count }}</span></button>
      {% endfor %}
    </div>
  </div>
  <div class="filter-controls">
    <select id="newsletter-sort-select" class="filter-select">
      <option value="relevance">Best match</option>
      <option value="newest">Newest first</option>
      <option value="oldest">Oldest first</option>
      <option value="title">Title A-Z</option>
      <option value="reading">Longest read</option>
    </select>
    <select id="newsletter-category-select" class="filter-select">
      <option value="">All categories</option>
    </select>
    <input id="newsletter-tag-input" class="filter-input" type="search" aria-label="Filter search by tag" placeholder="Filter by tag">
  </div>
  <input id="newsletter-search-input" class="search-input" type="search" aria-label="Enter your search term" placeholder="Enter your search term...">
  <div id="newsletter-search-status" class="search-status"></div>
  <div id="newsletter-search-results" class="search-results"></div>
</section>

<section class="archive-preview">
  <div class="home-carousel-section__header">
    <div>
      <p class="section-kicker">Featured</p>
      <h2>Good places to begin</h2>
      <p class="home-carousel-section__lede">If you are exploring for the first time, these curated issues are the quickest way in.</p>
    </div>
  </div>
  <div class="archive-list archive-list--compact">
    {% for issue in features.featured_issues limit: 3 %}
    <article class="archive-item archive-item--featured">
      <div class="card-badges"><span class="result-badge result-badge--accent">Featured</span></div>
      <div class="search-section">{{ issue.primary_category }}</div>
      <h3><a href="{{ issue.url | relative_url }}">{{ issue.title }}</a></h3>
      <p class="card-meta">{{ issue.published_label }} · {{ issue.reading_time }} min read</p>
      <p>{{ issue.summary }}</p>
    </article>
    {% endfor %}
  </div>
</section>
"""

FEED_XML = """---
layout: null
permalink: /feed.xml
---
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Frontier Threads</title>
    <link>{{ '/' | absolute_url }}</link>
    <description>Daily newsletter on science, technology, markets, world affairs, and ideas.</description>
    <language>en-us</language>
    {% assign issues = site.issues | sort: 'issue_date' | reverse %}
    {% for issue in issues %}
    <item>
      <title>{{ issue.display_date | xml_escape }}</title>
      <link>{{ issue.url | absolute_url }}</link>
      <guid>{{ issue.url | absolute_url }}</guid>
      <pubDate>{{ issue.issue_date | date_to_rfc822 }}</pubDate>
      <description>{{ issue.summary | xml_escape }}</description>
    </item>
    {% endfor %}
  </channel>
</rss>
"""

SITEMAP_PAGE = """---
layout: default
title: Sitemap
permalink: /sitemap/
---
{% assign features = site.data.site_features %}
<section class="landing-hero">
  <p class="issue-kicker">Sitemap</p>
  <h1>Everything in one place.</h1>
  <p class="landing-copy">Use this page to jump between the homepage, archive tools, subscription endpoints, and past issues.</p>
</section>

<section class="archive-preview">
  <div class="card-kicker">Core Pages</div>
  <div class="archive-list">
    {% for page in features.core_pages %}
    <article class="archive-item">
      <div class="search-section">{{ page.primary_category }}</div>
      <h3><a href="{{ page.url | relative_url }}">{{ page.title }}</a></h3>
      <p>{{ page.summary }}</p>
    </article>
    {% endfor %}
  </div>
</section>

<section class="archive-preview">
  <div class="card-kicker">Featured Issues</div>
  <div class="archive-list">
    {% for issue in features.featured_issues %}
    <article class="archive-item">
      <div class="card-badges"><span class="result-badge result-badge--accent">Featured</span></div>
      <h3><a href="{{ issue.url | relative_url }}">{{ issue.title }}</a></h3>
      <p class="card-meta">{{ issue.published_label }} · {{ issue.reading_time }} min read</p>
      <p>{{ issue.summary }}</p>
    </article>
    {% endfor %}
  </div>
</section>
"""


SITE_CSS = """
html[data-theme-mode="light"] {
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
  --masthead-bg:
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.12), transparent 30%),
    linear-gradient(135deg, rgba(37, 30, 34, 0.985), rgba(50, 44, 49, 0.97));
  --masthead-border: rgba(249, 115, 22, 0.38);
  --masthead-copy: rgba(241, 245, 249, 0.9);
  --section-card-bg: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.94));
  --markets-card-bg: linear-gradient(180deg, rgba(255,247,237,0.95), rgba(255,255,255,0.92));
  --market-panel-bg: linear-gradient(180deg, rgba(255,247,217,0.78), rgba(255,253,246,0.88));
  --econ-panel-bg: linear-gradient(180deg, rgba(255,255,255,0.72), rgba(248,250,252,0.84));
  --market-tile-bg: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(248,250,252,0.94));
  --investment-bg: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,247,237,0.92));
  --accent-soft: rgba(249, 115, 22, 0.12);
  --lede-color: #243041;
  --success: #15803d;
  --danger: #dc2626;
}
html[data-theme-mode="dark"] {
  color-scheme: dark light;
  --bg: linear-gradient(180deg, #111827 0%, #0f172a 55%, #020617 100%);
  --panel: rgba(15, 23, 42, 0.82);
  --panel-strong: rgba(15, 23, 42, 0.9);
  --ink: #f8fafc;
  --muted: #cbd5e1;
  --line: rgba(148, 163, 184, 0.18);
  --accent: #fb923c;
  --accent-2: #38bdf8;
  --shadow: rgba(2, 6, 23, 0.35);
  --masthead-bg:
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.14), transparent 30%),
    linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.94));
  --masthead-border: rgba(148, 163, 184, 0.24);
  --masthead-copy: rgba(226, 232, 240, 0.86);
  --section-card-bg: linear-gradient(180deg, rgba(15,23,42,0.84), rgba(15,23,42,0.74));
  --markets-card-bg: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.86));
  --market-panel-bg: linear-gradient(180deg, rgba(30,41,59,0.86), rgba(15,23,42,0.84));
  --econ-panel-bg: linear-gradient(180deg, rgba(15,23,42,0.82), rgba(15,23,42,0.74));
  --market-tile-bg: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.9));
  --investment-bg: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.86));
  --accent-soft: rgba(249, 115, 22, 0.14);
  --lede-color: #e2e8f0;
  --success: #4ade80;
  --danger: #fb7185;
}
html:not([data-theme-mode]) {
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
  --masthead-bg:
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.12), transparent 30%),
    linear-gradient(135deg, rgba(37, 30, 34, 0.985), rgba(50, 44, 49, 0.97));
  --masthead-border: rgba(249, 115, 22, 0.38);
  --masthead-copy: rgba(241, 245, 249, 0.9);
  --section-card-bg: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.94));
  --markets-card-bg: linear-gradient(180deg, rgba(255,247,237,0.95), rgba(255,255,255,0.92));
  --market-panel-bg: linear-gradient(180deg, rgba(255,247,217,0.78), rgba(255,253,246,0.88));
  --econ-panel-bg: linear-gradient(180deg, rgba(255,255,255,0.72), rgba(248,250,252,0.84));
  --market-tile-bg: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(248,250,252,0.94));
  --investment-bg: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,247,237,0.92));
  --accent-soft: rgba(249, 115, 22, 0.12);
  --lede-color: #243041;
  --success: #15803d;
  --danger: #dc2626;
}
@media (prefers-color-scheme: dark) {
  html:not([data-theme-mode]) {
    color-scheme: dark light;
    --bg: linear-gradient(180deg, #111827 0%, #0f172a 55%, #020617 100%);
    --panel: rgba(15, 23, 42, 0.82);
    --panel-strong: rgba(15, 23, 42, 0.9);
    --ink: #f8fafc;
    --muted: #cbd5e1;
    --line: rgba(148, 163, 184, 0.18);
    --accent: #fb923c;
    --accent-2: #38bdf8;
    --shadow: rgba(2, 6, 23, 0.35);
    --masthead-bg:
      radial-gradient(circle at top right, rgba(249, 115, 22, 0.14), transparent 30%),
      linear-gradient(135deg, rgba(15, 23, 42, 0.98), rgba(30, 41, 59, 0.94));
    --masthead-border: rgba(148, 163, 184, 0.24);
    --masthead-copy: rgba(226, 232, 240, 0.86);
    --section-card-bg: linear-gradient(180deg, rgba(15,23,42,0.84), rgba(15,23,42,0.74));
    --markets-card-bg: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.86));
    --market-panel-bg: linear-gradient(180deg, rgba(30,41,59,0.86), rgba(15,23,42,0.84));
    --econ-panel-bg: linear-gradient(180deg, rgba(15,23,42,0.82), rgba(15,23,42,0.74));
    --market-tile-bg: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.9));
    --investment-bg: linear-gradient(180deg, rgba(30,41,59,0.92), rgba(15,23,42,0.86));
    --accent-soft: rgba(249, 115, 22, 0.14);
    --lede-color: #e2e8f0;
    --success: #4ade80;
    --danger: #fb7185;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  overflow-x: clip;
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
  align-items: center;
}
.site-nav a {
  color: var(--muted);
  font-weight: 600;
}
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
.theme-toggle:hover {
  color: var(--ink);
}
.theme-toggle__icon {
  font-size: 0.95rem;
}
.page-footer {
  margin-top: 24px;
  padding: 22px 20px 28px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 24px;
  box-shadow: 0 10px 28px var(--shadow);
}
.page-footer-follow .social-icons {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  align-items: center;
  list-style: none;
  margin: 0;
  padding: 0;
}
.page-footer-follow .social-icons a {
  color: var(--muted);
  font-weight: 600;
}
.page-footer-copyright {
  margin-top: 12px;
  color: var(--muted);
  font-size: 0.95rem;
}
.page-content { display: grid; gap: 16px; }
.page-content,
.pin-section,
.archive-preview,
.discovery-section,
.home-carousel-section,
.home-carousel {
  max-width: 100%;
  min-width: 0;
}
.hero-banner,
.footer-banner {
  position: relative;
  min-height: 340px;
  overflow: hidden;
  border-radius: 28px;
  border: 1px solid var(--line);
  background-color: #0f172a;
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
  box-shadow: 0 16px 36px var(--shadow);
}
.hero-banner__overlay,
.footer-banner__overlay {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg, rgba(15, 23, 42, 0.82), rgba(15, 23, 42, 0.46)),
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.24), transparent 34%);
}
.hero-banner__content,
.footer-banner__content {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 14px;
  align-content: end;
  min-height: 340px;
  padding: 28px;
  color: #f8fafc;
}
.hero-banner .card-kicker,
.footer-banner .card-kicker {
  margin-bottom: 0;
  color: #fdba74;
}
.hero-banner h1,
.footer-banner h2 {
  margin: 0;
  max-width: 12ch;
  line-height: 0.98;
  letter-spacing: -0.04em;
}
.hero-banner h1 {
  font-size: clamp(2.5rem, 5vw, 4.5rem);
}
.footer-banner h2 {
  font-size: clamp(1.9rem, 3.5vw, 3.2rem);
}
.hero-banner p,
.footer-banner p {
  margin: 0;
  max-width: 60ch;
  color: rgba(241, 245, 249, 0.9);
}
.search-panel--top,
.pin-section,
.discovery-section,
.featured-section,
.rss-section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 24px;
  box-shadow: 0 10px 28px var(--shadow);
  padding: 24px;
}
.search-panel__header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hero-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}
.filter-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}
.filter-select,
.filter-input {
  min-height: 44px;
  padding: 0 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--panel-strong);
  color: var(--ink);
  font: inherit;
}
.filter-select {
  min-width: 180px;
}
.filter-input {
  flex: 1 1 220px;
}
.quick-filter-group {
  margin-top: 16px;
}
.quick-filter-group--tight {
  margin-top: 14px;
}
.quick-filter-label {
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 0.92rem;
  font-weight: 700;
}
.archive-date-panel {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}
.date-filter-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.date-filter-field {
  display: grid;
  gap: 6px;
}
.date-filter-field span {
  color: var(--muted);
  font-size: 0.84rem;
  font-weight: 700;
}
.quick-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--panel-strong);
  color: var(--ink);
  font: inherit;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
}
.filter-chip span {
  color: var(--muted);
  font-size: 0.8rem;
}
.filter-chip:hover {
  border-color: rgba(14, 165, 233, 0.36);
}
.filter-chip--ghost {
  background: transparent;
}
.home-carousel-section {
  margin: 1rem 0;
}
.home-carousel-section__header {
  display: flex;
  flex-wrap: wrap;
  gap: 0.85rem;
  justify-content: space-between;
  align-items: end;
  margin-bottom: 0.7rem;
}
.home-carousel-section__header h2 {
  margin: 0;
  line-height: 1.05;
  letter-spacing: -0.03em;
}
.section-kicker {
  margin: 0 0 10px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.home-carousel-section__lede {
  margin: 0.65rem 0 0 0;
  max-width: 48rem;
  color: var(--muted);
  font-size: 1.03rem;
  line-height: 1.5;
}
.home-carousel-section__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
.home-carousel-section__see-all {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.7rem 1rem;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(128, 128, 128, 0.05);
  color: inherit !important;
  text-decoration: none !important;
  font-weight: 700;
}
.carousel-controls {
  display: inline-flex;
  gap: 0.45rem;
}
.carousel-controls__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.6rem;
  height: 2.6rem;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: rgba(15, 23, 42, 0.92);
  color: #f8fafc;
  cursor: pointer;
}
.search-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(249, 115, 22, 0.18), rgba(14, 165, 233, 0.18));
  color: var(--accent);
  font-size: 1.1rem;
}
.home-carousel {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(18rem, 26rem);
  gap: 0.85rem;
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding-bottom: 0.25rem;
  scrollbar-width: thin;
}
.home-carousel::-webkit-scrollbar {
  height: 0.55rem;
}
.home-carousel::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.38);
  border-radius: 999px;
}
.carousel-card {
  scroll-snap-align: start;
  min-height: 100%;
}
.feature-card,
.pin-card,
.rss-card {
  background: var(--panel-strong);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 18px 18px 16px;
  box-shadow: 0 10px 22px var(--shadow);
  height: 100%;
}
.card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.result-badge {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.12);
  border: 1px solid rgba(14, 165, 233, 0.22);
  color: var(--accent-2);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.result-badge--accent {
  background: rgba(249, 115, 22, 0.12);
  border-color: rgba(249, 115, 22, 0.26);
  color: var(--accent);
}
.pin-card::before,
.feature-card::before,
.rss-card::before {
  content: "";
  display: block;
  width: 56px;
  height: 3px;
  margin-bottom: 14px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.72));
}
.feature-card h3,
.pin-card h3,
.rss-card h3 {
  margin: 0;
  font-size: 1.15rem;
  line-height: 1.15;
  letter-spacing: -0.02em;
}
.feature-card p,
.pin-card p,
.rss-card p,
.section-copy {
  margin: 10px 0 0;
  color: var(--muted);
}
.card-meta {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 0.92rem;
  font-weight: 700;
}
.card-tags,
.taxonomy-row,
.issue-meta-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.taxonomy-chip,
.meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--muted);
  font-size: 0.82rem;
  font-weight: 700;
}
.taxonomy-chip--category,
.meta-pill {
  color: var(--ink);
  background: linear-gradient(135deg, rgba(249, 115, 22, 0.12), rgba(14, 165, 233, 0.12));
}
.section-copy {
  max-width: 70ch;
}
.rss-card {
  display: grid;
  grid-template-columns: 1fr;
  gap: 18px;
  align-items: start;
  padding: 22px 22px 20px;
}
.rss-card__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-start;
}
.rss-section .issue-actions {
  margin-top: 0;
}
.footer-banner__text {
  font-size: 1.05rem;
  line-height: 1.65;
}
.footer-banner__author {
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #fdba74;
}
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
.archive-grid {
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}
.archive-list--compact {
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
}
.archive-item,
.search-result {
  padding: 18px;
  background: var(--panel-strong);
  border: 1px solid var(--line);
  border-radius: 18px;
}
.archive-item--featured {
  position: relative;
  overflow: hidden;
}
.archive-item--featured::before {
  content: "";
  position: absolute;
  inset: 0 auto auto 0;
  width: 100%;
  height: 3px;
  background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.72));
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
.archive-item .card-tags,
.search-result .card-tags {
  margin-top: 12px;
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
html[data-theme-mode="dark"] .search-input {
  background: rgba(15, 23, 42, 0.7);
}
@media (prefers-color-scheme: dark) {
  .search-input { background: rgba(15, 23, 42, 0.7); }
}
.search-status {
  margin-top: 10px;
  color: var(--muted);
  font-size: 0.95rem;
}
.search-empty {
  padding: 18px;
  border: 1px dashed var(--line);
  border-radius: 18px;
  color: var(--muted);
  background: rgba(128, 128, 128, 0.04);
}
.search-result-snippet {
  margin-top: 8px;
  color: var(--muted);
  font-size: 0.95rem;
}
.search-hit {
  color: var(--ink);
  font-weight: 700;
  background: linear-gradient(180deg, transparent 45%, rgba(249, 115, 22, 0.22) 45%);
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
.issue-page {
  padding: 6px 0 2px;
}
.shell {
  max-width: 900px;
  margin: 0 auto;
}
.newsletter-shell {
  width: 100%;
}
.masthead {
  background: var(--masthead-bg);
  color: #f8fafc;
  border: 1px solid var(--masthead-border);
  border-radius: 28px;
  padding: 32px 32px 24px;
  box-shadow: 0 18px 40px rgba(24, 33, 47, 0.16);
}
.eyebrow {
  margin: 0 0 10px;
  font: 700 12px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
}
.masthead h1 {
  margin: 0;
  font-size: 42px;
  line-height: 1.02;
  letter-spacing: -0.03em;
  color: #f8fafc;
}
.masthead p {
  margin: 12px 0 0;
  color: var(--masthead-copy);
  font-size: 17px;
  max-width: 680px;
}
.masthead .taxonomy-chip,
.masthead .meta-pill {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.16);
  color: #f8fafc;
}
.content {
  margin-top: 16px;
}
.issue-page .issue-content {
  background: transparent;
  border: 0;
  box-shadow: none;
  padding: 0;
}
.title {
  display: none;
}
.section-card {
  background: var(--section-card-bg);
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 24px 26px;
  margin: 14px 0;
  box-shadow: 0 10px 24px var(--shadow);
  backdrop-filter: blur(8px);
  position: relative;
  overflow: hidden;
}
.section-card::before {
  content: "";
  position: absolute;
  inset: 0 auto auto 0;
  width: 100%;
  height: 3px;
  background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.7), transparent 85%);
  opacity: 0.9;
}
.section-title {
  margin: 0 0 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
  color: var(--accent);
  font-size: 13px;
  line-height: 1.2;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.section-card--markets-economy {
  background: var(--markets-card-bg);
  border-color: rgba(249, 115, 22, 0.30);
}
.story-title {
  margin: 24px 0 10px;
  font-size: 26px;
  line-height: 1.18;
  letter-spacing: -0.02em;
  position: relative;
}
.story-title:first-of-type {
  margin-top: 8px;
}
.story-title::after {
  content: "";
  display: block;
  width: 52px;
  height: 3px;
  margin-top: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.7));
  opacity: 0.85;
}
.issue-page p {
  margin: 12px 0;
  font-size: 16px;
}
.meta {
  color: var(--muted);
  font-size: 14px;
  font-weight: 600;
}
.meta-link {
  margin-top: 14px;
}
.link-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.92), rgba(99, 102, 241, 0.9));
  color: #eff6ff !important;
  text-decoration: none;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.01em;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
}
.link-chip::after {
  content: "↗";
  font-size: 12px;
  opacity: 0.9;
}
.lede {
  margin: 0;
  font-size: 17px;
  color: var(--lede-color);
}
.issue-page ul {
  margin: 10px 0 16px 22px;
  padding: 0;
}
.issue-page li {
  margin: 8px 0;
}
.market-wrap {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 14px;
  margin-top: 10px;
}
.market-panel,
.econ-panel {
  background: var(--market-panel-bg);
  border: 1px solid rgba(249, 115, 22, 0.30);
  border-radius: 20px;
  padding: 12px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
}
.econ-panel {
  background: var(--econ-panel-bg);
  border-color: var(--line);
}
.panel-kicker {
  display: inline-block;
  margin-bottom: 12px;
  padding: 6px 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.92), rgba(99, 102, 241, 0.9));
  color: #eff6ff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.market-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.market-tile {
  background: var(--market-tile-bg);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 10px 11px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
  position: relative;
  overflow: hidden;
}
.market-tile::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 4px;
  background: linear-gradient(90deg, var(--accent), rgba(14, 165, 233, 0.72));
  opacity: 0.9;
}
.stat-label {
  margin: 4px 0 6px;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.stat-value {
  font-size: 21px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--ink);
}
.stat-detail {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 700;
  color: var(--ink);
  opacity: 0.92;
}
.stat-detail.up { color: var(--success); }
.stat-detail.down { color: var(--danger); }
.econ-grid {
  display: grid;
  gap: 10px;
}
.econ-row {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.45;
  position: relative;
  overflow: hidden;
}
.econ-row::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: linear-gradient(180deg, var(--accent), rgba(14, 165, 233, 0.7));
}
.investment-card {
  margin-top: 16px;
  padding: 16px 18px 8px;
  border-radius: 20px;
  border: 1px solid rgba(249, 115, 22, 0.30);
  background: var(--investment-bg);
  box-shadow: 0 10px 22px var(--shadow);
}
.investment-card .story-title {
  margin-top: 0;
}
.investment-copy {
  margin: 10px 0;
}
.brief-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}
.brief-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 14px 16px;
  font-size: 15px;
  line-height: 1.45;
  position: relative;
  overflow: hidden;
}
.brief-card::after {
  content: "";
  position: absolute;
  right: -24px;
  bottom: -24px;
  width: 76px;
  height: 76px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(249, 115, 22, 0.12) 0%, rgba(249,115,22,0) 72%);
  background: radial-gradient(circle, var(--accent-soft) 0%, rgba(249,115,22,0) 72%);
}
blockquote {
  margin: 18px 0;
  padding: 14px 18px;
  background: rgba(249, 115, 22, 0.12);
  background: var(--accent-soft);
  border-left: 4px solid var(--accent);
  border-radius: 0 14px 14px 0;
  font-size: 18px;
}
.feature-image {
  margin: 16px 0 18px;
}
.feature-image img {
  display: block;
  width: 100%;
  max-height: 360px;
  object-fit: cover;
  border-radius: 20px;
  border: 1px solid var(--line);
  box-shadow: 0 14px 30px var(--shadow);
}
.feature-image figcaption {
  margin-top: 8px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}
.footer {
  color: var(--muted);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  padding: 10px 6px 0;
  text-align: center;
}
.back-to-top {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--ink);
  font-weight: 700;
  text-decoration: none;
  box-shadow: 0 8px 18px var(--shadow);
}
.back-to-top:hover {
  text-decoration: none;
  filter: brightness(1.02);
}
@media (max-width: 760px) {
  .site-header { flex-direction: column; align-items: flex-start; }
  .site-shell { padding-inline: 10px; }
  .filter-controls {
    flex-direction: column;
  }
  .date-filter-grid {
    grid-template-columns: 1fr;
  }
  .filter-select,
  .filter-input {
    width: 100%;
  }
  .hero-banner,
  .footer-banner,
  .hero-banner__content,
  .footer-banner__content {
    min-height: 280px;
  }
  .hero-banner__content,
  .footer-banner__content {
    padding: 22px 18px;
  }
  .search-panel--top,
  .pin-section,
  .discovery-section,
  .featured-section,
  .rss-section {
    padding: 20px;
  }
  .home-carousel,
  .rss-card {
    grid-template-columns: 1fr;
  }
  .home-carousel {
    grid-auto-columns: 88%;
  }
  .rss-card__actions {
    justify-content: flex-start;
  }
  .page-footer {
    padding: 18px 16px 22px;
  }
  .landing-hero,
  .search-panel,
  .archive-preview,
  .current-issue-card,
  .issue-hero { padding: 20px; }
  .masthead {
    padding: 26px 20px 22px;
    border-radius: 18px;
  }
  .masthead h1 {
    font-size: 31px;
  }
  .masthead p {
    font-size: 16px;
  }
  .section-card {
    padding: 20px 18px;
    border-radius: 18px;
  }
  .story-title {
    font-size: 22px;
  }
  .issue-page p {
    font-size: 16px;
  }
  .market-wrap,
  .market-grid,
  .brief-grid {
    grid-template-columns: 1fr;
  }
  .market-panel,
  .econ-panel,
  .market-tile,
  .brief-card,
  .econ-row {
    border-radius: 16px;
  }
}
"""


SEARCH_JS = """(function () {
  const input = document.getElementById('newsletter-search-input');
  const results = document.getElementById('newsletter-search-results');
  const status = document.getElementById('newsletter-search-status');
  const categorySelect = document.getElementById('newsletter-category-select');
  const sortSelect = document.getElementById('newsletter-sort-select');
  const tagInput = document.getElementById('newsletter-tag-input');
  const yearSelect = document.getElementById('newsletter-year-select');
  const monthSelect = document.getElementById('newsletter-month-select');
  const dateFromInput = document.getElementById('newsletter-date-from');
  const dateToInput = document.getElementById('newsletter-date-to');
  const clearFiltersButton = document.getElementById('newsletter-clear-filters');
  const archiveList = document.getElementById('newsletter-archive-list');
  if (!input || !results || !status) return;

  const baseUrl = (window.frontierThreadsConfig && window.frontierThreadsConfig.baseUrl) || '';
  const searchUrl = `${baseUrl}/search.json`;
  let items = [];
  let bootstrapped = false;

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function readParams() {
    const url = new URL(window.location.href);
    return {
      q: url.searchParams.get('q') || '',
      category: url.searchParams.get('category') || '',
      tag: url.searchParams.get('tag') || '',
      year: url.searchParams.get('year') || '',
      month: url.searchParams.get('month') || '',
      from: url.searchParams.get('from') || '',
      to: url.searchParams.get('to') || '',
      sort: url.searchParams.get('sort') || '',
    };
  }

  function writeParams() {
    const url = new URL(window.location.href);
    const params = {
      q: input.value.trim(),
      category: categorySelect ? categorySelect.value : '',
      tag: tagInput ? tagInput.value.trim() : '',
      year: yearSelect ? yearSelect.value : '',
      month: monthSelect ? monthSelect.value : '',
      from: dateFromInput ? dateFromInput.value : '',
      to: dateToInput ? dateToInput.value : '',
      sort: sortSelect ? sortSelect.value : '',
    };
    Object.entries(params).forEach(([key, value]) => {
      if (value) {
        url.searchParams.set(key, value);
      } else {
        url.searchParams.delete(key);
      }
    });
    window.history.replaceState({}, '', url.toString());
  }

  function metaLine(item) {
    if (item.kind === 'page') return 'Site page';
    return `${item.published_label || item.display_date} · ${item.reading_time} min read`;
  }

  function resetDateFilters() {
    if (yearSelect) yearSelect.value = '';
    if (monthSelect) monthSelect.value = '';
    if (dateFromInput) dateFromInput.value = '';
    if (dateToInput) dateToInput.value = '';
  }

  function badgeMarkup(item) {
    const badges = [];
    if (item.pinned) badges.push('<span class="result-badge">Pinned</span>');
    if (item.featured) badges.push('<span class="result-badge result-badge--accent">Featured</span>');
    return badges.length ? `<div class="card-badges">${badges.join('')}</div>` : '';
  }

  function chips(item) {
    const tags = Array.isArray(item.tags) ? item.tags.slice(0, 4) : [];
    const category = item.primary_category ? `<span class="taxonomy-chip taxonomy-chip--category">${escapeHtml(item.primary_category)}</span>` : '';
    return `<div class="card-tags">${category}${tags.map((tag) => `<span class="taxonomy-chip">${escapeHtml(tag)}</span>`).join('')}</div>`;
  }

  function snippetFor(item, terms) {
    const haystack = item.search_text || '';
    const lower = haystack.toLowerCase();
    let index = -1;
    for (const term of terms) {
      index = lower.indexOf(term);
      if (index !== -1) break;
    }
    if (index === -1) return '';
    const start = Math.max(0, index - 70);
    const end = Math.min(haystack.length, index + 170);
    let snippet = haystack.slice(start, end).trim();
    if (start > 0) snippet = `...${snippet}`;
    if (end < haystack.length) snippet = `${snippet}...`;
    let rendered = escapeHtml(snippet);
    for (const term of terms) {
      const pattern = new RegExp(term.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'ig');
      rendered = rendered.replace(pattern, (match) => `<span class="search-hit">${match}</span>`);
    }
    return rendered;
  }

  function renderResults(matches, hasFilters, terms) {
    if (!hasFilters) {
      results.innerHTML = '';
      status.textContent = `Search ${items.length} indexed pages and issues.`;
      return;
    }
    status.textContent = `${matches.length} result${matches.length === 1 ? '' : 's'}.`;
    if (!matches.length) {
      results.innerHTML = '<div class="search-empty">No matches yet. Try a broader keyword, a different tag, or clear one of the filters.</div>';
      return;
    }
    results.innerHTML = matches.slice(0, 50).map((item) => {
      const snippet = snippetFor(item, terms);
      return `
        <article class="search-result">
          ${badgeMarkup(item)}
          <div class="search-section">${escapeHtml(item.primary_category || item.date)}</div>
          <h3><a href="${baseUrl}${item.url}">${escapeHtml(item.title)}</a></h3>
          <p class="card-meta">${escapeHtml(metaLine(item))}</p>
          <p>${escapeHtml(item.summary)}</p>
          ${chips(item)}
          ${snippet ? `<div class="search-result-snippet">${snippet}</div>` : ''}
        </article>
      `;
    }).join('');
  }

  function renderArchive(matches) {
    if (!archiveList) return;
    const issueMatches = matches.filter((item) => item.kind === 'issue');
    if (!issueMatches.length) {
      archiveList.innerHTML = '<div class="search-empty">No issues match these filters yet.</div>';
      return;
    }
    archiveList.innerHTML = issueMatches.map((item) => `
      <article class="archive-item ${item.featured ? 'archive-item--featured' : ''}" data-date="${escapeHtml(item.date)}" data-category="${escapeHtml(item.primary_category || '')}" data-tags="${escapeHtml((item.tags || []).join(','))}" data-reading-time="${escapeHtml(item.reading_time)}" data-title="${escapeHtml(item.title)}">
        ${badgeMarkup(item)}
        <div class="search-section">${escapeHtml(item.primary_category || 'Issue')}</div>
        <h3><a href="${baseUrl}${item.url}">${escapeHtml(item.title)}</a></h3>
        <p class="card-meta">${escapeHtml(metaLine(item))}</p>
        <p>${escapeHtml(item.summary)}</p>
        ${chips(item)}
      </article>
    `).join('');
  }

  function sortMatches(matches) {
    const sortValue = sortSelect ? sortSelect.value : (archiveList ? 'newest' : 'relevance');
    const sorted = matches.slice();
    if (sortValue === 'title') {
      sorted.sort((a, b) => a.title.localeCompare(b.title));
    } else if (sortValue === 'oldest') {
      sorted.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
    } else if (sortValue === 'reading') {
      sorted.sort((a, b) => (b.reading_time || 0) - (a.reading_time || 0) || (b.date || '').localeCompare(a.date || ''));
    } else if (sortValue === 'newest') {
      sorted.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
    } else {
      sorted.sort((a, b) => (b.score || 0) - (a.score || 0) || (b.date || '').localeCompare(a.date || ''));
    }
    return sorted;
  }

  function filterItems() {
    const query = input.value.trim().toLowerCase().replace(/\\s+/g, ' ');
    const terms = query ? query.split(' ').filter(Boolean) : [];
    const selectedCategory = categorySelect ? categorySelect.value.toLowerCase() : '';
    const tagTerm = tagInput ? tagInput.value.trim().toLowerCase() : '';
    const yearTerm = yearSelect ? yearSelect.value : '';
    const monthTerm = monthSelect ? monthSelect.value : '';
    const fromTerm = dateFromInput ? dateFromInput.value : '';
    const toTerm = dateToInput ? dateToInput.value : '';
    const pool = archiveList ? items.filter((item) => item.kind === 'issue') : items;
    const hasFilters = Boolean(query || selectedCategory || tagTerm || yearTerm || monthTerm || fromTerm || toTerm);

    const matches = pool.map((item) => {
      const title = (item.title || '').toLowerCase();
      const summary = (item.summary || '').toLowerCase();
      const text = (item.search_text || '').toLowerCase();
      const itemDate = item.date || '';
      const categories = (item.categories || []).map((value) => value.toLowerCase());
      const tags = (item.tags || []).map((value) => value.toLowerCase());
      if (selectedCategory && !categories.includes(selectedCategory) && (item.primary_category || '').toLowerCase() !== selectedCategory) {
        return null;
      }
      if (tagTerm && !tags.some((tag) => tag.includes(tagTerm))) {
        return null;
      }
      if (yearTerm && !itemDate.startsWith(yearTerm)) {
        return null;
      }
      if (monthTerm && !itemDate.startsWith(monthTerm)) {
        return null;
      }
      if (fromTerm && itemDate && itemDate < fromTerm) {
        return null;
      }
      if (toTerm && itemDate && itemDate > toTerm) {
        return null;
      }

      let score = 0;
      if (terms.length) {
        let matched = 0;
        for (const term of terms) {
          let termScore = 0;
          if (title.includes(term)) termScore += 12;
          if (summary.includes(term)) termScore += 6;
          if (tags.some((tag) => tag.includes(term))) termScore += 7;
          if (categories.some((category) => category.includes(term))) termScore += 4;
          if (text.includes(term)) termScore += 2;
          if (termScore > 0) matched += 1;
          score += termScore;
        }
        if (!score) return null;
        if (matched === terms.length) score += 20;
      } else {
        score = 1;
      }

      if (item.featured) score += 4;
      if (item.pinned) score += 2;
      return { ...item, score };
    }).filter(Boolean);

    const sorted = sortMatches(matches);
    renderResults(sorted, hasFilters, terms);
    renderArchive(sorted);
  }

  function populateControls() {
    const pool = archiveList ? items.filter((item) => item.kind === 'issue') : items;
    const categories = Array.from(new Set(pool.flatMap((item) => item.categories || []))).sort();
    if (categorySelect) {
      const selected = categorySelect.value;
      categorySelect.innerHTML = '<option value=\"\">All categories</option>' + categories.map((category) => `<option value=\"${escapeHtml(category)}\">${escapeHtml(category)}</option>`).join('');
      categorySelect.value = categories.includes(selected) ? selected : selected || '';
    }
  }

  function applyInitialState() {
    const params = readParams();
    if (params.q) input.value = params.q;
    if (tagInput && params.tag) tagInput.value = params.tag;
    if (yearSelect && params.year) yearSelect.value = params.year;
    if (monthSelect && params.month) monthSelect.value = params.month;
    if (dateFromInput && params.from) dateFromInput.value = params.from;
    if (dateToInput && params.to) dateToInput.value = params.to;
    if (sortSelect && params.sort) sortSelect.value = params.sort;
    if (categorySelect && params.category) categorySelect.value = params.category;
    bootstrapped = true;
    filterItems();
  }

  function applyShortcut(dataset) {
    if (dataset.searchQuery) input.value = dataset.searchQuery;
    if (dataset.searchTag && tagInput) tagInput.value = dataset.searchTag;
    if (dataset.searchCategory && categorySelect) categorySelect.value = dataset.searchCategory;
    if (dataset.searchYear && yearSelect) {
      resetDateFilters();
      yearSelect.value = dataset.searchYear;
    }
    if (dataset.searchMonth && monthSelect) {
      resetDateFilters();
      monthSelect.value = dataset.searchMonth;
      if (yearSelect) yearSelect.value = dataset.searchMonth.slice(0, 4);
    }
    if (dataset.searchSort && sortSelect) sortSelect.value = dataset.searchSort;
    if (bootstrapped) writeParams();
    filterItems();
  }

  fetch(searchUrl)
    .then((response) => response.json())
    .then((data) => {
      items = Array.isArray(data) ? data : [];
      populateControls();
      applyInitialState();
    })
    .catch(() => {
      status.textContent = 'Search index failed to load.';
      if (archiveList) archiveList.innerHTML = '<div class="search-empty">Search index failed to load.</div>';
    });

  [input, categorySelect, sortSelect, tagInput, yearSelect, monthSelect, dateFromInput, dateToInput].forEach((element) => {
    if (!element) return;
    element.addEventListener('input', function () {
      if (bootstrapped) writeParams();
      filterItems();
    });
    element.addEventListener('change', function () {
      if (bootstrapped) writeParams();
      filterItems();
    });
  });

  if (clearFiltersButton) {
    clearFiltersButton.addEventListener('click', function () {
      input.value = '';
      if (categorySelect) categorySelect.value = '';
      if (tagInput) tagInput.value = '';
      resetDateFilters();
      if (sortSelect) sortSelect.value = archiveList ? 'newest' : 'relevance';
      if (bootstrapped) writeParams();
      filterItems();
    });
  }

  function scrollCarousel(id, direction) {
    const track = document.querySelector(`[data-carousel-track="${id}"]`);
    if (!track) return;
    const step = Math.max(track.clientWidth * 0.82, 280);
    track.scrollBy({ left: direction * step, behavior: 'smooth' });
  }

  document.addEventListener('click', function (event) {
    const prev = event.target.closest('[data-carousel-prev]');
    const next = event.target.closest('[data-carousel-next]');
    const shortcut = event.target.closest('[data-search-query], [data-search-tag], [data-search-category], [data-search-sort]');

    if (prev) scrollCarousel(prev.getAttribute('data-carousel-prev'), -1);
    if (next) scrollCarousel(next.getAttribute('data-carousel-next'), 1);
    if (shortcut) applyShortcut(shortcut.dataset);
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


THEME_KEYWORDS: list[tuple[str, str, tuple[str, ...]]] = [
    ("Quantum Foundations", "Physics", ("quantum", "contextuality", "loop quantum", "quantum gravity", "relativity", "spacetime")),
    ("AI Research", "AI & Computing", ("ai", "language model", "llm", "agent", "machine learning", "deep learning", "openai")),
    ("Research Tools", "AI & Computing", ("tool", "dataset", "api", "framework", "open-source", "mcp", "workflow", "infrastructure")),
    ("Markets", "Markets & Economy", ("market", "stocks", "treasury", "inflation", "fed", "economy", "gdp", "cpi", "bitcoin", "oil")),
    ("World Affairs", "World Affairs", ("geopolitic", "conflict", "diplom", "trade", "united nations", "humanitarian", "security")),
    ("Biomedicine", "Life Sciences", ("biology", "medicine", "health", "neuroscience", "brain", "aging", "clinical", "genome")),
    ("Engineering", "Technology & Engineering", ("engineering", "robotics", "materials", "semiconductor", "grid", "infrastructure", "manufacturing")),
    ("Mathematics", "Mathematics & Ideas", ("mathematics", "math", "theorem", "proof", "infinity", "geometry")),
    ("Philosophy", "Mathematics & Ideas", ("philosophy", "epistemology", "truth", "consciousness", "knowledge")),
]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(f'"{yaml_escape(value)}"' for value in values) + "]"


def load_site_curations() -> dict[str, object]:
    defaults: dict[str, object] = {
        "featured_issue_dates": [],
    }
    if not CURATIONS_PATH.exists():
        return defaults
    payload = json.loads(CURATIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return defaults
    return {
        **defaults,
        **payload,
    }


def build_filter_url(*, q: str = "", tag: str = "", category: str = "", sort: str = "") -> str:
    params: list[str] = []
    if q:
        params.append(f"q={quote(q)}")
    if tag:
        params.append(f"tag={quote(tag)}")
    if category:
        params.append(f"category={quote(category)}")
    if sort:
        params.append(f"sort={quote(sort)}")
    return "/search/" + (f"?{'&'.join(params)}" if params else "")


def clean_summary(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("## "):
            continue
        if stripped.startswith("### ") and "The day's" in stripped:
            continue
        return stripped
    return "Daily newsletter covering science, technology, world affairs, and ideas."


def estimate_reading_time(text: str) -> int:
    words = len(re.findall(r"\w+", text))
    return max(1, (words + 219) // 220)


def detect_themes(text: str) -> list[tuple[str, str, int]]:
    normalized = text.lower()
    scored: list[tuple[str, str, int]] = []
    for label, category, keywords in THEME_KEYWORDS:
        score = sum(normalized.count(keyword) for keyword in keywords)
        if score > 0:
            scored.append((label, category, score))
    return sorted(scored, key=lambda item: (-item[2], item[0]))


def issue_title_from_themes(themes: list[tuple[str, str, int]], summary: str) -> str:
    labels = [label for label, _, _ in themes[:3]]
    if labels:
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} and {labels[1]}"
        return f"{labels[0]}, {labels[1]}, and {labels[2]}"
    sentence = summary.split(".")[0].strip()
    if len(sentence) > 70:
        sentence = sentence[:67].rstrip() + "..."
    return sentence or "Daily Briefing"


def format_display_time(timestamp: dt.datetime) -> str:
    return timestamp.strftime("%b %d, %Y · %I:%M %p").replace(" 0", " ")


def split_display_time(timestamp: dt.datetime) -> tuple[str, str]:
    return (
        timestamp.strftime("%B %d, %Y"),
        timestamp.strftime("%I:%M %p").lstrip("0"),
    )


def issue_published_label(issue_date: dt.date, display_time: str) -> str:
    return f"{issue_date.strftime('%b %d, %Y')} · {display_time}"


def headings_from_markdown(markdown_text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^#{2,3}\s+(.+)$", markdown_text, flags=re.MULTILINE)]


def build_search_text(markdown_text: str, headings: list[str], tags: list[str], categories: list[str]) -> str:
    payload = " ".join([plain_text(markdown_text), *headings, *tags, *categories])
    return re.sub(r"\s+", " ", payload).strip()


def extract_metadata(markdown_text: str, issue_date: dt.date, issue_path: Path, sender) -> dict[str, str]:
    lines = markdown_text.splitlines()
    summary = clean_summary(lines)
    headings = headings_from_markdown(markdown_text)
    plain = plain_text(markdown_text)
    themes = detect_themes(plain)
    tags = [label for label, _, _ in themes[:6]]
    categories = []
    for _, category, _ in themes:
        if category not in categories:
            categories.append(category)
        if len(categories) == 3:
            break
    if not categories:
        categories = ["Science & Technology"]
    search_text = build_search_text(markdown_text, headings, tags, categories)
    themes = detect_themes(search_text)
    title = issue_title_from_themes(themes, summary)
    published_at = dt.datetime.fromtimestamp(issue_path.stat().st_mtime)
    display_date = issue_date.strftime("%B %d, %Y")
    display_time = published_at.strftime("%I:%M %p").lstrip("0")
    reading_time = estimate_reading_time(search_text)
    content_html = sender.blocks_to_html(sender.markdown_to_blocks(markdown_text))
    return {
        "title": title,
        "display_date": display_date,
        "display_time": display_time,
        "issue_date": issue_date.isoformat(),
        "published_at": published_at.isoformat(timespec="minutes"),
        "published_label": issue_published_label(issue_date, display_time),
        "reading_time": str(reading_time),
        "summary": summary,
        "content_html": content_html,
        "search_text": search_text,
        "headings": headings,
        "url": f"/issues/{issue_date.isoformat()}/",
        "tags": tags,
        "categories": categories,
        "primary_category": categories[0],
    }


def issue_document(entry: dict[str, str]) -> str:
    return (
        "---\n"
        f'layout: issue\n'
        f'title: "{yaml_escape(entry["title"])}"\n'
        f'issue_date: "{entry["issue_date"]}"\n'
        f'display_date: "{yaml_escape(entry["display_date"])}"\n'
        f'display_time: "{yaml_escape(entry["display_time"])}"\n'
        f'published_at: "{yaml_escape(entry["published_at"])}"\n'
        f'published_label: "{yaml_escape(entry["published_label"])}"\n'
        f'reading_time: {entry["reading_time"]}\n'
        f'primary_category: "{yaml_escape(entry["primary_category"])}"\n'
        f"categories: {yaml_list(entry['categories'])}\n"
        f"tags: {yaml_list(entry['tags'])}\n"
        f'summary: "{yaml_escape(entry["summary"])}"\n'
        f'permalink: "{entry["url"]}"\n'
        "---\n"
        f'{entry["content_html"]}\n'
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_reference_images() -> None:
    images_dir = SITE_DIR / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        PERSONAL_SITE_ASSETS / "M57_JwstKong_960.JPG": images_dir / "newsletter-hero.jpg",
        PERSONAL_SITE_ASSETS / "Crab_MultiChandra_960.JPG": images_dir / "newsletter-footer.jpg",
    }
    for source, destination in mapping.items():
        if source.exists():
            shutil.copy2(source, destination)


def build_site_pages() -> list[dict[str, object]]:
    return [
        {
            "id": "home",
            "date": "site",
            "display_date": "Homepage",
            "display_time": "",
            "published_label": "Site page",
            "published_at": "",
            "title": "Frontier Threads homepage",
            "summary": "Current issue landing page with pinned items, featured issues, discovery panels, and top-level newsletter search.",
            "url": "/",
            "search_text": "homepage current issue pinned featured issues discovery rss newsletter search archive frontier threads",
            "reading_time": 1,
            "tags": ["homepage", "archive", "search"],
            "categories": ["Site"],
            "primary_category": "Site",
            "kind": "page",
            "pinned": False,
            "featured": False,
        },
        {
            "id": "archive",
            "date": "site",
            "display_date": "Archive",
            "display_time": "",
            "published_label": "Site page",
            "published_at": "",
            "title": "Frontier Threads archive",
            "summary": "Full list of archived newsletter issues with browser-side search access.",
            "url": "/archive/",
            "search_text": "archive browse issues newsletter dates search frontier threads",
            "reading_time": 1,
            "tags": ["archive", "issues", "browse"],
            "categories": ["Site"],
            "primary_category": "Site",
            "kind": "page",
            "pinned": True,
            "featured": False,
        },
        {
            "id": "search",
            "date": "site",
            "display_date": "Search",
            "display_time": "",
            "published_label": "Site page",
            "published_at": "",
            "title": "Frontier Threads search",
            "summary": "Dedicated full-text search page for the newsletter archive and site navigation.",
            "url": "/search/",
            "search_text": "search full text keyword archive newsletters site frontier threads",
            "reading_time": 1,
            "tags": ["search", "keyword", "archive"],
            "categories": ["Site"],
            "primary_category": "Site",
            "kind": "page",
            "pinned": True,
            "featured": False,
        },
        {
            "id": "feed",
            "date": "site",
            "display_date": "Feed",
            "display_time": "",
            "published_label": "Site page",
            "published_at": "",
            "title": "Frontier Threads RSS feed",
            "summary": "Subscription feed for new Frontier Threads issues.",
            "url": "/feed.xml",
            "search_text": "rss feed subscribe frontier threads latest issues",
            "reading_time": 1,
            "tags": ["rss", "feed", "subscribe"],
            "categories": ["Site"],
            "primary_category": "Site",
            "kind": "page",
            "pinned": True,
            "featured": False,
        },
        {
            "id": "sitemap",
            "date": "site",
            "display_date": "Sitemap",
            "display_time": "",
            "published_label": "Site page",
            "published_at": "",
            "title": "Frontier Threads sitemap",
            "summary": "Jump page for the homepage, archive, search, RSS feed, and every published issue.",
            "url": "/sitemap/",
            "search_text": "sitemap pages current issue archive search rss feed issues frontier threads",
            "reading_time": 1,
            "tags": ["sitemap", "navigation", "rss"],
            "categories": ["Site"],
            "primary_category": "Site",
            "kind": "page",
            "pinned": False,
            "featured": False,
        },
    ]


def build_site_features(entries: list[dict[str, str]], curations: dict[str, object]) -> dict[str, object]:
    issue_entries = sorted(entries, key=lambda item: item["issue_date"], reverse=True)
    latest_issue = issue_entries[0] if issue_entries else None
    site_pages = build_site_pages()
    page_lookup = {page["id"]: page for page in site_pages}

    pinned: list[dict[str, object]] = []
    if latest_issue:
        pinned.append(
            {
                "title": latest_issue["title"],
                "summary": latest_issue["summary"],
                "url": latest_issue["url"],
                "primary_category": "Current Issue",
                "tags": latest_issue["tags"][:3],
                "reading_time": int(latest_issue["reading_time"]),
                "published_label": latest_issue["published_label"],
                "display_date": latest_issue["display_date"],
                "display_time": latest_issue["display_time"],
                "kind": "issue",
                "pinned": True,
                "featured": True,
            }
        )
    for page_id in ("archive", "search", "feed"):
        page = page_lookup[page_id]
        pinned.append({**page})

    featured_dates = [str(value) for value in curations.get("featured_issue_dates", []) if str(value).strip()]
    featured_lookup = {entry["issue_date"]: entry for entry in issue_entries}
    featured_issues: list[dict[str, object]] = []
    seen_dates: set[str] = set()
    target_featured_count = 3
    for issue_date in featured_dates:
        entry = featured_lookup.get(issue_date)
        if not entry or issue_date in seen_dates:
            continue
        featured_issues.append({**entry, "featured": True, "pinned": False})
        seen_dates.add(issue_date)
        if len(featured_issues) >= target_featured_count:
            break
    for entry in issue_entries:
        if len(featured_issues) >= target_featured_count:
            break
        if entry["issue_date"] in seen_dates:
            continue
        featured_issues.append({**entry, "featured": False, "pinned": False})
        seen_dates.add(entry["issue_date"])

    tag_counts = Counter(tag for entry in issue_entries for tag in entry["tags"])
    top_tags = [
        {
            "name": tag,
            "count": count,
            "url": build_filter_url(tag=tag, sort="relevance"),
        }
        for tag, count in tag_counts.most_common(12)
    ]
    category_counts = Counter(category for entry in issue_entries for category in entry["categories"])
    top_categories = [
        {
            "name": category,
            "count": count,
            "url": build_filter_url(category=category, sort="newest"),
        }
        for category, count in category_counts.most_common(8)
    ]

    discovery_topics = [
        {
            "title": tag["name"],
            "summary": f"{tag['count']} issue{'s' if tag['count'] != 1 else ''} indexed under this thread.",
            "url": tag["url"],
            "primary_category": "Topic",
        }
        for tag in top_tags[:4]
    ]

    year_counts = Counter(entry["issue_date"][:4] for entry in issue_entries)
    month_counts = Counter(entry["issue_date"][:7] for entry in issue_entries)
    archive_years = [
        {
            "value": year,
            "label": year,
            "count": year_counts[year],
            "url": build_filter_url(sort="newest") + f"{'&' if '?' in build_filter_url(sort='newest') else '?'}year={quote(year)}",
        }
        for year in sorted(year_counts.keys(), reverse=True)
    ]
    archive_months = [
        {
            "value": month,
            "label": dt.date.fromisoformat(f"{month}-01").strftime("%B %Y"),
            "count": month_counts[month],
            "url": build_filter_url(sort="newest") + f"{'&' if '?' in build_filter_url(sort='newest') else '?'}month={quote(month)}",
        }
        for month in sorted(month_counts.keys(), reverse=True)
    ]
    min_issue_date = issue_entries[-1]["issue_date"] if issue_entries else ""
    max_issue_date = issue_entries[0]["issue_date"] if issue_entries else ""

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "issue_count": len(issue_entries),
        "latest_issue": latest_issue,
        "pinned": pinned,
        "featured_issues": featured_issues,
        "recent_issues": issue_entries[:8],
        "top_tags": top_tags,
        "top_categories": top_categories,
        "discovery_topics": discovery_topics,
        "archive_years": archive_years,
        "archive_months": archive_months,
        "min_issue_date": min_issue_date,
        "max_issue_date": max_issue_date,
        "core_pages": [page_lookup["home"], page_lookup["archive"], page_lookup["search"], page_lookup["feed"], page_lookup["sitemap"]],
    }


def build_search_index(entries: list[dict[str, str]], site_features: dict[str, object]) -> str:
    featured_dates = {
        item["issue_date"]
        for item in site_features.get("featured_issues", [])
        if isinstance(item, dict) and item.get("issue_date")
    }
    payload = []
    for entry in sorted(entries, key=lambda item: item["issue_date"], reverse=True):
        payload.append(
            {
                "date": entry["issue_date"],
                "display_date": entry["display_date"],
                "display_time": entry["display_time"],
                "published_label": entry["published_label"],
                "published_at": entry["published_at"],
                "title": entry["title"],
                "summary": entry["summary"],
                "url": entry["url"],
                "search_text": entry["search_text"],
                "reading_time": int(entry["reading_time"]),
                "tags": entry["tags"],
                "categories": entry["categories"],
                "primary_category": entry["primary_category"],
                "kind": "issue",
                "featured": entry["issue_date"] in featured_dates,
                "pinned": False,
            }
        )
    payload.extend(build_site_pages())
    return json.dumps(payload, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Jekyll-based archive source tree for GitHub Pages.")
    parser.parse_args()

    sender = load_sender_module()
    baseurl = os.environ.get("NEWSLETTER_BASEURL", "").strip()
    if baseurl == "/":
        baseurl = ""
    elif baseurl:
        baseurl = "/" + baseurl.strip("/")
    site_url = os.environ.get("NEWSLETTER_SITE_URL", "").strip().rstrip("/")
    if baseurl and site_url.endswith(baseurl):
        site_url = site_url[: -len(baseurl)].rstrip("/")
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    copy_reference_images()
    curations = load_site_curations()

    entries: list[dict[str, str]] = []
    for issue_path in sorted(ISSUES_DIR.glob("*-daily-newsletter.md")):
        issue_date = dt.date.fromisoformat(issue_path.name[:10])
        markdown_text = issue_path.read_text(encoding="utf-8")
        entry = extract_metadata(markdown_text, issue_date, issue_path, sender)
        entries.append(entry)
        write_text(SITE_DIR / "_issues" / f"{issue_date.isoformat()}.md", issue_document(entry))

    site_features = build_site_features(entries, curations)

    write_text(SITE_DIR / "_config.yml", config_yml(baseurl=baseurl, site_url=site_url))
    write_text(SITE_DIR / "_data" / "site_features.json", json.dumps(site_features, indent=2))
    write_text(SITE_DIR / "_layouts" / "default.html", DEFAULT_LAYOUT)
    write_text(SITE_DIR / "_layouts" / "issue.html", ISSUE_LAYOUT)
    write_text(SITE_DIR / "index.html", HOME_PAGE)
    write_text(SITE_DIR / "archive.html", ARCHIVE_PAGE)
    write_text(SITE_DIR / "search.html", SEARCH_PAGE)
    write_text(SITE_DIR / "feed.xml", FEED_XML)
    write_text(SITE_DIR / "sitemap.html", SITEMAP_PAGE)
    write_text(SITE_DIR / "assets" / "site.css", SITE_CSS.strip() + "\n")
    write_text(SITE_DIR / "assets" / "search.js", SEARCH_JS.strip() + "\n")
    write_text(SITE_DIR / "search.json", build_search_index(entries, site_features))

    print(f"Built Jekyll archive source in {SITE_DIR}")


if __name__ == "__main__":
    main()
