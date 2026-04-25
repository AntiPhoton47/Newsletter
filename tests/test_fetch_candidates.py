from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_candidates as fc  # noqa: E402


class FetchCandidatesTests(unittest.TestCase):
    def test_parse_pub_date_accepts_iso_timestamps(self) -> None:
        parsed = fc.parse_pub_date("2026-04-02T12:10:00Z")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.date(), dt.date(2026, 4, 2))

    def test_classify_newsletter_entry_defaults_nature_briefing_to_need_to_know(self) -> None:
        section = fc.classify_newsletter_entry(
            {
                "title": "Daily briefing: The countdown to NASA's Artemis II Moon mission launch",
                "summary": "The science that NASA's latest Moon mission will conduct.",
                "newsletter_source": "Nature Briefing",
            }
        )

        self.assertEqual(section, "Need To Know")

    def test_classify_newsletter_entry_routes_ai_items_to_ai(self) -> None:
        section = fc.classify_newsletter_entry(
            {
                "title": "OpenAI rolls out a new agent stack for developers",
                "summary": "The new model and agent workflow tighten inference costs and coding support.",
                "newsletter_source": "Superpower Daily",
            }
        )

        self.assertEqual(section, "AI")


if __name__ == "__main__":
    unittest.main()
