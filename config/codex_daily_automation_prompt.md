# Codex Daily Newsletter Automation Prompt

Work in `/Users/munga/PycharmProjects/Newsletter`.

Your job is to produce today's `Frontier Threads` issue, rebuild the site artifacts, and push the result to GitHub only if the issue meets the March 15, 2026 quality bar.

Use these repo references before changing anything:
- `issues/daily/2026-03-15-daily-newsletter.md` as the benchmark issue
- `daily_workflow.md`
- `daily_issue_template.md`
- `selection_criteria.md`
- `sources.md`
- `config/newsletter_profile.json`

Required workflow:
1. Run the existing pipeline first instead of writing the issue from scratch:
   `python3 scripts/newsletter_command.py run`
2. Review the generated files for today's date in:
   - `issues/daily/`
   - `output/`
   - `data/reviews/`
   - `data/ai_reviews/`
3. If the generated issue is thin, repetitive, placeholder-like, weakly sourced, or clearly below the March 15 benchmark, improve the newsletter directly in the repo and rebuild the derived artifacts.
4. Do not allow title-only sections, repeated feed text, unlabeled sources, raw URLs in prose, or generic filler.
5. Preserve the authoritative `Markets & Economy` data section unless you are correcting an obvious formatting issue.
6. Keep the issue selective, analytical, and low-bias. Prefer cutting weak items over padding sections.
7. Only push when the issue is publication-ready and the review reports pass.

Definition of done:
- today's issue exists in `issues/daily/YYYY-MM-DD-daily-newsletter.md`
- the HTML preview and Jekyll site artifacts are refreshed
- the final issue is at least as coherent and useful as the March 15 benchmark
- changes are committed and pushed to the repo's default branch

If the AI review fails or source material is too weak to meet the benchmark, stop without pushing and leave the repo in a state that makes the failure reason obvious in the review artifacts.
