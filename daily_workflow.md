# Daily Workflow

This document defines a repeatable workflow for producing each daily newsletter issue.

It is designed to work with:

- [sources.md](/Users/munga/PycharmProjects/Newsletter/sources.md)
- [selection_criteria.md](/Users/munga/PycharmProjects/Newsletter/selection_criteria.md)
- [story_scorecard.md](/Users/munga/PycharmProjects/Newsletter/story_scorecard.md)

## 1. Gather Candidate Stories

Use [sources.md](/Users/munga/PycharmProjects/Newsletter/sources.md) as the starting map.

For each section:

- scan primary sources first where possible
- use high-quality journalism for context and synthesis
- maintain a healthy mix of primary, specialist, and reference/discovery sources over time
- collect more candidates than you expect to publish
- note the date, source, and a one-line reason the story might matter

Target:

- `3-6` candidates for core sections
- `2-4` candidates for secondary sections
- enough items to populate short takes without repeating main entries

## 2. Score Stories

Use [story_scorecard.md](/Users/munga/PycharmProjects/Newsletter/story_scorecard.md) for candidate evaluation.

For each serious candidate:

- assign scores across the core criteria
- write brief notes on novelty, conceptual payoff, and relevance
- decide whether the item is a likely `main entry`, `short take`, or `exclude`

Use [selection_criteria.md](/Users/munga/PycharmProjects/Newsletter/selection_criteria.md) to break ties.

## 3. Build the Issue Portfolio

Before writing, decide the shape of the issue.

A strong issue should usually contain:

- one high-significance lead story
- several strong research or science/technology stories
- at least one policy, geopolitical, or macro story
- at least one tools/infrastructure story
- a mix of immediate news and slower structural developments

Check for:

- repetition across sections
- repetition from the previous issue unless the repeated story has a genuinely new development or angle
- overreliance on the same source in a section when a better or more direct source is available
- too much dependence on one outlet
- too much focus on one domain at the expense of the others

## 4. Assign Stories by Depth

Sort stories into three levels:

### Main Entries

Use for stories with:

- high conceptual density
- strong source backing
- broad or durable significance

### Short Takes

Use for stories that:

- add breadth
- are useful but secondary
- can be explained in one or two informative lines
- are distinct from the section's main entries

### Excluded

Drop stories that are:

- redundant
- weakly sourced
- too incremental
- mostly hype without analytic value

## 5. Draft the Markdown Issue

Write or update the daily issue file in:

- `issues/daily/YYYY-MM-DD-daily-newsletter.md`

Follow the existing section structure and style.

When drafting:

- keep the intro high-level and thematic
- make `Quick Hits` summarize the strongest sections, not random headlines
- keep source lines explicit and labeled
- avoid raw URLs in body copy
- keep short takes concise, source-backed, and informative enough to add one concrete fact, implication, or reason the item matters
- if you revisit a story from the previous issue, make the new value explicit rather than lightly rephrasing the earlier copy
- choose `2-4` notable company movers for `Markets & Economy` based on the day's action rather than a fixed ticker list
- make `Upcoming Investment Opportunities` specific to today's regime and catalysts rather than repeating a standing basket
- keep the investment-opportunities analysis focused on `2-3` strong clusters and explain what would make the thesis stronger or weaker
- make `Entertainment` concrete: list specific upcoming or currently hot movies, books, shows, games, or events rather than writing vague overview copy
- include at least one book when there is a credible fit, preferably one that connects to the issue's main themes in science, technology, history, philosophy, or world affairs
- make `World News` broader than a two-story digest when the source material supports it, and include European developments when they are materially relevant
- add a `Breaking News` subsection to `World News` when there are genuinely fast-moving developments that benefit from rapid, source-labeled treatment
- use `Breaking News` for `1-3` items sourced primarily from fast, reputable outlets or direct institutions such as AP, Reuters, BBC, Bloomberg, Financial Times, UN bodies, the European Commission, or NATO
- make `Tools You Can Use` actionable by linking directly to actual tools, products, repos, or APIs whenever possible
- give `Travel` a different destination from the previous issue when possible and include one image
- keep issue prose reader-facing and avoid meta comments about the writing process

## 6. Verify Section Quality

Before rendering, confirm:

- each section has a clear purpose
- short takes do not duplicate the main stories in the same section
- repeated stories from the last issue add a real factual or analytical increment
- the source mix across sections still feels deliberate rather than habitual
- the section order still feels coherent
- entertainment is concrete and date- or momentum-aware rather than hand-wavy
- entertainment includes books when there is a strong thematic fit with the rest of the issue
- short takes consistently add a small but useful analytical or factual increment rather than only restating the headline
- world news has enough breadth to feel globally useful, including Europe when relevant
- any `Breaking News` items are truly time-sensitive, clearly labeled, and sourced conservatively enough to avoid rumor-chasing
- tools links point to actual usable destinations rather than mostly commentary pages
- entertainment and travel remain concise and current
- travel includes an image that renders correctly
- the issue still feels curated rather than merely exhaustive

## 7. Render Preview

Generate the HTML preview:

```bash
python3 scripts/send_daily_newsletter.py --preview-html --latest
```

Review:

- spacing
- card layout
- dark/light mode behavior
- mobile responsiveness
- source links
- image rendering

## 8. Final Editorial Pass

Check:

- factual precision
- section balance
- tone
- absence of unnecessary political or social bias
- readability
- no obvious dead weight

Questions to ask:

- What are the three most valuable things in the issue?
- Does every section contain at least one item worth the reader's time?
- Are there any sections that feel padded rather than selective?

## 9. Send or Schedule

When the issue is ready:

```bash
python3 scripts/send_daily_newsletter.py --latest
```

For scheduled delivery, rely on the configured `launchd` job described in [README.md](/Users/munga/PycharmProjects/Newsletter/README.md).

## 10. Maintain the Editorial System

Update these files when needed:

- [sources.md](/Users/munga/PycharmProjects/Newsletter/sources.md) when new recurring sources are added
- [selection_criteria.md](/Users/munga/PycharmProjects/Newsletter/selection_criteria.md) when the target reader or editorial priorities change
- [story_scorecard.md](/Users/munga/PycharmProjects/Newsletter/story_scorecard.md) when the scoring workflow needs refinement

## Practical Rule of Thumb

If a story is interesting but not clearly useful, either:

- turn it into a short take
- cut it

The newsletter should feel selective, not merely comprehensive.
