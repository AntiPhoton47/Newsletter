from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_candidates as fc  # noqa: E402


class FetchCandidateCoverageTests(unittest.TestCase):
    def test_build_source_probe_queries_adds_unmapped_sources(self) -> None:
        probes = fc.build_source_probe_queries(
            "World News",
            ["Reuters", "BBC News", "United Nations"],
            ["Europe policy site:reuters.com OR site:ft.com"],
        )

        self.assertIn(("BBC News", "(war OR conflict OR europe OR china) site:bbc.com"), probes)
        self.assertIn(("United Nations", "(war OR conflict OR europe OR china) site:un.org"), probes)
        self.assertFalse(any(source == "Reuters" for source, _ in probes))

    def test_query_matches_source_uses_domain_hints(self) -> None:
        self.assertTrue(fc.query_matches_source("Europe policy site:reuters.com OR site:ft.com", "Reuters"))
        self.assertFalse(fc.query_matches_source("site:nature.com quantum physics", "Reuters"))

    def test_build_story_clusters_groups_similar_titles(self) -> None:
        entries = [
            {
                "title": "Iran ceasefire strains as Lebanon attacks continue",
                "publisher": "AP News",
                "summary": "The truce is under pressure after attacks linked to Lebanon.",
                "published": "2026-04-09T10:00:00Z",
                "source_type": "google-news-rss",
            },
            {
                "title": "Lebanon attacks test Iran ceasefire durability",
                "publisher": "Reuters",
                "summary": "Regional attacks are straining the Iran ceasefire.",
                "published": "2026-04-09T11:00:00Z",
                "source_type": "google-news-rss",
            },
            {
                "title": "Artemis II crew returns from Moon flyby",
                "publisher": "BBC News",
                "summary": "The mission completed its lunar pass.",
                "published": "2026-04-09T09:00:00Z",
                "source_type": "google-news-rss",
            },
        ]

        clusters = fc.build_story_clusters(entries)

        self.assertEqual(len(clusters), 2)
        leading_cluster = max(clusters, key=lambda cluster: int(cluster["support_count"]))
        self.assertEqual(leading_cluster["support_count"], 2)

    def test_build_source_coverage_marks_query_checked_sources(self) -> None:
        coverage = fc.build_source_coverage(
            "World News",
            ["Reuters", "BBC News", "United Nations"],
            [
                {"query": "Europe policy site:reuters.com OR site:bbc.com", "status": "ok"},
                {"query": "humanitarian site:un.org", "status": "ok"},
            ],
            [
                {
                    "title": "Europe expands defense lending",
                    "publisher": "Reuters",
                    "summary": "A new package expands procurement financing.",
                    "published": "2026-04-09T10:00:00Z",
                    "source_type": "google-news-rss",
                }
            ],
            {},
        )

        self.assertEqual(coverage["checked_source_count"], 3)
        uncovered = coverage["uncovered_sources"]
        self.assertEqual(uncovered, [])


if __name__ == "__main__":
    unittest.main()
