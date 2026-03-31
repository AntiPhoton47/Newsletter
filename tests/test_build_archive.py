from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_archive  # noqa: E402


class DummySender:
    @staticmethod
    def markdown_to_blocks(text: str) -> str:
        return text

    @staticmethod
    def blocks_to_html(text: str) -> str:
        return f"<p>{text}</p>"


class BuildArchiveTests(unittest.TestCase):
    def test_extract_metadata_uses_issue_date_for_display_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "2026-03-16-daily-newsletter.md"
            path.write_text("# Frontier Threads\n\nA test summary.\n", encoding="utf-8")
            timestamp = dt.datetime(2026, 3, 21, 20, 37).timestamp()
            os.utime(path, (timestamp, timestamp))

            entry = build_archive.extract_metadata(
                path.read_text(encoding="utf-8"),
                dt.date(2026, 3, 16),
                path,
                DummySender(),
            )

        self.assertEqual(entry["display_date"], "March 16, 2026")
        self.assertEqual(entry["display_time"], "8:37 PM")
        self.assertEqual(entry["published_label"], "Mar 16, 2026 · 8:37 PM")

    def test_build_site_features_respects_curated_featured_dates(self) -> None:
        entries = [
            {
                "issue_date": "2026-03-31",
                "display_date": "March 31, 2026",
                "display_time": "10:36 PM",
                "published_label": "Mar 31, 2026 · 10:36 PM",
                "published_at": "2026-03-31T22:36",
                "title": "Latest issue",
                "summary": "Latest summary.",
                "url": "/issues/2026-03-31/",
                "search_text": "ai research tools",
                "reading_time": "10",
                "tags": ["AI Research", "Research Tools"],
                "categories": ["AI & Computing"],
                "primary_category": "AI & Computing",
            },
            {
                "issue_date": "2026-03-15",
                "display_date": "March 15, 2026",
                "display_time": "12:14 PM",
                "published_label": "Mar 15, 2026 · 12:14 PM",
                "published_at": "2026-03-15T12:14",
                "title": "Benchmark issue",
                "summary": "Benchmark summary.",
                "url": "/issues/2026-03-15/",
                "search_text": "ai research mathematics",
                "reading_time": "12",
                "tags": ["AI Research", "Mathematics"],
                "categories": ["AI & Computing", "Mathematics & Ideas"],
                "primary_category": "AI & Computing",
            },
        ]

        features = build_archive.build_site_features(
            entries,
            {"featured_issue_dates": ["2026-03-15"]},
        )

        self.assertEqual(features["latest_issue"]["issue_date"], "2026-03-31")
        self.assertEqual(features["featured_issues"][0]["issue_date"], "2026-03-15")
        self.assertEqual(features["top_tags"][0]["name"], "AI Research")
        self.assertEqual(features["archive_years"][0]["value"], "2026")
        self.assertEqual(features["archive_months"][0]["value"], "2026-03")
        self.assertEqual(features["min_issue_date"], "2026-03-15")
        self.assertEqual(features["max_issue_date"], "2026-03-31")


if __name__ == "__main__":
    unittest.main()
