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
- `config/newsletter_profile.json`

Required workflow:
1. Start from the repository's existing workflow instead of inventing a parallel process:
   `python3 scripts/newsletter_command.py run`
2. Review the generated files for today's date in:
   - `issues/daily/`
   - `output/`
   - `data/reviews/`
   - `data/ai_reviews/`
3. If the generated issue is thin, repetitive, placeholder-like, weakly sourced, or clearly below the March 15 benchmark, improve the newsletter directly in the repo and rebuild the derived artifacts before considering a push.
4. Use the March 15 issue as the reference for structure, explanatory density, section balance, tone, and editorial finish. Matching headings is not enough; the issue should feel equally curated and equally readable.
5. Do not allow title-only sections, repeated feed text, unlabeled sources, raw URLs in prose, generic filler, obvious placeholders, or sections that merely restate headlines without explanation.
6. Preserve the authoritative `Markets & Economy` data section unless you are correcting an obvious formatting issue.
7. Keep the issue selective, analytical, low-bias, and useful to a technically sophisticated reader. Prefer cutting weak items over padding sections.
8. If a section cannot be supported at benchmark quality from the available material, keep it concise rather than filling it with low-value copy.
9. Commit and push only when the issue is publication-ready and the review reports pass. If quality is below benchmark, do not push.

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
