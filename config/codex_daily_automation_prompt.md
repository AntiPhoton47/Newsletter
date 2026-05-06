# Codex Daily Newsletter Automation Prompt

Work in `/Users/munga/PycharmProjects/Newsletter`.

This task needs live network access against the linked GitHub repository for this project so source research, market checks, and publishing can complete normally.

Your job is to produce today's `Frontier Threads` issue, rebuild the site artifacts, and push the result directly to `main` only if the issue meets the April 13, 2026 quality bar.

Use these repo references before changing anything:
- `issues/daily/2026-04-13-daily-newsletter.md` as the benchmark issue
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
3. Use the packet, `sources.md`, `selection_criteria.md`, `daily_workflow.md`, `daily_issue_template.md`, and the April 13 benchmark as the editorial operating system for the run.
4. Search the listed sources directly on the web. Prefer underlying publisher and institution pages over Google wrapper pages, and use the candidate snapshot only as a discovery aid rather than the final source of truth.
5. Before drafting, do a top-level triage pass for globally significant events. If there are major developments in conflicts, space missions, frontier AI/security, markets, geopolitics, or science that fit the reader, they should usually appear somewhere in the issue rather than being missed because they were absent from one section's candidate snapshot.
6. Enforce source-mix discipline actively rather than passively. Do not lean too hard on a small familiar cluster of outlets when stronger or more relevant sources from `sources.md` are available. In particular:
   - check PhilPapers first for philosophy when the section needs current, relevant material
   - check arXiv and the Physical Review family, PRX Quantum, Quantum, and comparable primary venues for research-heavy physics and mathematics stories before defaulting to Nature coverage
   - use 1440, Morning Brew, Superpower Daily, Nature Briefing, and The Download as supplements and discovery aids, not as the section backbone
7. Capture useful notes in `data/research_notes/YYYY-MM-DD.md`, then write the final publication-ready issue directly to `issues/daily/YYYY-MM-DD-daily-newsletter.md`.
8. Draft the issue yourself from the packet and live source reporting. Optional repo AI tools may assist, but they are never required and must not block drafting, review, or publication when unavailable.
9. Use the April 13 issue as the reference for structure, explanatory density, section balance, tone, and editorial finish. Matching headings is not enough; the issue should feel equally curated and equally readable.
10. This automation requires live network access for direct source research, fresher market data, and `git push`. If a fetch, market refresh, or publish step fails, report the concrete failing step instead of generic runner-misconfiguration language.
11. Do not allow title-only sections, repeated feed text, unlabeled sources, raw URLs in prose, generic filler, obvious placeholders, or sections that merely restate headlines without explanation.
12. Preserve the authoritative `Markets & Economy` section from the scaffold or the generated data unless you are correcting an obvious formatting issue, but replace the company lines with 2-4 notable companies chosen for that day rather than reusing a fixed set.
13. Market quotes and macro lines must use the latest available credible data. If live fetches can produce fresher values than the cache, use them. If live fetches fail, use the latest recent cached market snapshot with explicit as-of dates. If neither live data nor a recent cache can support a credible `Markets & Economy` block, stop without pushing.
14. Add a clean `Private-Market Watchlist` subsection only when there is real private-company news worth covering, such as IPO planning, secondary sales, valuation resets, fundraising, regulatory shifts, or strategic actions. Do not keep the same private companies there by default.
15. Repeated stories should be rare. Only carry a story into consecutive issues if there is a clearly new development, number, institution, consequence, or stronger explanatory frame.
16. Pick a different cool destination for `Travel` than the previous issue when possible, include a photo that actually depicts the named destination, and make sure the image renders in the markdown and HTML preview.
17. Prefer matter-of-fact reporting, descriptive titles, and clean summaries over thesis-heavy or slogan-like framing. Avoid repetitive `X matters because Y` scaffolding, overexplaining significance when it is already clear from the reporting, and forcing an application angle onto ideas that are already interesting on their own terms.
18. Keep the prose reader-facing. Do not include meta language aimed at the operator, the chat, or the drafting process inside the published issue.
19. Keep the issue selective, analytical, low-bias, and useful to a technically sophisticated reader. Prefer cutting weak items over padding sections.
20. Once the issue is publication-ready, run:
   `python3 scripts/newsletter_command.py publish --git-commit --git-push`
21. If review or benchmark quality fails, improve the issue and rerun `publish`. If you cannot reach benchmark quality from the available material, stop without pushing.

Git requirements:
- Push changes to the linked GitHub repository's `main` branch.
- Use a clear commit message in the form: `Update newsletter issue YYYY-MM-DD`.
- Do not open a pull request unless the environment requires it instead of direct push.

Definition of done:
- today's issue exists in `issues/daily/YYYY-MM-DD-daily-newsletter.md`
- the HTML preview and Jekyll site artifacts are refreshed
- the final issue is at least as coherent and useful as the April 13 benchmark
- changes are committed and pushed to `main`

Failure policy:
- If editorial review fails or source material is too weak to meet the benchmark, stop without pushing and leave the repo in a state that makes the failure reason obvious in the review artifacts.
- Optional AI drafting or AI review tooling being unavailable is not, by itself, a reason to stop; continue with direct writing and the non-optional quality gates.
- Do not push a weak issue just to satisfy the schedule.
