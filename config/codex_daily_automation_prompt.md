# Codex Daily Newsletter Automation Prompt

Work in `/Users/munga/PycharmProjects/Newsletter`.

This task runs in Codex cloud against the linked GitHub repository for this project.

Your job is to produce today's `Frontier Threads` issue, rebuild the site artifacts, and push the result directly to `main` only if the issue meets the March 15, 2026 quality bar.

Use these repo references before changing anything:
- `issues/daily/2026-03-15-daily-newsletter.md` as the benchmark issue
- `daily_workflow.md`
- `daily_issue_template.md`
- `selection_criteria.md`
- `sources.md`
- `story_scorecard.md`
- `config/newsletter_profile.json`

Required workflow:
1. Prepare the run context first:
   `python3 scripts/newsletter_command.py prepare`
2. Read the generated packet and scaffolds for today's date in:
   - `data/editorial_packets/YYYY-MM-DD.md`
   - `data/editorial_packets/YYYY-MM-DD.json`
   - `data/editorial_packets/YYYY-MM-DD-issue-scaffold.md`
   - `data/research_notes/YYYY-MM-DD.md`
3. Use the packet, `sources.md`, `selection_criteria.md`, `daily_workflow.md`, `daily_issue_template.md`, and the March 15 benchmark as the editorial operating system for the run.
4. Search the listed sources directly on the web. Prefer underlying publisher and institution pages over Google wrapper pages, and use the candidate snapshot only as a discovery aid rather than the final source of truth.
5. Capture useful notes in `data/research_notes/YYYY-MM-DD.md`, then write the final publication-ready issue directly to `issues/daily/YYYY-MM-DD-daily-newsletter.md`.
6. Use the March 15 issue as the reference for structure, explanatory density, section balance, tone, and editorial finish. Matching headings is not enough; the issue should feel equally curated and equally readable.
7. Do not allow title-only sections, repeated feed text, unlabeled sources, raw URLs in prose, generic filler, obvious placeholders, or sections that merely restate headlines without explanation.
8. Preserve the authoritative `Markets & Economy` section from the scaffold or the generated data unless you are correcting an obvious formatting issue.
9. Keep the issue selective, analytical, low-bias, and useful to a technically sophisticated reader. Prefer cutting weak items over padding sections.
10. Once the issue is publication-ready, run:
   `python3 scripts/newsletter_command.py publish --git-commit --git-push`
11. If review or benchmark quality fails, improve the issue and rerun `publish`. If you cannot reach benchmark quality from the available material, stop without pushing.

Git requirements:
- Push changes to the linked GitHub repository's `main` branch.
- Use a clear commit message in the form: `Update newsletter issue YYYY-MM-DD`.
- Do not open a pull request unless the environment requires it instead of direct push.

Definition of done:
- today's issue exists in `issues/daily/YYYY-MM-DD-daily-newsletter.md`
- the HTML preview and Jekyll site artifacts are refreshed
- the final issue is at least as coherent and useful as the March 15 benchmark
- changes are committed and pushed to `main`

Failure policy:
- If the AI review fails or source material is too weak to meet the benchmark, stop without pushing and leave the repo in a state that makes the failure reason obvious in the review artifacts.
- Do not push a weak issue just to satisfy the schedule.
