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
- `scripts/newsletter_command.py`: single remote-friendly entrypoint that runs the full pipeline and can optionally commit/push the result
- `output`: generated HTML previews
- `site`: generated Jekyll site source for GitHub Pages
- `launchd/com.munga.newsletter.daily.plist`: example scheduler job
- `.github/workflows/publish-newsletter-site.yml`: optional GitHub Pages publishing workflow
- `.env.example`: SMTP configuration template
- `config/newsletter_profile.json`: default editorial and automation profile for the remote command
- `config/codex_daily_automation_prompt.md`: ready-to-paste Codex Desktop automation prompt for unattended daily generation
- `sources.md`: editorial source registry grouped by section and source type
- `selection_criteria.md`: editorial rubric for story selection tailored to the target reader
- `story_scorecard.md`: reusable template for scoring and triaging candidate stories
- `daily_workflow.md`: repeatable end-to-end workflow for gathering, scoring, writing, rendering, and sending an issue
- `daily_issue_template.md`: reusable Markdown template for building a new daily issue

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in your SMTP settings and recipient email.
3. Recommended default: fill in `OPENAI_API_KEY` and keep the AI settings enabled. The project is now tuned for a fail-closed, AI-required workflow if you want output at or above the March 15, 2026 benchmark issue quality.
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

## One-command remote run

If you want a single command that fetches sources, generates the issue, rebuilds the archive/search index, and optionally emails and publishes it, use:

```bash
python3 scripts/newsletter_command.py run
```

By default, the profile in `config/newsletter_profile.json` now assumes:
- overwrite the current day's issue
- keep email sending off unless requested
- commit the generated changes
- push the result to GitHub

Useful variants:

```bash
python3 scripts/newsletter_command.py run --send
python3 scripts/newsletter_command.py run --date 2026-03-21 --send
python3 scripts/newsletter_command.py run --send --git-commit --git-push
python3 scripts/newsletter_command.py run --no-overwrite
```

That last form is the closest to the full remote-trigger workflow:
- fetch candidates
- generate the newsletter
- run review
- render HTML
- rebuild the Jekyll site and search index
- send the email
- commit and push the updated archive so GitHub Pages refreshes

For an SSH-style remote trigger, the command would look like:

```bash
ssh <machine> 'cd /Users/munga/PycharmProjects/Newsletter && python3 scripts/newsletter_command.py run --send --git-commit --git-push'
```

## Trigger From Phone

The cleanest minimal-intervention setup is now GitHub-based:

1. Push this project to GitHub.
2. Add the required repository secrets:
   - `OPENAI_API_KEY`
   - optional SMTP secrets if you want the email sent automatically
3. Use the workflow [generate-newsletter.yml](/Users/munga/PycharmProjects/Newsletter/.github/workflows/generate-newsletter.yml).

You now have two phone-friendly trigger options:

- `GitHub app / mobile web`: open the `Generate Newsletter` workflow and tap `Run workflow`.
- `API trigger`: send a `repository_dispatch` event from a phone shortcut or HTTP client.

Example `repository_dispatch` request:

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer <github-token>" \
  https://api.github.com/repos/<owner>/<repo>/dispatches \
  -d '{
    "event_type": "run-newsletter",
    "client_payload": {
      "issue_date": "2026-03-21",
      "send_email": true
    }
  }'
```

What that workflow does:
- runs the full newsletter generation pipeline
- rebuilds the archive, search index, sitemap, and current issue pages
- commits the generated newsletter artifacts back to the repo
- pushes the changes
- lets the Pages publish workflow update the live site

That means your phone interaction can be as small as:
- tap `Run workflow` in GitHub, or
- trigger one saved shortcut / HTTP request

## Daily schedule on GitHub

The workflow [generate-newsletter.yml](/Users/munga/PycharmProjects/Newsletter/.github/workflows/generate-newsletter.yml) now also runs automatically every day at `06:35 UTC`.

Recommended repository secrets for production quality:
- `OPENAI_API_KEY`
- `NEWSLETTER_USE_AI=true`
- `NEWSLETTER_REQUIRE_AI=true`
- `NEWSLETTER_AI_REVIEW_MIN_SCORE=90`
- optional SMTP secrets if you want automatic email delivery

The scheduled workflow is configured to fail closed if the AI drafting or AI review layers are unavailable, which is the safest mode if the March 15, 2026 issue is your quality benchmark.

## Codex Desktop Automation Prompt

If you want Codex Desktop Automations to drive the repo directly instead of relying only on GitHub Actions, use the prompt in [config/codex_daily_automation_prompt.md](/Users/munga/PycharmProjects/Newsletter/config/codex_daily_automation_prompt.md).

That prompt tells Codex to:
- use the March 15 benchmark and the repo templates as hard references
- run the existing pipeline first
- refuse to push if the review reports fail or the issue is visibly below benchmark quality
- commit and push only publication-ready output

## Daily schedule on macOS

Copy the sample plist into `~/Library/LaunchAgents` and load it:

```bash
cp launchd/com.munga.newsletter.daily.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.munga.newsletter.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.munga.newsletter.daily.plist
```

The sample job runs every day at 07:30 local time. It now calls `scripts/newsletter_command.py run --send --git-commit --git-push`, so it generates the issue, runs the review gates, rebuilds the archive, sends the email, and pushes the refreshed artifacts to GitHub.

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
- The recommended production mode is now: `NEWSLETTER_USE_AI=true`, `NEWSLETTER_REQUIRE_AI=true`, and `NEWSLETTER_AI_REVIEW_MIN_SCORE=90`.
- `scripts/build_archive.py` builds a Jekyll archive with a current-issue landing page, browseable archive, and client-side keyword search.
- `scripts/run_daily_pipeline.py` is the one-command daily automation entry point.
- `scripts/newsletter_command.py` is the remote-friendly wrapper around the pipeline and is the recommended command to trigger over SSH or any other remote shell.
- the daily pipeline now fails closed: if review checks detect low-quality artifacts, the draft is generated but preview/build/send are blocked until the issue is fixed
- if `NEWSLETTER_REQUIRE_AI=true`, the pipeline also fails closed when the AI editorial layer is unavailable
- `config/newsletter_profile.json` is where you keep the standing editorial instructions that the AI drafting layer should follow on every run
- `sources.md` is the current reference for where each newsletter section is drawing material from.
- `selection_criteria.md` defines how stories should be prioritized and tailored to the reader's interests.
- `story_scorecard.md` provides a lightweight scoring workflow for deciding whether a story should become a main entry, short take, or be excluded.
- `daily_workflow.md` ties the sourcing, scoring, drafting, and publishing steps into one repeatable editorial process.
- `daily_issue_template.md` provides the working structure for drafting each new issue.
