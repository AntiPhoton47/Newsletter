from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_editorial_packet as pep  # noqa: E402


class PrepareEditorialPacketTests(unittest.TestCase):
    def test_parse_sources_by_section(self) -> None:
        sample = """# Sources

## By Section

### Need To Know
- Nature
- Science

### AI
- OpenAI
- GitHub

## By Source Type
- ignored
"""
        parsed = pep.parse_sources_by_section(sample)
        self.assertEqual(parsed["Need To Know"], ["Nature", "Science"])
        self.assertEqual(parsed["AI"], ["OpenAI", "GitHub"])

    def test_benchmark_stats_counts_words_and_sources(self) -> None:
        sample = """# Frontier Threads

## March 15, 2026

## Need To Know

**Source:** Example

Body text here.

**Link:** [Read](https://example.com)
"""
        stats = pep.benchmark_stats(sample)
        self.assertEqual(stats["source_count"], 1)
        self.assertEqual(stats["link_count"], 1)
        self.assertGreater(stats["word_count"], 0)

    def test_build_notes_scaffold_includes_travel_image_field(self) -> None:
        scaffold = pep.build_notes_scaffold(
            pep.dt.date(2026, 3, 31),
            {
                "Travel": ["Lonely Planet"],
                "AI": ["OpenAI"],
            },
        )

        self.assertIn("## Travel", scaffold)
        self.assertIn("- Image URL:", scaffold)
        self.assertIn("- Image URL (optional):", scaffold)

    def test_detect_systemic_candidate_fetch_failure_flags_total_outage(self) -> None:
        payload = {
            "fetch": {
                "summary": {
                    "total_queries": 12,
                    "failed_queries": 12,
                    "sections_with_entries": 0,
                    "total_entries": 0,
                    "checked_sources": 0,
                    "newsletter_entries": 0,
                },
                "sections": {
                    "Need To Know": {
                        "queries": [
                            {
                                "status": "failed",
                                "error": "attempt 1 default: <urlopen error [Errno 8] nodename nor servname provided, or not known>",
                            }
                        ]
                    }
                },
            }
        }

        message = pep.detect_systemic_candidate_fetch_failure(payload)
        self.assertIsNotNone(message)
        self.assertIn("Candidate fetch failed for every configured query", message)
        self.assertIn("nodename nor servname provided", message)

    def test_detect_systemic_candidate_fetch_failure_ignores_thin_but_nonzero_run(self) -> None:
        payload = {
            "fetch": {
                "summary": {
                    "total_queries": 12,
                    "failed_queries": 9,
                    "sections_with_entries": 2,
                    "total_entries": 5,
                    "checked_sources": 3,
                    "newsletter_entries": 1,
                },
                "sections": {},
            }
        }

        self.assertIsNone(pep.detect_systemic_candidate_fetch_failure(payload))


if __name__ == "__main__":
    unittest.main()
