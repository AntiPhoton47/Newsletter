# Newsletter

This folder contains a local daily newsletter pipeline:

- fetch candidates from configured news queries
- generate a draft daily issue as Markdown in `issues/daily`
- optionally have an OpenAI model polish the draft into a read-ready issue
- optionally have a second OpenAI model review the issue for release readiness
- render it to a styled HTML email
- build a Jekyll archive site for GitHub Pages
- send it through any SMTP provider
- schedule it on macOS with `launchd`

## Layout

- `issues/daily`: daily Markdown issues named `YYYY-MM-DD-daily-newsletter.md`
- `config/section_queries.json`: feed/search queries used for automated candidate gathering
- `data/candidates`: raw fetched candidate story data by date
- `scripts/send_daily_newsletter.py`: renderer and email sender
- `scripts/fetch_candidates.py`: fetches candidates from configured queries
- `scripts/generate_issue.py`: generates a draft issue from candidate data
- `scripts/ai_generate_issue.py`: uses OpenAI to rewrite the draft into a stronger editorial issue
- `scripts/review_issue.py`: runs quality checks on generated issues before send
- `scripts/ai_review_issue.py`: uses OpenAI to score and gate the issue for automatic delivery
- `scripts/openai_pipeline.py`: shared OpenAI API and AI-config helpers
- `scripts/build_archive.py`: builds a Jekyll source tree for the archive into `site/`
- `scripts/run_daily_pipeline.py`: runs fetch, generate, render, archive, and optional send
- `output`: generated HTML previews
- `site`: generated Jekyll site source for GitHub Pages
- `launchd/com.munga.newsletter.daily.plist`: example scheduler job
- `.github/workflows/publish-newsletter-site.yml`: optional GitHub Pages publishing workflow
- `.env.example`: SMTP configuration template
- `sources.md`: editorial source registry grouped by section and source type
- `selection_criteria.md`: editorial rubric for story selection tailored to the target reader
- `story_scorecard.md`: reusable template for scoring and triaging candidate stories
- `daily_workflow.md`: repeatable end-to-end workflow for gathering, scoring, writing, rendering, and sending an issue
- `daily_issue_template.md`: reusable Markdown template for building a new daily issue

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in your SMTP settings and recipient email.
3. Optional but recommended: fill in `OPENAI_API_KEY` and the AI settings if you want the draft polished and reviewed automatically.
4. Fetch candidates and generate an issue:

```bash
python3 scripts/run_daily_pipeline.py --overwrite
```

5. Review the generated issue in `issues/daily` if you want a manual check.
6. Render a preview if needed:

```bash
python3 scripts/send_daily_newsletter.py --preview-html --latest
```

7. Send a test message:

```bash
python3 scripts/send_daily_newsletter.py --latest
```

## Daily schedule on macOS

Copy the sample plist into `~/Library/LaunchAgents` and load it:

```bash
cp launchd/com.munga.newsletter.daily.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.munga.newsletter.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.munga.newsletter.daily.plist
```

The sample job runs every day at 07:30 local time. It now calls the full pipeline script, which fetches candidates, generates the issue, optionally applies AI drafting and AI review, renders the preview, builds the archive, and sends the email.

## Notes

- The sender script has no third-party Python dependencies.
- `--preview-html` always writes a browser-openable preview into `output/`.
- If there is no issue matching today's date, the script falls back to the latest daily issue.
- `scripts/fetch_candidates.py` uses configured Google News RSS search queries as a feed-based ingestion layer.
- Google News RSS is currently the discovery layer for automated candidate gathering; the intended editorial sources remain the underlying publishers and institutions listed in `sources.md`.
- `scripts/generate_issue.py` produces a draft issue automatically; you can still edit the Markdown before sending.
- `scripts/ai_generate_issue.py` upgrades that draft into a more readable issue when `OPENAI_API_KEY` is configured.
- `scripts/review_issue.py` blocks the pipeline when low-quality feed artifacts or obvious placeholders remain in the draft.
- `scripts/ai_review_issue.py` adds an editorial release gate and can block automatic delivery if the issue is not ready.
- `scripts/build_archive.py` builds a Jekyll archive with a current-issue landing page, browseable archive, and client-side keyword search.
- `scripts/run_daily_pipeline.py` is the one-command daily automation entry point.
- the daily pipeline now fails closed: if review checks detect low-quality artifacts, the draft is generated but preview/build/send are blocked until the issue is fixed
- if `NEWSLETTER_REQUIRE_AI=true`, the pipeline also fails closed when the AI editorial layer is unavailable
- `sources.md` is the current reference for where each newsletter section is drawing material from.
- `selection_criteria.md` defines how stories should be prioritized and tailored to the reader's interests.
- `story_scorecard.md` provides a lightweight scoring workflow for deciding whether a story should become a main entry, short take, or be excluded.
- `daily_workflow.md` ties the sourcing, scoring, drafting, and publishing steps into one repeatable editorial process.
- `daily_issue_template.md` provides the working structure for drafting each new issue.
