# Project Rules

This repository contains the `Frontier Threads` daily newsletter workflow.

## Newsletter Benchmark

- Treat [`issues/daily/2026-04-13-daily-newsletter.md`](/Users/munga/PycharmProjects/Newsletter/issues/daily/2026-04-13-daily-newsletter.md) as the current editorial benchmark unless a newer benchmark is explicitly configured in [`config/newsletter_profile.json`](/Users/munga/PycharmProjects/Newsletter/config/newsletter_profile.json).

## Newsletter Automation Requirements

- Newsletter automation runs require live network access for direct source research, fresher market data, and `git push`.
- Prefer a local full-access runner for the newsletter automation so source research, market refreshes, and publishing can complete normally.

## Editorial Workflow

- Start newsletter runs with `python3 scripts/newsletter_command.py prepare`.
- Read the dated packet and scaffolds before drafting.
- Keep the issue selective, source-labeled, benchmark-quality, and publication-ready before running `python3 scripts/newsletter_command.py publish --git-commit --git-push`.

## Important Limitation

- This file is a project instruction file. It can guide future runs, but it cannot itself override a sandbox or network policy injected by the Codex Desktop automation runner.
